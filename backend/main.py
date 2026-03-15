"""Genesis RPG — FastAPI backend with WebSocket game sessions and REST API."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from game.engine import game_engine, create_character, CombatEngine
from game.models import (
    CharacterClass,
    CharacterRace,
    GameSession,
    Location,
    NPC,
    Quest,
    StoryEvent,
)
from agents.orchestrator import (
    process_player_input,
    process_tool_results,
)
from services import (
    firestore_service,
    gemini_service,
    media_service,
    storage_service,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Genesis RPG",
    description="AI-powered cinematic tabletop RPG game master",
    version="1.0.0",
)

_origins = settings.CORS_ORIGINS
_allow_creds = "*" not in _origins  # credentials not allowed with wildcard
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_allow_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Connection Manager ─────────────────────────────────────────────────────

class ConnectionManager:
    """Manages WebSocket connections per session."""

    def __init__(self) -> None:
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self.active.setdefault(session_id, []).append(ws)
        count = len(self.active[session_id])
        logger.info("Player connected to session %s (%d total)", session_id, count)
        # Notify all clients of player count change
        await self.broadcast(session_id, {
            "type": "players_online",
            "data": {"count": count},
        })

    async def disconnect(self, session_id: str, ws: WebSocket) -> None:
        if session_id in self.active:
            self.active[session_id] = [w for w in self.active[session_id] if w is not ws]
            if not self.active[session_id]:
                del self.active[session_id]
            else:
                await self.broadcast(session_id, {
                    "type": "players_online",
                    "data": {"count": len(self.active[session_id])},
                })

    def get_player_count(self, session_id: str) -> int:
        return len(self.active.get(session_id, []))

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        for ws in self.active.get(session_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                logger.warning("Failed to send to WebSocket in session %s", session_id)

    async def send_personal(self, ws: WebSocket, message: dict[str, Any]) -> None:
        await ws.send_json(message)


manager = ConnectionManager()


ACTION_WINDOW_SECONDS = 12  # How long players have to submit actions


class ActionWindow:
    """Collects player actions during a time window, then batches them to the AI.

    Exploration: All players submit actions during the window. When it closes,
    all actions are sent as one prompt and the AI narrates the combined result.

    Combat: Strict initiative order. Only the active combatant can act.
    No window needed — their action processes immediately.
    """

    def __init__(self) -> None:
        # session_id -> list of (character_name, action_text)
        self.pending_actions: dict[str, list[tuple[str, str]]] = {}
        # session_id -> asyncio.Task for the window timer
        self.window_timers: dict[str, asyncio.Task] = {}
        # session_id -> whether AI is currently processing
        self.is_processing: dict[str, bool] = {}
        # session_id -> which players have submitted this window
        self.submitted: dict[str, set[str]] = {}

    def is_combat(self, session: GameSession) -> bool:
        return session.combat.is_active

    def get_combat_turn(self, session: GameSession) -> str:
        """Get current combatant name in combat."""
        current = session.combat.current_combatant
        if current and current.is_player:
            return current.name
        return ""

    def is_busy(self, session_id: str) -> bool:
        return self.is_processing.get(session_id, False)

    async def submit_action(
        self, session_id: str, session: GameSession,
        character_name: str, action_text: str,
    ) -> str | None:
        """Submit a player action. Returns error message or None on success."""
        if self.is_busy(session_id):
            return "The Game Master is still narrating. Please wait."

        # ── Combat: immediate, strict initiative ──
        if self.is_combat(session):
            current = self.get_combat_turn(session)
            if not current:
                return "It's the enemy's turn. Please wait."
            if current.lower() != character_name.lower():
                return f"It's {current}'s turn in combat."
            # Process immediately
            self.is_processing[session_id] = True
            return None

        # ── Exploration: action window ──
        # Check if player already submitted this window
        if session_id in self.submitted and character_name.lower() in self.submitted[session_id]:
            return "You've already submitted your action. Waiting for other players..."

        # Add to pending
        self.pending_actions.setdefault(session_id, []).append(
            (character_name, action_text)
        )
        self.submitted.setdefault(session_id, set()).add(character_name.lower())

        # Broadcast that this player has declared
        alive_players = [p for p in session.players if p.hp > 0]
        submitted_count = len(self.submitted.get(session_id, set()))
        total_players = len(alive_players)

        await manager.broadcast(session_id, {
            "type": "action_window",
            "data": {
                "status": "collecting",
                "submitted_by": character_name,
                "submitted_count": submitted_count,
                "total_players": total_players,
                "seconds_remaining": ACTION_WINDOW_SECONDS,
            },
        })

        # Start window timer on first action (if not already running)
        if session_id not in self.window_timers or self.window_timers[session_id].done():
            self.window_timers[session_id] = asyncio.create_task(
                self._window_countdown(session_id, session)
            )

        # If all alive players have submitted, close window early
        if submitted_count >= total_players:
            if session_id in self.window_timers and not self.window_timers[session_id].done():
                self.window_timers[session_id].cancel()
            asyncio.create_task(self._close_window(session_id, session))

        return None  # Accepted

    async def _window_countdown(self, session_id: str, session: GameSession) -> None:
        """Count down the action window and broadcast remaining time."""
        for remaining in range(ACTION_WINDOW_SECONDS, 0, -1):
            await asyncio.sleep(1)
            # Broadcast countdown every 3 seconds
            if remaining % 3 == 0 or remaining <= 3:
                await manager.broadcast(session_id, {
                    "type": "action_window",
                    "data": {
                        "status": "countdown",
                        "seconds_remaining": remaining,
                        "submitted_count": len(self.submitted.get(session_id, set())),
                        "total_players": len([p for p in session.players if p.hp > 0]),
                    },
                })
        # Window closed — process all actions
        await self._close_window(session_id, session)

    async def _close_window(self, session_id: str, session: GameSession) -> None:
        """Close the action window and process all collected actions."""
        actions = self.pending_actions.pop(session_id, [])
        self.submitted.pop(session_id, None)
        if session_id in self.window_timers:
            del self.window_timers[session_id]

        if not actions:
            return

        self.is_processing[session_id] = True

        await manager.broadcast(session_id, {
            "type": "action_window",
            "data": {"status": "closed"},
        })

        # Build combined prompt
        if len(actions) == 1:
            char_name, text = actions[0]
            combined = text
            speaker = char_name
        else:
            parts = [f"{name}: {text}" for name, text in actions]
            combined = "Multiple players act simultaneously:\n" + "\n".join(parts)
            speaker = "Party"

        # Process through the AI pipeline
        await _handle_batched_actions(session_id, session, combined, speaker)

        self.is_processing[session_id] = False

        # Broadcast that a new action window is open
        await manager.broadcast(session_id, {
            "type": "action_window",
            "data": {
                "status": "open",
                "seconds_remaining": ACTION_WINDOW_SECONDS,
                "submitted_count": 0,
                "total_players": len([p for p in session.players if p.hp > 0]),
            },
        })

    def finish_combat_action(self, session_id: str) -> None:
        """Mark combat action processing as done."""
        self.is_processing[session_id] = False


action_window = ActionWindow()


# ── REST API ───────────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    campaign_name: str = "New Campaign"
    setting: str = "A dark fantasy world of magic and danger"


class CreateCharacterRequest(BaseModel):
    session_id: str
    name: str
    race: CharacterRace = CharacterRace.HUMAN
    character_class: CharacterClass = CharacterClass.WARRIOR
    backstory: str = ""
    personality: str = ""
    appearance: str = ""


@app.get("/")
async def root():
    return {"name": "Genesis RPG", "version": "1.0.0", "status": "running"}


@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest):
    """Create a new game session."""
    session = game_engine.create_session(req.campaign_name, req.setting)

    # World map is generated when game starts (after locations exist)

    return {
        "session_id": session.id,
        "campaign_name": req.campaign_name,
        "setting": req.setting,
    }


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get current session state."""
    session = game_engine.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session.model_dump(mode="json")


