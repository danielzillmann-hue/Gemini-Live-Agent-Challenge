"use client";

import { User, Heart, Shield, Sparkles } from "lucide-react";
import { useGameStore } from "@/hooks/useGameStore";
import { cn, getHpColor, getHpPercentage } from "@/lib/utils";

export default function PartyPanel() {
  const { players } = useGameStore();

  return (
    <div className="h-full flex flex-col">
      <div className="genesis-panel-header">Party</div>
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {players.map((char) => {
          const hpPct = getHpPercentage(char.hp, char.max_hp);
          const hpColor = getHpColor(char.hp, char.max_hp);

          return (
            <div key={char.id} className="genesis-panel p-3 space-y-2">
              {/* Header */}
              <div className="flex items-center gap-2.5">
                {char.portrait_url ? (
                  <img
                    src={char.portrait_url}
                    alt={char.name}
                    className="w-12 h-12 rounded-lg object-cover border border-genesis-border"
                  />
                ) : (
                  <div className="w-12 h-12 rounded-lg bg-genesis-bg flex items-center justify-center border border-genesis-border">
                    <User className="w-5 h-5 text-genesis-text-dim" />
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <div className="font-display text-genesis-text text-sm tracking-wider truncate">
                    {char.name}
                  </div>
                  <div className="text-genesis-text-dim text-xs capitalize">
                    Lvl {char.level} {char.race} {char.character_class}
                  </div>
                </div>
              </div>

              {/* HP Bar */}
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-genesis-text-dim flex items-center gap-1">
                    <Heart className="w-3 h-3" /> HP
                  </span>
                  <span className="text-genesis-text font-mono">
                    {char.hp}/{char.max_hp}
                  </span>
                </div>
                <div className="h-2 bg-genesis-bg rounded-full overflow-hidden">
                  <div
                    className={cn("h-full rounded-full transition-all duration-700", hpColor, hpPct < 25 && "animate-pulse")}
                    style={{ width: `${hpPct}%` }}
                  />
                </div>
              </div>

              {/* Stats */}
              <div className="flex justify-between text-xs text-genesis-text-dim pt-1">
                <span className="flex items-center gap-1">
                  <Shield className="w-3 h-3" /> AC {char.armor_class}
                </span>
                <span className="flex items-center gap-1">
                  <Sparkles className="w-3 h-3" /> XP {char.xp}
                </span>
                <span>{char.gold}g</span>
              </div>

              {/* Ability Scores */}
              <div className="grid grid-cols-3 gap-1 pt-1">
                {[
                  { key: "strength", label: "STR" },
                  { key: "dexterity", label: "DEX" },
                  { key: "constitution", label: "CON" },
                  { key: "intelligence", label: "INT" },
                  { key: "wisdom", label: "WIS" },
                  { key: "charisma", label: "CHA" },
                ].map(({ key, label }) => (
                  <div key={key} className="text-center bg-genesis-bg/50 rounded px-1 py-0.5">
                    <div className="text-genesis-text-dim text-[9px] tracking-wider">{label}</div>
                    <div className="text-genesis-text text-xs font-mono">
                      {char.ability_scores[key as keyof typeof char.ability_scores]}
                    </div>
                  </div>
                ))}
              </div>

              {/* Conditions */}
              {char.conditions.length > 0 && (
                <div className="flex flex-wrap gap-1 pt-1">
                  {char.conditions.map((c) => (
                    <span key={c} className="px-1.5 py-0.5 bg-genesis-red/20 text-genesis-red text-[10px] rounded capitalize">
                      {c}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {players.length === 0 && (
          <div className="text-genesis-text-dim text-sm text-center py-8">
            No characters yet
          </div>
        )}
      </div>
    </div>
  );
}
