from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _id() -> str:
    return uuid.uuid4().hex[:12]


# ── Enums ──────────────────────────────────────────────────────────────────

class CharacterClass(str, Enum):
    WARRIOR = "warrior"
    MAGE = "mage"
    RANGER = "ranger"
    ROGUE = "rogue"
    PALADIN = "paladin"
    CLERIC = "cleric"
    BARD = "bard"
    WARLOCK = "warlock"
    DRUID = "druid"
    MONK = "monk"


class CharacterRace(str, Enum):
    HUMAN = "human"
    ELF = "elf"
    DWARF = "dwarf"
    HALFLING = "halfling"
    ORC = "orc"
    TIEFLING = "tiefling"
    DRAGONBORN = "dragonborn"
    GNOME = "gnome"


class DamageType(str, Enum):
    SLASHING = "slashing"
    PIERCING = "piercing"
    BLUDGEONING = "bludgeoning"
    FIRE = "fire"
    ICE = "ice"
    LIGHTNING = "lightning"
    NECROTIC = "necrotic"
    RADIANT = "radiant"
    PSYCHIC = "psychic"
    POISON = "poison"


class CombatPhase(str, Enum):
    INITIATIVE = "initiative"
    PLAYER_TURN = "player_turn"
    ENEMY_TURN = "enemy_turn"
    RESOLUTION = "resolution"
    ENDED = "ended"


class StoryBeat(str, Enum):
    EXPOSITION = "exposition"
    RISING_ACTION = "rising_action"
    CLIMAX = "climax"
    FALLING_ACTION = "falling_action"
    RESOLUTION = "resolution"


class DramaLevel(int, Enum):
    LOW = 1
    MEDIUM = 4
    HIGH = 7
    CINEMATIC = 10


class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


# ── Stats & Items ──────────────────────────────────────────────────────────

class AbilityScores(BaseModel):
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10

    def modifier(self, ability: str) -> int:
        return (getattr(self, ability) - 10) // 2


