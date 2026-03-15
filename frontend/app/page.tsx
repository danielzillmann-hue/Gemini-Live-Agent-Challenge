"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Sword, Wand2, Shield, Skull, Crown, Scroll, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useGameStore } from "@/hooks/useGameStore";
import CharacterCreation from "@/components/CharacterCreation";

type Phase = "title" | "setup" | "characters" | "launching";

const PRESETS = [
  {
    name: "The Shattered Crown",
    setting:
      "A dark medieval kingdom fractured by civil war. The throne sits empty since the king's assassination, and five noble houses vie for power while an ancient evil stirs beneath the mountains. Magic is feared and practitioners hunted.",
    icon: Crown,
  },
  {
    name: "Voidwalkers",
    setting:
      "A dying world at the edge of reality, where the boundary between the material plane and the void has thinned. Entire cities vanish overnight, consumed by the encroaching nothing. The last bastion of civilization sits atop a floating island, anchored by failing arcane chains.",
    icon: Skull,
  },
  {
    name: "The Emerald Accord",
    setting:
      "A sprawling, ancient forest where nature and civilization coexist in uneasy balance. Elven tree-cities tower above, dwarven mines burrow below, and human traders navigate the root-paths between. A plague is turning animals feral and plants hostile.",
    icon: Scroll,
  },
];

