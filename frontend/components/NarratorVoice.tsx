"use client";

import { useEffect, useRef } from "react";
import { useGameStore } from "@/hooks/useGameStore";

/**
 * NarratorVoice — reads narration and dialogue aloud using the
 * browser's Speech Synthesis API. Can be toggled on/off by players.
 */
export default function NarratorVoice() {
  const { storyLog, narratorVoiceEnabled } = useGameStore();
  const lastSpokenIndex = useRef(0);
  const voiceRef = useRef<SpeechSynthesisVoice | null>(null);

  // Pick a good narrator voice once available
  useEffect(() => {
    function pickVoice() {
      const voices = window.speechSynthesis?.getVoices() || [];
      // Prefer a deep English voice for narrator feel
      const preferred = voices.find(
        (v) => v.lang.startsWith("en") && /male|daniel|james|david|george/i.test(v.name)
      );
      voiceRef.current = preferred || voices.find((v) => v.lang.startsWith("en")) || voices[0] || null;
    }

    pickVoice();
    window.speechSynthesis?.addEventListener("voiceschanged", pickVoice);
    return () => {
      window.speechSynthesis?.removeEventListener("voiceschanged", pickVoice);
    };
  }, []);

  // Speak new narration entries
  useEffect(() => {
    if (!narratorVoiceEnabled || !window.speechSynthesis) return;

    const newEntries = storyLog.slice(lastSpokenIndex.current);
    lastSpokenIndex.current = storyLog.length;

    for (const entry of newEntries) {
      // Only speak narration and dialogue, not system messages or dice
      if (entry.type !== "narration" && entry.type !== "dialogue") continue;

      const text = entry.content
        .replace(/\[NEW_SCENE\]/g, "")
        .replace(/\[CINEMATIC\]/g, "")
        .replace(/\[NPC_INTRO:.*?\]/g, "")
        .replace(/\[COMBAT_START\]/g, "")
        .trim();

      if (!text) continue;

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 0.9;
      utterance.pitch = entry.type === "dialogue" ? 1.1 : 0.85;
      utterance.volume = 0.9;
      if (voiceRef.current) {
        utterance.voice = voiceRef.current;
      }

      window.speechSynthesis.speak(utterance);
    }
  }, [storyLog, narratorVoiceEnabled]);

  // Cancel speech when disabled
  useEffect(() => {
    if (!narratorVoiceEnabled) {
      window.speechSynthesis?.cancel();
    }
  }, [narratorVoiceEnabled]);

  return null;
}
