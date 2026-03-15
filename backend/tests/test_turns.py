"""Tests for the ActionWindow multiplayer turn system."""

import asyncio
import pytest
from game.engine import create_character
from game.models import CharacterRace, CharacterClass, GameSession, WorldState, CombatState
from handlers.turns import ActionWindow


def _make_session(num_players=2) -> GameSession:
    session = GameSession(world=WorldState(campaign_name="Test"))
    for i in range(num_players):
        char = create_character(f"Player{i}", CharacterRace.HUMAN, CharacterClass.WARRIOR)
        session.players.append(char)
    return session


class TestActionWindowExploration:
    @pytest.mark.asyncio
    async def test_single_player_not_queued(self):
        """Single player actions should not be queued."""
        window = ActionWindow()
        session = _make_session(1)
        # Single player should not use action window at all
        # (This is handled in main.py, not ActionWindow)
        assert not window.is_busy(session.id)

    @pytest.mark.asyncio
    async def test_submit_action_accepted(self):
        window = ActionWindow()
        broadcasts = []

        async def mock_broadcast(sid, msg):
            broadcasts.append(msg)

        async def mock_process(sid, s, text, speaker):
            pass

        window.set_callbacks(mock_broadcast, mock_process)
        session = _make_session(2)
        error = await window.submit_action(session.id, session, "Player0", "I search the room")
        assert error is None

    @pytest.mark.asyncio
    async def test_duplicate_action_rejected(self):
        window = ActionWindow()
        broadcasts = []

        async def mock_broadcast(sid, msg):
            broadcasts.append(msg)

        async def mock_process(sid, s, t, sp):
            pass

        window.set_callbacks(mock_broadcast, mock_process)
        session = _make_session(2)

        await window.submit_action(session.id, session, "Player0", "I search")
        error = await window.submit_action(session.id, session, "Player0", "I search again")
        assert error is not None
        assert "already submitted" in error.lower()

    @pytest.mark.asyncio
    async def test_busy_during_processing(self):
        window = ActionWindow()

        async def mock_broadcast(sid, msg):
            pass

        async def mock_process(sid, s, t, sp):
            pass

        window.set_callbacks(mock_broadcast, mock_process)
        window.is_processing["test"] = True
        session = _make_session(2)
        session.id = "test"
        error = await window.submit_action("test", session, "Player0", "action")
        assert error is not None
        assert "still narrating" in error.lower()


class TestActionWindowCombat:
    @pytest.mark.asyncio
    async def test_combat_wrong_turn_rejected(self):
        window = ActionWindow()

        async def noop(*a):
            pass

        window.set_callbacks(noop, noop)
        session = _make_session(2)
        # Simulate active combat with Player1's turn
        from game.models import Combatant, CombatPhase
        session.combat = CombatState(
            is_active=True, round_number=1, phase=CombatPhase.PLAYER_TURN,
            combatants=[
                Combatant(id="p1", name="Player1", initiative=15, is_player=True),
                Combatant(id="p0", name="Player0", initiative=10, is_player=True),
            ],
            current_turn_index=0,
        )
        error = await window.submit_action(session.id, session, "Player0", "I attack")
        assert error is not None
        assert "Player1" in error

    @pytest.mark.asyncio
    async def test_combat_correct_turn_accepted(self):
        window = ActionWindow()

        async def noop(*a):
            pass

        window.set_callbacks(noop, noop)
        session = _make_session(2)
        from game.models import Combatant, CombatPhase
        session.combat = CombatState(
            is_active=True, round_number=1, phase=CombatPhase.PLAYER_TURN,
            combatants=[
                Combatant(id="p0", name="Player0", initiative=15, is_player=True),
                Combatant(id="p1", name="Player1", initiative=10, is_player=True),
            ],
            current_turn_index=0,
        )
        error = await window.submit_action(session.id, session, "Player0", "I attack")
        assert error is None
