"use client";

import { BookOpen, Circle, CheckCircle2 } from "lucide-react";
import { useGameStore } from "@/hooks/useGameStore";
import { cn } from "@/lib/utils";

export default function QuestLog() {
  const { world } = useGameStore();
  const quests = world?.quests || [];
  const activeQuests = quests.filter((q) => q.is_active && !q.is_complete);
  const completedQuests = quests.filter((q) => q.is_complete);

  return (
    <div className="h-full flex flex-col">
      <div className="genesis-panel-header flex items-center gap-2">
        <BookOpen className="w-4 h-4" />
        <span>Quest Log</span>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {activeQuests.length === 0 && completedQuests.length === 0 && (
          <div className="text-genesis-text-dim text-sm text-center py-8">
            No quests yet. Your story awaits...
          </div>
        )}

        {activeQuests.length > 0 && (
          <div>
            <div className="text-genesis-accent text-[10px] tracking-[0.2em] uppercase mb-2">
              Active Quests
            </div>
            <div className="space-y-2">
              {activeQuests.map((quest) => (
                <div key={quest.id} className="genesis-panel p-3">
                  <h4 className="font-display text-genesis-text text-sm tracking-wider mb-1">
                    {quest.title}
                  </h4>
                  {quest.description && (
                    <p className="text-genesis-text-dim text-xs leading-relaxed mb-2">
                      {quest.description}
                    </p>
                  )}
                  {quest.objectives.length > 0 && (
                    <div className="space-y-1">
                      {quest.objectives.map((obj, i) => {
                        const done = quest.completed_objectives.includes(i);
                        return (
                          <div key={i} className="flex items-start gap-1.5">
                            {done ? (
                              <CheckCircle2 className="w-3.5 h-3.5 text-genesis-green shrink-0 mt-0.5" />
                            ) : (
                              <Circle className="w-3.5 h-3.5 text-genesis-text-dim shrink-0 mt-0.5" />
                            )}
                            <span
                              className={cn(
                                "text-xs leading-relaxed",
                                done ? "text-genesis-text-dim line-through" : "text-genesis-text",
                              )}
                            >
                              {obj}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                  {(quest.reward_xp > 0 || quest.reward_gold > 0) && (
                    <div className="flex gap-3 mt-2 text-genesis-text-dim text-[10px]">
                      {quest.reward_xp > 0 && <span>+{quest.reward_xp} XP</span>}
                      {quest.reward_gold > 0 && <span>+{quest.reward_gold}g</span>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {completedQuests.length > 0 && (
          <div>
            <div className="text-genesis-green/70 text-[10px] tracking-[0.2em] uppercase mb-2">
              Completed
            </div>
            <div className="space-y-1">
              {completedQuests.map((quest) => (
                <div key={quest.id} className="px-3 py-2 rounded-lg bg-genesis-bg/30">
                  <span className="text-genesis-text-dim text-xs line-through">
                    {quest.title}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
