"""Genesis ADK Orchestrator — coordinates all sub-agents for the game session."""

from __future__ import annotations

import json
import logging
from typing import Any

from google.adk import Agent, Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai import types

from config import settings
from game.engine import GameEngine, game_engine, roll_dice, roll_d20, create_character
from game.models import (
    Character,
    CharacterClass,
    CharacterRace,
    GameSession,
    GeneratedMedia,
    Location,
    MediaType,
    NPC,
    Quest,
    StoryEvent,
)
from services import gemini_service, media_service, storage_service

logger = logging.getLogger(__name__)


# ── Tool Functions (exposed to ADK agents) ────────────────────────────────

def narrate_scene(
    session_id: str, scene_description: str, mood: str = "neutral"
) -> dict[str, Any]:
    """Generate narration for a scene transition or story beat."""
    return {
        "action": "narrate",
        "session_id": session_id,
        "scene": scene_description,
        "mood": mood,
    }


def generate_scene_art(
    session_id: str,
    scene_description: str,
    characters_present: list[str] | None = None,
    camera_angle: str = "wide",
) -> dict[str, Any]:
    """Request scene illustration generation."""
    return {
        "action": "generate_image",
        "session_id": session_id,
        "description": scene_description,
        "characters": characters_present or [],
        "camera": camera_angle,
    }


def generate_cinematic_video(
    session_id: str,
    scene_description: str,
    mood: str = "epic",
    duration_seconds: int = 5,
) -> dict[str, Any]:
    """Request cinematic video generation for dramatic moments."""
    return {
        "action": "generate_video",
        "session_id": session_id,
        "description": scene_description,
        "mood": mood,
        "duration": duration_seconds,
    }


def roll_check(
    character_name: str,
    ability: str,
    difficulty_class: int = 10,
    advantage: bool = False,
    disadvantage: bool = False,
) -> dict[str, Any]:
    """Roll an ability check for a character."""
    total, raw = roll_d20()
    if advantage:
        total2, raw2 = roll_d20()
        if total2 > total:
            total, raw = total2, raw2
    elif disadvantage:
        total2, raw2 = roll_d20()
        if total2 < total:
            total, raw = total2, raw2

    success = total >= difficulty_class
    is_crit = raw == 20
    is_fumble = raw == 1

    return {
        "character": character_name,
        "ability": ability,
        "roll": raw,
        "total": total,
        "dc": difficulty_class,
        "success": success,
        "critical_success": is_crit,
        "critical_failure": is_fumble,
    }


def start_combat_encounter(
    session_id: str,
    enemy_names: list[str],
    enemy_descriptions: list[str],
    challenge_rating: float = 1.0,
) -> dict[str, Any]:
    """Initiate a combat encounter."""
    return {
        "action": "start_combat",
        "session_id": session_id,
        "enemies": [
            {"name": n, "description": d, "cr": challenge_rating}
            for n, d in zip(enemy_names, enemy_descriptions)
        ],
    }


def resolve_combat_action(
    session_id: str,
    attacker_name: str,
    action_type: str,
    target_name: str = "",
    weapon_or_spell: str = "",
) -> dict[str, Any]:
    """Resolve a combat action (attack, spell, ability, etc.)."""
    return {
        "action": "combat_action",
        "session_id": session_id,
        "attacker": attacker_name,
        "type": action_type,
        "target": target_name,
        "weapon_or_spell": weapon_or_spell,
    }


def create_npc(
    session_id: str,
    name: str,
    description: str,
    personality: str,
    voice_style: str = "neutral",
    is_hostile: bool = False,
) -> dict[str, Any]:
    """Create a new NPC in the world."""
    return {
        "action": "create_npc",
        "session_id": session_id,
        "name": name,
        "description": description,
        "personality": personality,
        "voice_style": voice_style,
        "is_hostile": is_hostile,
    }


def update_quest(
    session_id: str,
    quest_title: str,
    update_type: str = "progress",
    details: str = "",
) -> dict[str, Any]:
    """Update quest state — progress, complete, or add new quest."""
    return {
        "action": "quest_update",
        "session_id": session_id,
        "quest": quest_title,
        "update": update_type,
        "details": details,
    }


def change_location(
    session_id: str,
    location_name: str,
    location_description: str,
    location_type: str = "generic",
) -> dict[str, Any]:
    """Move the party to a new location."""
    return {
        "action": "change_location",
        "session_id": session_id,
        "name": location_name,
        "description": location_description,
        "type": location_type,
    }


def update_world_state(
    session_id: str,
    time_of_day: str = "",
    weather: str = "",
    advance_day: bool = False,
    world_event: str = "",
) -> dict[str, Any]:
    """Update world state — time, weather, global events."""
    return {
        "action": "world_update",
        "session_id": session_id,
        "time_of_day": time_of_day,
        "weather": weather,
        "advance_day": advance_day,
        "event": world_event,
    }


