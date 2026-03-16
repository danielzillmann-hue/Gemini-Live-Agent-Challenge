"use client";

import { useState, useRef, useCallback } from "react";
import { Mic, MicOff, Phone, PhoneOff } from "lucide-react";
import { cn } from "@/lib/utils";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8080";

interface LiveVoiceProps {
  sessionId: string;
  npcId: string;
  npcName: string;
  onTranscription?: (text: string, speaker: string) => void;
  onEnd?: () => void;
}

/**
 * LiveVoice — Real-time voice conversation with an NPC using Gemini Live API.
 *
 * Captures microphone audio as PCM, streams to backend via WebSocket,
 * receives NPC audio responses and plays them in real-time.
 */
export default function LiveVoice({
  sessionId, npcId, npcName, onTranscription, onEnd,
}: LiveVoiceProps) {
  const [isActive, setIsActive] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [status, setStatus] = useState<string>("");
  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const npcSpeakingRef = useRef(false);

  const startConversation = useCallback(async () => {
    try {
      setStatus("Connecting...");

      // Connect to Live API WebSocket
      const ws = new WebSocket(`${WS_URL}/ws/${sessionId}/live/${npcId}`);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus(`Waiting for ${npcName}...`);
      };

      ws.onmessage = async (event) => {
        const msg = JSON.parse(event.data);

        if (msg.type === "live_ready") {
          setStatus(`Speaking with ${npcName}`);
          setIsActive(true);
          await startMicrophone();
        } else if (msg.type === "audio_response") {
          // Play NPC audio (don't await — prevents blocking message handler)
          npcSpeakingRef.current = true;
          playAudio(msg.data.audio);
        } else if (msg.type === "live_transcription") {
          onTranscription?.(msg.data.text, msg.data.speaker);
        } else if (msg.type === "turn_complete") {
          // NPC finished speaking — unmute mic for next player input
          npcSpeakingRef.current = false;
          setStatus(`Speaking with ${npcName}`);
        } else if (msg.type === "error") {
          setStatus(`Error: ${msg.data.message}`);
          stopConversation();
        }
      };

      ws.onclose = (event) => {
        if (event.code !== 1000) {
          setStatus("Voice chat unavailable — NPC will respond via text");
        }
        stopConversation();
      };

      ws.onerror = () => {
        setStatus("Voice chat unavailable");
        stopConversation();
      };
    } catch (err) {
      setStatus("Failed to start");
      console.error("Live voice error:", err);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, npcId, npcName]);

  async function startMicrophone() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      streamRef.current = stream;

      const audioContext = new AudioContext({ sampleRate: 16000 });
      audioContextRef.current = audioContext;

      const source = audioContext.createMediaStreamSource(stream);
      // Use ScriptProcessorNode to capture raw PCM (deprecated but widely supported)
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (e) => {
        // Don't send mic audio while NPC is speaking (prevents echo/confusion)
        if (isMuted || npcSpeakingRef.current || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

        const inputData = e.inputBuffer.getChannelData(0);
        // Convert Float32 to Int16 PCM
        const pcm = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcm[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }

        // Send as base64
        const b64 = btoa(String.fromCharCode(...new Uint8Array(pcm.buffer)));
        wsRef.current.send(JSON.stringify({
          type: "audio_chunk",
          data: { audio: b64 },
        }));
      };

      source.connect(processor);
      processor.connect(audioContext.destination);
    } catch (err) {
      console.error("Microphone error:", err);
      setStatus("Microphone access denied");
    }
  }

  // Shared playback context for smooth audio (Gemini outputs 24kHz 16-bit PCM)
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const nextPlayTime = useRef(0);

  function getPlaybackCtx(): AudioContext {
    if (!playbackCtxRef.current || playbackCtxRef.current.state === "closed") {
      playbackCtxRef.current = new AudioContext({ sampleRate: 24000 });
    }
    if (playbackCtxRef.current.state === "suspended") {
      playbackCtxRef.current.resume();
    }
    return playbackCtxRef.current;
  }

  async function playAudio(base64Audio: string) {
    try {
      // Decode base64 to raw bytes
      const raw = Uint8Array.from(atob(base64Audio), (c) => c.charCodeAt(0));

      // Ensure we have an even number of bytes (16-bit = 2 bytes per sample)
      const validLength = raw.length - (raw.length % 2);
      if (validLength === 0) return;

      // Create a proper ArrayBuffer and view for Int16 interpretation
      const buffer = new ArrayBuffer(validLength);
      const view = new Uint8Array(buffer);
      view.set(raw.subarray(0, validLength));

      // Interpret as 16-bit little-endian PCM
      const dataView = new DataView(buffer);
      const numSamples = validLength / 2;
      const float32 = new Float32Array(numSamples);
      for (let i = 0; i < numSamples; i++) {
        const sample = dataView.getInt16(i * 2, true); // little-endian
        float32[i] = sample / 32768.0;
      }

      // Create audio buffer at 24kHz (Gemini Live API output rate)
      const ctx = getPlaybackCtx();
      const audioBuffer = ctx.createBuffer(1, float32.length, 24000);
      audioBuffer.getChannelData(0).set(float32);

      // Schedule for gapless sequential playback
      const now = ctx.currentTime;
      if (nextPlayTime.current < now) {
        nextPlayTime.current = now + 0.05; // Small buffer to prevent underrun
      }

      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);
      source.start(nextPlayTime.current);
      nextPlayTime.current += audioBuffer.duration;
    } catch (err) {
      console.error("Audio playback error:", err);
    }
  }

  function stopConversation() {
    // Send end signal
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "end_conversation" }));
      wsRef.current.close();
    }
    wsRef.current = null;

    // Stop microphone
    processorRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    audioContextRef.current?.close();
    // Stop playback
    playbackCtxRef.current?.close();
    playbackCtxRef.current = null;
    nextPlayTime.current = 0;

    setIsActive(false);
    // Don't clear error status — let user see what went wrong
    setStatus((prev) => prev.startsWith("Error") || prev.includes("unavailable") ? prev : "");
    onEnd?.();
  }

  function toggleMute() {
    setIsMuted(!isMuted);
  }

  if (!isActive) {
    return (
      <button
        onClick={startConversation}
        className="genesis-button-secondary text-xs px-3 py-1.5 flex items-center gap-1.5"
        title={`Talk to ${npcName}`}
      >
        <Phone className="w-3.5 h-3.5" />
        Talk to {npcName}
      </button>
    );
  }

  return (
    <div className="genesis-panel p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-genesis-green animate-pulse" />
          <span className="text-genesis-accent text-xs font-display tracking-wider">
            {status}
          </span>
        </div>
        <div className="flex gap-1">
          <button
            onClick={toggleMute}
            className={cn(
              "w-7 h-7 rounded flex items-center justify-center transition-colors",
              isMuted ? "text-genesis-red" : "text-genesis-green"
            )}
          >
            {isMuted ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
          </button>
          <button
            onClick={stopConversation}
            className="w-7 h-7 rounded flex items-center justify-center text-genesis-red hover:bg-genesis-red/10"
          >
            <PhoneOff className="w-4 h-4" />
          </button>
        </div>
      </div>
      <p className="text-genesis-text-dim text-[10px]">
        Speak naturally. {npcName} will respond in real-time.
      </p>
    </div>
  );
}
