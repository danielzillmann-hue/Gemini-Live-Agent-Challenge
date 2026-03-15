"use client";

import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { Dice5, Swords, ImageIcon, Film, Info } from "lucide-react";
import { useGameStore } from "@/hooks/useGameStore";
import type { StoryEntry } from "@/lib/types";
import { cn } from "@/lib/utils";

function EntryIcon({ type }: { type: StoryEntry["type"] }) {
  switch (type) {
    case "dice": return <Dice5 className="w-3.5 h-3.5 text-genesis-accent" />;
    case "combat": return <Swords className="w-3.5 h-3.5 text-genesis-red" />;
    case "image": return <ImageIcon className="w-3.5 h-3.5 text-genesis-blue" />;
    case "video": return <Film className="w-3.5 h-3.5 text-genesis-purple" />;
    case "system": return <Info className="w-3.5 h-3.5 text-genesis-text-dim" />;
    default: return null;
  }
}

function StoryEntryItem({ entry }: { entry: StoryEntry }) {
  const isNarration = entry.type === "narration";
  const isDialogue = entry.type === "dialogue";
  const isAction = entry.type === "action";
  const isDice = entry.type === "dice";
  const isSystem = entry.type === "system";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className={cn(
        "py-2 px-3 rounded-lg",
        isAction && "bg-genesis-accent/5 border-l-2 border-genesis-accent",
        isDice && "bg-genesis-bg",
        isSystem && "text-center",
      )}
    >
      <div className="flex items-start gap-2">
        <EntryIcon type={entry.type} />
        <div className="flex-1 min-w-0">
          {isAction && (
            <span className="text-genesis-accent text-xs font-display tracking-wider block mb-0.5">
              {entry.speaker || "Player"}
            </span>
          )}
          {isDialogue && entry.speaker && (
            <span className="text-genesis-accent text-xs font-display tracking-wider block mb-0.5">
              {entry.speaker}
            </span>
          )}
          <p
            className={cn(
              "text-sm leading-relaxed whitespace-pre-wrap",
              isNarration && "narration-text",
              isDialogue && "dialogue-text",
              isAction && "text-genesis-text/80",
              isDice && "text-genesis-text font-mono text-xs",
              isSystem && "text-genesis-text-dim text-xs italic",
            )}
          >
            {entry.content}
          </p>

          {/* Dice Result Badge */}
          {isDice && entry.diceResult && (
            <div className="flex items-center gap-2 mt-1.5">
              <span
                className={cn(
                  "dice-roll text-sm",
                  entry.diceResult.is_critical && "dice-roll-crit",
                )}
              >
                {entry.diceResult.value}
              </span>
              {entry.diceResult.dc && (
                <span className="text-genesis-text-dim text-xs">
                  vs DC {entry.diceResult.dc} —{" "}
                  <span className={entry.diceResult.success ? "text-genesis-green" : "text-genesis-red"}>
                    {entry.diceResult.success ? "Success" : "Failure"}
                  </span>
                </span>
              )}
            </div>
          )}

          {/* Inline Image */}
          {entry.mediaType === "image" && entry.mediaUrl && (
            <img
              src={entry.mediaUrl}
              alt={entry.content}
              className="mt-2 rounded-lg max-h-48 object-cover border border-genesis-border"
            />
          )}
        </div>
      </div>
    </motion.div>
  );
}

export default function NarrativeLog() {
  const { storyLog, isThinking } = useGameStore();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [storyLog.length]);

  return (
    <div className="genesis-panel h-full flex flex-col overflow-hidden">
      <div className="genesis-panel-header shrink-0">Narrative</div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-1">
        {storyLog.length === 0 && (
          <div className="flex items-center justify-center h-full text-genesis-text-dim text-sm">
            The story has yet to begin...
          </div>
        )}
        {storyLog.map((entry) => (
          <StoryEntryItem key={entry.id} entry={entry} />
        ))}
        {isThinking && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="py-2 px-3"
          >
            <div className="thinking-indicator">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
              <span className="ml-2 text-genesis-text-dim text-xs">
                The Game Master weaves the tale...
              </span>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}
