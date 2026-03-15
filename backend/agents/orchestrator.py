"""Genesis ADK Orchestrator — agent definitions, runner, and event processing."""

from __future__ import annotations

import json
import logging
from typing import Any

from google.adk import Agent, Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai import types

from config import settings
from agents.prompts import (
    NARRATOR_INSTRUCTION,
    RULES_INSTRUCTION,
    ART_DIRECTOR_INSTRUCTION,
    WORLD_KEEPER_INSTRUCTION,
)
from agents.tools import (
    narrate_scene, generate_scene_art, generate_cinematic_video, set_music_mood,
    roll_check, start_combat_encounter, resolve_combat_action,
    create_npc, update_quest, change_location, update_world_state,
    award_experience, generate_loot, record_npc_memory,
    add_world_consequence, update_faction_reputation, add_lore_entry,
)
from agents.tool_handlers import TOOL_HANDLERS
from game.engine import game_engine
from game.models import GameSession

logger = logging.getLogger(__name__)


# ── System Instruction ────────────────────────────────────────────────────

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
- All game mechanics should be processed internally through tools and narrated naturally.
- Your output should always read like vivid prose, never like data or code.

MANDATORY TOOL USAGE — YOU MUST USE THESE TOOLS ACTIVELY:

DICE ROLLS (roll_check) — REQUIRED for:
- ANY action with uncertain outcome: searching, persuading, sneaking, climbing, jumping
- Perception checks when scanning for danger or hidden things
- Investigation checks when examining objects or clues
- ANY physical feat: breaking doors, lifting heavy objects, dodging traps
- Social interactions: persuasion, deception, intimidation
- DO NOT just narrate success/failure. ALWAYS call roll_check first, then narrate based on the result.
- Example: Player says "I search the room" → call roll_check(character, "wisdom", dc=12) → narrate based on success/failure

SCENE IMAGES (generate_scene_art) — REQUIRED for:
- Every new location the party enters (use [NEW_SCENE] tag AND call generate_scene_art)
- Every combat encounter start
- Every significant NPC introduction
- Any dramatic story moment
- AT MINIMUM: generate one image every 2-3 player actions
- Include the [NEW_SCENE] tag in your narration text when the visual setting changes

MUSIC (set_music_mood) — REQUIRED:
- Call set_music_mood at least once per scene change
- Change mood when tension shifts: peaceful exploration → tense discovery → combat
- Valid moods: peaceful, mysterious, tense, combat, epic, triumphant, sad

XP AWARDS (award_experience) — REQUIRED:
- Award 25-50 XP for clever actions or good roleplay
- Award 50-100 XP for overcoming challenges (traps, puzzles, social encounters)
- Award 100-200 XP for combat victories
- Award 200-500 XP for quest completion
- Call award_experience after EVERY meaningful accomplishment

QUESTS (update_quest) — REQUIRED:
- Create a quest within the first 2-3 player turns using update_quest with update_type="new"
- Progress quests as objectives are met
- Complete quests and award rewards when done

NPC MEMORY (record_npc_memory) — REQUIRED:
- After EVERY significant NPC interaction, call record_npc_memory
- Include sentiment (-10 to +10) based on how the interaction went
- NPCs who appear in context have a "memories" field — reference their past interactions

LOOT (generate_loot) — REQUIRED:
- Generate loot after combat victories
- Generate loot when searching defeated enemies, treasure chests, or hidden caches
- Vary rarity: 70% common, 20% uncommon, 8% rare, 2% epic/legendary
- Give items story-connected names and lore

CONSEQUENCES (add_world_consequence) — REQUIRED:
- When players make meaningful choices, call add_world_consequence
- Examples: sparing an enemy, destroying something, making a promise, choosing a path

LOREBOOK (add_lore_entry) — REQUIRED:
- When you introduce important world details (place names, historical events, magic systems), save them with add_lore_entry

