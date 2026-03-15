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
from game.engine import CombatEngine, GameEngine, game_engine, roll_dice, roll_d20, create_character
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

CRITICAL OUTPUT RULES:
- NEVER output raw JSON in your responses. Always respond with natural narration text.
- When dice rolls are needed, use your roll_check tool, then narrate the result dramatically.
- All game mechanics should be processed internally through tools and narrated naturally.
- Your output should always read like vivid prose, never like data or code.

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


_created_sessions: set[str] = set()


async def _ensure_session(session_id: str) -> None:
    """Create an ADK session if it doesn't exist yet."""
    if session_id not in _created_sessions:
        await session_service.create_session(
            app_name="genesis_rpg",
            user_id="player",
            session_id=session_id,
        )
        _created_sessions.add(session_id)


async def process_player_input(
    session_id: str,
    player_input: str,
    game_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Process player input through the ADK agent pipeline.

    Returns a list of actions/events to be dispatched to the frontend.
    """
    await _ensure_session(session_id)

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
                        text = part.text.strip()
                        # Filter out raw JSON responses from sub-agents
                        # that leaked through without narration
                        if text.startswith("{") or text.startswith("```"):
                            try:
                                cleaned = text.strip("`").strip()
                                if cleaned.startswith("json"):
                                    cleaned = cleaned[4:].strip()
                                parsed = json.loads(cleaned)
                                # Extract narration hint if present
                                hint = parsed.get("narration_hint", "")
                                if hint:
                                    events.append({
                                        "type": "narration",
                                        "content": hint,
                                    })
                                # Also emit as tool result
                                action = parsed.get("action", "")
                                if action:
                                    events.append({
                                        "type": "tool_call",
                                        "name": action,
                                        "args": parsed.get("details", parsed),
                                    })
                                continue
                            except (json.JSONDecodeError, AttributeError):
                                pass  # Not JSON, treat as narration
                        events.append({
                            "type": "narration",
                            "content": text,
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

            elif name == "narrate_scene":
                # Narrate scene tool — emit as narration
                scene_desc = args.get("scene", "")
                if scene_desc:
                    ws_messages.append({
                        "type": "narration",
                        "data": {"content": scene_desc},
                    })

            elif name in ("roll_check", "skill_check"):
                # Apply dice roll results to character state
                session = game_engine.get_session(session_id)
                if session and not args.get("success", True):
                    # On failed save/check, apply damage if specified
                    damage = args.get("damage", 0)
                    if damage:
                        char_name = args.get("character", "")
                        for p in session.players:
                            if p.name.lower() == char_name.lower():
                                p.hp = max(0, p.hp - damage)
                                break
                ws_messages.append({
                    "type": "dice_result",
                    "data": args,
                })

            elif name == "start_combat_encounter":
                # Actually start combat in the game engine
                session = game_engine.get_session(session_id)
                if session:
                    enemies_data = args.get("enemies", [])
                    for enemy in enemies_data:
                        npc = NPC(
                            name=enemy.get("name", "Enemy"),
                            description=enemy.get("description", ""),
                            is_hostile=True,
                            hp=int(10 + enemy.get("cr", 1) * 8),
                            max_hp=int(10 + enemy.get("cr", 1) * 8),
                            armor_class=int(10 + enemy.get("cr", 1) * 2),
                            challenge_rating=enemy.get("cr", 1.0),
                        )
                        game_engine.add_npc(session_id, npc)

                    enemy_ids = [
                        nid for nid, n in session.world.npcs.items()
                        if n.is_hostile and n.hp > 0
                    ]
                    combat_state = game_engine.start_combat(session_id, enemy_ids)
                    if combat_state:
                        ws_messages.append({
                            "type": "combat_update",
                            "data": combat_state.model_dump(mode="json"),
                        })
                        # Generate battle map
                        try:
                            map_bytes = await media_service.generate_battle_map(
                                location_description=args.get("description", session.world.setting_description),
                            )
                            if map_bytes:
                                map_url = await storage_service.upload_media(
                                    map_bytes, "image", "image/png", session_id
                                )
                                ws_messages.append({
                                    "type": "battle_map",
                                    "data": {"url": map_url},
                                })
                        except Exception:
                            logger.warning("Battle map generation failed")

            elif name == "resolve_combat_action":
                # Actually resolve combat through the engine
                session = game_engine.get_session(session_id)
                if session and session.combat.is_active:
                    attacker_name = args.get("attacker", "")
                    target_name = args.get("target", "")
                    action_type = args.get("type", "attack")

                    attacker = next(
                        (c for c in session.combat.combatants if c.name.lower() == attacker_name.lower()), None
                    )
                    defender = next(
                        (c for c in session.combat.combatants if c.name.lower() == target_name.lower()), None
                    )

                    if attacker and defender and action_type == "attack":
                        result = CombatEngine.resolve_attack(attacker, defender)
                        # Sync HP back to player/NPC models
                        for p in session.players:
                            matching = next((c for c in session.combat.combatants if c.id == p.id), None)
                            if matching:
                                p.hp = matching.hp
                        for npc in session.world.npcs.values():
                            matching = next((c for c in session.combat.combatants if c.id == npc.id), None)
                            if matching:
                                npc.hp = matching.hp

                        ws_messages.append({
                            "type": "dice_result",
                            "data": {
                                "character": result.actor_name,
                                "roll_type": "d20",
                                "value": result.roll,
                                "is_critical": result.is_critical,
                                "is_fumble": result.is_miss and result.roll == 1,
                            },
                        })
                        ws_messages.append({
                            "type": "combat_update",
                            "data": session.combat.model_dump(mode="json"),
                        })

                    # Advance turn
                    next_combatant = CombatEngine.next_turn(session.combat)
                    if not session.combat.is_active:
                        ws_messages.append({
                            "type": "combat_update",
                            "data": {"is_active": False, "phase": "ended"},
                        })
                else:
                    ws_messages.append({
                        "type": "combat_update",
                        "data": {"action": "resolve", **args},
                    })

            elif name == "create_npc":
                # Create NPC in game engine AND generate portrait
                npc = NPC(
                    name=args.get("name", ""),
                    description=args.get("description", ""),
                    personality=args.get("personality", ""),
                    voice_style=args.get("voice_style", "neutral"),
                    is_hostile=args.get("is_hostile", False),
                    location=game_session.world.current_location_id,
                )
                game_engine.add_npc(session_id, npc)

                portrait_url = ""
                try:
                    portrait_bytes = await media_service.generate_character_portrait(
                        name=args.get("name", ""),
                        race="human",
                        character_class="commoner",
                        appearance=args.get("description", ""),
                    )
                    if portrait_bytes:
                        portrait_url = await storage_service.upload_media(
                            portrait_bytes, "image", "image/png", session_id
                        )
                        npc.portrait_url = portrait_url
                except Exception:
                    logger.warning("NPC portrait generation failed for %s", args.get("name"))

                ws_messages.append({
                    "type": "npc_portrait",
                    "data": {
                        "id": npc.id,
                        "name": npc.name,
                        "portrait_url": portrait_url,
                        "description": npc.description,
                        "personality": npc.personality,
                    },
                })

            elif name == "change_location":
                # Update backend state
                loc = Location(
                    name=args.get("name", ""),
                    description=args.get("description", ""),
                    location_type=args.get("type", "generic"),
                    visited=True,
                )
                game_engine.add_location(session_id, loc)
                game_engine.move_to_location(session_id, loc.id)

                # Generate scene image
                scene_url = ""
                try:
                    scene_bytes = await media_service.generate_scene_image(
                        scene_description=args.get("description", ""),
                        time_of_day=game_session.world.time_of_day,
                        weather=game_session.world.weather,
                    )
                    if scene_bytes:
                        scene_url = await storage_service.upload_media(
                            scene_bytes, "image", "image/png", session_id
                        )
                        loc.image_url = scene_url
                except Exception:
                    logger.warning("Location scene generation failed")

                ws_messages.append({
                    "type": "location_change",
                    "data": {
                        "name": loc.name,
                        "description": loc.description,
                        "image_url": scene_url,
                        "location_id": loc.id,
                    },
                })

            elif name == "update_quest":
                # Update quest state in backend
                session = game_engine.get_session(session_id)
                if session:
                    quest_title = args.get("quest", "")
                    update_type = args.get("update", "progress")
                    details = args.get("details", "")

                    existing = next(
                        (q for q in session.world.quests if q.title.lower() == quest_title.lower()),
                        None,
                    )
                    if existing:
                        if update_type == "complete":
                            existing.is_complete = True
                            existing.is_active = False
                            # Award rewards
                            for p in session.players:
                                p.xp += existing.reward_xp
                                p.gold += existing.reward_gold
                        elif update_type == "progress" and details:
                            # Mark next objective complete
                            for i, obj in enumerate(existing.objectives):
                                if i not in existing.completed_objectives:
                                    existing.completed_objectives.append(i)
                                    break
                    elif update_type == "new" or not existing:
                        # Create new quest
                        new_quest = Quest(
                            title=quest_title,
                            description=details,
                            objectives=[details] if details else [],
                        )
                        game_engine.add_quest(session_id, new_quest)

                ws_messages.append({
                    "type": "quest_update",
                    "data": {
                        **args,
                        "quests": [q.model_dump(mode="json") for q in session.world.quests] if session else [],
                    },
                })

            elif name == "update_world_state":
                # Actually update backend world state
                session = game_engine.get_session(session_id)
                if session:
                    if args.get("time_of_day"):
                        session.world.time_of_day = args["time_of_day"]
                    if args.get("weather"):
                        session.world.weather = args["weather"]
                    if args.get("advance_day"):
                        session.world.day_count += 1
                    if args.get("event"):
                        session.world.global_events.append(args["event"])

                ws_messages.append({
                    "type": "world_update",
                    "data": {
                        "time_of_day": session.world.time_of_day if session else "",
                        "weather": session.world.weather if session else "",
                        "day_count": session.world.day_count if session else 1,
                    },
                })

            elif name == "set_music_mood":
                ws_messages.append({
                    "type": "music_change",
                    "data": args,
                })

    return ws_messages
