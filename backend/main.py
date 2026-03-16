"""Genesis RPG — FastAPI backend with WebSocket game sessions and REST API."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from google.genai import types
from config import settings
from game.engine import game_engine, create_character
from game.models import (
    CharacterClass,
    CharacterRace,
    StoryEvent,
)
from agents.orchestrator import process_player_input
from handlers.actions import process_single_action, handle_batched_actions, set_callbacks as set_action_callbacks
from handlers.turns import action_window
from services import (
    firestore_service,
    gemini_service,
    media_service,
    storage_service,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Genesis RPG", version="1.0.0")

_origins = settings.CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials="*" not in _origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Connection Manager ─────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self) -> None:
        self.active: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.active.setdefault(session_id, []).append(ws)
            count = len(self.active[session_id])
        logger.info("Player connected to session %s (%d total)", session_id, count)
        await self.broadcast(session_id, {"type": "players_online", "data": {"count": count}})

    async def disconnect(self, session_id: str, ws: WebSocket) -> None:
        async with self._lock:
            if session_id in self.active:
                self.active[session_id] = [w for w in self.active[session_id] if w is not ws]
                if not self.active[session_id]:
                    del self.active[session_id]
                    return
                count = len(self.active[session_id])
        await self.broadcast(session_id, {"type": "players_online", "data": {"count": count}})

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        connections = list(self.active.get(session_id, []))
        failed: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                failed.append(ws)
        # Clean up dead connections
        if failed:
            async with self._lock:
                if session_id in self.active:
                    self.active[session_id] = [w for w in self.active[session_id] if w not in failed]

    async def send_personal(self, ws: WebSocket, message: dict[str, Any]) -> None:
        try:
            await ws.send_json(message)
        except Exception:
            logger.debug("Failed to send personal message")


manager = ConnectionManager()

# Track which sessions have camera active (for dice roll mode)
camera_active_sessions: set[str] = set()
# Pending dice rolls waiting for physical dice input
pending_dice_rolls: dict[str, dict[str, Any]] = {}  # session_id -> roll info


# ── Wire up callbacks (avoids circular imports) ────────────────────────────

async def _generate_scene_from_narration(session_id: str, session, narration: str) -> None:
    """Generate a scene image — tries native interleaved first, falls back to Imagen."""
    try:
        # Try native interleaved: ask Gemini to generate just the image for this scene
        parts = await gemini_service.generate_interleaved(
            prompt=f"Generate a single illustration for this fantasy RPG scene (no text, just the image):\n\n{narration[:300]}",
            system_instruction="Generate a detailed fantasy illustration matching the scene description. Dark fantasy art style, dramatic lighting.",
        )
        for part in parts:
            if part["type"] == "image":
                image_data = part["data"]
                if isinstance(image_data, str):
                    image_bytes = base64.b64decode(image_data)
                else:
                    image_bytes = image_data
                url = await storage_service.upload_media(
                    image_bytes, "image", part.get("mime_type", "image/png"), session_id
                )
                await manager.broadcast(session_id, {
                    "type": "scene_image", "session_id": session_id,
                    "data": {"url": url, "description": narration[:100]},
                })
                return  # Success — don't fall through
    except Exception:
        logger.debug("Interleaved scene generation failed, trying Imagen")

    # Fallback: separate Imagen call with cleaned-up prompt
    try:
        # Strip story tags and clean up for image generation
        clean = narration.replace("[NEW_SCENE]", "").replace("[CINEMATIC]", "").strip()
        scene_bytes = await media_service.generate_scene_image(
            scene_description=f"Fantasy RPG scene: {clean[:300]}",
            time_of_day=session.world.time_of_day,
            weather=session.world.weather,
        )
        if scene_bytes:
            url = await storage_service.upload_media(scene_bytes, "image", "image/png", session_id)
            await manager.broadcast(session_id, {
                "type": "scene_image", "session_id": session_id,
                "data": {"url": url, "description": narration[:100]},
            })
    except Exception:
        logger.warning("Scene generation from narration failed for session %s", session_id)


set_action_callbacks(manager.broadcast, _generate_scene_from_narration)

# Wire up dice state for tool handlers
from agents.tool_handlers import set_dice_state
set_dice_state(camera_active_sessions, pending_dice_rolls)

action_window.set_callbacks(
    manager.broadcast, handle_batched_actions,
    lambda sid: len(manager.active.get(sid, [])),
)


# ── REST API ───────────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    campaign_name: str = Field("New Campaign", min_length=1, max_length=200)
    setting: str = Field("A dark fantasy world of magic and danger", min_length=1, max_length=2000)


class CreateCharacterRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    race: CharacterRace = CharacterRace.HUMAN
    character_class: CharacterClass = CharacterClass.WARRIOR
    backstory: str = Field("", max_length=1000)
    personality: str = Field("", max_length=500)
    appearance: str = Field("", max_length=500)


@app.get("/")
async def root():
    return {"name": "Genesis RPG", "version": "1.0.0", "status": "running"}


@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest):
    session = game_engine.create_session(req.campaign_name, req.setting)
    return {"session_id": session.id, "campaign_name": req.campaign_name, "setting": req.setting}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    session = game_engine.get_session(session_id)
    # Auto-restore from Firestore if not in memory
    if not session:
        try:
            session = await firestore_service.load_session(session_id)
            if session:
                game_engine.sessions[session.id] = session
                logger.info("Restored session %s from Firestore", session_id)
        except Exception:
            pass
    if not session:
        raise HTTPException(404, "Session not found")
    return session.model_dump(mode="json")


@app.get("/api/sessions")
async def list_sessions():
    """List sessions from both memory and Firestore."""
    # Merge in-memory sessions with Firestore saved sessions
    sessions: dict[str, dict] = {}

    # In-memory sessions (currently active)
    for sid, s in game_engine.sessions.items():
        sessions[sid] = {
            "id": sid,
            "campaign_name": s.world.campaign_name,
            "player_count": len(s.players),
            "is_active": True,
        }

    # Firestore sessions (persisted)
    try:
        saved = await firestore_service.list_sessions()
        for s in saved:
            if s["id"] not in sessions:
                sessions[s["id"]] = {
                    "id": s["id"],
                    "campaign_name": s.get("campaign_name", "Saved Campaign"),
                    "player_count": s.get("player_count", 0),
                    "is_active": True,  # Saved sessions are resumable
                }
    except Exception:
        logger.debug("Failed to list Firestore sessions")

    return list(sessions.values())


@app.post("/api/settings/model")
async def set_model(data: dict[str, Any]):
    """Switch between Flash (fast) and Pro (quality) models at runtime."""
    model = data.get("model", "flash")
    if model == "pro":
        settings.GEMINI_MODEL = settings.GEMINI_PRO_MODEL
    else:
        settings.GEMINI_MODEL = settings.GEMINI_FLASH_MODEL
    # Rebuild the agent with the new model
    from agents.orchestrator import genesis_agent
    genesis_agent.model = settings.GEMINI_MODEL
    logger.info("Switched orchestrator model to %s", settings.GEMINI_MODEL)
    return {"model": settings.GEMINI_MODEL}


@app.get("/api/settings/model")
async def get_model():
    """Get the current model."""
    return {"model": settings.GEMINI_MODEL}


@app.post("/api/sessions/{session_id}/characters")
async def add_character(session_id: str, req: CreateCharacterRequest):
    session = game_engine.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    character = create_character(
        name=req.name, race=req.race, character_class=req.character_class,
        backstory=req.backstory, personality=req.personality, appearance=req.appearance,
    )

    try:
        portrait_bytes = await media_service.generate_character_portrait(
            name=req.name, race=req.race.value, character_class=req.character_class.value,
            appearance=req.appearance or f"A {req.race.value} {req.character_class.value}",
        )
        if portrait_bytes:
            url = await storage_service.upload_media(portrait_bytes, "image", "image/png", session_id)
            character.portrait_url = url
    except Exception:
        logger.warning("Portrait generation/upload failed for %s", req.name)

    game_engine.add_player(session_id, character)
    await manager.broadcast(session_id, {"type": "character_joined", "data": character.model_dump(mode="json")})
    return character.model_dump(mode="json")


@app.post("/api/sessions/{session_id}/save")
async def save_session(session_id: str):
    session = game_engine.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    await firestore_service.save_session(session)
    return {"status": "saved"}


@app.post("/api/sessions/{session_id}/load")
async def load_session(session_id: str):
    session = await firestore_service.load_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found in Firestore")
    game_engine.sessions[session.id] = session
    return session.model_dump(mode="json")


@app.get("/api/campaigns")
async def list_campaigns():
    campaigns = await firestore_service.list_campaigns()
    return [c.model_dump(mode="json") for c in campaigns]


# ── Character Roster (persistent across campaigns) ────────────────────────

@app.post("/api/characters/save")
async def save_character_to_roster(data: dict[str, Any]):
    """Save a character to the persistent roster for reuse across campaigns."""
    await firestore_service.save_character(data, owner_id=data.get("owner_id", "default"))
    return {"status": "saved", "character_id": data.get("id")}


@app.get("/api/characters")
async def list_saved_characters(owner_id: str = "default"):
    """List all saved characters in the roster."""
    return await firestore_service.list_characters(owner_id)


@app.get("/api/characters/{character_id}")
async def get_saved_character(character_id: str):
    """Load a specific saved character."""
    char = await firestore_service.load_character(character_id)
    if not char:
        raise HTTPException(404, "Character not found")
    return char


@app.post("/api/sessions/{session_id}/characters/import/{character_id}")
async def import_character_to_session(session_id: str, character_id: str):
    """Import a saved character into a game session."""
    session = game_engine.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    char_data = await firestore_service.load_character(character_id)
    if not char_data:
        raise HTTPException(404, "Character not found")

    from game.models import Character
    character = Character.model_validate(char_data)
    # Heal to full for new campaign
    character.hp = character.max_hp
    character.conditions = []
    character.is_dead = False

    game_engine.add_player(session_id, character)
    await manager.broadcast(session_id, {"type": "character_joined", "data": character.model_dump(mode="json")})
    return character.model_dump(mode="json")


@app.post("/api/sessions/{session_id}/characters/save-all")
async def save_all_characters_from_session(session_id: str):
    """Save all characters from a session to the persistent roster (after campaign ends)."""
    session = game_engine.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    saved = []
    for char in session.players:
        char_data = char.model_dump(mode="json")
        await firestore_service.save_character(char_data)
        saved.append({"id": char.id, "name": char.name, "level": char.level})

    return {"status": "saved", "characters": saved}


@app.delete("/api/characters/{character_id}")
async def delete_saved_character(character_id: str):
    """Delete a character from the roster."""
    await firestore_service.delete_character(character_id)
    return {"status": "deleted"}


@app.get("/api/sessions/{session_id}/recap")
async def get_session_recap(session_id: str):
    """Generate a 'Previously on...' recap with interleaved text + image."""
    session = game_engine.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    recap_text = game_engine.generate_session_recap(session)

    # Use native interleaved output for dramatic recap with illustration
    try:
        parts = await gemini_service.generate_interleaved(
            prompt=(
                f"Create a dramatic 'Previously on...' recap in 3-4 sentences, "
                f"with an illustration of the most dramatic moment:\n\n{recap_text}"
            ),
            system_instruction=(
                "You are a dramatic narrator creating a 'Previously on...' recap. "
                "Write vivid prose in present tense. Generate one illustration showing "
                "the most memorable moment from the recap."
            ),
        )

        recap_narration = ""
        recap_image = ""
        for part in parts:
            if part["type"] == "text":
                recap_narration += part["content"]
            elif part["type"] == "image":
                try:
                    image_data = part["data"]
                    if isinstance(image_data, str):
                        image_bytes = base64.b64decode(image_data)
                    else:
                        image_bytes = image_data
                    recap_image = await storage_service.upload_media(
                        image_bytes, "image", part.get("mime_type", "image/png"), session_id
                    )
                except Exception:
                    pass

        return {
            "recap": recap_narration or recap_text,
            "raw": recap_text,
            "image_url": recap_image,
            "interleaved": True,
        }
    except Exception:
        # Fallback to text-only recap
        try:
            dramatic_recap = await gemini_service.generate_text(
                prompt=f"Rewrite this as a dramatic 'Previously on...' narration in 3-4 sentences:\n\n{recap_text}",
                system_instruction="You are a dramatic narrator. Write in present tense, vivid prose.",
                temperature=0.8, max_tokens=300,
            )
        except Exception:
            dramatic_recap = recap_text

        return {"recap": dramatic_recap, "raw": recap_text, "image_url": "", "interleaved": False}


class TTSRequest(BaseModel):
    text: str
    voice_type: str = "narrator"


@app.post("/api/tts")
async def text_to_speech(req: TTSRequest):
    from google.cloud import texttospeech

    # Use Neural2/Journey voices (widely available) with Studio as fallback
    voice_configs = {
        "narrator": {"name": "en-US-Neural2-D", "gender": "MALE", "pitch": -2.0, "rate": 0.95},
        "npc_gruff": {"name": "en-US-Neural2-J", "gender": "MALE", "pitch": -6.0, "rate": 0.85},
        "npc_noble": {"name": "en-US-Neural2-J", "gender": "MALE", "pitch": 2.0, "rate": 0.9},
        "npc_mysterious": {"name": "en-US-Neural2-D", "gender": "MALE", "pitch": -4.0, "rate": 0.8},
        "npc_cheerful": {"name": "en-US-Neural2-A", "gender": "MALE", "pitch": 2.0, "rate": 1.05},
        "npc_female_warm": {"name": "en-US-Neural2-F", "gender": "FEMALE", "pitch": 1.0, "rate": 0.95},
        "npc_female_stern": {"name": "en-US-Neural2-F", "gender": "FEMALE", "pitch": -2.0, "rate": 0.9},
        "npc_old": {"name": "en-US-Neural2-J", "gender": "MALE", "pitch": -3.0, "rate": 0.8},
        "npc_young": {"name": "en-US-Neural2-A", "gender": "MALE", "pitch": 3.0, "rate": 1.0},
        "npc_male": {"name": "en-US-Neural2-D", "gender": "MALE", "pitch": 0.0, "rate": 0.95},
        "npc_female": {"name": "en-US-Neural2-F", "gender": "FEMALE", "pitch": 0.0, "rate": 0.95},
    }

    config = voice_configs.get(req.voice_type, voice_configs["narrator"])
    pitch = config.get("pitch", 0.0)
    rate = config.get("rate", 0.95)
    gender_str = config.get("gender", "MALE")
    gender = texttospeech.SsmlVoiceGender.FEMALE if gender_str == "FEMALE" else texttospeech.SsmlVoiceGender.MALE

    ssml = f'<speak><prosody rate="{int(rate * 100)}%" pitch="{pitch:+.0f}st">{req.text}</prosody></speak>'

    try:
        client = texttospeech.TextToSpeechClient()
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(ssml=ssml),
            voice=texttospeech.VoiceSelectionParams(language_code="en-US", name=config["name"], ssml_gender=gender),
            audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3),
        )
        return {"audio": base64.b64encode(response.audio_content).decode(), "format": "mp3"}
    except Exception as e:
        logger.exception("TTS generation failed: %s", e)
        return {"audio": "", "format": "none", "fallback": True}


# ── Gemini Live API — Real-Time Voice Conversation ────────────────────────

@app.websocket("/ws/{session_id}/live/{npc_id}")
async def websocket_live_voice(ws: WebSocket, session_id: str, npc_id: str):
    """Real-time voice conversation with an NPC using Gemini Live API.

    Client sends raw PCM audio chunks (16-bit, 16kHz, little-endian) as base64.
    Server responds with audio chunks from the NPC's voice.
    """
    session = game_engine.get_session(session_id)
    if not session:
        await ws.close(code=4004, reason="Session not found")
        return

    # Find the NPC
    npc = session.world.npcs.get(npc_id)
    npc_name = npc.name if npc else "Narrator"
    npc_personality = npc.personality if npc else ""
    npc_voice = npc.voice_style if npc else "neutral"

    # Build game context for the NPC
    context = game_engine.get_context_summary(session)
    context_str = json.dumps(context, indent=2, default=str)[:2000]

    await ws.accept()
    logger.info("Live voice session started with %s in session %s", npc_name, session_id)

    try:
        from services.live_api_service import create_live_session

        async with await create_live_session(
            npc_name=npc_name,
            npc_personality=npc_personality,
            npc_voice_style=npc_voice,
            game_context=context_str,
        ) as live_session:
            await ws.send_json({"type": "live_ready", "data": {"npc": npc_name}})

            conversation_active = True
            npc_transcript_buffer = []  # Buffer NPC words into sentences
            player_transcript_buffer = []  # Buffer player words

            async def receive_from_gemini():
                """Receive audio/text responses from Gemini and forward to client."""
                try:
                    async for response in live_session.receive():
                        if not conversation_active:
                            break
                        sc = response.server_content

                        # Forward audio chunks to client for playback
                        if sc and sc.model_turn:
                            for part in sc.model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    audio_b64 = base64.b64encode(part.inline_data.data).decode()
                                    await ws.send_json({
                                        "type": "audio_response",
                                        "data": {"audio": audio_b64, "npc": npc_name},
                                    })

                        # Buffer NPC transcription into complete messages
                        if sc and sc.output_transcription and sc.output_transcription.text:
                            npc_transcript_buffer.append(sc.output_transcription.text)

                        # Buffer player transcription (input)
                        if sc and sc.input_transcription and sc.input_transcription.text:
                            player_transcript_buffer.append(sc.input_transcription.text)

                        # On turn complete, flush buffered transcription as one message
                        if sc and sc.turn_complete:
                            # Send player's speech as one message
                            if player_transcript_buffer:
                                player_text = "".join(player_transcript_buffer).strip()
                                if player_text:
                                    await ws.send_json({
                                        "type": "live_transcription",
                                        "data": {"text": player_text, "speaker": "You"},
                                    })
                                player_transcript_buffer.clear()

                            # Send NPC's speech as one message
                            if npc_transcript_buffer:
                                npc_text = "".join(npc_transcript_buffer).strip()
                                if npc_text:
                                    await ws.send_json({
                                        "type": "live_transcription",
                                        "data": {"text": npc_text, "speaker": npc_name},
                                    })
                                npc_transcript_buffer.clear()

                            await ws.send_json({"type": "turn_complete", "data": {}})
                except Exception as e:
                    # Flush remaining buffers
                    if npc_transcript_buffer:
                        npc_text = "".join(npc_transcript_buffer).strip()
                        if npc_text:
                            try:
                                await ws.send_json({
                                    "type": "live_transcription",
                                    "data": {"text": npc_text, "speaker": npc_name},
                                })
                            except Exception:
                                pass
                    logger.debug("Gemini receive ended: %s", e)

            async def receive_from_client():
                """Receive audio from client and forward to Gemini."""
                nonlocal conversation_active
                try:
                    while conversation_active:
                        raw = await ws.receive_text()
                        msg = json.loads(raw)
                        if msg.get("type") == "audio_chunk":
                            audio_b64 = msg["data"].get("audio", "")
                            if audio_b64:
                                await live_session.send_realtime_input(
                                    audio=types.Blob(
                                        data=base64.b64decode(audio_b64),
                                        mime_type="audio/pcm;rate=16000",
                                    )
                                )
                        elif msg.get("type") == "end_conversation":
                            conversation_active = False
                            break
                except Exception as e:
                    logger.debug("Client receive ended: %s", e)
                    conversation_active = False

            # Run both directions concurrently
            async with asyncio.TaskGroup() as tg:
                tg.create_task(receive_from_gemini())
                tg.create_task(receive_from_client())

    except ImportError:
        await ws.send_json({"type": "error", "data": {"message": "Live API not available"}})
    except Exception as e:
        logger.exception("Live voice session error: %s", e)
        try:
            await ws.send_json({"type": "error", "data": {"message": f"Live session failed: {str(e)}"}})
        except Exception:
            pass
    finally:
        logger.info("Live voice session ended with %s", npc_name)


# ── WebSocket Game Loop ───────────────────────────────────────────────────

@app.websocket("/ws/{session_id}")
async def websocket_game(ws: WebSocket, session_id: str):
    session = game_engine.get_session(session_id)

    # Auto-restore from Firestore if session not in memory (e.g., after Cloud Run cold start)
    if not session:
        try:
            session = await firestore_service.load_session(session_id)
            if session:
                game_engine.sessions[session.id] = session
                logger.info("Restored session %s from Firestore", session_id)
        except Exception:
            logger.warning("Failed to restore session %s from Firestore", session_id)

    if not session:
        await ws.close(code=4004, reason="Session not found")
        return

    await manager.connect(session_id, ws)
    await manager.send_personal(ws, {"type": "game_state_sync", "data": session.model_dump(mode="json")})

    # For restored sessions, send recap on connect (no start_game needed)
    if session.story_events and session_id not in _started_sessions:
        _started_sessions.add(session_id)
        recent = [e for e in session.story_events[-10:] if e.event_type == "narration" and e.content]
        if recent:
            await manager.send_personal(ws, {
                "type": "system_notice",
                "data": {"message": f"Welcome back to {session.world.campaign_name}. Here's where you left off..."},
            })
            for event in recent[-3:]:
                await manager.send_personal(ws, {
                    "type": "system_notice",
                    "data": {"message": event.content},
                })
        # Restore scene image and world map
        for loc in session.world.locations.values():
            if loc.id == session.world.current_location_id and loc.image_url:
                await manager.send_personal(ws, {
                    "type": "scene_image",
                    "data": {"url": loc.image_url, "description": loc.name},
                })
                break
        if session.world.world_map_url:
            await manager.send_personal(ws, {
                "type": "world_map_update",
                "data": {"url": session.world.world_map_url},
            })

    try:
        while True:
            raw = await ws.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send_personal(ws, {"type": "error", "data": {"message": "Invalid JSON"}})
                continue

            msg_type = message.get("type", "")
            msg_data = message.get("data", {})

            if msg_type == "player_action":
                await _handle_player_action(session_id, session, msg_data)
            elif msg_type == "voice_input":
                transcript = msg_data.get("transcript", "")
                if transcript:
                    await _handle_player_action(session_id, session, {"text": transcript, "character_name": msg_data.get("character_name", "Player")})
            elif msg_type == "dice_roll":
                # Physical dice result — resolve pending roll if one exists
                await _handle_physical_dice(session_id, session, msg_data)
            elif msg_type == "camera_frame":
                await _handle_camera_frame(session_id, session, msg_data)
            elif msg_type == "camera_toggle":
                if msg_data.get("active"):
                    camera_active_sessions.add(session_id)
                else:
                    camera_active_sessions.discard(session_id)
            elif msg_type == "start_game":
                await _handle_start_game(session_id, session)
            elif msg_type == "player_chat":
                await manager.broadcast(session_id, {"type": "player_chat", "data": msg_data})
            elif msg_type == "webrtc_signal":
                await manager.broadcast(session_id, {"type": "webrtc_signal", "data": msg_data})
            elif msg_type == "ping":
                await manager.send_personal(ws, {"type": "pong", "data": {}})

    except WebSocketDisconnect:
        await manager.disconnect(session_id, ws)
        logger.info("Player disconnected from session %s", session_id)


# ── Message Handlers ──────────────────────────────────────────────────────

async def _handle_player_action(session_id: str, session, data: dict[str, Any]) -> None:
    player_input = data.get("text", "")
    if not player_input:
        return

    character_name = data.get("character_name", "Player")

    # Single player: immediate (check connected clients, not character count)
    connected_count = len(manager.active.get(session_id, []))
    if connected_count <= 1:
        session.add_event(StoryEvent(event_type="player_action", content=player_input, speaker=character_name))
        await process_single_action(session_id, session, character_name, player_input)
        return

    # Multiplayer: route through ActionWindow
    is_combat = action_window.is_combat(session)

    error = await action_window.submit_action(session_id, session, character_name, player_input)
    if error:
        await manager.broadcast(session_id, {"type": "error", "data": {"message": error}})
        return

    # Combat: process immediately
    if is_combat:
        session.add_event(StoryEvent(event_type="player_action", content=player_input, speaker=character_name))
        await process_single_action(session_id, session, character_name, player_input)
        action_window.finish_combat_action(session_id)


async def _handle_physical_dice(session_id: str, session, data: dict[str, Any]) -> None:
    """Handle a physical dice roll result — resolve any pending roll check."""
    value = data.get("value")
    if value is None:
        return

    # Broadcast the dice result visually
    await manager.broadcast(session_id, {"type": "dice_result", "data": data})

    # Check if there's a pending roll waiting for physical dice
    if session_id in pending_dice_rolls:
        pending = pending_dice_rolls.pop(session_id)
        dc = pending.get("dc", 10)
        char_name = pending.get("character", "Player")
        ability = pending.get("ability", "check")

        # Find character's ability modifier
        modifier = 0
        if session:
            for p in session.players:
                if p.name.lower() == char_name.lower():
                    modifier = p.ability_scores.modifier(ability) if hasattr(p.ability_scores, 'modifier') else 0
                    break

        total = value + modifier
        success = total >= dc
        is_crit = value == 20
        is_fumble = value == 1

        # Narrate the result
        if is_crit:
            narration = f"A natural 20! {char_name} succeeds spectacularly!"
        elif is_fumble:
            narration = f"A natural 1... {char_name} fails catastrophically."
        elif success:
            narration = f"{char_name} rolls a {value} + {modifier} = {total} against DC {dc}. Success!"
        else:
            narration = f"{char_name} rolls a {value} + {modifier} = {total} against DC {dc}. Failed."

        await manager.broadcast(session_id, {
            "type": "narration",
            "data": {"content": narration},
        })

        # Now continue the AI narration with the result
        context = game_engine.get_context_summary(session)
        follow_up = (
            f"The {ability} check result: {char_name} rolled {value} (total {total}) "
            f"against DC {dc}. {'Success' if success else 'Failure'}. "
            f"{'Critical success!' if is_crit else 'Critical failure!' if is_fumble else ''} "
            f"Narrate what happens as a result."
        )
        await process_single_action(session_id, session, "narrator", follow_up)


async def _handle_camera_frame(session_id: str, session, data: dict[str, Any]) -> None:
    frame_b64 = data.get("frame", "")
    if not frame_b64:
        return
    frame_bytes = base64.b64decode(frame_b64)
    try:
        result = await gemini_service.analyze_image(
            frame_bytes,
            prompt='Look at this image. Are there any dice visible? If so, report the value. Return JSON: {"dice_found": true/false, "values": [{"type": "d20", "value": 17}]}',
        )
        parsed = json.loads(result)
        if parsed.get("dice_found"):
            for die in parsed.get("values", []):
                # Feed the detected dice value through the physical dice handler
                await _handle_physical_dice(session_id, session, {
                    "character": data.get("character_name", "Player"),
                    "roll_type": die.get("type", "d20"),
                    "value": die["value"],
                    "is_critical": die["value"] == 20,
                    "is_fumble": die["value"] == 1,
                })
    except (json.JSONDecodeError, KeyError):
        pass


# Track which sessions have already started (prevents duplicate openings)
_started_sessions: set[str] = set()


async def _handle_start_game(session_id: str, session) -> None:
    if not session.players:
        await manager.broadcast(session_id, {"type": "error", "data": {"message": "No players. Create characters first."}})
        return

    # Prevent duplicate openings — only run once per session
    if session_id in _started_sessions:
        # Late joiner to an active session
        await manager.broadcast(session_id, {
            "type": "system_notice",
            "data": {"message": f"A new adventurer joins the party! Welcome to {session.world.campaign_name}."},
        })
        await manager.broadcast(session_id, {
            "type": "game_state_sync",
            "data": session.model_dump(mode="json"),
        })
        return

    # Restored session — already handled on WebSocket connect
    if len(session.story_events) > 0:
        _started_sessions.add(session_id)
        return

    _started_sessions.add(session_id)

    await manager.broadcast(session_id, {"type": "thinking", "data": {}})

    player_descriptions = ", ".join(f"{p.name} the {p.race.value} {p.character_class.value}" for p in session.players)

    # ── Native Interleaved Output ─────────────────────────────────────────
    # Use Gemini's native multimodal capabilities to generate text + images
    # in a single response stream — true interleaved storytelling output.

    interleaved_prompt = (
        f"Create a dramatic opening scene for a tabletop RPG campaign.\n\n"
        f"Campaign: {session.world.campaign_name}\n"
        f"Setting: {session.world.setting_description}\n"
        f"Party: {player_descriptions}\n\n"
        f"Write 3-4 paragraphs of vivid narration that sets the scene, introduces the "
        f"starting location, and presents an immediate hook. Generate an illustration "
        f"for the opening scene. Make it cinematic and immersive."
    )

    interleaved_parts = await gemini_service.generate_interleaved(
        prompt=interleaved_prompt,
        context=game_engine.get_context_summary(session),
        temperature=0.9,
    )

    # Process interleaved parts — text becomes narration, images become scene images
    ws_messages: list[dict[str, Any]] = []
    for part in interleaved_parts:
        if part["type"] == "text":
            content = part["content"]
            ws_messages.append({"type": "narration", "data": {"content": content}})
            session.add_event(StoryEvent(
                event_type="narration", content=content, speaker="narrator",
                drama_level=game_engine.calculate_drama_level(session),
            ))
        elif part["type"] == "image":
            try:
                image_data = part["data"]
                # Handle both bytes and base64-encoded strings
                if isinstance(image_data, str):
                    image_bytes = base64.b64decode(image_data)
                else:
                    image_bytes = image_data
                mime = part.get("mime_type", "image/png")
                ext = "png" if "png" in mime else "jpg"
                url = await storage_service.upload_media(
                    image_bytes, "image", mime, session_id
                )
                ws_messages.append({"type": "scene_image", "data": {"url": url, "description": "Opening scene"}})
            except Exception:
                logger.warning("Failed to upload interleaved image")

    # If interleaved produced no images, generate one from the actual narration text
    has_image = any(m["type"] == "scene_image" for m in ws_messages)
    if not has_image:
        # Extract narration text to use as image prompt (much better than generic setting)
        narration_texts = [m["data"]["content"] for m in ws_messages if m["type"] == "narration"]
        scene_prompt = " ".join(narration_texts)[:400] if narration_texts else session.world.setting_description
        try:
            scene_bytes = await media_service.generate_scene_image(
                scene_description=f"Fantasy RPG scene illustration: {scene_prompt}",
                time_of_day=session.world.time_of_day, weather=session.world.weather,
            )
            if scene_bytes:
                url = await storage_service.upload_media(scene_bytes, "image", "image/png", session_id)
                ws_messages.insert(0, {"type": "scene_image", "data": {"url": url, "description": scene_prompt[:100]}})
        except Exception:
            logger.warning("Fallback opening scene image also failed")

    # If interleaved produced no text, fall back to ADK agent pipeline
    has_text = any(m["type"] == "narration" for m in ws_messages)
    if not has_text:
        context = game_engine.get_context_summary(session)
        opening_prompt = (
            f"Begin the adventure! Party: {player_descriptions}. "
            f"Setting: {session.world.setting_description}. "
            f"Create a dramatic opening scene."
        )
        tool_events = await process_player_input(session_id, opening_prompt, context)
        from agents.orchestrator import process_tool_results
        fallback_messages = await process_tool_results(session_id, tool_events, session)
        ws_messages.extend(fallback_messages)

    # Generate world map in background
    asyncio.create_task(_generate_world_map(session))

    for msg in ws_messages:
        msg["session_id"] = session_id
        await manager.broadcast(session_id, msg)


async def _generate_world_map(session) -> None:
    try:
        map_bytes = await media_service.generate_world_map(
            setting_description=session.world.setting_description,
            locations=[loc.name for loc in session.world.locations.values()] or None,
        )
        if map_bytes:
            url = await storage_service.upload_media(map_bytes, "map", "image/png", session.id)
            session.world.world_map_url = url
            await manager.broadcast(session.id, {"type": "world_map_update", "data": {"url": url}})
    except Exception:
        logger.exception("Failed to generate world map for session %s", session.id)


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