@app.get("/api/sessions")
async def list_sessions():
    """List all active sessions."""
    return [
        {
            "id": sid,
            "campaign_name": s.world.campaign_name,
            "player_count": len(s.players),
            "is_active": s.is_active,
        }
        for sid, s in game_engine.sessions.items()
    ]


@app.post("/api/sessions/{session_id}/characters")
async def add_character(session_id: str, req: CreateCharacterRequest):
    """Create and add a character to a session."""
    session = game_engine.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    character = create_character(
        name=req.name,
        race=req.race,
        character_class=req.character_class,
        backstory=req.backstory,
        personality=req.personality,
        appearance=req.appearance,
    )

    # Generate portrait (non-blocking — don't fail character creation if this fails)
    try:
        portrait_bytes = await media_service.generate_character_portrait(
            name=req.name,
            race=req.race.value,
            character_class=req.character_class.value,
            appearance=req.appearance or f"A {req.race.value} {req.character_class.value}",
        )
        if portrait_bytes:
            url = await storage_service.upload_media(
                portrait_bytes, "image", "image/png", session_id
            )
            character.portrait_url = url
    except Exception:
        logger.warning("Portrait generation/upload failed for %s, continuing without", req.name)

    game_engine.add_player(session_id, character)

    # Broadcast to all connected clients
    await manager.broadcast(session_id, {
        "type": "character_joined",
        "data": character.model_dump(mode="json"),
    })

    return character.model_dump(mode="json")


