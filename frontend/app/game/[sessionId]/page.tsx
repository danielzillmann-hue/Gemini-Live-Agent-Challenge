"use client";

import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import {
  Mic, MicOff, Send, Camera, CameraOff, Volume2, VolumeX, MessageSquare, MessageSquareOff,
  Swords, Map, BookOpen, Backpack, Users, Settings, Save, MessageCircle,
} from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useVoice } from "@/hooks/useVoice";
import { useGameStore } from "@/hooks/useGameStore";
import MainStage from "@/components/MainStage";
import NarrativeLog from "@/components/NarrativeLog";
import PartyPanel from "@/components/PartyPanel";
import CombatTracker from "@/components/CombatTracker";
import QuestLog from "@/components/QuestLog";
import Inventory from "@/components/Inventory";
import WorldMapPanel from "@/components/WorldMapPanel";
import NPCJournal from "@/components/NPCJournal";
import AudioManager from "@/components/AudioManager";
import NarratorVoice from "@/components/NarratorVoice";
import CharacterCreation from "@/components/CharacterCreation";
import ChatPanel from "@/components/ChatPanel";
import { api } from "@/lib/api";

type SidePanel = "party" | "quests" | "inventory" | "map" | "npcs" | "chat" | null;

export default function GamePage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const [input, setInput] = useState("");
  const [sidePanel, setSidePanel] = useState<SidePanel>("party");
  const [cameraActive, setCameraActive] = useState(false);
  const [gameStarted, setGameStarted] = useState(false);
  const [myCharacterName, setMyCharacterName] = useState<string>("");
  const [needsCharacter, setNeedsCharacter] = useState(false);
  const [aiModel, setAiModel] = useState<"flash" | "pro">("flash");
  const hasCheckedCharacter = useRef(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const cameraIntervalRef = useRef<ReturnType<typeof setInterval>>(undefined);

  const {
    isConnected, isThinking, players, combat, storyLog,
    musicMood, isMuted, toggleMute, worldMapUrl, npcs,
    world, narratorVoiceEnabled, toggleNarratorVoice,
    playersOnline, currentTurn,
    actionWindowStatus, actionWindowSeconds, actionWindowSubmitted,
    actionWindowTotal, hasSubmittedAction,
  } = useGameStore();

  const isMultiplayer = players.length > 1;
  const isCombat = combat?.is_active || false;
  const combatTurn = isCombat ? currentTurn : "";
  const isMyTurnCombat = !isCombat || !combatTurn || combatTurn.toLowerCase() === (myCharacterName || "").toLowerCase();
  const inputDisabled = isThinking
    || (isMultiplayer && isCombat && !isMyTurnCombat)
    || (isMultiplayer && !isCombat && hasSubmittedAction);

  const { send } = useWebSocket(sessionId);

  const { isListening, toggleListening } = useVoice({
    onTranscript: (text) => {
      send("player_action", { text, character_name: myCharacterName || players[0]?.name || "Player" });
    },
  });

  // Check if this player needs to create a character (joined via direct link)
  // Uses sessionStorage to track if THIS browser tab created a character
  useEffect(() => {
    if (isConnected && !hasCheckedCharacter.current) {
      hasCheckedCharacter.current = true;

      const createdChar = sessionStorage.getItem(`genesis_char_${sessionId}`);
      if (createdChar) {
        // This tab already created a character — restore name
        setMyCharacterName(createdChar);
        return;
      }

      // Wait for state sync, then check if we need character creation
      const timer = setTimeout(() => {
        const storedChar = sessionStorage.getItem(`genesis_char_${sessionId}`);
        if (!storedChar) {
          setNeedsCharacter(true);
        }
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [isConnected, sessionId]);

  // Start game once connected and not yet started
  useEffect(() => {
    if (isConnected && !gameStarted && players.length > 0) {
      send("start_game", {});
      setGameStarted(true);
    }
  }, [isConnected, gameStarted, players.length, send]);

  function handleSendMessage() {
    const text = input.trim();
    if (!text) return;
    const charName = myCharacterName || players[0]?.name || "Player";
    send("player_action", { text, character_name: charName });
    useGameStore.getState().addStoryEntry({
      type: "action",
      content: text,
      speaker: charName,
    });
    // Mark action as submitted for this window
    if (isMultiplayer && !isCombat) {
      useGameStore.setState({ hasSubmittedAction: true });
    }
    setInput("");
    inputRef.current?.focus();
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  }

  async function toggleCamera() {
    if (cameraActive) {
      if (cameraIntervalRef.current) clearInterval(cameraIntervalRef.current);
      const stream = videoRef.current?.srcObject as MediaStream;
      stream?.getTracks().forEach((t) => t.stop());
      if (videoRef.current) videoRef.current.srcObject = null;
      setCameraActive(false);
      send("camera_toggle", { active: false });
    } else {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        if (videoRef.current) videoRef.current.srcObject = stream;
        setCameraActive(true);
        send("camera_toggle", { active: true });

        // Send frames periodically for dice detection
        cameraIntervalRef.current = setInterval(() => {
          if (!videoRef.current) return;
          const canvas = document.createElement("canvas");
          canvas.width = videoRef.current.videoWidth;
          canvas.height = videoRef.current.videoHeight;
          const ctx = canvas.getContext("2d");
          if (ctx && canvas.width > 0) {
            ctx.drawImage(videoRef.current, 0, 0);
            const frame = canvas.toDataURL("image/jpeg", 0.7).split(",")[1];
            send("camera_frame", {
              frame,
              purpose: "dice_detection",
              character_name: myCharacterName || players[0]?.name || "Player",
            });
          }
        }, 3000);
      } catch {
        console.error("Camera access denied");
      }
    }
  }

  async function toggleModel() {
    const newModel = aiModel === "flash" ? "pro" : "flash";
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";
      await fetch(`${API_URL}/api/settings/model`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: newModel }),
      });
      setAiModel(newModel);
    } catch {
      console.error("Failed to switch model");
    }
  }

  async function handleSave() {
    try {
      await api.saveSession(sessionId);
      // Also save all characters to the persistent roster
      await api.saveAllCharactersFromSession(sessionId);
      useGameStore.getState().addStoryEntry({
        type: "system",
        content: "Game and characters saved successfully.",
      });
    } catch {
      console.error("Failed to save");
    }
  }

  return (
    <div className="h-screen w-screen flex flex-col bg-genesis-bg overflow-hidden">
      <AudioManager />
      <NarratorVoice />

      {/* ── Character Creation Overlay (for players joining via link) ── */}
      {needsCharacter && (
        <div className="absolute inset-0 z-50 bg-genesis-bg/95 backdrop-blur-sm flex items-center justify-center p-6">
          <div className="w-full max-w-4xl">
            <CharacterCreation
              sessionId={sessionId}
              onComplete={() => {
                setNeedsCharacter(false);
                // Get the last added player (the one we just created)
                const latestPlayers = useGameStore.getState().players;
                if (latestPlayers.length > 0) {
                  const name = latestPlayers[latestPlayers.length - 1].name;
                  setMyCharacterName(name);
                  sessionStorage.setItem(`genesis_char_${sessionId}`, name);
                }
              }}
            />
          </div>
        </div>
      )}

      {/* ── Top Bar ──────────────────────────────────────────── */}
      <header className="h-12 flex items-center justify-between px-4 border-b border-genesis-border bg-genesis-panel/80 backdrop-blur-sm shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="font-display text-genesis-accent text-sm tracking-[0.2em]">GENESIS</h1>
          <div className="w-px h-5 bg-genesis-border" />
          <span className="text-genesis-text text-sm font-display tracking-wider">
            {world?.campaign_name || "Loading..."}
          </span>
        </div>
        <div className="flex items-center gap-2 text-genesis-text-dim text-xs">
          {world && (
            <>
              <span>Day {world.day_count}</span>
              <span className="opacity-40">|</span>
              <span className="capitalize">{world.time_of_day}</span>
              <span className="opacity-40">|</span>
              <span className="capitalize">{world.weather}</span>
              <span className="opacity-40">|</span>
            </>
          )}
          {playersOnline > 1 && (
            <>
              <Users className="w-3 h-3" />
              <span>{playersOnline} players</span>
              <span className="opacity-40">|</span>
            </>
          )}
          <span className={`w-2 h-2 rounded-full ${isConnected ? "bg-genesis-green" : "bg-genesis-red"}`} />
          <span>{isConnected ? "Connected" : "Disconnected"}</span>
          <button
            onClick={toggleModel}
            className={`ml-2 px-2 py-0.5 rounded text-[10px] font-display tracking-wider transition-all ${
              aiModel === "pro"
                ? "bg-genesis-purple/20 text-genesis-purple border border-genesis-purple/40"
                : "bg-genesis-accent/10 text-genesis-accent border border-genesis-accent/30"
            }`}
            title={aiModel === "pro" ? "Using Pro (quality) — click for Flash (speed)" : "Using Flash (speed) — click for Pro (quality)"}
          >
            {aiModel === "pro" ? "PRO" : "FLASH"}
          </button>
          <button onClick={handleSave} className="ml-1 p-1.5 hover:text-genesis-accent transition-colors" title="Save Game">
            <Save className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* ── Main Layout ──────────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar — Panel Switcher */}
        <nav className="w-12 flex flex-col items-center py-3 gap-1 border-r border-genesis-border bg-genesis-panel/50 shrink-0">
          {[
            { id: "party" as SidePanel, icon: Users, label: "Party" },
            { id: "quests" as SidePanel, icon: BookOpen, label: "Quests" },
            { id: "inventory" as SidePanel, icon: Backpack, label: "Inventory" },
            { id: "map" as SidePanel, icon: Map, label: "World Map" },
            { id: "npcs" as SidePanel, icon: Swords, label: "NPCs" },
            { id: "chat" as SidePanel, icon: MessageCircle, label: "Party Chat" },
          ].map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              onClick={() => setSidePanel(sidePanel === id ? null : id)}
              className={`w-9 h-9 rounded-lg flex items-center justify-center transition-all duration-200 ${
                sidePanel === id
                  ? "bg-genesis-accent/10 text-genesis-accent"
                  : "text-genesis-text-dim hover:text-genesis-text hover:bg-genesis-bg/50"
              }`}
              title={label}
            >
              <Icon className="w-4.5 h-4.5" />
            </button>
          ))}
        </nav>

        {/* Side Panel Content */}
        {sidePanel && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 280, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            className="border-r border-genesis-border bg-genesis-panel/30 overflow-y-auto shrink-0"
          >
            {sidePanel === "party" && <PartyPanel />}
            {sidePanel === "quests" && <QuestLog />}
            {sidePanel === "inventory" && <Inventory />}
            {sidePanel === "map" && <WorldMapPanel />}
            {sidePanel === "npcs" && <NPCJournal />}
            {sidePanel === "chat" && <ChatPanel send={send} myName={myCharacterName || players[0]?.name || "Player"} />}
          </motion.aside>
        )}

        {/* Center — Main Stage + Narrative */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Main Stage (Scene Image / Video / Battle Map) */}
          <div className="h-[45%] shrink-0 p-3 pb-0">
            <MainStage />
          </div>

          {/* Narrative Log */}
          <div className="flex-1 overflow-hidden p-3 pt-2">
            <NarrativeLog />
          </div>
        </main>

        {/* Right Panel — Combat Tracker (when active) */}
        {combat?.is_active && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 260, opacity: 1 }}
            className="border-l border-genesis-border bg-genesis-panel/30 overflow-y-auto shrink-0"
          >
            <CombatTracker />
          </motion.aside>
        )}
      </div>

      {/* ── Action Window / Turn Indicator (multiplayer) ────── */}
      {isMultiplayer && !isCombat && actionWindowStatus !== "none" && actionWindowStatus !== "closed" && (
        <div className="px-4 py-1.5 text-center text-xs font-display tracking-wider border-t border-genesis-border shrink-0 bg-genesis-accent/10 text-genesis-accent flex items-center justify-center gap-3">
          {hasSubmittedAction ? (
            <span>Action submitted! Waiting for others... ({actionWindowSubmitted}/{actionWindowTotal})</span>
          ) : (
            <span>Declare your action! ({actionWindowSubmitted}/{actionWindowTotal} ready)</span>
          )}
          {actionWindowSeconds > 0 && (
            <span className="bg-genesis-accent/20 px-2 py-0.5 rounded font-mono">
              {actionWindowSeconds}s
            </span>
          )}
        </div>
      )}
      {isMultiplayer && isCombat && combatTurn && (
        <div className={`px-4 py-1.5 text-center text-xs font-display tracking-wider border-t border-genesis-border shrink-0 ${
          isMyTurnCombat
            ? "bg-genesis-accent/10 text-genesis-accent"
            : "bg-genesis-bg text-genesis-text-dim"
        }`}>
          {isMyTurnCombat
            ? `Your turn in combat, ${myCharacterName}!`
            : `Waiting for ${combatTurn}'s combat turn...`
          }
        </div>
      )}

      {/* ── Input Bar ────────────────────────────────────────── */}
      <footer className="h-16 flex items-center gap-3 px-4 border-t border-genesis-border bg-genesis-panel/80 backdrop-blur-sm shrink-0">
        {/* Voice */}
        <button
          onClick={toggleListening}
          className={`w-10 h-10 rounded-lg flex items-center justify-center transition-all ${
            isListening
              ? "bg-genesis-red text-white animate-pulse"
              : "bg-genesis-bg text-genesis-text-dim hover:text-genesis-accent border border-genesis-border"
          }`}
          title={isListening ? "Stop listening" : "Start voice input"}
        >
          {isListening ? <MicOff className="w-4.5 h-4.5" /> : <Mic className="w-4.5 h-4.5" />}
        </button>

        {/* Camera */}
        <button
          onClick={toggleCamera}
          className={`w-10 h-10 rounded-lg flex items-center justify-center transition-all ${
            cameraActive
              ? "bg-genesis-blue text-white"
              : "bg-genesis-bg text-genesis-text-dim hover:text-genesis-accent border border-genesis-border"
          }`}
          title={cameraActive ? "Disable camera" : "Enable camera (dice detection)"}
        >
          {cameraActive ? <CameraOff className="w-4.5 h-4.5" /> : <Camera className="w-4.5 h-4.5" />}
        </button>

        {/* Hidden video element for camera */}
        <video ref={videoRef} autoPlay playsInline className="hidden" />

        {/* Text Input */}
        <div className="flex-1 relative">
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              isThinking
                ? "The Game Master is narrating..."
                : isMultiplayer && !isCombat && hasSubmittedAction
                  ? "Action submitted. Waiting for other players..."
                  : isMultiplayer && isCombat && !isMyTurnCombat
                    ? `Waiting for ${combatTurn}'s combat turn...`
                    : isMultiplayer
                      ? `${myCharacterName}, what do you do?`
                      : "Describe your action... (press Enter to send)"
            }
            disabled={inputDisabled}
            className="genesis-input pr-12 disabled:opacity-50"
          />
          {isThinking && (
            <div className="absolute right-4 top-1/2 -translate-y-1/2 thinking-indicator">
              <span className="dot" /><span className="dot" /><span className="dot" />
            </div>
          )}
        </div>

        {/* Send */}
        <button
          onClick={handleSendMessage}
          disabled={!input.trim() || inputDisabled}
          className="w-10 h-10 rounded-lg bg-genesis-accent text-genesis-bg flex items-center justify-center
                     disabled:opacity-30 disabled:cursor-not-allowed hover:bg-genesis-accent-dim transition-colors"
        >
          <Send className="w-4.5 h-4.5" />
        </button>

        {/* Narrator Voice Toggle */}
        <button
          onClick={toggleNarratorVoice}
          className={`w-10 h-10 rounded-lg flex items-center justify-center transition-all ${
            narratorVoiceEnabled
              ? "bg-genesis-accent/20 text-genesis-accent border border-genesis-accent/50"
              : "bg-genesis-bg text-genesis-text-dim hover:text-genesis-accent border border-genesis-border"
          }`}
          title={narratorVoiceEnabled ? "Disable narrator voice" : "Enable narrator voice"}
        >
          {narratorVoiceEnabled
            ? <MessageSquare className="w-4.5 h-4.5" />
            : <MessageSquareOff className="w-4.5 h-4.5" />
          }
        </button>

        {/* Mute Music */}
        <button
          onClick={toggleMute}
          className="w-10 h-10 rounded-lg bg-genesis-bg text-genesis-text-dim
                     hover:text-genesis-accent border border-genesis-border flex items-center justify-center transition-colors"
          title={isMuted ? "Unmute music" : "Mute music"}
        >
          {isMuted ? <VolumeX className="w-4.5 h-4.5" /> : <Volume2 className="w-4.5 h-4.5" />}
        </button>
      </footer>
    </div>
  );
}
