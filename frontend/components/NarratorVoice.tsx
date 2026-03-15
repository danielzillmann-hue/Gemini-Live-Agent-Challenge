"use client";

import { useEffect, useRef } from "react";
import { useGameStore } from "@/hooks/useGameStore";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

/**
 * NarratorVoice — reads narration and dialogue aloud using
 * Google Cloud Text-to-Speech (natural voice) with browser TTS fallback.
 */
export default function NarratorVoice() {
  const { storyLog, narratorVoiceEnabled } = useGameStore();
  const lastSpokenIndex = useRef(0);
  const audioQueue = useRef<string[]>([]);
  const isPlaying = useRef(false);
  const currentAudio = useRef<HTMLAudioElement | null>(null);

  function cleanText(text: string): string {
    return text
      .replace(/\[NEW_SCENE\]/g, "")
      .replace(/\[CINEMATIC\]/g, "")
      .replace(/\[NPC_INTRO:.*?\]/g, "")
      .replace(/\[COMBAT_START\]/g, "")
      .replace(/```[\s\S]*?```/g, "") // Remove code blocks
      .replace(/\{[\s\S]*?\}/g, "") // Remove JSON
      .trim();
  }

  async function playNext() {
    if (!narratorVoiceEnabled || audioQueue.current.length === 0) {
      isPlaying.current = false;
      return;
    }

    isPlaying.current = true;
    const text = audioQueue.current.shift()!;

    try {
      // Try Cloud TTS first (natural voice)
      const res = await fetch(`${API_URL}/api/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice_type: "narrator" }),
      });

      if (res.ok) {
        const data = await res.json();
        if (data.audio && !data.fallback) {
          // Play the Cloud TTS audio
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
      // Cloud TTS unavailable, fall through to browser TTS
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

    // Pick best available voice
    const voices = window.speechSynthesis.getVoices();
    const preferred = voices.find(
      (v) => v.lang.startsWith("en") && /daniel|james|david|george/i.test(v.name)
    );
    if (preferred) utterance.voice = preferred;

    utterance.onend = () => playNext();
    utterance.onerror = () => playNext();
    window.speechSynthesis.speak(utterance);
  }

  // Queue new narration entries
  useEffect(() => {
    if (!narratorVoiceEnabled) return;

    const newEntries = storyLog.slice(lastSpokenIndex.current);
    lastSpokenIndex.current = storyLog.length;

    for (const entry of newEntries) {
      if (entry.type !== "narration" && entry.type !== "dialogue") continue;

      const text = cleanText(entry.content);
      if (!text || text.length < 3) continue;

      audioQueue.current.push(text);
    }

    if (!isPlaying.current && audioQueue.current.length > 0) {
      playNext();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storyLog.length, narratorVoiceEnabled]);

  // Stop everything when disabled
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
