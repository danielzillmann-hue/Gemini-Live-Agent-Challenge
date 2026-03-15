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


class Item(BaseModel):
    id: str = Field(default_factory=_id)
    name: str
    description: str = ""
    item_type: str = "misc"  # weapon, armor, potion, scroll, misc
    properties: dict[str, Any] = Field(default_factory=dict)
    equipped: bool = False
    quantity: int = 1


class Spell(BaseModel):
    name: str
    level: int = 0
    description: str = ""
    damage_type: DamageType | None = None
    damage_dice: str = ""  # e.g. "2d6"
    range: str = "self"
    casting_time: str = "1 action"


# ── Characters ─────────────────────────────────────────────────────────────

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
    inventory: list[Item] = Field(default_factory=list)
    spells: list[Spell] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)  # poisoned, stunned, etc.
    gold: int = 50

    @property
    def is_alive(self) -> bool:
        return self.hp > 0


class NPC(BaseModel):
    id: str = Field(default_factory=_id)
    name: str
    description: str = ""
    personality: str = ""
    appearance: str = ""
    portrait_url: str = ""
    voice_style: str = "neutral"  # gruff, noble, mysterious, cheerful, etc.
    location: str = ""
    is_hostile: bool = False
    relationship: int = 0  # -100 to 100
    known_info: list[str] = Field(default_factory=list)
    dialogue_history: list[str] = Field(default_factory=list)
    hp: int = 20
    max_hp: int = 20
    armor_class: int = 10
    challenge_rating: float = 1.0


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


class WorldState(BaseModel):
    campaign_name: str = "New Campaign"
    setting_description: str = ""
    world_map_url: str = ""
    locations: dict[str, Location] = Field(default_factory=dict)
    npcs: dict[str, NPC] = Field(default_factory=dict)
    quests: list[Quest] = Field(default_factory=list)
    current_location_id: str = ""
    time_of_day: str = "morning"
    weather: str = "clear"
    day_count: int = 1
    global_events: list[str] = Field(default_factory=list)


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