COMBAT (start_combat_encounter) — REQUIRED:
- When hostile creatures appear, ALWAYS initiate combat with start_combat_encounter
- Don't just narrate "you fight them" — use the combat system with proper initiative and attack rolls
- Introduce combat encounters every 3-5 turns to keep gameplay exciting

WORKFLOW FOR EACH PLAYER INPUT:
1. Understand what the player is trying to do
2. Call roll_check for ANY uncertain outcome (this is mandatory, not optional)
3. Call generate_scene_art if the visual setting has changed (include [NEW_SCENE] in text)
4. Narrate the result with vivid description based on the roll outcome
5. Call set_music_mood if the tone has shifted
6. Call update_quest / record_npc_memory / add_world_consequence as appropriate
7. Call award_experience for any accomplishment
8. End with a natural prompt for the next action

BACKSTORY INTEGRATION:
- Read player backstories from context. Weave backstory elements into the narrative.
- A character's lost family member might appear as an NPC. Their sworn enemy could be a villain.

WEATHER EFFECTS:
- Weather affects combat mechanically (see weather_effects in context).
- Narrate weather impacts on the environment.

BOSS FIGHTS:
- Boss encounters should have multiple phases with unique mechanics.
- Use [CINEMATIC] tags for boss reveals and phase transitions.

