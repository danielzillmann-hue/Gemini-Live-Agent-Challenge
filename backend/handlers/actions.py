"""Player action processing — single and batched action handling."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from game.engine import game_engine, roll_d20
from game.models import GameSession, StoryEvent
from agents.orchestrator import process_player_input, process_tool_results
from services import firestore_service

logger = logging.getLogger(__name__)

# These are set by main.py at startup to avoid circular imports
_broadcast = None
_generate_scene_from_narration = None


def set_callbacks(broadcast, scene_gen) -> None:
    global _broadcast, _generate_scene_from_narration
    _broadcast = broadcast
    _generate_scene_from_narration = scene_gen


async def process_single_action(
    session_id: str, session: GameSession,
    character_name: str, player_input: str,
) -> None:
    """Core action processing — AI pipeline, media gen, state sync."""
    context = game_engine.get_context_summary(session)

    await _broadcast(session_id, {"type": "thinking", "data": {}})

    tool_events = await process_player_input(session_id, player_input, context)
    ws_messages = await process_tool_results(session_id, tool_events, session)

    # Check if the AI narrated combat without calling dice tools
    has_dice = any(m["type"] == "dice_result" for m in ws_messages)
    has_combat_narration = False

    for msg in ws_messages:
        msg["session_id"] = session_id
        await _broadcast(session_id, msg)

        if msg["type"] == "narration":
            content = msg["data"].get("content", "")
            session.add_event(StoryEvent(
                event_type="narration", content=content, speaker="narrator",
                drama_level=game_engine.calculate_drama_level(session),
            ))

            if "[NEW_SCENE]" in content or "[CINEMATIC]" in content:
                clean_content = content.replace("[NEW_SCENE]", "").replace("[CINEMATIC]", "").strip()
                asyncio.create_task(_generate_scene_from_narration(session_id, session, clean_content))

            # Detect if AI narrated combat/checks without rolling dice
            combat_keywords = re.compile(
                r'\b(attack|swing|strike|slash|stab|shoot|cast|hit|miss|damage|wound|block|dodge|parry|'
                r'search|examine|investigate|persuade|deceive|intimidate|sneak|climb|jump|pick the lock|'
                r'perception|check|roll)\b', re.IGNORECASE
            )
            if combat_keywords.search(content):
                has_combat_narration = True

    # If AI narrated combat/checks but didn't roll dice, inject a visible roll
    if has_combat_narration and not has_dice and session.players:
        player = session.get_alive_players()[0] if session.get_alive_players() else session.players[0]
        total, raw = roll_d20(player.ability_scores.modifier("strength"))
        # Determine what kind of check from the player input
        ability = "strength"
        for ab in ["wisdom", "dexterity", "charisma", "intelligence", "constitution"]:
            if ab[:3].lower() in player_input.lower():
                ability = ab
                break
        if any(w in player_input.lower() for w in ["search", "look", "examine", "investigate", "notice", "spot"]):
            ability = "wisdom"
        elif any(w in player_input.lower() for w in ["persuade", "convince", "talk", "negotiate", "charm"]):
            ability = "charisma"
        elif any(w in player_input.lower() for w in ["sneak", "hide", "dodge", "climb", "jump", "pick"]):
            ability = "dexterity"

        modifier = player.ability_scores.modifier(ability)
        total = raw + modifier
        dc = 12  # Default DC
        success = total >= dc

        await _broadcast(session_id, {
            "session_id": session_id,
            "type": "dice_result",
            "data": {
                "character": player.name,
                "ability": ability,
                "roll_type": "d20",
                "value": raw,
                "total": total,
                "dc": dc,
                "success": success,
                "is_critical": raw == 20,
                "is_fumble": raw == 1,
            },
        })

    # Sync full game state
    await _broadcast(session_id, {
        "type": "game_state_sync",
        "data": {
            "combat": session.combat.model_dump(mode="json"),
            "world": session.world.model_dump(mode="json"),
            "players": [p.model_dump(mode="json") for p in session.players],
            "npcs": {nid: n.model_dump(mode="json") for nid, n in session.world.npcs.items()},
            "quests": [q.model_dump(mode="json") for q in session.world.quests],
        },
    })

    # Auto-save after every action (protects against Cloud Run shutdown)
    try:
        await firestore_service.save_session(session)
    except Exception:
        logger.warning("Auto-save failed for session %s", session_id)


async def handle_batched_actions(
    session_id: str, session: GameSession,
    combined_input: str, speaker: str,
) -> None:
    """Process batched exploration actions from multiple players."""
    session.add_event(StoryEvent(
        event_type="player_action", content=combined_input, speaker=speaker,
    ))
    await process_single_action(session_id, session, speaker, combined_input)
