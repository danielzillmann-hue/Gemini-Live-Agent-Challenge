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

    # Fallback: separate Imagen call
    try:
        scene_bytes = await media_service.generate_scene_image(
            scene_description=narration[:200],
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
    return [
        {"id": sid, "campaign_name": s.world.campaign_name, "player_count": len(s.players), "is_active": s.is_active}
        for sid, s in game_engine.sessions.items()
    ]


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

    voice_configs = {
        "narrator": {"name": "en-US-Studio-Q", "gender": "MALE", "pitch": -2.0, "rate": 0.95},
        "npc_gruff": {"name": "en-US-Studio-J", "gender": "MALE", "pitch": -6.0, "rate": 0.85},
        "npc_noble": {"name": "en-GB-Studio-B", "gender": "MALE", "pitch": 0.0, "rate": 0.9},
        "npc_mysterious": {"name": "en-US-Studio-Q", "gender": "MALE", "pitch": -4.0, "rate": 0.8},
        "npc_cheerful": {"name": "en-US-Studio-O", "gender": "MALE", "pitch": 2.0, "rate": 1.05},
        "npc_female_warm": {"name": "en-US-Studio-O", "gender": "FEMALE", "pitch": 1.0, "rate": 0.95},
        "npc_female_stern": {"name": "en-GB-Studio-C", "gender": "FEMALE", "pitch": -2.0, "rate": 0.9},
        "npc_old": {"name": "en-US-Studio-J", "gender": "MALE", "pitch": -3.0, "rate": 0.8},
        "npc_young": {"name": "en-US-Studio-O", "gender": "MALE", "pitch": 3.0, "rate": 1.0},
        "npc_male": {"name": "en-US-Studio-O", "gender": "MALE", "pitch": 0.0, "rate": 0.95},
        "npc_female": {"name": "en-US-Studio-O", "gender": "FEMALE", "pitch": 0.0, "rate": 0.95},
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
    except Exception:
        logger.warning("TTS generation failed")
        return {"audio": "", "format": "none", "fallback": True}


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
                await manager.broadcast(session_id, {"type": "dice_result", "data": msg_data})
            elif msg_type == "camera_frame":
                await _handle_camera_frame(session_id, session, msg_data)
            elif msg_type == "start_game":
                await _handle_start_game(session_id, session)
            elif msg_type == "player_chat":
                await manager.broadcast(session_id, {"type": "player_chat", "data": msg_data})
            elif msg_type == "webrtc_signal":
                await manager.broadcast(session_id, {"type": "webrtc_signal", "data": msg_data})

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
                await manager.broadcast(session_id, {"type": "dice_result", "data": {
                    "character": data.get("character_name", "Player"),
                    "roll_type": die.get("type", "d20"), "value": die["value"],
                    "is_critical": die["value"] == 20, "is_fumble": die["value"] == 1,
                }})
    except (json.JSONDecodeError, KeyError):
        pass


async def _handle_start_game(session_id: str, session) -> None:
    if not session.players:
        await manager.broadcast(session_id, {"type": "error", "data": {"message": "No players. Create characters first."}})
        return

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

    # If interleaved produced no images, generate one separately as fallback
    has_image = any(m["type"] == "scene_image" for m in ws_messages)
    if not has_image:
        try:
            scene_bytes = await media_service.generate_scene_image(
                scene_description=f"Opening scene: {session.world.setting_description}",
                time_of_day=session.world.time_of_day, weather=session.world.weather,
            )
            if scene_bytes:
                url = await storage_service.upload_media(scene_bytes, "image", "image/png", session_id)
                ws_messages.insert(0, {"type": "scene_image", "data": {"url": url, "description": "Opening scene"}})
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
