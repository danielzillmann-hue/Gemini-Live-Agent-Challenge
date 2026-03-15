import { create } from "zustand";
import type {
  Character,
  CombatState,
  DiceResult,
  GameSession,
  MusicMood,
  NPC,
  Quest,
  StoryEntry,
  WorldState,
} from "@/lib/types";
import { generateId } from "@/lib/utils";

interface GameStore {
  // Session
  sessionId: string | null;
  campaignName: string;
  setting: string;
  isConnected: boolean;
  isThinking: boolean;

  // Players & World
  players: Character[];
  world: WorldState | null;
  combat: CombatState | null;
  npcs: Record<string, NPC>;

  // Multiplayer
  playersOnline: number;

  // Narrative
  storyLog: StoryEntry[];
  currentSceneImage: string | null;
  currentSceneVideo: string | null;
  currentBattleMap: string | null;
  worldMapUrl: string | null;

  // Audio
  musicMood: MusicMood;
  musicIntensity: number;
  isMuted: boolean;

  // Narration voice
  narratorVoiceEnabled: boolean;

  // Actions
  setSession: (id: string, name: string, setting: string) => void;
  setConnected: (connected: boolean) => void;
  setThinking: (thinking: boolean) => void;
  addStoryEntry: (entry: Omit<StoryEntry, "id" | "timestamp">) => void;
  setPlayers: (players: Character[]) => void;
  addPlayer: (player: Character) => void;
  updatePlayer: (id: string, updates: Partial<Character>) => void;
  setWorld: (world: WorldState) => void;
  setCombat: (combat: CombatState | null) => void;
  setSceneImage: (url: string) => void;
  setSceneVideo: (url: string | null) => void;
  setBattleMap: (url: string) => void;
  setWorldMap: (url: string) => void;
  setMusic: (mood: MusicMood, intensity: number) => void;
  toggleMute: () => void;
  toggleNarratorVoice: () => void;
  addNPC: (npc: NPC) => void;
  updateQuests: (quests: Quest[]) => void;
  handleWSMessage: (msg: Record<string, unknown>) => void;
  reset: () => void;
}

const initialState = {
  sessionId: null,
  campaignName: "",
  setting: "",
  isConnected: false,
  isThinking: false,
  players: [],
  world: null,
  combat: null,
  npcs: {},
  playersOnline: 1,
  storyLog: [],
  currentSceneImage: null,
  currentSceneVideo: null,
  currentBattleMap: null,
  worldMapUrl: null,
  musicMood: "peaceful" as MusicMood,
  musicIntensity: 0.3,
  isMuted: false,
  narratorVoiceEnabled: true,
};

