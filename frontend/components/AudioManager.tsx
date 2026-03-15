"use client";

import { useEffect, useRef } from "react";
import { useGameStore } from "@/hooks/useGameStore";

/**
 * Ambient audio manager — plays mood-appropriate background music
 * using the Web Audio API with generated tones/drones.
 *
 * This creates procedural ambient soundscapes rather than requiring
 * pre-recorded audio files, so it works without any external assets.
 */

const MOOD_CONFIGS: Record<
  string,
  { baseFreq: number; harmonics: number[]; filterFreq: number; gain: number; tempo: number }
> = {
  peaceful: { baseFreq: 220, harmonics: [1, 1.5, 2, 3], filterFreq: 800, gain: 0.06, tempo: 0.3 },
  mysterious: { baseFreq: 165, harmonics: [1, 1.26, 1.5, 2.5], filterFreq: 600, gain: 0.07, tempo: 0.2 },
  tense: { baseFreq: 110, harmonics: [1, 1.06, 1.5, 2.12], filterFreq: 1200, gain: 0.08, tempo: 0.5 },
  combat: { baseFreq: 82, harmonics: [1, 1.33, 1.5, 2, 3], filterFreq: 2000, gain: 0.1, tempo: 1.0 },
  epic: { baseFreq: 146, harmonics: [1, 1.25, 1.5, 2, 2.5, 3], filterFreq: 1600, gain: 0.09, tempo: 0.7 },
  triumphant: { baseFreq: 196, harmonics: [1, 1.25, 1.5, 2, 3], filterFreq: 2000, gain: 0.08, tempo: 0.6 },
  sad: { baseFreq: 185, harmonics: [1, 1.2, 1.5, 2], filterFreq: 500, gain: 0.05, tempo: 0.15 },
};

export default function AudioManager() {
  const { musicMood, musicIntensity, isMuted } = useGameStore();
  const ctxRef = useRef<AudioContext | null>(null);
  const oscillatorsRef = useRef<OscillatorNode[]>([]);
  const gainNodeRef = useRef<GainNode | null>(null);
  const filterRef = useRef<BiquadFilterNode | null>(null);
  const lfoRef = useRef<OscillatorNode | null>(null);

  useEffect(() => {
    // Create audio context on first mood change (requires user gesture)
    if (!ctxRef.current) {
      try {
        ctxRef.current = new AudioContext();
      } catch {
        return; // Audio not supported
      }
    }

    const ctx = ctxRef.current;
    if (ctx.state === "suspended") {
      ctx.resume().catch(() => {});
    }

    // Clean up previous oscillators
    oscillatorsRef.current.forEach((osc) => {
      try { osc.stop(); } catch { /* already stopped */ }
    });
    if (lfoRef.current) {
      try { lfoRef.current.stop(); } catch { /* already stopped */ }
    }

    if (isMuted) {
      oscillatorsRef.current = [];
      return;
    }

    const config = MOOD_CONFIGS[musicMood] || MOOD_CONFIGS.peaceful;
    const masterGain = ctx.createGain();
    masterGain.gain.value = config.gain * musicIntensity;
    gainNodeRef.current = masterGain;

    const filter = ctx.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = config.filterFreq;
    filter.Q.value = 1;
    filterRef.current = filter;

    filter.connect(masterGain);
    masterGain.connect(ctx.destination);

    // Create harmonic oscillators
    const newOscs: OscillatorNode[] = [];
    config.harmonics.forEach((harmonic, i) => {
      const osc = ctx.createOscillator();
      const oscGain = ctx.createGain();
      osc.type = i === 0 ? "sine" : "triangle";
      osc.frequency.value = config.baseFreq * harmonic;
      oscGain.gain.value = 1 / (i + 1) / config.harmonics.length;
      osc.connect(oscGain);
      oscGain.connect(filter);
      osc.start();
      newOscs.push(osc);
    });
    oscillatorsRef.current = newOscs;

    // LFO for gentle pulsing
    const lfo = ctx.createOscillator();
    const lfoGain = ctx.createGain();
    lfo.type = "sine";
    lfo.frequency.value = config.tempo * 0.1;
    lfoGain.gain.value = config.gain * 0.3;
    lfo.connect(lfoGain);
    lfoGain.connect(masterGain.gain);
    lfo.start();
    lfoRef.current = lfo;

    return () => {
      newOscs.forEach((osc) => {
        try { osc.stop(); } catch { /* already stopped */ }
      });
      try { lfo.stop(); } catch { /* already stopped */ }
    };
  }, [musicMood, musicIntensity, isMuted]);

  // Update gain when intensity or mute changes
  useEffect(() => {
    if (gainNodeRef.current) {
      const config = MOOD_CONFIGS[musicMood] || MOOD_CONFIGS.peaceful;
      gainNodeRef.current.gain.setTargetAtTime(
        isMuted ? 0 : config.gain * musicIntensity,
        ctxRef.current?.currentTime || 0,
        0.5
      );
    }
  }, [musicIntensity, isMuted, musicMood]);

  return null; // Invisible component
}
