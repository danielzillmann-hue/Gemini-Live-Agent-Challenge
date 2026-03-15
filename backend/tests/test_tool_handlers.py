"""Unit tests for tool handlers — verify each handler produces correct state changes and messages."""

import pytest
from game.engine import GameEngine, create_character
from game.models import (
    CharacterRace, CharacterClass, NPC, Quest, Faction, GameSession,
)
from agents.tool_handlers import (
    handle_narrate_scene, handle_roll_check, handle_update_quest,
    handle_update_world, handle_award_xp, handle_generate_loot,
    handle_npc_memory, handle_consequence, handle_faction_reputation,
    handle_add_lore, handle_create_npc, handle_change_location,
    TOOL_HANDLERS,
)


@pytest.fixture
def engine():
    """Use the global game_engine singleton so tool handlers can see sessions."""
    from game.engine import game_engine
    # Clear any existing sessions
    game_engine.sessions.clear()
    return game_engine


@pytest.fixture
def session(engine):
    s = engine.create_session("Test", "Dark fantasy")
    char = create_character("Hero", CharacterRace.HUMAN, CharacterClass.WARRIOR)
    engine.add_player(s.id, char)
    return s


class TestNarrateScene:
    @pytest.mark.asyncio
    async def test_emits_narration(self, session):
        msgs = await handle_narrate_scene("test", {"scene": "A dark cave"}, session)
        assert len(msgs) == 1
        assert msgs[0]["type"] == "narration"
        assert msgs[0]["data"]["content"] == "A dark cave"

    @pytest.mark.asyncio
    async def test_empty_scene(self, session):
        msgs = await handle_narrate_scene("test", {}, session)
        assert len(msgs) == 0


class TestRollCheck:
    @pytest.mark.asyncio
    async def test_emits_dice_result(self, session):
        msgs = await handle_roll_check("test", {
            "character": "Hero", "ability": "strength",
            "roll": 15, "success": True,
        }, session)
        assert len(msgs) == 1
        assert msgs[0]["type"] == "dice_result"

    @pytest.mark.asyncio
    async def test_failed_roll_with_damage(self, session):
        old_hp = session.players[0].hp
        msgs = await handle_roll_check("test", {
            "character": "Hero", "success": False, "damage": 5,
        }, session)
        assert session.players[0].hp == old_hp - 5

    @pytest.mark.asyncio
    async def test_failed_roll_no_damage(self, session):
        old_hp = session.players[0].hp
        msgs = await handle_roll_check("test", {
            "character": "Hero", "success": False,
        }, session)
        assert session.players[0].hp == old_hp


class TestUpdateQuest:
    @pytest.mark.asyncio
    async def test_create_new_quest(self, session):
        msgs = await handle_update_quest(session.id, {
            "quest": "Find the sword", "update": "new", "details": "Go to the cave",
        }, session)
        assert len(session.world.quests) == 1
        assert session.world.quests[0].title == "Find the sword"

    @pytest.mark.asyncio
    async def test_complete_quest(self, engine, session):
        quest = Quest(title="Test Quest", reward_xp=100, reward_gold=50, is_active=True)
        engine.add_quest(session.id, quest)

        old_xp = session.players[0].xp
        old_gold = session.players[0].gold

        msgs = await handle_update_quest(session.id, {
            "quest": "Test Quest", "update": "complete",
        }, session)

        assert quest.is_complete
        assert not quest.is_active
        assert session.players[0].xp == old_xp + 100
        assert session.players[0].gold == old_gold + 50

    @pytest.mark.asyncio
    async def test_progress_quest(self, engine, session):
        quest = Quest(title="Multi Step", objectives=["Step 1", "Step 2", "Step 3"])
        engine.add_quest(session.id, quest)

        await handle_update_quest(session.id, {
            "quest": "Multi Step", "update": "progress", "details": "Done step 1",
        }, session)
        assert 0 in quest.completed_objectives
        assert 1 not in quest.completed_objectives