@app.post("/api/sessions/{session_id}/save")
async def save_session(session_id: str):
    """Save session to Firestore."""
    session = game_engine.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    await firestore_service.save_session(session)
    return {"status": "saved"}


@app.post("/api/sessions/{session_id}/load")
async def load_session(session_id: str):
    """Load session from Firestore."""
    session = await firestore_service.load_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found in Firestore")
    game_engine.sessions[session.id] = session
    return session.model_dump(mode="json")


@app.get("/api/campaigns")
async def list_campaigns():
    """List all saved campaigns."""
    campaigns = await firestore_service.list_campaigns()
    return [c.model_dump(mode="json") for c in campaigns]


class TTSRequest(BaseModel):
    text: str
    voice_type: str = "narrator"  # narrator, npc_male, npc_female


@app.post("/api/tts")
async def text_to_speech(req: TTSRequest):
    """Convert text to natural speech using Google Cloud TTS."""
    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()

    # Voice profiles for different speaker types
    voice_configs = {
        "narrator": {
            "name": "en-US-Studio-Q",  # Deep, authoritative male
            "ssml_gender": texttospeech.SsmlVoiceGender.MALE,
        },
        "npc_male": {
            "name": "en-US-Studio-O",  # Warm male
            "ssml_gender": texttospeech.SsmlVoiceGender.MALE,
        },
        "npc_female": {
            "name": "en-US-Studio-O",  # Will use female variant
            "ssml_gender": texttospeech.SsmlVoiceGender.FEMALE,
        },
    }

    config = voice_configs.get(req.voice_type, voice_configs["narrator"])

    # Use SSML for better prosody
    ssml = f'<speak><prosody rate="95%" pitch="-2st">{req.text}</prosody></speak>'
    if req.voice_type != "narrator":
        ssml = f"<speak>{req.text}</speak>"

    synthesis_input = texttospeech.SynthesisInput(ssml=ssml)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name=config["name"],
        ssml_gender=config["ssml_gender"],
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=0.95,
        pitch=-1.0 if req.voice_type == "narrator" else 0.0,
    )

    try:
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        audio_b64 = base64.b64encode(response.audio_content).decode()
        return {"audio": audio_b64, "format": "mp3"}
    except Exception:
        logger.warning("TTS generation failed, falling back to browser TTS")
        return {"audio": "", "format": "none", "fallback": True}


# ── WebSocket Game Loop ───────────────────────────────────────────────────

