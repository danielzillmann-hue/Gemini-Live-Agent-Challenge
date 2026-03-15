"use client";

import { Swords, Heart, Shield, Zap } from "lucide-react";
import { useGameStore } from "@/hooks/useGameStore";
import { cn, getHpColor, getHpPercentage } from "@/lib/utils";

export default function CombatTracker() {
  const { combat } = useGameStore();

  if (!combat || !combat.is_active) return null;

  return (
    <div className="h-full flex flex-col">
      <div className="genesis-panel-header flex items-center gap-2">
        <Swords className="w-4 h-4" />
        <span>Combat — Round {combat.round_number}</span>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
        {combat.combatants.map((combatant, idx) => {
          const isActive = idx === combat.current_turn_index;
          const hpPct = getHpPercentage(combatant.hp, combatant.max_hp);
          const hpColor = getHpColor(combatant.hp, combatant.max_hp);
          const isDead = combatant.hp <= 0;

          return (
            <div
              key={combatant.id}
              className={cn(
                "rounded-lg p-2.5 transition-all duration-300",
                isActive && "combat-initiative-active bg-genesis-accent/5",
                isDead && "opacity-40",
                !isActive && !isDead && "bg-genesis-bg/30",
              )}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  {isActive && (
                    <Zap className="w-3 h-3 text-genesis-accent animate-pulse" />
                  )}
                  <span
                    className={cn(
                      "text-sm font-display tracking-wider",
                      combatant.is_player ? "text-genesis-text" : "text-genesis-red",
                      isDead && "line-through",
                    )}
                  >
                    {combatant.name}
                  </span>
                </div>
                <span className="text-genesis-text-dim text-xs font-mono">
                  Init: {combatant.initiative}
                </span>
              </div>

              {/* HP Bar */}
              <div className="flex items-center gap-2">
                <Heart className="w-3 h-3 text-genesis-text-dim shrink-0" />
                <div className="flex-1 h-1.5 bg-genesis-bg rounded-full overflow-hidden">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all duration-500",
                      hpColor,
                      hpPct < 25 && "animate-pulse",
                    )}
                    style={{ width: `${hpPct}%` }}
                  />
                </div>
                <span className="text-genesis-text text-[10px] font-mono w-12 text-right">
                  {combatant.hp}/{combatant.max_hp}
                </span>
              </div>

              {/* Stats & Conditions */}
              <div className="flex items-center justify-between mt-1">
                <span className="text-genesis-text-dim text-[10px] flex items-center gap-1">
                  <Shield className="w-2.5 h-2.5" /> AC {combatant.armor_class}
                </span>
                <div className="flex gap-1">
                  {combatant.conditions.map((c) => (
                    <span
                      key={c}
                      className="px-1 py-0.5 bg-genesis-purple/20 text-genesis-purple text-[9px] rounded capitalize"
                    >
                      {c}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Phase Indicator */}
      <div className="p-3 border-t border-genesis-border">
        <div className="text-center text-genesis-text-dim text-xs tracking-wider uppercase">
          {combat.phase === "player_turn" && (
            <span className="text-genesis-accent">
              {combat.combatants[combat.current_turn_index]?.name}&apos;s Turn
            </span>
          )}
          {combat.phase === "enemy_turn" && (
            <span className="text-genesis-red">Enemy Turn</span>
          )}
          {combat.phase === "ended" && (
            <span className="text-genesis-green">Combat Ended</span>
          )}
        </div>
      </div>
    </div>
  );
}
