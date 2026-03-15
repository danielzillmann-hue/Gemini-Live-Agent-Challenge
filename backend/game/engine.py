"""Core game engine — manages state transitions, combat, dice, and session lifecycle."""

from __future__ import annotations

import random
from typing import Any

from game.models import (
    AbilityScores,
    Character,
    CharacterClass,
    CharacterRace,
    CombatAction,
    Combatant,
    CombatPhase,
    CombatState,
    DramaLevel,
    GameSession,
    Item,
    Location,
    NPC,
    Quest,
    StoryBeat,
    StoryEvent,
    WorldState,
)


# ── Dice ───────────────────────────────────────────────────────────────────

def roll_dice(notation: str) -> tuple[int, list[int]]:
    """Roll dice in NdM+B notation. Returns (total, individual_rolls)."""
    notation = notation.strip().lower()
    bonus = 0
    if "+" in notation:
        notation, bonus_str = notation.split("+", 1)
        bonus = int(bonus_str.strip())
    elif "-" in notation:
        parts = notation.split("-", 1)
        notation = parts[0]
        bonus = -int(parts[1].strip())

    if "d" not in notation:
        return int(notation) + bonus, [int(notation)]

    count_str, sides_str = notation.split("d", 1)
    count = int(count_str) if count_str else 1
    sides = int(sides_str)

    rolls = [random.randint(1, sides) for _ in range(count)]
    return sum(rolls) + bonus, rolls


def roll_d20(modifier: int = 0) -> tuple[int, int]:
    """Roll a d20 with modifier. Returns (total, raw_roll)."""
    raw = random.randint(1, 20)
    return raw + modifier, raw


def roll_ability_scores() -> AbilityScores:
    """Roll 4d6 drop lowest for each ability score."""
    scores = {}
    for ability in ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]:
        rolls = sorted([random.randint(1, 6) for _ in range(4)])
        scores[ability] = sum(rolls[1:])  # drop lowest
    return AbilityScores(**scores)


# ── Class Defaults ─────────────────────────────────────────────────────────

CLASS_HP: dict[CharacterClass, int] = {
    CharacterClass.WARRIOR: 12,
    CharacterClass.PALADIN: 11,
    CharacterClass.RANGER: 10,
    CharacterClass.CLERIC: 9,
    CharacterClass.DRUID: 9,
    CharacterClass.MONK: 9,
    CharacterClass.ROGUE: 8,
    CharacterClass.BARD: 8,
    CharacterClass.WARLOCK: 8,
    CharacterClass.MAGE: 6,
}

CLASS_AC: dict[CharacterClass, int] = {
    CharacterClass.WARRIOR: 16,
    CharacterClass.PALADIN: 16,
    CharacterClass.RANGER: 14,
    CharacterClass.CLERIC: 15,
    CharacterClass.DRUID: 12,
    CharacterClass.MONK: 14,
    CharacterClass.ROGUE: 13,
    CharacterClass.BARD: 12,
    CharacterClass.WARLOCK: 12,
    CharacterClass.MAGE: 11,
}

CLASS_STARTER_ITEMS: dict[CharacterClass, list[dict[str, Any]]] = {
    CharacterClass.WARRIOR: [
        {"name": "Longsword", "item_type": "weapon", "properties": {"damage": "1d8", "type": "slashing"}},
        {"name": "Chain Mail", "item_type": "armor", "equipped": True},
        {"name": "Shield", "item_type": "armor", "equipped": True},
    ],
    CharacterClass.MAGE: [
        {"name": "Quarterstaff", "item_type": "weapon", "properties": {"damage": "1d6", "type": "bludgeoning"}},
        {"name": "Spellbook", "item_type": "misc"},
        {"name": "Mana Potion", "item_type": "potion", "quantity": 3},
    ],
    CharacterClass.RANGER: [
        {"name": "Longbow", "item_type": "weapon", "properties": {"damage": "1d8", "type": "piercing", "range": "150ft"}},
        {"name": "Short Sword", "item_type": "weapon", "properties": {"damage": "1d6", "type": "slashing"}},
        {"name": "Leather Armor", "item_type": "armor", "equipped": True},
    ],
    CharacterClass.ROGUE: [
        {"name": "Dagger", "item_type": "weapon", "properties": {"damage": "1d4", "type": "piercing"}, "quantity": 2},
        {"name": "Thieves' Tools", "item_type": "misc"},
        {"name": "Leather Armor", "item_type": "armor", "equipped": True},
    ],
    CharacterClass.PALADIN: [
        {"name": "Warhammer", "item_type": "weapon", "properties": {"damage": "1d8", "type": "bludgeoning"}},
        {"name": "Chain Mail", "item_type": "armor", "equipped": True},
        {"name": "Holy Symbol", "item_type": "misc"},
    ],
    CharacterClass.CLERIC: [
        {"name": "Mace", "item_type": "weapon", "properties": {"damage": "1d6", "type": "bludgeoning"}},
        {"name": "Scale Mail", "item_type": "armor", "equipped": True},
        {"name": "Holy Symbol", "item_type": "misc"},
        {"name": "Healing Potion", "item_type": "potion", "quantity": 2},
    ],
    CharacterClass.BARD: [
        {"name": "Rapier", "item_type": "weapon", "properties": {"damage": "1d8", "type": "piercing"}},
        {"name": "Lute", "item_type": "misc"},
        {"name": "Leather Armor", "item_type": "armor", "equipped": True},
    ],
    CharacterClass.WARLOCK: [
        {"name": "Eldritch Staff", "item_type": "weapon", "properties": {"damage": "1d6", "type": "necrotic"}},
        {"name": "Pact Tome", "item_type": "misc"},
        {"name": "Leather Armor", "item_type": "armor", "equipped": True},
    ],
    CharacterClass.DRUID: [
        {"name": "Scimitar", "item_type": "weapon", "properties": {"damage": "1d6", "type": "slashing"}},
        {"name": "Wooden Shield", "item_type": "armor", "equipped": True},
        {"name": "Herbalism Kit", "item_type": "misc"},
    ],
    CharacterClass.MONK: [
        {"name": "Quarterstaff", "item_type": "weapon", "properties": {"damage": "1d6", "type": "bludgeoning"}},
        {"name": "Dart", "item_type": "weapon", "properties": {"damage": "1d4", "type": "piercing"}, "quantity": 10},
    ],
}