When starting a new session, always:
1. Set the opening scene with an illustration (generate_scene_art)
2. Introduce the setting with dramatic narration
3. Present an immediate quest hook (update_quest with type="new")
4. Introduce at least one NPC (create_npc)
5. Set initial music mood (set_music_mood)
6. Add key setting details to lorebook (add_lore_entry)"""


# ── Agent Definitions ─────────────────────────────────────────────────────

narrator_agent = Agent(
    model=settings.GEMINI_MODEL,
    name="narrator",
    description="Handles all storytelling, narration, and NPC dialogue",
    instruction=NARRATOR_INSTRUCTION,
    tools=[FunctionTool(narrate_scene), FunctionTool(set_music_mood)],
)

rules_agent = Agent(
    model=settings.GEMINI_FLASH_MODEL,
    name="rules",
    description="Manages game mechanics, dice rolls, combat, and character stats",
    instruction=RULES_INSTRUCTION,
    tools=[FunctionTool(roll_check), FunctionTool(start_combat_encounter), FunctionTool(resolve_combat_action)],
)

art_director_agent = Agent(
    model=settings.GEMINI_FLASH_MODEL,
    name="art_director",
    description="Generates scene illustrations, portraits, and battle maps",
    instruction=ART_DIRECTOR_INSTRUCTION,
    tools=[FunctionTool(generate_scene_art), FunctionTool(generate_cinematic_video)],
)

world_keeper_agent = Agent(
    model=settings.GEMINI_FLASH_MODEL,
    name="world_keeper",
    description="Manages NPCs, quests, locations, and world state",
    instruction=WORLD_KEEPER_INSTRUCTION,
    tools=[FunctionTool(create_npc), FunctionTool(update_quest),
           FunctionTool(change_location), FunctionTool(update_world_state)],
)

genesis_agent = Agent(
    model=settings.GEMINI_MODEL,
    name="genesis",
    description="Master Game Master orchestrating the tabletop RPG experience",
    instruction=GENESIS_SYSTEM_INSTRUCTION,
    sub_agents=[narrator_agent, rules_agent, art_director_agent, world_keeper_agent],
    tools=[
        FunctionTool(narrate_scene), FunctionTool(generate_scene_art),
        FunctionTool(generate_cinematic_video), FunctionTool(roll_check),
        FunctionTool(start_combat_encounter), FunctionTool(resolve_combat_action),
        FunctionTool(create_npc), FunctionTool(update_quest),
        FunctionTool(change_location), FunctionTool(update_world_state),
        FunctionTool(set_music_mood), FunctionTool(award_experience),
        FunctionTool(generate_loot), FunctionTool(record_npc_memory),
        FunctionTool(add_world_consequence), FunctionTool(update_faction_reputation),
        FunctionTool(add_lore_entry),
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
    if session_id not in _created_sessions:
        await session_service.create_session(
            app_name="genesis_rpg", user_id="player", session_id=session_id,
        )
        _created_sessions.add(session_id)


async def process_player_input(
    session_id: str, player_input: str, game_context: dict[str, Any],
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
    seen_tool_calls: set[str] = set()  # Deduplicate tool calls

    async for event in runner.run_async(
        user_id="player", session_id=session_id, new_message=content,
    ):
        # Capture INTERMEDIATE tool calls (ADK processes these internally,
        # but we need to intercept them for dice results, XP, loot, etc.)
        if not event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                if part.function_call:
                    call_id = f"{part.function_call.name}:{json.dumps(dict(part.function_call.args) if part.function_call.args else {}, sort_keys=True)}"
                    if call_id not in seen_tool_calls:
                        seen_tool_calls.add(call_id)
                        events.append({
                            "type": "tool_call",
                            "name": part.function_call.name,
                            "args": dict(part.function_call.args) if part.function_call.args else {},
                        })
                # Also capture tool responses that contain our tool results
                if part.function_response:
                    try:
                        response_data = dict(part.function_response.response) if part.function_response.response else {}
                        # If the tool returned roll/combat results, extract them
                        if "roll" in response_data or "success" in response_data:
                            call_id = f"roll_result:{json.dumps(response_data, sort_keys=True, default=str)}"
                            if call_id not in seen_tool_calls:
                                seen_tool_calls.add(call_id)
                                events.append({
                                    "type": "tool_call",
                                    "name": response_data.get("action", "roll_check"),
                                    "args": response_data,
                                })
                    except Exception:
                        pass

        # Capture FINAL response (narration text)
        if event.is_final_response():
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        text = part.text.strip()
                        # Filter raw JSON from sub-agents
                        if text.startswith("{") or text.startswith("```"):
                            try:
                                cleaned = text.strip("`").strip()
                                if cleaned.startswith("json"):
                                    cleaned = cleaned[4:].strip()
                                parsed = json.loads(cleaned)
                                hint = parsed.get("narration_hint", "")
                                if hint:
                                    events.append({"type": "narration", "content": hint})
                                action = parsed.get("action", "")
                                if action:
                                    events.append({"type": "tool_call", "name": action, "args": parsed.get("details", parsed)})
                                continue
                            except (json.JSONDecodeError, AttributeError):
                                pass
                        events.append({"type": "narration", "content": text})
                    if part.function_call:
                        call_id = f"{part.function_call.name}:{json.dumps(dict(part.function_call.args) if part.function_call.args else {}, sort_keys=True)}"
                        if call_id not in seen_tool_calls:
                            events.append({
                                "type": "tool_call",
                                "name": part.function_call.name,
                                "args": dict(part.function_call.args) if part.function_call.args else {},
                            })

    return events


async def process_tool_results(
    session_id: str, tool_events: list[dict[str, Any]], game_session: GameSession,
) -> list[dict[str, Any]]:
    """Process tool call results using the handler registry.

    Each handler is a focused function in tool_handlers.py.
    """
    ws_messages: list[dict[str, Any]] = []

    for event in tool_events:
        if event["type"] == "narration":
            ws_messages.append({"type": "narration", "data": {"content": event["content"]}})

        elif event["type"] == "tool_call":
            name = event["name"]
            args = event.get("args", {})

            handler = TOOL_HANDLERS.get(name)
            if handler:
                try:
                    results = await handler(session_id, args, game_session)
                    # Handle sync lambdas (music_change)
                    if not hasattr(results, '__await__') and isinstance(results, list):
                        ws_messages.extend(results)
                    else:
                        ws_messages.extend(results)
                except Exception:
                    logger.exception("Tool handler failed for %s", name)
            else:
                logger.warning("No handler for tool: %s", name)

    return ws_messages