@app.websocket("/ws/{session_id}")
async def websocket_game(ws: WebSocket, session_id: str):
    """Main WebSocket endpoint for real-time game interaction."""
    session = game_engine.get_session(session_id)
    if not session:
        await ws.close(code=4004, reason="Session not found")
        return

    await manager.connect(session_id, ws)

    # Send initial state sync
    await manager.send_personal(ws, {
        "type": "game_state_sync",
        "data": session.model_dump(mode="json"),
    })

    try:
        while True:
            raw = await ws.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send_personal(ws, {
                    "type": "error",
                    "data": {"message": "Invalid JSON"},
                })
                continue

            msg_type = message.get("type", "")
            msg_data = message.get("data", {})

            if msg_type == "player_action":
                await _handle_player_action(session_id, session, msg_data)

            elif msg_type == "voice_input":
                await _handle_voice_input(session_id, session, msg_data)

            elif msg_type == "dice_roll":
                await _handle_dice_roll(session_id, session, msg_data)

            elif msg_type == "camera_frame":
                await _handle_camera_frame(session_id, session, msg_data)

            elif msg_type == "start_game":
                await _handle_start_game(session_id, session)

            elif msg_type == "player_chat":
                # Text chat — broadcast to all players (not sent to AI)
                await manager.broadcast(session_id, {
                    "type": "player_chat",
                    "data": {
                        "sender": msg_data.get("sender", "Unknown"),
                        "message": msg_data.get("message", ""),
                    },
                })

            elif msg_type == "webrtc_signal":
                # WebRTC signaling — relay to all other clients
                await manager.broadcast(session_id, {
                    "type": "webrtc_signal",
                    "data": msg_data,
                })

            else:
                await manager.send_personal(ws, {
                    "type": "error",
                    "data": {"message": f"Unknown message type: {msg_type}"},
                })

    except WebSocketDisconnect:
        await manager.disconnect(session_id, ws)
        logger.info("Player disconnected from session %s", session_id)


# ── Message Handlers ──────────────────────────────────────────────────────

async def _handle_player_action(
    session_id: str, session: GameSession, data: dict[str, Any]
) -> None:
    """Route player action through the appropriate system."""
    player_input = data.get("text", "")
    if not player_input:
        return

    character_name = data.get("character_name", "Player")

    # Single player: process immediately, no window needed
    if len(session.players) <= 1:
        await _process_single_action(session_id, session, character_name, player_input)
        return

    # Multiplayer: check combat state BEFORE submitting to avoid race
    is_combat = action_window.is_combat(session)

    error = await action_window.submit_action(
        session_id, session, character_name, player_input,
    )
    if error:
        await manager.broadcast(session_id, {
            "type": "error",
            "data": {"message": error},
        })
        return

    # Combat actions process immediately (ActionWindow validated turn order)
    if is_combat:
        session.add_event(StoryEvent(
            event_type="player_action",
            content=player_input,
            speaker=character_name,
        ))
        await _process_single_action(session_id, session, character_name, player_input)
        action_window.finish_combat_action(session_id)


async def _handle_batched_actions(
    session_id: str, session: GameSession,
    combined_input: str, speaker: str,
) -> None:
    """Process batched exploration actions from multiple players."""
    session.add_event(StoryEvent(
        event_type="player_action",
        content=combined_input,
        speaker=speaker,
    ))

    await _process_single_action(session_id, session, speaker, combined_input)


