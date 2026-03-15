// ── Core Game Types ───────────────────────────────────────────────────────

export interface AbilityScores {
  strength: number;
  dexterity: number;
  constitution: number;
  intelligence: number;
  wisdom: number;
  charisma: number;
}

export interface Item {
  id: string;
  name: string;
  description: string;
  item_type: string;
  properties: Record<string, unknown>;
  equipped: boolean;
  quantity: number;
}

export interface Character {
  id: string;
  name: string;
  race: string;
  character_class: string;
  level: number;
  xp: number;
  hp: number;
  max_hp: number;
  armor_class: number;
  ability_scores: AbilityScores;
  backstory: string;
  personality: string;
  appearance: string;
  portrait_url: string;
  inventory: Item[];
  spells: Spell[];
  conditions: string[];
  gold: number;
}

export interface Spell {
  name: string;
  level: number;
  description: string;
  damage_type: string | null;
  damage_dice: string;
  range: string;
  casting_time: string;
}

export interface NPC {
  id: string;
  name: string;
  description: string;
  personality: string;
  portrait_url: string;
  voice_style: string;
  location: string;
  is_hostile: boolean;
  relationship: number;
  known_info: string[];
}

export interface Location {
  id: string;
  name: string;
  description: string;
  location_type: string;
  image_url: string;
  connected_locations: string[];
  visited: boolean;
  x: number;
  y: number;
}

export interface Quest {
  id: string;
  title: string;
  description: string;
  objectives: string[];
  completed_objectives: number[];
  is_active: boolean;
  is_complete: boolean;
  reward_xp: number;
  reward_gold: number;
}

export interface Combatant {
  id: string;
  name: string;
  initiative: number;
  hp: number;
  max_hp: number;
  armor_class: number;
  is_player: boolean;
  conditions: string[];
}

export interface CombatState {
  is_active: boolean;
  round_number: number;
  phase: string;
  combatants: Combatant[];
  current_turn_index: number;
  battle_map_url: string;
}

export interface WorldState {
  campaign_name: string;
  setting_description: string;
  world_map_url: string;
  locations: Record<string, Location>;
  npcs: Record<string, NPC>;
  quests: Quest[];
  current_location_id: string;
  time_of_day: string;
  weather: string;
  day_count: number;
}

export interface GameSession {
  id: string;
  campaign_id: string;
  session_number: number;
  players: Character[];
  world: WorldState;
  combat: CombatState;
  story_beat: string;
  is_active: boolean;
}

// ── WebSocket Message Types ──────────────────────────────────────────────

export type WSMessageType =
  | "narration"
  | "dialogue"
  | "scene_image"
  | "scene_video"
  | "battle_map"
  | "character_portrait"
  | "npc_portrait"
  | "world_map_update"
  | "quest_update"
  | "inventory_update"
  | "combat_update"
  | "dice_result"
  | "music_change"
  | "ambient_audio"
  | "game_state_sync"
  | "character_joined"
  | "location_change"
  | "world_update"
  | "thinking"
  | "error";

export interface WSMessage {
  type: WSMessageType;
  data: Record<string, unknown>;
  session_id: string;
}

// ── Story Event (for narrative log) ──────────────────────────────────────

export interface StoryEntry {
  id: string;
  type: "narration" | "dialogue" | "action" | "dice" | "system" | "image" | "video" | "combat";
  content: string;
  speaker?: string;
  mediaUrl?: string;
  mediaType?: "image" | "video";
  diceResult?: DiceResult;
  timestamp: number;
}

export interface DiceResult {
  character: string;
  roll_type: string;
  value: number;
  total?: number;
  dc?: number;
  success?: boolean;
  is_critical: boolean;
  is_fumble: boolean;
}

// ── UI State ─────────────────────────────────────────────────────────────

export type MusicMood =
  | "peaceful"
  | "tense"
  | "combat"
  | "mysterious"
  | "triumphant"
  | "sad"
  | "epic";

export interface AudioState {
  musicMood: MusicMood;
  musicIntensity: number;
  ambientDescription: string;
  isMuted: boolean;
}