def set_music_mood(
    mood: str, intensity: float = 0.5
) -> dict[str, Any]:
    """Change the background music mood and intensity."""
    return {
        "action": "music_change",
        "mood": mood,
        "intensity": min(1.0, max(0.0, intensity)),
    }


# ── Agent Definitions ─────────────────────────────────────────────────────

GENESIS_SYSTEM_INSTRUCTION = """You are Genesis, the master AI Game Master orchestrating an immersive tabletop RPG experience.

You coordinate a team of specialized sub-capabilities:
1. NARRATION: Vivid storytelling, NPC dialogue, scene-setting
2. RULES: Combat mechanics, dice rolls, character progression
3. ART: Scene illustrations, character portraits, battle maps
4. VIDEO: Cinematic cutscenes for dramatic moments
5. WORLD: NPC tracking, quest management, world state
6. SOUND: Music and ambient audio atmosphere

CORE PRINCIPLES:
- Player agency is sacred. Never railroad. React to and build upon player choices.
- Show, don't tell. Use your tools to generate visuals for important moments.
- Pacing matters. Alternate between action, exploration, and social encounters.
- Every NPC should feel alive with motivations, secrets, and personality.
- Combat should be tactical, dramatic, and consequential.
- Use cinematic video for the most dramatic moments (boss reveals, plot twists, critical hits).
- Keep the world consistent. Actions have consequences that ripple forward.

WORKFLOW FOR EACH PLAYER INPUT:
1. Understand what the player is trying to do
2. Determine if a dice roll is needed (uncertain outcomes only)
3. Narrate the result with vivid description
4. Generate art if this is a visually significant moment (new scene, dramatic action, NPC introduction)
5. Generate video only for peak dramatic moments (drama level 7+)
6. Update world state, quests, and NPCs as needed
7. Set appropriate music mood
8. End with a natural prompt for the next action

DRAMA LEVEL GUIDE (for media decisions):
1-3: Text narration only, maybe ambient scene image
4-6: Generate scene illustration
7-8: Generate detailed illustration + consider video
9-10: Full cinematic video treatment (boss fights, major reveals, deaths)

When starting a new session, always:
1. Generate a world map
2. Set the opening scene with an illustration
3. Introduce the setting with dramatic narration
4. Present an immediate hook to engage players"""

narrator_agent = Agent(
    model=settings.GEMINI_MODEL,
    name="narrator",
    description="Handles all storytelling, narration, and NPC dialogue",
    instruction=gemini_service.NARRATOR_SYSTEM_INSTRUCTION,
    tools=[
        FunctionTool(narrate_scene),
        FunctionTool(set_music_mood),
    ],
)

rules_agent = Agent(
    model=settings.GEMINI_FLASH_MODEL,
    name="rules",
    description="Manages game mechanics, dice rolls, combat, and character stats",
    instruction=gemini_service.RULES_SYSTEM_INSTRUCTION,
    tools=[
        FunctionTool(roll_check),
        FunctionTool(start_combat_encounter),
        FunctionTool(resolve_combat_action),
    ],
)

art_director_agent = Agent(
    model=settings.GEMINI_FLASH_MODEL,
    name="art_director",
    description="Generates scene illustrations, portraits, and battle maps",
    instruction=gemini_service.ART_DIRECTOR_SYSTEM_INSTRUCTION,
    tools=[
        FunctionTool(generate_scene_art),
        FunctionTool(generate_cinematic_video),
    ],
)

world_keeper_agent = Agent(
    model=settings.GEMINI_FLASH_MODEL,
    name="world_keeper",
    description="Manages NPCs, quests, locations, and world state",
    instruction=gemini_service.WORLD_KEEPER_SYSTEM_INSTRUCTION,
    tools=[
        FunctionTool(create_npc),
        FunctionTool(update_quest),
        FunctionTool(change_location),
        FunctionTool(update_world_state),
    ],
)


# ── Master Orchestrator ───────────────────────────────────────────────────

genesis_agent = Agent(
    model=settings.GEMINI_MODEL,
    name="genesis",
    description="Master Game Master orchestrating the tabletop RPG experience",
    instruction=GENESIS_SYSTEM_INSTRUCTION,
    sub_agents=[narrator_agent, rules_agent, art_director_agent, world_keeper_agent],
    tools=[
        FunctionTool(narrate_scene),
        FunctionTool(generate_scene_art),
        FunctionTool(generate_cinematic_video),
        FunctionTool(roll_check),
        FunctionTool(start_combat_encounter),
        FunctionTool(resolve_combat_action),
        FunctionTool(create_npc),
        FunctionTool(update_quest),
        FunctionTool(change_location),
        FunctionTool(update_world_state),
        FunctionTool(set_music_mood),
    ],
)


