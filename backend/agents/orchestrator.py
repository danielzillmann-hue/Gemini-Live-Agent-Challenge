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
- When dice rolls are needed, use your roll_check tool, then narrate the result dramatically.
- All game mechanics should be processed internally through tools and narrated naturally.
- Your output should always read like vivid prose, never like data or code.

WORKFLOW FOR EACH PLAYER INPUT:
1. Understand what the player is trying to do
2. Determine if a dice roll is needed (uncertain outcomes only)
3. Narrate the result with vivid description
4. Generate art if this is a visually significant moment
5. Generate video only for peak dramatic moments (drama level 7+)
6. Update world state, quests, and NPCs as needed
7. Set appropriate music mood
8. End with a natural prompt for the next action

CHARACTER PROGRESSION:
- Award XP for combat victories (50-200 XP), quest completion (100-500 XP),
  and clever/heroic actions (25-100 XP). Use the award_experience tool.
- When a character levels up, narrate it dramatically.

NPC MEMORY & RELATIONSHIPS:
- After significant NPC interactions, use record_npc_memory to save what happened.
- NPCs remember past interactions. Check the "memories" field in npcs_present context.
- NPCs should react differently based on relationship level and memories.

CONSEQUENCES:
- When players make major choices, use add_world_consequence to track the ripple effects.
- Reference active consequences from context — they should affect the narrative.

FACTIONS:
- Use update_faction_reputation when player actions affect a faction's view of them.

LOOT & ITEMS:
- After combat or discoveries, use generate_loot to create unique items.
- Items should have names, descriptions, and lore connected to the story.

LOREBOOK:
- When introducing important world details, use add_lore_entry to save them.

WEATHER EFFECTS:
- Weather affects combat mechanically (see weather_effects in context).

BACKSTORY INTEGRATION:
- Read player backstories from context. Weave backstory elements into the narrative.

BOSS FIGHTS:
- Boss encounters should have multiple phases with unique mechanics.
- Use [CINEMATIC] tags for boss reveals and phase transitions.

When starting a new session, always:
1. Generate a world map
2. Set the opening scene with an illustration
3. Introduce the setting with dramatic narration
4. Present an immediate hook to engage players
5. Set initial music mood"""


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

    async for event in runner.run_async(
        user_id="player", session_id=session_id, new_message=content,
    ):
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
