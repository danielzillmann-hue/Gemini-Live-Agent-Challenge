"use client";

import { useEffect, useRef } from "react";
import { useGameStore } from "@/hooks/useGameStore";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

interface QueueEntry {
  text: string;
  voiceType: string;
}

// Map NPC voice_style to TTS voice type
const VOICE_MAP: Record<string, string> = {
  gruff: "npc_gruff",
  noble: "npc_noble",
  mysterious: "npc_mysterious",
  cheerful: "npc_cheerful",
  neutral: "npc_male",
  warm: "npc_female_warm",
  stern: "npc_female_stern",
  old: "npc_old",
  young: "npc_young",
};

export default function NarratorVoice() {
  const { storyLog, narratorVoiceEnabled } = useGameStore();
  const lastSpokenIndex = useRef(0);
  const audioQueue = useRef<QueueEntry[]>([]);
  const isPlaying = useRef(false);
  const currentAudio = useRef<HTMLAudioElement | null>(null);

  function cleanText(text: string): string {
    return text
      .replace(/\[NEW_SCENE\]/g, "")
      .replace(/\[CINEMATIC\]/g, "")
      .replace(/\[NPC_INTRO:.*?\]/g, "")
      .replace(/\[COMBAT_START\]/g, "")
      .replace(/```[\s\S]*?```/g, "")
      .replace(/\{[\s\S]*?\}/g, "")
      .trim();
  }

  async function playNext() {
    if (!narratorVoiceEnabled || audioQueue.current.length === 0) {
      isPlaying.current = false;
      return;
    }

    isPlaying.current = true;
    const { text, voiceType } = audioQueue.current.shift()!;

    try {
      const res = await fetch(`${API_URL}/api/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice_type: voiceType }),
      });

      if (res.ok) {
        const data = await res.json();
        if (data.audio && !data.fallback) {
          const audio = new Audio(`data:audio/mp3;base64,${data.audio}`);
          currentAudio.current = audio;
          audio.onended = () => {
            currentAudio.current = null;
            playNext();
          };
          audio.onerror = () => {
            currentAudio.current = null;
            fallbackBrowserTTS(text);
          };
          await audio.play();
          return;
        }
      }
    } catch {
      // Fall through to browser TTS
    }

    fallbackBrowserTTS(text);
  }

  function fallbackBrowserTTS(text: string) {
    if (!window.speechSynthesis || !narratorVoiceEnabled) {
      playNext();
      return;
    }

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.9;
    utterance.pitch = 0.85;
    utterance.volume = 0.9;

    const voices = window.speechSynthesis.getVoices();
    const preferred = voices.find(
      (v) => v.lang.startsWith("en") && /daniel|james|david|george/i.test(v.name)
    );
    if (preferred) utterance.voice = preferred;

    utterance.onend = () => playNext();
    utterance.onerror = () => playNext();
    window.speechSynthesis.speak(utterance);
  }

  useEffect(() => {
    if (!narratorVoiceEnabled) return;

    const newEntries = storyLog.slice(lastSpokenIndex.current);
    lastSpokenIndex.current = storyLog.length;

    for (const entry of newEntries) {
      // Only speak narration, not dialogue (Live API handles NPC voice directly)
      if (entry.type !== "narration") continue;

      const text = cleanText(entry.content);
      if (!text || text.length < 3) continue;

      // Determine voice based on entry type and speaker
      let voiceType = "narrator";
      if (entry.type === "dialogue" && entry.speaker) {
        // Try to match NPC voice style from the store
        const npcs = useGameStore.getState().npcs;
        const npc = Object.values(npcs).find(
          (n) => n.name.toLowerCase() === (entry.speaker || "").toLowerCase()
        );
        if (npc) {
          voiceType = VOICE_MAP[npc.voice_style] || "npc_male";
        } else {
          voiceType = "npc_male";
        }
      }

      audioQueue.current.push({ text, voiceType });
    }

    if (!isPlaying.current && audioQueue.current.length > 0) {
      playNext();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storyLog.length, narratorVoiceEnabled]);

  useEffect(() => {
    if (!narratorVoiceEnabled) {
      audioQueue.current = [];
      isPlaying.current = false;
      if (currentAudio.current) {
        currentAudio.current.pause();
        currentAudio.current = null;
      }
      window.speechSynthesis?.cancel();
    }
  }, [narratorVoiceEnabled]);

  return null;
}
