"""Unit tests for the game engine — dice, combat, leveling, achievements."""

import pytest
from game.engine import (
    roll_dice, roll_d20, roll_ability_scores, create_character,
    CombatEngine, GameEngine,
)
from game.models import (
    Character, CharacterClass, CharacterRace, Combatant,
    CombatState, CombatPhase, NPC, Quest, Location,
    Faction, LoreEntry, Achievement,
)


# ── Dice ──────────────────────────────────────────────────────────────────

class TestDice:
    def test_roll_d20_range(self):
        for _ in range(100):
            total, raw = roll_d20()
            assert 1 <= raw <= 20
            assert total == raw  # No modifier

    def test_roll_d20_with_modifier(self):
        for _ in range(50):
            total, raw = roll_d20(5)
            assert total == raw + 5

    def test_roll_dice_simple(self):
        for _ in range(50):
            total, rolls = roll_dice("1d6")
            assert 1 <= total <= 6
            assert len(rolls) == 1

    def test_roll_dice_multiple(self):
        for _ in range(50):
            total, rolls = roll_dice("3d6")
            assert 3 <= total <= 18
            assert len(rolls) == 3

    def test_roll_dice_with_bonus(self):
        total, rolls = roll_dice("1d6+3")
        assert 4 <= total <= 9

    def test_roll_dice_with_negative(self):
        total, rolls = roll_dice("1d6-1")
        assert 0 <= total <= 5

    def test_roll_ability_scores(self):
        scores = roll_ability_scores()
        for attr in ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]:
            val = getattr(scores, attr)
            assert 3 <= val <= 18  # 4d6 drop lowest


# ── Character Creation ────────────────────────────────────────────────────

class TestCharacterCreation:
    def test_create_basic_character(self):
        char = create_character("Kira", CharacterRace.ELF, CharacterClass.RANGER)
        assert char.name == "Kira"
        assert char.race == CharacterRace.ELF
        assert char.character_class == CharacterClass.RANGER
        assert char.level == 1
        assert char.hp > 0
        assert char.max_hp == char.hp
        assert len(char.inventory) > 0  # Starter items

    def test_create_character_with_backstory(self):
        char = create_character(
            "Thane", CharacterRace.DWARF, CharacterClass.WARRIOR,
            backstory="Former blacksmith", personality="Gruff but loyal",
        )
        assert char.backstory == "Former blacksmith"
        assert char.personality == "Gruff but loyal"

    def test_class_starter_items(self):
        mage = create_character("Zeph", CharacterRace.HUMAN, CharacterClass.MAGE)
        item_names = [i.name for i in mage.inventory]
        assert "Quarterstaff" in item_names or "Spellbook" in item_names

        warrior = create_character("Tank", CharacterRace.ORC, CharacterClass.WARRIOR)
        item_names = [i.name for i in warrior.inventory]
        assert "Longsword" in item_names


# ── Character Progression ─────────────────────────────────────────────────

class TestProgression:
    def test_xp_threshold(self):
        char = create_character("Test", CharacterRace.HUMAN, CharacterClass.WARRIOR)
        assert char.level == 1
        assert char.xp_to_next_level == 300

    def test_add_xp_no_level(self):
        char = create_character("Test", CharacterRace.HUMAN, CharacterClass.WARRIOR)
        leveled = char.add_xp(100)
        assert not leveled
        assert char.xp == 100

    def test_add_xp_level_up(self):
        char = create_character("Test", CharacterRace.HUMAN, CharacterClass.WARRIOR)
        char.add_xp(300)
        assert char.can_level_up
        changes = char.level_up()
        assert changes["new_level"] == 2
        assert char.level == 2
        assert char.hp == char.max_hp  # Full heal

    def test_level_up_hp_increase(self):
        char = create_character("Test", CharacterRace.HUMAN, CharacterClass.MAGE)
        old_max = char.max_hp
        char.add_xp(300)
        char.level_up()
        assert char.max_hp > old_max  # Mage gets d6 + CON

    def test_max_level(self):
        char = create_character("Test", CharacterRace.HUMAN, CharacterClass.WARRIOR)
        char.level = 20
        char.xp = 999999
        assert not char.can_level_up
        assert char.xp_to_next_level == 0


# ── Combat ────────────────────────────────────────────────────────────────

