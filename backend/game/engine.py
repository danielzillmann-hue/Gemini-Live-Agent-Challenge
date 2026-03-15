"""Core game engine — manages state transitions, combat, dice, and session lifecycle."""

from __future__ import annotations

import random
from typing import Any

from game.models import (
    AbilityScores,
    Achievement,
    Character,
    CharacterClass,
    CharacterRace,
    CombatAction,
    Combatant,
    CombatPhase,
    CombatState,
    Consequence,
    DramaLevel,
    Faction,
    GameSession,
    Item,
    ItemRarity,
    Location,
    LoreEntry,
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
        # Keep only alive combatants
        combat.combatants = [c for c in combat.combatants if c.hp > 0]

        if not combat.combatants:
            combat.is_active = False
            combat.phase = CombatPhase.ENDED
            return None

        # Check victory/defeat conditions
        players_alive = any(c.is_player for c in combat.combatants)
        enemies_alive = any(not c.is_player for c in combat.combatants)
        if not players_alive or not enemies_alive:
            combat.is_active = False
            combat.phase = CombatPhase.ENDED
            return None

        # Advance turn safely
        combat.current_turn_index = (combat.current_turn_index + 1) % len(combat.combatants)
        if combat.current_turn_index == 0:
            combat.round_number += 1

        current = combat.combatants[combat.current_turn_index]
        combat.phase = CombatPhase.PLAYER_TURN if current.is_player else CombatPhase.ENEMY_TURN
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

    def award_xp(self, session_id: str, xp: int) -> list[dict[str, Any]]:
        """Award XP to all alive players. Returns level-up info for any who leveled."""
        session = self.get_session(session_id)
        if not session:
            return []
        level_ups = []
        for p in session.get_alive_players():
            leveled = p.add_xp(xp)
            if leveled:
                changes = p.level_up()
                if changes:
                    level_ups.append({"character": p.name, **changes})
        return level_ups

    def grant_achievement(
        self, session_id: str, character_name: str, title: str, description: str = "", icon: str = ""
    ) -> Achievement | None:
        """Grant an achievement to a character."""
        session = self.get_session(session_id)
        if not session:
            return None
        for p in session.players:
            if p.name.lower() == character_name.lower():
                # Don't duplicate
                if any(a.title == title for a in p.achievements):
                    return None
                achievement = Achievement(
                    title=title, description=description, icon=icon, earned_by=character_name,
                )
                p.achievements.append(achievement)
                return achievement
        return None

    def check_achievements(self, session: GameSession) -> list[Achievement]:
        """Check and award automatic achievements based on stats."""
        new_achievements = []
        for p in session.players:
            checks = [
                (p.kills >= 1, "First Blood", "Defeated your first enemy", "🗡️"),
                (p.kills >= 10, "Slayer", "Defeated 10 enemies", "⚔️"),
                (p.kills >= 50, "Legend of War", "Defeated 50 enemies", "🏆"),
                (p.crits >= 1, "Lucky Strike", "Rolled your first critical hit", "🎯"),
                (p.crits >= 10, "Fortune's Favorite", "10 critical hits", "✨"),
                (p.quests_completed >= 1, "Adventurer", "Completed your first quest", "📜"),
                (p.quests_completed >= 5, "Questmaster", "Completed 5 quests", "🏅"),
                (p.level >= 5, "Seasoned", "Reached level 5", "⭐"),
                (p.level >= 10, "Veteran", "Reached level 10", "🌟"),
                (p.deaths >= 1, "Death Defier", "Returned from death", "💀"),
            ]
            for condition, title, desc, icon in checks:
                if condition and not any(a.title == title for a in p.achievements):
                    a = Achievement(title=title, description=desc, icon=icon, earned_by=p.name)
                    p.achievements.append(a)
                    new_achievements.append(a)
        return new_achievements

    def add_faction(self, session_id: str, faction: Faction) -> bool:
        session = self.get_session(session_id)
        if not session:
            return False
        session.world.factions[faction.id] = faction
        return True

    def add_lore_entry(self, session_id: str, entry: LoreEntry) -> bool:
        session = self.get_session(session_id)
        if not session:
            return False
        session.world.lorebook.append(entry)
        return True

    def generate_session_recap(self, session: GameSession) -> str:
        """Generate a recap of the session so far."""
        events = session.get_recent_events(30)
        if not events:
            return "The adventure has just begun."

        recap_parts = []
        for e in events:
            if e.event_type in ("narration", "player_action") and e.content:
                recap_parts.append(e.content[:100])

        player_status = ", ".join(
            f"{p.name} (Lvl {p.level}, {p.hp}/{p.max_hp} HP)"
            for p in session.players
        )
        active_quests = ", ".join(
            q.title for q in session.world.quests if q.is_active and not q.is_complete
        )

        return (
            f"Session recap for {session.world.campaign_name}:\n"
            f"Party: {player_status}\n"
            f"Location: {session.world.current_location_id}\n"
            f"Day {session.world.day_count}, {session.world.time_of_day}\n"
            f"Active quests: {active_quests or 'None'}\n"
            f"Recent events: {' | '.join(recap_parts[-10:])}"
        )

    def get_context_summary(self, session: GameSession) -> dict[str, Any]:
        """Build a comprehensive context summary for the AI agents."""
        recent = session.get_recent_events(15)

        # Find relevant lore based on recent events
        recent_text = " ".join(e.content for e in recent if e.content)
        relevant_lore = session.world.find_lore(recent_text)

        # NPC memory summaries for NPCs in current location
        npc_context = []
        for n in session.world.npcs.values():
            if n.location == session.world.current_location_id:
                npc_context.append({
                    "name": n.name,
                    "relationship": n.relationship,
                    "personality": n.personality,
                    "voice_style": n.voice_style,
                    "faction": n.faction,
                    "memories": n.get_memory_summary(),
                })

        # Active consequences
        active_consequences = [
            {"trigger": c.trigger_event, "effect": c.effect, "severity": c.severity}
            for c in session.world.consequences
            if not c.resolved
        ][-5:]

        # Faction standings
        faction_info = [
            {
                "name": f.name,
                "reputation": {k: v for k, v in f.reputation.items()},
                "description": f.description[:100],
            }
            for f in session.world.factions.values()
        ]

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
                    "xp": p.xp,
                    "xp_to_next": p.xp_to_next_level,
                    "conditions": p.conditions,
                    "backstory": p.backstory[:200] if p.backstory else "",
                    "personality": p.personality[:100] if p.personality else "",
                    "inventory_summary": [i.name for i in p.inventory[:5]],
                    "spells": [s.name for s in p.spells],
                }
                for p in session.players
            ],
            "npcs_present": npc_context,
            "active_quests": [
                {"title": q.title, "objectives": q.objectives, "description": q.description}
                for q in session.world.quests
                if q.is_active and not q.is_complete
            ],
            "factions": faction_info,
            "active_consequences": active_consequences,
            "relevant_lore": [
                {"title": l.title, "content": l.content[:200]}
                for l in relevant_lore[:3]
            ],
            "story_beat": session.story_beat.value,
            "combat_active": session.combat.is_active,
            "recent_events": [
                {"type": e.event_type, "content": e.content[:200]}
                for e in recent
            ],
            "drama_level": self.calculate_drama_level(session),
            "style_sheet": session.style_sheet,
            "weather_effects": _get_weather_effects(session.world.weather),
        }


def _get_weather_effects(weather: str) -> dict[str, Any]:
    """Get mechanical effects of current weather."""
    effects = {
        "clear": {"combat_modifier": 0, "description": "No weather effects"},
        "rain": {"combat_modifier": -1, "description": "Disadvantage on ranged attacks, fire damage halved"},
        "fog": {"combat_modifier": -2, "description": "Heavily obscured beyond 30ft, disadvantage on Perception"},
        "snow": {"combat_modifier": -1, "description": "Difficult terrain, cold damage +1d4"},
        "storm": {"combat_modifier": -3, "description": "Disadvantage on ranged & Perception, lightning risk"},
    }
    return effects.get(weather, effects["clear"])


# Singleton
game_engine = GameEngine()
