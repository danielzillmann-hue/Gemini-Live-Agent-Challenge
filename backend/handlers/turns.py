"""ActionWindow — batched turn management for multiplayer sessions."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from game.models import GameSession

logger = logging.getLogger(__name__)

ACTION_WINDOW_SECONDS = 12


class ActionWindow:
    """Collects player actions during a time window, then batches them to the AI.

    Exploration: All players submit actions during the window. When it closes,
    all actions are sent as one prompt and the AI narrates the combined result.

    Combat: Strict initiative order. Only the active combatant can act.
    No window needed — their action processes immediately.
    """

    def __init__(self) -> None:
        self.pending_actions: dict[str, list[tuple[str, str]]] = {}
        self.window_timers: dict[str, asyncio.Task] = {}
        self.is_processing: dict[str, bool] = {}
        self.submitted: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()
        self._broadcast = None
        self._process_batch = None

    def set_callbacks(self, broadcast, process_batch) -> None:
        """Set callback functions (avoids circular imports)."""
        self._broadcast = broadcast
        self._process_batch = process_batch

    def is_combat(self, session: GameSession) -> bool:
        return session.combat.is_active

    def get_combat_turn(self, session: GameSession) -> str:
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
        async with self._lock:
            return await self._submit_action_locked(session_id, session, character_name, action_text)

    async def _submit_action_locked(
        self, session_id: str, session: GameSession,
        character_name: str, action_text: str,
    ) -> str | None:
        if self.is_busy(session_id):
            return "The Game Master is still narrating. Please wait."

        if self.is_combat(session):
            current = self.get_combat_turn(session)
            if not current:
                return "It's the enemy's turn. Please wait."
            if current.lower() != character_name.lower():
                return f"It's {current}'s turn in combat."
            self.is_processing[session_id] = True
            return None

        if session_id in self.submitted and character_name.lower() in self.submitted[session_id]:
            return "You've already submitted your action. Waiting for other players..."

        self.pending_actions.setdefault(session_id, []).append(
            (character_name, action_text)
        )
        self.submitted.setdefault(session_id, set()).add(character_name.lower())

        alive_players = [p for p in session.players if p.hp > 0]
        submitted_count = len(self.submitted.get(session_id, set()))
        total_players = len(alive_players)

        if self._broadcast:
            await self._broadcast(session_id, {
                "type": "action_window",
                "data": {
                    "status": "collecting",
                    "submitted_by": character_name,
                    "submitted_count": submitted_count,
                    "total_players": total_players,
                    "seconds_remaining": ACTION_WINDOW_SECONDS,
                },
            })

        if session_id not in self.window_timers or self.window_timers[session_id].done():
            self.window_timers[session_id] = asyncio.create_task(
                self._window_countdown(session_id, session)
            )

        if submitted_count >= total_players:
            if session_id in self.window_timers and not self.window_timers[session_id].done():
                self.window_timers[session_id].cancel()
            asyncio.create_task(self._close_window(session_id, session))

        return None

    async def _window_countdown(self, session_id: str, session: GameSession) -> None:
        for remaining in range(ACTION_WINDOW_SECONDS, 0, -1):
            await asyncio.sleep(1)
            if remaining % 3 == 0 or remaining <= 3:
                if self._broadcast:
                    await self._broadcast(session_id, {
                        "type": "action_window",
                        "data": {
                            "status": "countdown",
                            "seconds_remaining": remaining,
                            "submitted_count": len(self.submitted.get(session_id, set())),
                            "total_players": len([p for p in session.players if p.hp > 0]),
                        },
                    })
        await self._close_window(session_id, session)

    async def _close_window(self, session_id: str, session: GameSession) -> None:
        actions = self.pending_actions.pop(session_id, [])
        self.submitted.pop(session_id, None)
        if session_id in self.window_timers:
            del self.window_timers[session_id]

        if not actions:
            return

        self.is_processing[session_id] = True

        if self._broadcast:
            await self._broadcast(session_id, {
                "type": "action_window",
                "data": {"status": "closed"},
            })

        if len(actions) == 1:
            char_name, text = actions[0]
            combined = text
            speaker = char_name
        else:
            parts = [f"{name}: {text}" for name, text in actions]
            combined = "Multiple players act simultaneously:\n" + "\n".join(parts)
            speaker = "Party"

        if self._process_batch:
            await self._process_batch(session_id, session, combined, speaker)

        self.is_processing[session_id] = False

        if self._broadcast:
            await self._broadcast(session_id, {
                "type": "action_window",
                "data": {
                    "status": "open",
                    "seconds_remaining": ACTION_WINDOW_SECONDS,
                    "submitted_count": 0,
                    "total_players": len([p for p in session.players if p.hp > 0]),
                },
            })

    def finish_combat_action(self, session_id: str) -> None:
        self.is_processing[session_id] = False


action_window = ActionWindow()