# ── Character Creation ─────────────────────────────────────────────────────

def create_character(
    name: str,
    race: CharacterRace,
    character_class: CharacterClass,
    backstory: str = "",
    personality: str = "",
    appearance: str = "",
) -> Character:
    """Create a new character with rolled stats and class-appropriate equipment."""
    scores = roll_ability_scores()
    base_hp = CLASS_HP.get(character_class, 10)
    hp = base_hp + scores.modifier("constitution")
    ac = CLASS_AC.get(character_class, 10)

    items = [
        Item(**item_data)
        for item_data in CLASS_STARTER_ITEMS.get(character_class, [])
    ]

    return Character(
        name=name,
        race=race,
        character_class=character_class,
        ability_scores=scores,
        hp=hp,
        max_hp=hp,
        armor_class=ac,
        backstory=backstory,
        personality=personality,
        appearance=appearance,
        inventory=items,
    )


# ── Combat Engine ──────────────────────────────────────────────────────────

class CombatEngine:
    """Handles tactical combat mechanics."""

    @staticmethod
    def start_combat(
        players: list[Character], enemies: list[NPC]
    ) -> CombatState:
        combatants: list[Combatant] = []

        for p in players:
            init_total, _ = roll_d20(p.ability_scores.modifier("dexterity"))
            combatants.append(Combatant(
                id=p.id, name=p.name, initiative=init_total,
                hp=p.hp, max_hp=p.max_hp, armor_class=p.armor_class,
                is_player=True, conditions=list(p.conditions),
            ))

        for e in enemies:
            init_total, _ = roll_d20()
            combatants.append(Combatant(
                id=e.id, name=e.name, initiative=init_total,
                hp=e.hp, max_hp=e.max_hp, armor_class=e.armor_class,
                is_player=False,
            ))

        combatants.sort(key=lambda c: c.initiative, reverse=True)

        return CombatState(
            is_active=True,
            round_number=1,
            phase=CombatPhase.PLAYER_TURN,
            combatants=combatants,
            current_turn_index=0,
        )

    @staticmethod
    def resolve_attack(
        attacker: Combatant,
        defender: Combatant,
        weapon_damage: str = "1d8",
        attack_modifier: int = 0,
    ) -> CombatAction:
        total, raw = roll_d20(attack_modifier)
        is_crit = raw == 20
        is_miss = raw == 1 or total < defender.armor_class

        damage = 0
        if not is_miss:
            dmg_total, _ = roll_dice(weapon_damage)
            damage = dmg_total * (2 if is_crit else 1)
            defender.hp = max(0, defender.hp - damage)

        return CombatAction(
            actor_id=attacker.id,
            actor_name=attacker.name,
            action_type="attack",
            target_id=defender.id,
            target_name=defender.name,
            roll=total,
            damage=damage,
            is_critical=is_crit,
            is_miss=is_miss,
        )

    @staticmethod
    def next_turn(combat: CombatState) -> Combatant | None:
        alive = [c for c in combat.combatants if c.hp > 0]
        if not alive:
            combat.is_active = False
            combat.phase = CombatPhase.ENDED
            return None

        combat.combatants = [c for c in combat.combatants if c.hp > 0]

        combat.current_turn_index = (combat.current_turn_index + 1) % len(combat.combatants)
        if combat.current_turn_index == 0:
            combat.round_number += 1

        current = combat.combatants[combat.current_turn_index]
        combat.phase = CombatPhase.PLAYER_TURN if current.is_player else CombatPhase.ENEMY_TURN

        players_alive = any(c.hp > 0 and c.is_player for c in combat.combatants)
        enemies_alive = any(c.hp > 0 and not c.is_player for c in combat.combatants)
        if not players_alive or not enemies_alive:
            combat.is_active = False
            combat.phase = CombatPhase.ENDED

        return current

    @staticmethod
    def get_drama_level(combat: CombatState) -> int:
        if not combat.is_active:
            return 1
        players = [c for c in combat.combatants if c.is_player and c.hp > 0]
        if not players:
            return DramaLevel.CINEMATIC
        avg_hp_pct = sum(c.hp / c.max_hp for c in players) / len(players)
        if avg_hp_pct < 0.2:
            return DramaLevel.CINEMATIC
        if avg_hp_pct < 0.5:
            return DramaLevel.HIGH
        if combat.round_number > 5:
            return DramaLevel.MEDIUM
        return DramaLevel.LOW