# ── Runner / Session Manager ──────────────────────────────────────────────

session_service = InMemorySessionService()

runner = Runner(
    agent=genesis_agent,
    app_name="genesis_rpg",
    session_service=session_service,
)


async def process_player_input(
    session_id: str,
    player_input: str,
    game_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Process player input through the ADK agent pipeline.

    Returns a list of actions/events to be dispatched to the frontend.
    """
    context_prompt = (
        f"GAME STATE:\n{json.dumps(game_context, indent=2, default=str)}\n\n"
        f"PLAYER SAYS: {player_input}"
    )

    content = types.Content(
        role="user",
        parts=[types.Part(text=context_prompt)],
    )

    events: list[dict[str, Any]] = []

    async for event in runner.run_async(
        user_id="player",
        session_id=session_id,
        new_message=content,
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        events.append({
                            "type": "narration",
                            "content": part.text,
                        })
                    if part.function_call:
                        events.append({
                            "type": "tool_call",
                            "name": part.function_call.name,
                            "args": dict(part.function_call.args) if part.function_call.args else {},
                        })

    return events


async def process_tool_results(
    session_id: str,
    tool_events: list[dict[str, Any]],
    game_session: GameSession,
) -> list[dict[str, Any]]:
    """Process tool call results and generate media as needed.

    Takes the raw tool events from the agent and executes the actual
    media generation, state updates, etc.

    Returns WebSocket messages to send to the frontend.
    """
    ws_messages: list[dict[str, Any]] = []

    for event in tool_events:
        if event["type"] == "narration":
            ws_messages.append({
                "type": "narration",
                "data": {"content": event["content"]},
            })

        elif event["type"] == "tool_call":
            name = event["name"]
            args = event.get("args", {})

            if name == "generate_scene_art":
                session = game_engine.get_session(session_id)
                if session:
                    image_bytes = await media_service.generate_scene_image(
                        scene_description=args.get("description", ""),
                        characters=args.get("characters"),
                        time_of_day=session.world.time_of_day,
                        weather=session.world.weather,
                        camera_angle=args.get("camera", "wide"),
                    )
                    if image_bytes:
                        url = await storage_service.upload_media(
                            image_bytes, "image", "image/png", session_id
                        )
                        ws_messages.append({
                            "type": "scene_image",
                            "data": {"url": url, "description": args.get("description", "")},
                        })

            elif name == "generate_cinematic_video":
                video_bytes = await media_service.generate_cinematic(
                    scene_description=args.get("description", ""),
                    mood=args.get("mood", "epic"),
                )
                if video_bytes:
                    url = await storage_service.upload_media(
                        video_bytes, "video", "video/mp4", session_id
                    )
                    ws_messages.append({
                        "type": "scene_video",
                        "data": {"url": url, "description": args.get("description", "")},
                    })

            elif name == "roll_check":
                ws_messages.append({
                    "type": "dice_result",
                    "data": args,
                })

            elif name == "start_combat_encounter":
                ws_messages.append({
                    "type": "combat_update",
                    "data": {"action": "start", **args},
                })

            elif name == "resolve_combat_action":
                ws_messages.append({
                    "type": "combat_update",
                    "data": {"action": "resolve", **args},
                })

            elif name == "create_npc":
                portrait_bytes = await media_service.generate_character_portrait(
                    name=args.get("name", ""),
                    race="human",
                    character_class="commoner",
                    appearance=args.get("description", ""),
                )
                portrait_url = ""
                if portrait_bytes:
                    portrait_url = await storage_service.upload_media(
                        portrait_bytes, "image", "image/png", session_id
                    )
                ws_messages.append({
                    "type": "npc_portrait",
                    "data": {
                        "name": args.get("name", ""),
                        "portrait_url": portrait_url,
                        "description": args.get("description", ""),
                        "personality": args.get("personality", ""),
                    },
                })

            elif name == "change_location":
                scene_bytes = await media_service.generate_scene_image(
                    scene_description=args.get("description", ""),
                )
                scene_url = ""
                if scene_bytes:
                    scene_url = await storage_service.upload_media(
                        scene_bytes, "image", "image/png", session_id
                    )
                ws_messages.append({
                    "type": "location_change",
                    "data": {
                        "name": args.get("name", ""),
                        "description": args.get("description", ""),
                        "image_url": scene_url,
                    },
                })

            elif name == "update_quest":
                ws_messages.append({
                    "type": "quest_update",
                    "data": args,
                })

            elif name == "update_world_state":
                ws_messages.append({
                    "type": "world_update",
                    "data": args,
                })

            elif name == "set_music_mood":
                ws_messages.append({
                    "type": "music_change",
                    "data": args,
                })

    return ws_messages
