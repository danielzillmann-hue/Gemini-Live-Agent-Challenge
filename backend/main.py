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
        logger.info("Player connected to session %s (%d total)", session_id, len(self.active[session_id]))

    def disconnect(self, session_id: str, ws: WebSocket) -> None:
        if session_id in self.active:
            self.active[session_id] = [w for w in self.active[session_id] if w is not ws]
            if not self.active[session_id]:
                del self.active[session_id]

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        for ws in self.active.get(session_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                logger.warning("Failed to send to WebSocket in session %s", session_id)

    async def send_personal(self, ws: WebSocket, message: dict[str, Any]) -> None:
        await ws.send_json(message)


manager = ConnectionManager()


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

    # Generate world map in background
    asyncio.create_task(_generate_world_map(session))

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

    # Generate portrait
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

            else:
                await manager.send_personal(ws, {
                    "type": "error",
                    "data": {"message": f"Unknown message type: {msg_type}"},
                })

    except WebSocketDisconnect:
        manager.disconnect(session_id, ws)
        logger.info("Player disconnected from session %s", session_id)


# ── Message Handlers ──────────────────────────────────────────────────────

async def _handle_player_action(
    session_id: str, session: GameSession, data: dict[str, Any]
) -> None:
    """Process a text-based player action through the AI pipeline."""
    player_input = data.get("text", "")
    if not player_input:
        return

    # Add player event to story
    session.add_event(StoryEvent(
        event_type="player_action",
        content=player_input,
        speaker=data.get("character_name", "Player"),
    ))

    # Build context for AI
    context = game_engine.get_context_summary(session)

    # Send "thinking" indicator
    await manager.broadcast(session_id, {"type": "thinking", "data": {}})

    # Process through ADK agent pipeline
    tool_events = await process_player_input(session_id, player_input, context)

    # Execute tool results (media generation, state updates)
    ws_messages = await process_tool_results(session_id, tool_events, session)

    # Broadcast all results to connected clients
    for msg in ws_messages:
        msg["session_id"] = session_id
        await manager.broadcast(session_id, msg)

        # Record narration events
        if msg["type"] == "narration":
            session.add_event(StoryEvent(
                event_type="narration",
                content=msg["data"].get("content", ""),
                speaker="narrator",
                drama_level=game_engine.calculate_drama_level(session),
            ))

    # Send updated game state
    await manager.broadcast(session_id, {
        "type": "game_state_sync",
        "data": {
            "combat": session.combat.model_dump(mode="json"),
            "world": {
                "time_of_day": session.world.time_of_day,
                "weather": session.world.weather,
                "day_count": session.world.day_count,
                "current_location_id": session.world.current_location_id,
            },
            "players": [p.model_dump(mode="json") for p in session.players],
            "quests": [q.model_dump(mode="json") for q in session.world.quests if q.is_active],
        },
    })


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

    # Generate opening scene image
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

    # Generate opening cinematic video
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
