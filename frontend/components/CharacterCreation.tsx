"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { User, Plus, Play, Upload, Save, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useGameStore } from "@/hooks/useGameStore";
import type { Character } from "@/lib/types";
/* eslint-disable @typescript-eslint/no-explicit-any */

const RACES = ["human", "elf", "dwarf", "halfling", "orc", "tiefling", "dragonborn", "gnome"];
const CLASSES = ["warrior", "mage", "ranger", "rogue", "paladin", "cleric", "bard", "warlock", "druid", "monk"];

interface Props {
  sessionId: string;
  onComplete: () => void;
}

interface SavedChar {
  id: string;
  name: string;
  race: string;
  character_class: string;
  level: number;
  xp: number;
  portrait_url: string;
  kills: number;
  quests_completed: number;
}

export default function CharacterCreation({ sessionId, onComplete }: Props) {
  const { players } = useGameStore();
  const [isCreating, setIsCreating] = useState(false);
  const [isImporting, setIsImporting] = useState<string | null>(null);
  const [savedChars, setSavedChars] = useState<SavedChar[]>([]);
  const [showRoster, setShowRoster] = useState(false);
  const [form, setForm] = useState({
    name: "",
    race: "human",
    character_class: "warrior",
    backstory: "",
    personality: "",
    appearance: "",
  });

  // Load saved characters on mount
  useEffect(() => {
    api.listSavedCharacters().then((chars) => {
      setSavedChars(chars as unknown as SavedChar[]);
    }).catch(() => {});
  }, []);

  async function handleCreate() {
    if (!form.name) return;
    setIsCreating(true);
    try {
      const character = await api.createCharacter({ session_id: sessionId, ...form });
      useGameStore.getState().addPlayer(character as unknown as Character);
      setForm({ name: "", race: "human", character_class: "warrior", backstory: "", personality: "", appearance: "" });
    } catch (err) {
      console.error("Failed to create character:", err);
    } finally {
      setIsCreating(false);
    }
  }

  async function handleImport(characterId: string) {
    setIsImporting(characterId);
    try {
      const character = await api.importCharacterToSession(sessionId, characterId);
      useGameStore.getState().addPlayer(character as unknown as Character);
    } catch (err) {
      console.error("Failed to import character:", err);
    } finally {
      setIsImporting(null);
    }
  }

  async function handleDeleteSaved(characterId: string) {
    try {
      await api.deleteSavedCharacter(characterId);
      setSavedChars((prev) => prev.filter((c) => c.id !== characterId));
    } catch (err) {
      console.error("Failed to delete character:", err);
    }
  }

  return (
    <div>
      <h2 className="font-display text-4xl text-genesis-accent text-center mb-2 tracking-wider">
        Assemble Your Party
      </h2>
      <p className="text-genesis-text-dim text-center mb-6">
        Create new characters or import veterans from previous campaigns.
      </p>

      {/* Tab switcher */}
      <div className="flex justify-center gap-2 mb-6">
        <button
          onClick={() => setShowRoster(false)}
          className={`px-4 py-2 rounded-lg text-sm font-display tracking-wider transition-all ${
            !showRoster
              ? "bg-genesis-accent/20 text-genesis-accent border border-genesis-accent/50"
              : "text-genesis-text-dim border border-genesis-border hover:text-genesis-text"
          }`}
        >
          <Plus className="inline w-4 h-4 mr-1 -mt-0.5" /> New Character
        </button>
        <button
          onClick={() => setShowRoster(true)}
          className={`px-4 py-2 rounded-lg text-sm font-display tracking-wider transition-all ${
            showRoster
              ? "bg-genesis-accent/20 text-genesis-accent border border-genesis-accent/50"
              : "text-genesis-text-dim border border-genesis-border hover:text-genesis-text"
          }`}
        >
          <Upload className="inline w-4 h-4 mr-1 -mt-0.5" /> Load Saved ({savedChars.length})
        </button>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Left Panel — Create or Load */}
        <div>
          {!showRoster ? (
            /* Character Form */
            <div className="genesis-panel p-6 space-y-4">
              <div>
                <label className="block text-genesis-text-dim text-xs tracking-wider uppercase mb-1.5">Name</label>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Kira Shadowmend"
                  className="genesis-input"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-genesis-text-dim text-xs tracking-wider uppercase mb-1.5">Race</label>
                  <select
                    value={form.race}
                    onChange={(e) => setForm({ ...form, race: e.target.value })}
                    className="genesis-select"
                  >
                    {RACES.map((r) => (
                      <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-genesis-text-dim text-xs tracking-wider uppercase mb-1.5">Class</label>
                  <select
                    value={form.character_class}
                    onChange={(e) => setForm({ ...form, character_class: e.target.value })}
                    className="genesis-select"
                  >
                    {CLASSES.map((c) => (
                      <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-genesis-text-dim text-xs tracking-wider uppercase mb-1.5">Appearance</label>
                <textarea
                  value={form.appearance}
                  onChange={(e) => setForm({ ...form, appearance: e.target.value })}
                  placeholder="Scarred face, silver hair, mismatched eyes..."
                  rows={2}
                  className="genesis-input resize-none"
                />
              </div>

              <div>
                <label className="block text-genesis-text-dim text-xs tracking-wider uppercase mb-1.5">Personality</label>
                <textarea
                  value={form.personality}
                  onChange={(e) => setForm({ ...form, personality: e.target.value })}
                  placeholder="Stoic but secretly compassionate..."
                  rows={2}
                  className="genesis-input resize-none"
                />
              </div>

              <div>
                <label className="block text-genesis-text-dim text-xs tracking-wider uppercase mb-1.5">Backstory</label>
                <textarea
                  value={form.backstory}
                  onChange={(e) => setForm({ ...form, backstory: e.target.value })}
                  placeholder="Once a noble knight, now a wandering exile..."
                  rows={3}
                  className="genesis-input resize-none"
                />
              </div>

              <button
                onClick={handleCreate}
                disabled={!form.name || isCreating}
                className="genesis-button w-full disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {isCreating ? (
                  <span className="thinking-indicator inline-flex">
                    <span className="dot" /><span className="dot" /><span className="dot" />
                    <span className="ml-2">Generating Portrait</span>
                  </span>
                ) : (
                  <><Plus className="inline w-4 h-4 mr-1 -mt-0.5" /> Create Character</>
                )}
              </button>
            </div>
          ) : (
            /* Saved Character Roster */
            <div className="space-y-3">
              {savedChars.length === 0 && (
                <div className="genesis-panel p-8 text-center text-genesis-text-dim">
                  <Save className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  <p className="text-sm">No saved characters yet</p>
                  <p className="text-xs mt-1">Characters are saved after completing a campaign</p>
                </div>
              )}

              {savedChars.map((char) => {
                const isInParty = players.some((p) => p.id === char.id);
                return (
                  <div key={char.id} className="genesis-panel p-3 flex items-center gap-3">
                    {char.portrait_url ? (
                      <img
                        src={char.portrait_url}
                        alt={char.name}
                        className="w-14 h-14 rounded-lg object-cover border border-genesis-border"
                      />
                    ) : (
                      <div className="w-14 h-14 rounded-lg bg-genesis-bg flex items-center justify-center border border-genesis-border">
                        <User className="w-6 h-6 text-genesis-text-dim" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="font-display text-genesis-text text-sm tracking-wider">
                        {char.name}
                      </div>
                      <div className="text-genesis-text-dim text-xs capitalize">
                        Lvl {char.level} {char.race} {char.character_class}
                      </div>
                      <div className="text-genesis-text-dim text-[10px]">
                        {char.kills} kills &bull; {char.quests_completed} quests &bull; {char.xp} XP
                      </div>
                    </div>
                    <div className="flex gap-1">
                      <button
                        onClick={() => handleImport(char.id)}
                        disabled={isInParty || isImporting === char.id}
                        className="genesis-button text-xs px-3 py-1.5 disabled:opacity-30"
                      >
                        {isImporting === char.id ? "..." : isInParty ? "In Party" : "Import"}
                      </button>
                      <button
                        onClick={() => handleDeleteSaved(char.id)}
                        className="p-1.5 text-genesis-text-dim hover:text-genesis-red transition-colors"
                        title="Delete character"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right Panel — Party Preview */}
        <div className="space-y-3">
          <div className="text-genesis-text-dim text-xs tracking-wider uppercase mb-2">
            Party ({players.length}/6)
          </div>

          {players.map((char, i) => (
            <motion.div
              key={char.id}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.1 }}
              className="genesis-panel p-3 flex items-center gap-3"
            >
              {char.portrait_url ? (
                <img
                  src={char.portrait_url}
                  alt={char.name}
                  className="w-14 h-14 rounded-lg object-cover border border-genesis-border"
                />
              ) : (
                <div className="w-14 h-14 rounded-lg bg-genesis-bg flex items-center justify-center border border-genesis-border">
                  <User className="w-6 h-6 text-genesis-text-dim" />
                </div>
              )}
              <div className="flex-1 min-w-0">
                <div className="font-display text-genesis-text text-sm tracking-wider">
                  {char.name}
                </div>
                <div className="text-genesis-text-dim text-xs">
                  {char.race} {char.character_class} &bull; Lvl {char.level}
                </div>
                <div className="text-genesis-text-dim text-xs">
                  HP: {char.hp}/{char.max_hp} &bull; AC: {char.armor_class}
                </div>
              </div>
            </motion.div>
          ))}

          {players.length === 0 && (
            <div className="genesis-panel p-8 text-center text-genesis-text-dim">
              <User className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="text-sm">No characters yet</p>
            </div>
          )}

          {players.length > 0 && (
            <motion.button
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              onClick={onComplete}
              className="genesis-button w-full mt-4 text-lg py-3 animate-glow"
            >
              <Play className="inline w-5 h-5 mr-2 -mt-0.5" />
              Begin Adventure
            </motion.button>
          )}
        </div>
      </div>
    </div>
  );
}