class TestAwardXP:
    @pytest.mark.asyncio
    async def test_awards_xp(self, engine, session):
        msgs = await handle_award_xp(session.id, {"xp": 100, "reason": "combat"}, session)
        assert msgs[0]["type"] == "xp_awarded"
        assert msgs[0]["data"]["xp"] == 100
        assert session.players[0].xp == 100

    @pytest.mark.asyncio
    async def test_level_up_on_xp(self, engine, session):
        msgs = await handle_award_xp(session.id, {"xp": 300}, session)
        assert any(m["type"] == "xp_awarded" for m in msgs)
        level_ups = msgs[0]["data"]["level_ups"]
        assert len(level_ups) == 1
        assert level_ups[0]["new_level"] == 2

    @pytest.mark.asyncio
    async def test_achievement_on_kill(self, engine, session):
        session.players[0].kills = 1
        msgs = await handle_award_xp(session.id, {"xp": 50}, session)
        achievements = [m for m in msgs if m["type"] == "achievement"]
        assert len(achievements) >= 1
        assert achievements[0]["data"]["title"] == "First Blood"


class TestGenerateLoot:
    @pytest.mark.asyncio
    async def test_creates_item(self, session):
        msgs = await handle_generate_loot("test", {
            "name": "Flame Sword", "type": "weapon", "rarity": "rare",
            "description": "Burns with eternal fire", "damage": "2d6",
        }, session)
        assert msgs[0]["type"] == "loot_found"
        assert msgs[0]["data"]["item"]["name"] == "Flame Sword"
        # Item added to first player's inventory
        assert any(i.name == "Flame Sword" for i in session.players[0].inventory)


class TestNPCMemory:
    @pytest.mark.asyncio
    async def test_records_memory(self, engine, session):
        npc = NPC(name="Bartender")
        engine.add_npc(session.id, npc)

        await handle_npc_memory(session.id, {
            "npc_name": "Bartender", "event": "Hero bought a drink",
            "sentiment": 5, "character": "Hero",
        }, session)

        bart = list(session.world.npcs.values())[0]
        assert len(bart.memories) == 1
        assert bart.relationship == 5


class TestConsequence:
    @pytest.mark.asyncio
    async def test_adds_consequence(self, session):
        msgs = await handle_consequence("test", {
            "trigger": "Burned the village", "effect": "Refugees flee", "severity": 7,
        }, session)
        assert len(session.world.consequences) == 1
        assert msgs[0]["type"] == "consequence"
        assert msgs[0]["data"]["severity"] == 7


class TestFactionReputation:
    @pytest.mark.asyncio
    async def test_adjusts_reputation(self, engine, session):
        faction = Faction(name="Thieves Guild")
        engine.add_faction(session.id, faction)

        msgs = await handle_faction_reputation(session.id, {
            "faction": "Thieves Guild", "character": "Hero",
            "change": 20, "reason": "Helped a thief",
        }, session)

        assert msgs[0]["type"] == "faction_update"
        assert msgs[0]["data"]["new_reputation"] == 20


class TestAddLore:
    @pytest.mark.asyncio
    async def test_adds_lore_entry(self, engine, session):
        msgs = await handle_add_lore(session.id, {
            "title": "The Old Gods", "content": "Ancient beings of chaos",
            "keywords": ["old gods", "ancient", "chaos"], "category": "world",
        }, session)
        assert len(session.world.lorebook) == 1
        assert session.world.lorebook[0].title == "The Old Gods"


class TestUpdateWorld:
    @pytest.mark.asyncio
    async def test_updates_time(self, session):
        msgs = await handle_update_world("test", {"time_of_day": "night"}, session)
        assert session.world.time_of_day == "night"
        assert msgs[0]["data"]["time_of_day"] == "night"

    @pytest.mark.asyncio
    async def test_advances_day(self, session):
        old_day = session.world.day_count
        await handle_update_world("test", {"advance_day": True}, session)
        assert session.world.day_count == old_day + 1

    @pytest.mark.asyncio
    async def test_changes_weather(self, session):
        await handle_update_world("test", {"weather": "storm"}, session)
        assert session.world.weather == "storm"


class TestHandlerRegistry:
    def test_all_handlers_registered(self):
        expected = [
            "narrate_scene", "roll_check", "start_combat", "combat_action",
            "create_npc", "change_location", "quest_update", "world_update",
            "music_change", "award_xp", "generate_loot", "npc_memory",
            "add_consequence", "faction_reputation", "add_lore",
            "generate_image", "generate_video",
        ]
        for name in expected:
            assert name in TOOL_HANDLERS, f"Handler missing for tool: {name}"

    def test_no_none_handlers(self):
        for name, handler in TOOL_HANDLERS.items():
            assert handler is not None, f"Handler is None for: {name}"
            assert callable(handler), f"Handler not callable for: {name}"