export default function HomePage() {
  const router = useRouter();
  const { setSession } = useGameStore();
  const [phase, setPhase] = useState<Phase>("title");
  const [campaignName, setCampaignName] = useState("");
  const [setting, setSetting] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  async function handleCreateSession() {
    if (!campaignName || !setting) return;
    setIsCreating(true);
    try {
      const result = await api.createSession(campaignName, setting);
      setSessionId(result.session_id);
      setSession(result.session_id, campaignName, setting);
      setPhase("characters");
    } catch (err) {
      console.error("Failed to create session:", err);
    } finally {
      setIsCreating(false);
    }
  }

  function handleStartGame() {
    if (sessionId) {
      setPhase("launching");
      setTimeout(() => router.push(`/game/${sessionId}`), 1500);
    }
  }

  return (
    <div className="min-h-screen bg-genesis-bg flex items-center justify-center relative overflow-hidden">
      {/* Animated background */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-genesis-accent/5 rounded-full blur-3xl animate-pulse-slow" />
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-genesis-purple/5 rounded-full blur-3xl animate-pulse-slow" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] border border-genesis-border/20 rounded-full" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] border border-genesis-border/10 rounded-full" />
      </div>

      <AnimatePresence mode="wait">
        {/* ── Title Screen ─────────────────────────────────────── */}
        {phase === "title" && (
          <motion.div
            key="title"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, y: -30 }}
            transition={{ duration: 0.8 }}
            className="relative z-10 text-center"
          >
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 1.2, ease: "easeOut" }}
            >
              <h1 className="font-display text-8xl font-bold text-genesis-accent tracking-[0.2em] mb-2">
                GENESIS
              </h1>
              <div className="w-64 h-px bg-gradient-to-r from-transparent via-genesis-accent to-transparent mx-auto mb-4" />
              <p className="font-display text-genesis-text-dim text-lg tracking-[0.3em] uppercase">
                AI Game Master
              </p>
            </motion.div>

            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.8, duration: 1 }}
              className="text-genesis-text-dim mt-8 mb-12 max-w-lg mx-auto leading-relaxed"
            >
              A cinematic tabletop RPG experience powered by AI. Every scene illustrated.
              Every battle map generated. Every story moment brought to life.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 1.2, duration: 0.6 }}
              className="flex gap-4 justify-center"
            >
              <button
                onClick={() => setPhase("setup")}
                className="genesis-button text-lg px-8 py-3 animate-glow"
              >
                <Sparkles className="inline-block w-5 h-5 mr-2 -mt-0.5" />
                New Campaign
              </button>
            </motion.div>

            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 1.8, duration: 0.6 }}
              className="mt-16 flex items-center justify-center gap-8 text-genesis-text-dim/40"
            >
              <div className="flex items-center gap-2 text-xs tracking-wider uppercase">
                <Sword className="w-3 h-3" /> Combat
              </div>
              <div className="flex items-center gap-2 text-xs tracking-wider uppercase">
                <Wand2 className="w-3 h-3" /> Magic
              </div>
              <div className="flex items-center gap-2 text-xs tracking-wider uppercase">
                <Shield className="w-3 h-3" /> Quests
              </div>
            </motion.div>
          </motion.div>
        )}

        {/* ── Campaign Setup ──────────────────────────────────── */}
        {phase === "setup" && (
          <motion.div
            key="setup"
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -30 }}
            transition={{ duration: 0.6 }}
            className="relative z-10 w-full max-w-3xl px-6"
          >
            <h2 className="font-display text-4xl text-genesis-accent text-center mb-2 tracking-wider">
              Forge Your World
            </h2>
            <p className="text-genesis-text-dim text-center mb-10">
              Choose a campaign preset or create your own setting
            </p>

            {/* Presets */}
            <div className="grid grid-cols-3 gap-4 mb-8">
              {PRESETS.map((preset) => (
                <button
                  key={preset.name}
                  onClick={() => {
                    setCampaignName(preset.name);
                    setSetting(preset.setting);
                  }}
                  className={`genesis-panel p-4 text-left transition-all duration-300 hover:border-genesis-accent/50 ${
                    campaignName === preset.name
                      ? "border-genesis-accent shadow-lg shadow-genesis-accent/10"
                      : ""
                  }`}
                >
                  <preset.icon className="w-6 h-6 text-genesis-accent mb-3" />
                  <h3 className="font-display text-genesis-text text-sm tracking-wider mb-2">
                    {preset.name}
                  </h3>
                  <p className="text-genesis-text-dim text-xs leading-relaxed line-clamp-3">
                    {preset.setting}
                  </p>
                </button>
              ))}
            </div>

            <div className="genesis-panel p-6 space-y-4">
              <div>
                <label className="block text-genesis-text-dim text-xs tracking-wider uppercase mb-2">
                  Campaign Name
                </label>
                <input
                  value={campaignName}
                  onChange={(e) => setCampaignName(e.target.value)}
                  placeholder="The Shattered Crown"
                  className="genesis-input"
                />
              </div>
              <div>
                <label className="block text-genesis-text-dim text-xs tracking-wider uppercase mb-2">
                  World Setting
                </label>
                <textarea
                  value={setting}
                  onChange={(e) => setSetting(e.target.value)}
                  placeholder="Describe your world — the more detail, the richer the experience..."
                  rows={4}
                  className="genesis-input resize-none"
                />
              </div>
            </div>

            <div className="flex justify-between mt-8">
              <button
                onClick={() => setPhase("title")}
                className="genesis-button-secondary"
              >
                Back
              </button>
              <button
                onClick={handleCreateSession}
                disabled={!campaignName || !setting || isCreating}
                className="genesis-button disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {isCreating ? (
                  <span className="thinking-indicator inline-flex">
                    <span className="dot" />
                    <span className="dot" />
                    <span className="dot" />
                    <span className="ml-2">Creating World</span>
                  </span>
                ) : (
                  "Create World"
                )}
              </button>
            </div>
          </motion.div>
        )}

        {/* ── Character Creation ───────────────────────────────── */}
        {phase === "characters" && sessionId && (
          <motion.div
            key="characters"
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, scale: 1.1 }}
            transition={{ duration: 0.6 }}
            className="relative z-10 w-full max-w-4xl px-6"
          >
            <CharacterCreation
              sessionId={sessionId}
              onComplete={handleStartGame}
            />
          </motion.div>
        )}

        {/* ── Launch Transition ────────────────────────────────── */}
        {phase === "launching" && (
          <motion.div
            key="launching"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="relative z-10 text-center"
          >
            <motion.div
              initial={{ scale: 1 }}
              animate={{ scale: [1, 1.2, 0] }}
              transition={{ duration: 1.5, ease: "easeInOut" }}
            >
              <h2 className="font-display text-5xl text-genesis-accent tracking-wider">
                {campaignName}
              </h2>
              <p className="text-genesis-text-dim mt-4 tracking-widest uppercase text-sm">
                The adventure begins...
              </p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