class TestCombat:
    def _make_combatant(self, name, hp=20, ac=10, is_player=True):
        return Combatant(id=name, name=name, hp=hp, max_hp=hp, armor_class=ac, is_player=is_player)

    def test_start_combat(self):
        players = [create_character("Hero", CharacterRace.HUMAN, CharacterClass.WARRIOR)]
        enemies = [NPC(name="Goblin", hp=10, max_hp=10, armor_class=8)]
        state = CombatEngine.start_combat(players, enemies)
        assert state.is_active
        assert state.round_number == 1
        assert len(state.combatants) == 2

    def test_initiative_order(self):
        players = [create_character("A", CharacterRace.HUMAN, CharacterClass.WARRIOR)]
        enemies = [NPC(name="B", hp=10, max_hp=10)]
        state = CombatEngine.start_combat(players, enemies)
        # Combatants sorted by initiative (descending)
        initiatives = [c.initiative for c in state.combatants]
        assert initiatives == sorted(initiatives, reverse=True)

    def test_resolve_attack_hit(self):
        attacker = self._make_combatant("Attacker")
        defender = self._make_combatant("Defender", ac=5)  # Easy to hit
        # Run multiple times to get at least one hit
        hits = 0
        for _ in range(20):
            defender.hp = 20
            result = CombatEngine.resolve_attack(attacker, defender)
            if not result.is_miss:
                hits += 1
                assert result.damage > 0
                assert defender.hp < 20
        assert hits > 0  # Should hit at least once with AC 5

    def test_resolve_attack_critical(self):
        attacker = self._make_combatant("Attacker")
        defender = self._make_combatant("Defender")
        # Brute force to find a crit (1/20 chance per roll)
        crits = 0
        for _ in range(200):
            defender.hp = 20
            result = CombatEngine.resolve_attack(attacker, defender)
            if result.is_critical:
                crits += 1
                assert result.damage > 0  # Crits always deal damage
        # Statistically should get at least 1 crit in 200 rolls
        assert crits > 0

    def test_next_turn_advances(self):
        players = [create_character("A", CharacterRace.HUMAN, CharacterClass.WARRIOR)]
        enemies = [NPC(name="B", hp=10, max_hp=10)]
        state = CombatEngine.start_combat(players, enemies)
        first_idx = state.current_turn_index
        CombatEngine.next_turn(state)
        assert state.current_turn_index != first_idx or len(state.combatants) == 1

    def test_combat_ends_when_enemies_die(self):
        state = CombatState(
            is_active=True, round_number=1, phase=CombatPhase.PLAYER_TURN,
            combatants=[
                self._make_combatant("Hero", hp=20, is_player=True),
                self._make_combatant("Goblin", hp=0, is_player=False),
            ],
        )
        CombatEngine.next_turn(state)
        assert not state.is_active
        assert state.phase == CombatPhase.ENDED

    def test_combat_ends_when_players_die(self):
        state = CombatState(
            is_active=True, round_number=1, phase=CombatPhase.PLAYER_TURN,
            combatants=[
                self._make_combatant("Hero", hp=0, is_player=True),
                self._make_combatant("Goblin", hp=10, is_player=False),
            ],
        )
        CombatEngine.next_turn(state)
        assert not state.is_active

    def test_empty_combatants(self):
        state = CombatState(is_active=True, combatants=[])
        result = CombatEngine.next_turn(state)
        assert result is None
        assert not state.is_active


# ── Game Engine ───────────────────────────────────────────────────────────

