"""Player action processing — single and batched action handling."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from game.engine import game_engine
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

    # Auto-save periodically
    if len(session.story_events) % 5 == 0:
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