class ItemRarity(str, Enum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class Item(BaseModel):
    id: str = Field(default_factory=_id)
    name: str
    description: str = ""
    item_type: str = "misc"  # weapon, armor, potion, scroll, misc
    rarity: ItemRarity = ItemRarity.COMMON
    properties: dict[str, Any] = Field(default_factory=dict)
    equipped: bool = False
    quantity: int = 1
    lore: str = ""  # AI-generated backstory for the item
    image_url: str = ""


class Spell(BaseModel):
    name: str
    level: int = 0
    description: str = ""
    damage_type: DamageType | None = None
    damage_dice: str = ""  # e.g. "2d6"
    range: str = "self"
    casting_time: str = "1 action"


# ── Characters ─────────────────────────────────────────────────────────────

XP_THRESHOLDS = [0, 300, 900, 2700, 6500, 14000, 23000, 34000, 48000, 64000,
                  85000, 100000, 120000, 140000, 165000, 195000, 225000, 265000, 305000, 355000]


class Character(BaseModel):
    id: str = Field(default_factory=_id)
    name: str
    race: CharacterRace = CharacterRace.HUMAN
    character_class: CharacterClass = CharacterClass.WARRIOR
    level: int = 1
    xp: int = 0
    hp: int = 20
    max_hp: int = 20
    armor_class: int = 10
    ability_scores: AbilityScores = Field(default_factory=AbilityScores)
    backstory: str = ""
    personality: str = ""
    appearance: str = ""
    portrait_url: str = ""
    portrait_history: list[str] = Field(default_factory=list)  # Evolution of portraits
    inventory: list[Item] = Field(default_factory=list)
    spells: list[Spell] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    gold: int = 50
    achievements: list[Achievement] = Field(default_factory=list)
    kills: int = 0
    crits: int = 0
    quests_completed: int = 0
    deaths: int = 0
    is_dead: bool = False  # Permanent death vs unconscious

    @property
    def is_alive(self) -> bool:
        return self.hp > 0 and not self.is_dead

    @property
    def xp_to_next_level(self) -> int:
        if self.level >= 20:
            return 0
        return XP_THRESHOLDS[self.level] - self.xp

    @property
    def can_level_up(self) -> bool:
        if self.level >= 20:
            return False
        return self.xp >= XP_THRESHOLDS[self.level]

    def add_xp(self, amount: int) -> bool:
        """Add XP and return True if level up is available."""
        self.xp += amount
        return self.can_level_up

    def level_up(self) -> dict[str, Any]:
        """Level up the character. Returns the changes made."""
        if not self.can_level_up:
            return {}
        self.level += 1
        # HP increase based on class
        hp_gains = {"warrior": 10, "paladin": 10, "ranger": 8, "cleric": 8,
                    "druid": 8, "monk": 8, "rogue": 8, "bard": 8, "warlock": 8, "mage": 6}
        hp_gain = hp_gains.get(self.character_class.value, 8) + self.ability_scores.modifier("constitution")
        self.max_hp += hp_gain
        self.hp = self.max_hp  # Full heal on level up
        return {
            "new_level": self.level,
            "hp_gained": hp_gain,
            "new_max_hp": self.max_hp,
        }


class NPCMemory(BaseModel):
    """A single memory an NPC has about a player interaction."""
    event: str  # What happened
    sentiment: int = 0  # -10 to +10
    character_involved: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class NPC(BaseModel):
    id: str = Field(default_factory=_id)
    name: str
    description: str = ""
    personality: str = ""
    appearance: str = ""
    portrait_url: str = ""
    voice_style: str = "neutral"  # gruff, noble, mysterious, cheerful, etc.
    voice_name: str = ""  # Cloud TTS voice ID for multi-voice
    location: str = ""
    is_hostile: bool = False
    relationship: int = 0  # -100 to 100
    faction: str = ""  # Faction ID this NPC belongs to
    known_info: list[str] = Field(default_factory=list)
    dialogue_history: list[str] = Field(default_factory=list)
    memories: list[NPCMemory] = Field(default_factory=list)  # Persistent memory
    hp: int = 20
    max_hp: int = 20
    armor_class: int = 10
    challenge_rating: float = 1.0

    def add_memory(self, event: str, sentiment: int = 0, character: str = "") -> None:
        self.memories.append(NPCMemory(
            event=event, sentiment=sentiment, character_involved=character,
        ))
        # Adjust relationship based on sentiment
        self.relationship = max(-100, min(100, self.relationship + sentiment))

    def get_memory_summary(self) -> str:
        if not self.memories:
            return "No prior interactions."
        recent = self.memories[-10:]
        return "; ".join(f"{m.event} (felt {'positive' if m.sentiment > 0 else 'negative' if m.sentiment < 0 else 'neutral'})" for m in recent)


class Faction(BaseModel):
    """A faction or group in the game world."""
    id: str = Field(default_factory=_id)
    name: str
    description: str = ""
    reputation: dict[str, int] = Field(default_factory=dict)  # character_name -> -100 to 100
    relationships: dict[str, int] = Field(default_factory=dict)  # faction_id -> -100 to 100
    leader: str = ""  # NPC name
    territory: list[str] = Field(default_factory=list)  # Location IDs

    def get_reputation(self, character_name: str) -> int:
        return self.reputation.get(character_name, 0)

    def adjust_reputation(self, character_name: str, amount: int) -> int:
        current = self.reputation.get(character_name, 0)
        new_val = max(-100, min(100, current + amount))
        self.reputation[character_name] = new_val
        return new_val


class Achievement(BaseModel):
    """An achievement/milestone earned by a player."""
    id: str = Field(default_factory=_id)
    title: str
    description: str = ""
    icon: str = ""  # emoji or icon name
    earned_by: str = ""  # character name
    earned_at: datetime = Field(default_factory=datetime.utcnow)


class LoreEntry(BaseModel):
    """A lorebook entry — injected into AI context when keywords match."""
    id: str = Field(default_factory=_id)
    title: str
    content: str = ""
    keywords: list[str] = Field(default_factory=list)  # Trigger words
    category: str = "world"  # world, character, faction, item, location


# ── World ──────────────────────────────────────────────────────────────────

class Location(BaseModel):
    id: str = Field(default_factory=_id)
    name: str
    description: str = ""
    location_type: str = "generic"  # town, dungeon, wilderness, tavern, castle
    image_url: str = ""
    connected_locations: list[str] = Field(default_factory=list)
    npcs: list[str] = Field(default_factory=list)  # NPC ids
    items: list[Item] = Field(default_factory=list)
    visited: bool = False
    x: float = 0.0
    y: float = 0.0


class Quest(BaseModel):
    id: str = Field(default_factory=_id)
    title: str
    description: str = ""
    objectives: list[str] = Field(default_factory=list)
    completed_objectives: list[int] = Field(default_factory=list)
    is_active: bool = True
    is_complete: bool = False
    reward_xp: int = 0
    reward_gold: int = 0
    reward_items: list[Item] = Field(default_factory=list)


class Consequence(BaseModel):
    """A consequence of a player action that ripples through the world."""
    id: str = Field(default_factory=_id)
    trigger_event: str  # What caused this
    effect: str  # What changed
    affected_entities: list[str] = Field(default_factory=list)  # NPC/location/faction IDs
    severity: int = 1  # 1-10
    resolved: bool = False


class WorldState(BaseModel):
    campaign_name: str = "New Campaign"
    setting_description: str = ""
    world_map_url: str = ""
    locations: dict[str, Location] = Field(default_factory=dict)
    npcs: dict[str, NPC] = Field(default_factory=dict)
    factions: dict[str, Faction] = Field(default_factory=dict)
    quests: list[Quest] = Field(default_factory=list)
    lorebook: list[LoreEntry] = Field(default_factory=list)
    consequences: list[Consequence] = Field(default_factory=list)
    current_location_id: str = ""
    time_of_day: str = "morning"
    weather: str = "clear"
    day_count: int = 1
    global_events: list[str] = Field(default_factory=list)

    def find_lore(self, text: str) -> list[LoreEntry]:
        """Find lorebook entries whose keywords match the given text."""
        text_lower = text.lower()
        return [
            entry for entry in self.lorebook
            if any(kw.lower() in text_lower for kw in entry.keywords)
        ]

    def add_consequence(self, trigger: str, effect: str, entities: list[str] | None = None, severity: int = 3) -> Consequence:
        c = Consequence(trigger_event=trigger, effect=effect, affected_entities=entities or [], severity=severity)
        self.consequences.append(c)
        return c


# ── Combat ─────────────────────────────────────────────────────────────────

class CombatAction(BaseModel):
    actor_id: str
    actor_name: str
    action_type: str  # attack, spell, ability, move, dodge, disengage
    target_id: str = ""
    target_name: str = ""
    roll: int = 0
    damage: int = 0
    description: str = ""
    is_critical: bool = False
    is_miss: bool = False


class Combatant(BaseModel):
    id: str
    name: str
    initiative: int = 0
    hp: int = 20
    max_hp: int = 20
    armor_class: int = 10
    is_player: bool = True
    conditions: list[str] = Field(default_factory=list)


class CombatState(BaseModel):
    is_active: bool = False
    round_number: int = 0
    phase: CombatPhase = CombatPhase.INITIATIVE
    combatants: list[Combatant] = Field(default_factory=list)
    current_turn_index: int = 0
    battle_map_url: str = ""
    action_log: list[CombatAction] = Field(default_factory=list)

    @property
    def current_combatant(self) -> Combatant | None:
        if not self.combatants:
            return None
        return self.combatants[self.current_turn_index % len(self.combatants)]


# ── Media & Events ─────────────────────────────────────────────────────────

class GeneratedMedia(BaseModel):
    id: str = Field(default_factory=_id)
    media_type: MediaType
    url: str = ""
    prompt: str = ""
    drama_level: int = 1
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = "pending"  # pending, generating, complete, failed


class StoryEvent(BaseModel):
    id: str = Field(default_factory=_id)
    event_type: str  # narration, dialogue, combat, discovery, quest, media
    content: str = ""
    speaker: str = ""  # NPC name or "narrator"
    media: GeneratedMedia | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    drama_level: int = 1


# ── Game Session ───────────────────────────────────────────────────────────

class GameSession(BaseModel):
    id: str = Field(default_factory=_id)
    campaign_id: str = ""
    session_number: int = 1
    players: list[Character] = Field(default_factory=list)
    world: WorldState = Field(default_factory=WorldState)
    combat: CombatState = Field(default_factory=CombatState)
    story_events: list[StoryEvent] = Field(default_factory=list)
    story_beat: StoryBeat = StoryBeat.EXPOSITION
    style_sheet: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True

    def add_event(self, event: StoryEvent) -> None:
        self.story_events.append(event)
        if len(self.story_events) > 500:
            self.story_events = self.story_events[-500:]
        self.updated_at = datetime.utcnow()

    def get_recent_events(self, n: int = 20) -> list[StoryEvent]:
        return self.story_events[-n:]

    def get_alive_players(self) -> list[Character]:
        return [p for p in self.players if p.is_alive]


# ── WebSocket Messages ────────────────────────────────────────────────────

class WSMessage(BaseModel):
    type: str  # See types below
    data: dict[str, Any] = Field(default_factory=dict)
    session_id: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Message types:
    # Client -> Server:
    #   player_action, voice_input, dice_roll, character_create,
    #   start_session, load_campaign, camera_frame
    #
    # Server -> Client:
    #   narration, dialogue, combat_update, scene_image, scene_video,
    #   battle_map, character_portrait, world_map_update, quest_update,
    #   inventory_update, ambient_audio, music_change, error,
    #   game_state_sync, npc_portrait, dice_result


class CampaignSummary(BaseModel):
    id: str = Field(default_factory=_id)
    name: str
    setting: str = ""
    session_count: int = 0
    last_played: datetime = Field(default_factory=datetime.utcnow)
    player_names: list[str] = Field(default_factory=list)
    world_map_url: str = ""