class TestGameEngine:
    def setup_method(self):
        self.engine = GameEngine()

    def test_create_session(self):
        session = self.engine.create_session("Test Campaign", "A dark world")
        assert session.world.campaign_name == "Test Campaign"
        assert session.id in self.engine.sessions

    def test_add_player(self):
        session = self.engine.create_session("Test", "Test")
        char = create_character("Hero", CharacterRace.HUMAN, CharacterClass.WARRIOR)
        assert self.engine.add_player(session.id, char)
        assert len(session.players) == 1

    def test_add_location(self):
        session = self.engine.create_session("Test", "Test")
        loc = Location(name="Tavern", description="A cozy tavern", location_type="tavern")
        assert self.engine.add_location(session.id, loc)
        assert loc.id in session.world.locations

    def test_move_to_location(self):
        session = self.engine.create_session("Test", "Test")
        loc = Location(name="Tavern")
        self.engine.add_location(session.id, loc)
        result = self.engine.move_to_location(session.id, loc.id)
        assert result is not None
        assert result.visited
        assert session.world.current_location_id == loc.id

    def test_award_xp(self):
        session = self.engine.create_session("Test", "Test")
        char = create_character("Hero", CharacterRace.HUMAN, CharacterClass.WARRIOR)
        self.engine.add_player(session.id, char)
        level_ups = self.engine.award_xp(session.id, 300)
        assert len(level_ups) == 1
        assert level_ups[0]["new_level"] == 2

    def test_achievements(self):
        session = self.engine.create_session("Test", "Test")
        char = create_character("Hero", CharacterRace.HUMAN, CharacterClass.WARRIOR)
        char.kills = 1
        self.engine.add_player(session.id, char)
        achievements = self.engine.check_achievements(session)
        titles = [a.title for a in achievements]
        assert "First Blood" in titles

    def test_no_duplicate_achievements(self):
        session = self.engine.create_session("Test", "Test")
        char = create_character("Hero", CharacterRace.HUMAN, CharacterClass.WARRIOR)
        char.kills = 1
        self.engine.add_player(session.id, char)
        first = self.engine.check_achievements(session)
        second = self.engine.check_achievements(session)
        assert len(first) > 0
        assert len(second) == 0  # No duplicates

    def test_add_quest(self):
        session = self.engine.create_session("Test", "Test")
        quest = Quest(title="Find the sword", objectives=["Go to cave", "Defeat dragon"])
        self.engine.add_quest(session.id, quest)
        assert len(session.world.quests) == 1

    def test_add_faction(self):
        session = self.engine.create_session("Test", "Test")
        faction = Faction(name="Thieves Guild", description="A shadowy organization")
        self.engine.add_faction(session.id, faction)
        assert faction.id in session.world.factions

    def test_faction_reputation(self):
        faction = Faction(name="Test")
        faction.adjust_reputation("Hero", 25)
        assert faction.get_reputation("Hero") == 25
        faction.adjust_reputation("Hero", -50)
        assert faction.get_reputation("Hero") == -25
        # Bounds check
        faction.adjust_reputation("Hero", -200)
        assert faction.get_reputation("Hero") == -100

    def test_lore_entry(self):
        session = self.engine.create_session("Test", "Test")
        entry = LoreEntry(title="The Dark Pact", content="An ancient evil", keywords=["dark", "pact"])
        self.engine.add_lore_entry(session.id, entry)
        found = session.world.find_lore("The dark ritual begins")
        assert len(found) == 1
        assert found[0].title == "The Dark Pact"

    def test_lore_no_match(self):
        session = self.engine.create_session("Test", "Test")
        entry = LoreEntry(title="Dragons", content="Fire breathers", keywords=["dragon"])
        self.engine.add_lore_entry(session.id, entry)
        found = session.world.find_lore("The tavern is cozy")
        assert len(found) == 0

    def test_consequence(self):
        session = self.engine.create_session("Test", "Test")
        c = session.world.add_consequence("Burned village", "Refugees flee to capital", severity=7)
        assert c.trigger_event == "Burned village"
        assert len(session.world.consequences) == 1

    def test_npc_memory(self):
        npc = NPC(name="Bartender")
        npc.add_memory("Hero bought a drink", sentiment=5, character="Hero")
        assert len(npc.memories) == 1
        assert npc.relationship == 5
        npc.add_memory("Hero started a fight", sentiment=-10, character="Hero")
        assert npc.relationship == -5
        summary = npc.get_memory_summary()
        assert "bought a drink" in summary

    def test_session_recap(self):
        session = self.engine.create_session("Epic Quest", "A dark world")
        char = create_character("Hero", CharacterRace.HUMAN, CharacterClass.WARRIOR)
        self.engine.add_player(session.id, char)
        from game.models import StoryEvent
        session.add_event(StoryEvent(event_type="narration", content="The adventure begins"))
        recap = self.engine.generate_session_recap(session)
        assert "Epic Quest" in recap
        assert "Hero" in recap

    def test_context_summary_complete(self):
        session = self.engine.create_session("Test", "Dark fantasy")
        char = create_character("Hero", CharacterRace.HUMAN, CharacterClass.WARRIOR, backstory="Lost child")
        self.engine.add_player(session.id, char)
        context = self.engine.get_context_summary(session)
        assert context["campaign"] == "Test"
        assert len(context["players"]) == 1
        assert context["players"][0]["backstory"] == "Lost child"
        assert "weather_effects" in context
        assert "relevant_lore" in context
        assert "factions" in context
        assert "active_consequences" in context

    def test_weather_effects(self):
        from game.engine import _get_weather_effects
        clear = _get_weather_effects("clear")
        assert clear["combat_modifier"] == 0
        storm = _get_weather_effects("storm")
        assert storm["combat_modifier"] == -3

    def test_story_events_capped(self):
        session = self.engine.create_session("Test", "Test")
        from game.models import StoryEvent
        for i in range(600):
            session.add_event(StoryEvent(event_type="narration", content=f"Event {i}"))
        assert len(session.story_events) == 500


# ── Model Serialization ──────────────────────────────────────────────────

class TestModels:
    def test_character_serialization(self):
        char = create_character("Test", CharacterRace.ELF, CharacterClass.MAGE)
        data = char.model_dump(mode="json")
        assert data["name"] == "Test"
        assert data["race"] == "elf"
        loaded = Character.model_validate(data)
        assert loaded.name == "Test"

    def test_game_session_serialization(self):
        engine = GameEngine()
        session = engine.create_session("Test", "Fantasy")
        char = create_character("Hero", CharacterRace.HUMAN, CharacterClass.WARRIOR)
        engine.add_player(session.id, char)
        data = session.model_dump(mode="json")
        assert data["world"]["campaign_name"] == "Test"
        # Round-trip
        from game.models import GameSession
        loaded = GameSession.model_validate(data)
        assert loaded.players[0].name == "Hero"