export const useGameStore = create<GameStore>((set, get) => ({
  ...initialState,

  setSession: (id, name, setting) =>
    set({ sessionId: id, campaignName: name, setting }),

  setConnected: (connected) => set({ isConnected: connected }),

  setThinking: (thinking) => set({ isThinking: thinking }),

  addStoryEntry: (entry) =>
    set((state) => ({
      storyLog: [
        ...state.storyLog,
        { ...entry, id: generateId(), timestamp: Date.now() },
      ].slice(-200), // keep last 200 entries
    })),

  setPlayers: (players) => set({ players }),

  addPlayer: (player) =>
    set((state) => ({ players: [...state.players, player] })),

  updatePlayer: (id, updates) =>
    set((state) => ({
      players: state.players.map((p) =>
        p.id === id ? { ...p, ...updates } : p
      ),
    })),

  setWorld: (world) => set({ world, worldMapUrl: world.world_map_url || get().worldMapUrl }),

  setCombat: (combat) => set({ combat }),

  setSceneImage: (url) => set({ currentSceneImage: url, currentSceneVideo: null }),

  setSceneVideo: (url) => set({ currentSceneVideo: url }),

  setBattleMap: (url) => set({ currentBattleMap: url }),

  setWorldMap: (url) => set({ worldMapUrl: url }),

  setMusic: (mood, intensity) => set({ musicMood: mood, musicIntensity: intensity }),

  toggleMute: () => set((state) => ({ isMuted: !state.isMuted })),

  toggleNarratorVoice: () => set((state) => {
    const newVal = !state.narratorVoiceEnabled;
    // Stop any current speech when disabling
    if (!newVal && typeof window !== "undefined") {
      window.speechSynthesis?.cancel();
    }
    return { narratorVoiceEnabled: newVal };
  }),

  addNPC: (npc) =>
    set((state) => ({
      npcs: { ...state.npcs, [npc.id]: npc },
    })),

  updateQuests: (quests) =>
    set((state) => {
      if (!state.world) return {};
      return { world: { ...state.world, quests } };
    }),

  handleWSMessage: (msg) => {
    const type = msg.type as string;
    const data = (msg.data || {}) as Record<string, unknown>;
    const store = get();

    switch (type) {
      case "narration":
        store.addStoryEntry({
          type: "narration",
          content: data.content as string,
        });
        set({ isThinking: false });
        break;

      case "dialogue":
        store.addStoryEntry({
          type: "dialogue",
          content: data.content as string,
          speaker: data.speaker as string,
        });
        break;

      case "scene_image":
        store.setSceneImage(data.url as string);
        store.addStoryEntry({
          type: "image",
          content: (data.description as string) || "Scene illustration",
          mediaUrl: data.url as string,
          mediaType: "image",
        });
        break;

      case "scene_video":
        store.setSceneVideo(data.url as string);
        store.addStoryEntry({
          type: "video",
          content: (data.description as string) || "Cinematic moment",
          mediaUrl: data.url as string,
          mediaType: "video",
        });
        break;

      case "battle_map":
        store.setBattleMap(data.url as string);
        break;

      case "world_map_update":
        store.setWorldMap(data.url as string);
        break;

      case "character_joined":
        store.addPlayer(data as unknown as Character);
        store.addStoryEntry({
          type: "system",
          content: `${(data as Record<string, string>).name} has joined the adventure.`,
        });
        break;

      case "npc_portrait":
        store.addNPC({
          id: generateId(),
          name: data.name as string,
          description: data.description as string,
          personality: data.personality as string,
          portrait_url: data.portrait_url as string,
          voice_style: "neutral",
          location: "",
          is_hostile: false,
          relationship: 0,
          known_info: [],
        });
        break;

      case "combat_update":
        if (data.combatants) {
          store.setCombat(data as unknown as CombatState);
        }
        store.addStoryEntry({
          type: "combat",
          content: (data.description as string) || "Combat update",
        });
        break;

      case "dice_result": {
        const dice = data as unknown as DiceResult;
        store.addStoryEntry({
          type: "dice",
          content: `${dice.character} rolled ${dice.value}${dice.is_critical ? " — CRITICAL!" : dice.is_fumble ? " — Critical Failure!" : ""}`,
          diceResult: dice,
        });
        break;
      }

      case "music_change":
        store.setMusic(
          data.mood as MusicMood,
          (data.intensity as number) || 0.5
        );
        break;

      case "quest_update":
        store.addStoryEntry({
          type: "system",
          content: `Quest: ${data.quest as string} — ${data.update as string}`,
        });
        // Update quests list if provided
        if (data.quests) {
          store.updateQuests(data.quests as Quest[]);
        }
        break;

      case "location_change":
        if (data.image_url) {
          store.setSceneImage(data.image_url as string);
        }
        store.addStoryEntry({
          type: "system",
          content: `Arrived at ${data.name as string}`,
        });
        break;

      case "world_update":
        // Update world state (time, weather, day)
        if (store.world) {
          set({
            world: {
              ...store.world,
              time_of_day: (data.time_of_day as string) || store.world.time_of_day,
              weather: (data.weather as string) || store.world.weather,
              day_count: (data.day_count as number) || store.world.day_count,
            },
          });
        }
        break;

      case "game_state_sync":
        if (data.players) store.setPlayers(data.players as Character[]);
        if (data.world) store.setWorld(data.world as unknown as WorldState);
        if (data.combat) store.setCombat(data.combat as unknown as CombatState);
        break;

      case "players_online":
        set({ playersOnline: (data.count as number) || 1 });
        break;

      case "thinking":
        set({ isThinking: true });
        break;

      case "error":
        store.addStoryEntry({
          type: "system",
          content: `Error: ${data.message as string}`,
        });
        set({ isThinking: false });
        break;
    }
  },

  reset: () => set(initialState),
}));