# ── Session Management ─────────────────────────────────────────────────────

class GameEngine:
    """Top-level game engine coordinating session state."""

    def __init__(self) -> None:
        self.sessions: dict[str, GameSession] = {}
        self.combat_engine = CombatEngine()

    def create_session(
        self, campaign_name: str = "New Campaign", setting: str = ""
    ) -> GameSession:
        session = GameSession(
            world=WorldState(
                campaign_name=campaign_name,
                setting_description=setting,
            ),
            style_sheet={
                "art_style": "dark fantasy illustration, detailed, dramatic lighting",
                "tone": "epic and immersive with moments of levity",
                "violence_level": "moderate",
            },
        )
        self.sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> GameSession | None:
        return self.sessions.get(session_id)

    def add_player(self, session_id: str, character: Character) -> bool:
        session = self.get_session(session_id)
        if not session:
            return False
        session.players.append(character)
        return True

    def add_location(self, session_id: str, location: Location) -> bool:
        session = self.get_session(session_id)
        if not session:
            return False
        session.world.locations[location.id] = location
        return True

    def move_to_location(self, session_id: str, location_id: str) -> Location | None:
        session = self.get_session(session_id)
        if not session or location_id not in session.world.locations:
            return None
        session.world.current_location_id = location_id
        location = session.world.locations[location_id]
        location.visited = True
        return location

    def add_quest(self, session_id: str, quest: Quest) -> bool:
        session = self.get_session(session_id)
        if not session:
            return False
        session.world.quests.append(quest)
        return True

    def add_npc(self, session_id: str, npc: NPC) -> bool:
        session = self.get_session(session_id)
        if not session:
            return False
        session.world.npcs[npc.id] = npc
        return True

    def start_combat(
        self, session_id: str, enemy_ids: list[str]
    ) -> CombatState | None:
        session = self.get_session(session_id)
        if not session:
            return None
        enemies = [
            session.world.npcs[eid]
            for eid in enemy_ids
            if eid in session.world.npcs
        ]
        if not enemies:
            return None
        session.combat = self.combat_engine.start_combat(
            session.get_alive_players(), enemies
        )
        return session.combat

    def advance_story_beat(self, session_id: str) -> StoryBeat | None:
        session = self.get_session(session_id)
        if not session:
            return None
        order = list(StoryBeat)
        idx = order.index(session.story_beat)
        if idx < len(order) - 1:
            session.story_beat = order[idx + 1]
        return session.story_beat

    def calculate_drama_level(self, session: GameSession) -> int:
        """Determine current drama level for media generation decisions."""
        if session.combat.is_active:
            return self.combat_engine.get_drama_level(session.combat)

        beat_drama = {
            StoryBeat.EXPOSITION: 2,
            StoryBeat.RISING_ACTION: 4,
            StoryBeat.CLIMAX: 8,
            StoryBeat.FALLING_ACTION: 5,
            StoryBeat.RESOLUTION: 3,
        }
        return beat_drama.get(session.story_beat, 3)

    def get_context_summary(self, session: GameSession) -> dict[str, Any]:
        """Build a context summary for the AI agents."""
        recent = session.get_recent_events(15)
        return {
            "campaign": session.world.campaign_name,
            "setting": session.world.setting_description,
            "current_location": session.world.locations.get(
                session.world.current_location_id, {}
            ),
            "time_of_day": session.world.time_of_day,
            "weather": session.world.weather,
            "day": session.world.day_count,
            "players": [
                {
                    "name": p.name,
                    "class": p.character_class.value,
                    "race": p.race.value,
                    "level": p.level,
                    "hp": p.hp,
                    "max_hp": p.max_hp,
                    "conditions": p.conditions,
                }
                for p in session.players
            ],
            "npcs_present": [
                {"name": n.name, "relationship": n.relationship}
                for n in session.world.npcs.values()
                if n.location == session.world.current_location_id
            ],
            "active_quests": [
                {"title": q.title, "objectives": q.objectives}
                for q in session.world.quests
                if q.is_active and not q.is_complete
            ],
            "story_beat": session.story_beat.value,
            "combat_active": session.combat.is_active,
            "recent_events": [
                {"type": e.event_type, "content": e.content[:200]}
                for e in recent
            ],
            "drama_level": self.calculate_drama_level(session),
            "style_sheet": session.style_sheet,
        }


# Singleton
game_engine = GameEngine()
