"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Mic, MicOff, PhoneCall, PhoneOff } from "lucide-react";
import { useGameStore } from "@/hooks/useGameStore";
import { cn } from "@/lib/utils";

/* eslint-disable @typescript-eslint/no-explicit-any */

interface ChatPanelProps {
  send: (type: string, data: Record<string, unknown>) => void;
  myName: string;
}

export default function ChatPanel({ send, myName }: ChatPanelProps) {
  const { chatMessages, playersOnline } = useGameStore();
  const [message, setMessage] = useState("");
  const [voiceActive, setVoiceActive] = useState(false);
  const [isMicMuted, setIsMicMuted] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const peerConnections = useRef<Map<string, RTCPeerConnection>>(new Map());
  const localStream = useRef<MediaStream | null>(null);
  const audioElements = useRef<Map<string, HTMLAudioElement>>(new Map());

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [chatMessages.length]);

  function handleSend() {
    const text = message.trim();
    if (!text) return;
    send("player_chat", { sender: myName, message: text });
    setMessage("");
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  // ── WebRTC Voice Chat ──────────────────────────────────────────────────

  const handleSignal = useCallback(
    (msg: Record<string, unknown>) => {
      const data = (msg.data || {}) as Record<string, unknown>;
      const signalType = data.signal_type as string;
      const fromId = data.from_id as string;

      if (!fromId || fromId === myName) return;

      if (signalType === "offer") {
        handleOffer(fromId, data.sdp as string);
      } else if (signalType === "answer") {
        handleAnswer(fromId, data.sdp as string);
      } else if (signalType === "ice_candidate") {
        handleIceCandidate(fromId, data.candidate as any);
      } else if (signalType === "voice_join") {
        // New peer joined — create offer
        if (voiceActive) {
          createOffer(fromId);
        }
      } else if (signalType === "voice_leave") {
        closePeerConnection(fromId);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [voiceActive, myName]
  );

  // Register signal handler on the WebSocket
  useEffect(() => {
    const origHandler = useGameStore.getState().handleWSMessage;
    const wrappedHandler = (msg: Record<string, unknown>) => {
      if ((msg.type as string) === "webrtc_signal") {
        handleSignal(msg);
      }
      origHandler(msg);
    };
    useGameStore.setState({ handleWSMessage: wrappedHandler });

    return () => {
      useGameStore.setState({ handleWSMessage: origHandler });
      // Clean up all WebRTC resources on unmount
      peerConnections.current.forEach((pc) => pc.close());
      peerConnections.current.clear();
      audioElements.current.forEach((a) => a.pause());
      audioElements.current.clear();
      localStream.current?.getTracks().forEach((t) => t.stop());
    };
  }, [handleSignal]);

  function getOrCreatePeer(peerId: string): RTCPeerConnection {
    if (peerConnections.current.has(peerId)) {
      return peerConnections.current.get(peerId)!;
    }

    const pc = new RTCPeerConnection({
      iceServers: [
        { urls: "stun:stun.l.google.com:19302" },
        { urls: "stun:stun1.l.google.com:19302" },
      ],
    });

    pc.onicecandidate = (event) => {
      if (event.candidate) {
        send("webrtc_signal", {
          signal_type: "ice_candidate",
          from_id: myName,
          to_id: peerId,
          candidate: event.candidate.toJSON(),
        });
      }
    };

    pc.ontrack = (event) => {
      const audio = new Audio();
      audio.srcObject = event.streams[0];
      audio.play().catch(() => {});
      audioElements.current.set(peerId, audio);
    };

    // Add local tracks
    if (localStream.current) {
      localStream.current.getTracks().forEach((track) => {
        pc.addTrack(track, localStream.current!);
      });
    }

    peerConnections.current.set(peerId, pc);
    return pc;
  }

  async function createOffer(peerId: string) {
    const pc = getOrCreatePeer(peerId);
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    send("webrtc_signal", {
      signal_type: "offer",
      from_id: myName,
      to_id: peerId,
      sdp: offer.sdp,
    });
  }

  async function handleOffer(fromId: string, sdp: string) {
    const pc = getOrCreatePeer(fromId);
    await pc.setRemoteDescription({ type: "offer", sdp } as RTCSessionDescriptionInit);
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    send("webrtc_signal", {
      signal_type: "answer",
      from_id: myName,
      to_id: fromId,
      sdp: answer.sdp,
    });
  }

  async function handleAnswer(fromId: string, sdp: string) {
    const pc = peerConnections.current.get(fromId);
    if (pc) {
      await pc.setRemoteDescription({ type: "answer", sdp } as RTCSessionDescriptionInit);
    }
  }

  async function handleIceCandidate(fromId: string, candidate: any) {
    const pc = peerConnections.current.get(fromId);
    if (pc && candidate) {
      await pc.addIceCandidate(candidate as RTCIceCandidateInit);
    }
  }

  function closePeerConnection(peerId: string) {
    const pc = peerConnections.current.get(peerId);
    if (pc) {
      pc.close();
      peerConnections.current.delete(peerId);
    }
    const audio = audioElements.current.get(peerId);
    if (audio) {
      audio.pause();
      audioElements.current.delete(peerId);
    }
  }

  async function toggleVoiceChat() {
    if (voiceActive) {
      // Leave voice chat
      send("webrtc_signal", { signal_type: "voice_leave", from_id: myName });
      peerConnections.current.forEach((pc) => pc.close());
      peerConnections.current.clear();
      audioElements.current.forEach((a) => a.pause());
      audioElements.current.clear();
      localStream.current?.getTracks().forEach((t) => t.stop());
      localStream.current = null;
      setVoiceActive(false);
    } else {
      // Join voice chat
      try {
        localStream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
        setVoiceActive(true);
        // Announce to other players
        send("webrtc_signal", { signal_type: "voice_join", from_id: myName });
      } catch {
        console.error("Microphone access denied");
      }
    }
  }

  function toggleMic() {
    if (localStream.current) {
      localStream.current.getAudioTracks().forEach((track) => {
        track.enabled = !track.enabled;
      });
      setIsMicMuted(!isMicMuted);
    }
  }

  return (
    <div className="h-full flex flex-col">
      <div className="genesis-panel-header flex items-center justify-between">
        <span>Party Chat</span>
        <div className="flex items-center gap-1">
          {voiceActive && (
            <button
              onClick={toggleMic}
              className={cn(
                "w-6 h-6 rounded flex items-center justify-center transition-colors",
                isMicMuted
                  ? "text-genesis-red"
                  : "text-genesis-green"
              )}
              title={isMicMuted ? "Unmute" : "Mute"}
            >
              {isMicMuted ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
            </button>
          )}
          <button
            onClick={toggleVoiceChat}
            className={cn(
              "w-6 h-6 rounded flex items-center justify-center transition-colors",
              voiceActive
                ? "bg-genesis-green/20 text-genesis-green"
                : "text-genesis-text-dim hover:text-genesis-accent"
            )}
            title={voiceActive ? "Leave voice chat" : "Join voice chat"}
          >
            {voiceActive ? <PhoneOff className="w-3.5 h-3.5" /> : <PhoneCall className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Voice status */}
      {voiceActive && (
        <div className="px-3 py-1.5 bg-genesis-green/5 border-b border-genesis-border text-genesis-green text-[10px] tracking-wider uppercase text-center">
          Voice chat active {isMicMuted && "— muted"}
        </div>
      )}

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-2">
        {chatMessages.length === 0 && (
          <div className="text-genesis-text-dim text-xs text-center py-4">
            Chat with your party here.
            {playersOnline > 1 && " Click the phone icon for voice chat."}
          </div>
        )}
        {chatMessages.map((msg) => {
          const isMe = msg.sender === myName;
          return (
            <div
              key={msg.id}
              className={cn(
                "max-w-[85%] px-3 py-1.5 rounded-lg text-xs",
                isMe
                  ? "ml-auto bg-genesis-accent/15 text-genesis-text"
                  : "bg-genesis-bg text-genesis-text"
              )}
            >
              {!isMe && (
                <div className="text-genesis-accent text-[9px] font-display tracking-wider mb-0.5">
                  {msg.sender}
                </div>
              )}
              <p>{msg.message}</p>
            </div>
          );
        })}
      </div>

      {/* Input */}
      <div className="p-2 border-t border-genesis-border flex gap-2">
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Message party..."
          className="flex-1 bg-genesis-bg border border-genesis-border rounded px-2.5 py-1.5 text-xs
                     text-genesis-text placeholder-genesis-text-dim focus:outline-none focus:border-genesis-accent"
        />
        <button
          onClick={handleSend}
          disabled={!message.trim()}
          className="w-7 h-7 rounded bg-genesis-accent text-genesis-bg flex items-center justify-center
                     disabled:opacity-30 hover:bg-genesis-accent-dim transition-colors"
        >
          <Send className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}
