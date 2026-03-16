"use client";

import { useParams } from "next/navigation";
import { Users, User, Skull } from "lucide-react";
import { useGameStore } from "@/hooks/useGameStore";
import { cn } from "@/lib/utils";
import LiveVoice from "@/components/LiveVoice";

function getRelationshipLabel(rel: number): { label: string; color: string } {
  if (rel >= 75) return { label: "Allied", color: "text-genesis-green" };
  if (rel >= 25) return { label: "Friendly", color: "text-genesis-blue" };
  if (rel >= -25) return { label: "Neutral", color: "text-genesis-text-dim" };
  if (rel >= -75) return { label: "Unfriendly", color: "text-yellow-500" };
  return { label: "Hostile", color: "text-genesis-red" };
}

export default function NPCJournal() {
  const params = useParams();
  const sessionId = params?.sessionId as string || "";
  const { npcs, world } = useGameStore();
  const allNpcs = {
    ...npcs,
    ...(world?.npcs || {}),
  };
  const npcList = Object.values(allNpcs);

  return (
    <div className="h-full flex flex-col">
      <div className="genesis-panel-header flex items-center gap-2">
        <Users className="w-4 h-4" />
        <span>NPC Journal</span>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {npcList.length === 0 && (
          <div className="text-genesis-text-dim text-sm text-center py-8">
            No NPCs encountered yet
          </div>
        )}

        {npcList.map((npc) => {
          const rel = getRelationshipLabel(npc.relationship);
          return (
            <div key={npc.id} className="genesis-panel p-3">
              <div className="flex items-start gap-2.5">
                {npc.portrait_url ? (
                  <img
                    src={npc.portrait_url}
                    alt={npc.name}
                    className="w-11 h-11 rounded-lg object-cover border border-genesis-border"
                  />
                ) : (
                  <div className="w-11 h-11 rounded-lg bg-genesis-bg flex items-center justify-center border border-genesis-border">
                    {npc.is_hostile ? (
                      <Skull className="w-4 h-4 text-genesis-red" />
                    ) : (
                      <User className="w-4 h-4 text-genesis-text-dim" />
                    )}
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="font-display text-genesis-text text-sm tracking-wider truncate">
                      {npc.name}
                    </span>
                    <span className={cn("text-[9px] tracking-wider uppercase", rel.color)}>
                      {rel.label}
                    </span>
                  </div>
                  {npc.description && (
                    <p className="text-genesis-text-dim text-[11px] leading-relaxed mt-0.5 line-clamp-2">
                      {npc.description}
                    </p>
                  )}
                  {npc.location && (
                    <span className="text-genesis-text-dim text-[9px] mt-1 block">
                      Last seen: {npc.location}
                    </span>
                  )}
                </div>
              </div>

              {/* Known Info */}
              {npc.known_info && npc.known_info.length > 0 && (
                <div className="mt-2 pt-2 border-t border-genesis-border/50">
                  <div className="text-genesis-text-dim text-[9px] tracking-wider uppercase mb-1">
                    Known Info
                  </div>
                  <ul className="space-y-0.5">
                    {npc.known_info.map((info, i) => (
                      <li key={i} className="text-genesis-text-dim text-[10px] pl-2 border-l border-genesis-border">
                        {info}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Live Voice Conversation */}
              {!npc.is_hostile && sessionId && (
                <div className="mt-2 pt-2 border-t border-genesis-border/50">
                  <LiveVoice
                    sessionId={sessionId}
                    npcId={npc.id}
                    npcName={npc.name}
                    onTranscription={(text, speaker) => {
                      useGameStore.getState().addStoryEntry({
                        type: "dialogue",
                        content: text,
                        speaker,
                      });
                    }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