async def _process_single_action(
    session_id: str, session: GameSession,
    character_name: str, player_input: str,
) -> None:
    """Core action processing — AI pipeline, media gen, state sync."""
    context = game_engine.get_context_summary(session)

    await manager.broadcast(session_id, {"type": "thinking", "data": {}})

    tool_events = await process_player_input(session_id, player_input, context)
    ws_messages = await process_tool_results(session_id, tool_events, session)

    for msg in ws_messages:
        msg["session_id"] = session_id
        await manager.broadcast(session_id, msg)

        if msg["type"] == "narration":
            content = msg["data"].get("content", "")
            session.add_event(StoryEvent(
                event_type="narration",
                content=content,
                speaker="narrator",
                drama_level=game_engine.calculate_drama_level(session),
            ))

            if "[NEW_SCENE]" in content or "[CINEMATIC]" in content:
                clean_content = content.replace("[NEW_SCENE]", "").replace("[CINEMATIC]", "").strip()
                asyncio.create_task(
                    _generate_scene_from_narration(session_id, session, clean_content)
                )

    # Sync full game state
    await manager.broadcast(session_id, {
        "type": "game_state_sync",
        "data": {
            "combat": session.combat.model_dump(mode="json"),
            "world": session.world.model_dump(mode="json"),
            "players": [p.model_dump(mode="json") for p in session.players],
            "npcs": {nid: n.model_dump(mode="json") for nid, n in session.world.npcs.items()},
            "quests": [q.model_dump(mode="json") for q in session.world.quests],
        },
    })

    # Auto-save periodically
    if len(session.story_events) % 5 == 0:
        try:
            await firestore_service.save_session(session)
        except Exception:
            logger.warning("Auto-save failed for session %s", session_id)


async def _handle_voice_input(
    session_id: str, session: GameSession, data: dict[str, Any]
) -> None:
    """Process voice input — transcribe and feed into player action pipeline."""
    audio_b64 = data.get("audio", "")
    if not audio_b64:
        return

    # For now, treat transcribed text as player action
    # In production, this would use Gemini Live API for real-time voice
    transcript = data.get("transcript", "")
    if transcript:
        await _handle_player_action(session_id, session, {
            "text": transcript,
            "character_name": data.get("character_name", "Player"),
        })


async def _handle_dice_roll(
    session_id: str, session: GameSession, data: dict[str, Any]
) -> None:
    """Handle physical dice roll from camera or manual input."""
    value = data.get("value")
    roll_type = data.get("roll_type", "d20")
    character_name = data.get("character_name", "Player")

    if value is not None:
        await manager.broadcast(session_id, {
            "type": "dice_result",
            "data": {
                "character": character_name,
                "roll_type": roll_type,
                "value": value,
                "is_critical": value == 20 and roll_type == "d20",
                "is_fumble": value == 1 and roll_type == "d20",
            },
        })


async def _handle_camera_frame(
    session_id: str, session: GameSession, data: dict[str, Any]
) -> None:
    """Process a camera frame for dice detection or environment scanning."""
    frame_b64 = data.get("frame", "")
    purpose = data.get("purpose", "dice_detection")

    if not frame_b64:
        return

    frame_bytes = base64.b64decode(frame_b64)

    if purpose == "dice_detection":
        result = await gemini_service.analyze_image(
            frame_bytes,
            prompt="Look at this image. Are there any dice visible? If so, report the value shown on each die. Return JSON: {\"dice_found\": true/false, \"values\": [{\"type\": \"d20\", \"value\": 17}]}",
        )
        try:
            parsed = json.loads(result)
            if parsed.get("dice_found"):
                for die in parsed.get("values", []):
                    await _handle_dice_roll(session_id, session, {
                        "value": die["value"],
                        "roll_type": die.get("type", "d20"),
                        "character_name": data.get("character_name", "Player"),
                    })
        except (json.JSONDecodeError, KeyError):
            logger.warning("Failed to parse dice detection result")


async def _handle_start_game(session_id: str, session: GameSession) -> None:
    """Initialize the game — generate opening narration and scene."""
    if not session.players:
        await manager.broadcast(session_id, {
            "type": "error",
            "data": {"message": "No players in session. Create characters first."},
        })
        return

    await manager.broadcast(session_id, {"type": "thinking", "data": {}})

    # Generate opening narration
    player_descriptions = ", ".join(
        f"{p.name} the {p.race.value} {p.character_class.value}" for p in session.players
    )
    context = game_engine.get_context_summary(session)

    opening_prompt = (
        f"Begin the adventure! The party consists of: {player_descriptions}. "
        f"Setting: {session.world.setting_description}. "
        f"Create a dramatic opening scene that hooks the players immediately. "
        f"Introduce the initial location vividly. Plant the seed of the main quest. "
        f"Use [NEW_SCENE] and [NPC_INTRO] tags as appropriate."
    )

    tool_events = await process_player_input(session_id, opening_prompt, context)
    ws_messages = await process_tool_results(session_id, tool_events, session)

    # Generate opening scene image (non-blocking)
    try:
        scene_bytes = await media_service.generate_scene_image(
            scene_description=f"Opening scene of {session.world.campaign_name}: {session.world.setting_description}",
            time_of_day=session.world.time_of_day,
            weather=session.world.weather,
        )
        if scene_bytes:
            url = await storage_service.upload_media(scene_bytes, "image", "image/png", session_id)
            ws_messages.insert(0, {
                "type": "scene_image",
                "data": {"url": url, "description": "Opening scene"},
            })
    except Exception:
        logger.warning("Opening scene image failed, continuing without")

    # Generate world map and opening cinematic in background
    asyncio.create_task(_generate_world_map(session))
    video_task = asyncio.create_task(_generate_opening_cinematic(session_id, session))

    for msg in ws_messages:
        msg["session_id"] = session_id
        await manager.broadcast(session_id, msg)

    # Wait for video and send if ready
    try:
        video_result = await asyncio.wait_for(video_task, timeout=120)
        if video_result:
            await manager.broadcast(session_id, video_result)
    except asyncio.TimeoutError:
        logger.warning("Opening cinematic timed out for session %s", session_id)


# ── Background Tasks ──────────────────────────────────────────────────────

async def _generate_scene_from_narration(
    session_id: str, session: GameSession, narration: str
) -> None:
    """Generate a scene image triggered by [NEW_SCENE] or [CINEMATIC] tags."""
    try:
        # Use first 200 chars of narration as the scene description
        scene_desc = narration[:200]
        scene_bytes = await media_service.generate_scene_image(
            scene_description=scene_desc,
            time_of_day=session.world.time_of_day,
            weather=session.world.weather,
        )
        if scene_bytes:
            url = await storage_service.upload_media(
                scene_bytes, "image", "image/png", session_id
            )
            await manager.broadcast(session_id, {
                "type": "scene_image",
                "session_id": session_id,
                "data": {"url": url, "description": scene_desc[:100]},
            })
    except Exception:
        logger.warning("Scene generation from narration failed for session %s", session_id)


async def _generate_world_map(session: GameSession) -> None:
    """Generate world map in background."""
    try:
        locations = list(session.world.locations.values())
        location_names = [loc.name for loc in locations] if locations else None

        map_bytes = await media_service.generate_world_map(
            setting_description=session.world.setting_description,
            locations=location_names,
        )
        if map_bytes:
            url = await storage_service.upload_media(
                map_bytes, "map", "image/png", session.id
            )
            session.world.world_map_url = url
            await manager.broadcast(session.id, {
                "type": "world_map_update",
                "data": {"url": url},
            })
    except Exception:
        logger.exception("Failed to generate world map for session %s", session.id)


async def _generate_opening_cinematic(
    session_id: str, session: GameSession
) -> dict[str, Any] | None:
    """Generate opening cinematic video."""
    try:
        video_bytes = await media_service.generate_cinematic(
            scene_description=(
                f"Epic cinematic opening for '{session.world.campaign_name}'. "
                f"{session.world.setting_description}. "
                f"Sweeping aerial shot revealing a vast fantasy landscape, "
                f"then descending to the starting location."
            ),
            mood="epic",
            camera_movement="slow aerial descent",
            visual_effects=["volumetric fog", "god rays", "particle dust"],
        )
        if video_bytes:
            url = await storage_service.upload_media(
                video_bytes, "video", "video/mp4", session_id
            )
            return {
                "type": "scene_video",
                "session_id": session_id,
                "data": {"url": url, "description": "Opening cinematic"},
            }
    except Exception:
        logger.exception("Failed to generate opening cinematic for %s", session_id)
    return None


# ── Health Check ──────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
