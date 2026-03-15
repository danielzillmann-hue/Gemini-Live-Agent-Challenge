"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Maximize2, Minimize2, Play, X } from "lucide-react";
import { useGameStore } from "@/hooks/useGameStore";

export default function MainStage() {
  const { currentSceneImage, currentSceneVideo, currentBattleMap, combat } =
    useGameStore();
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showVideo, setShowVideo] = useState(false);
  const videoPlayerRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-play video when a new one arrives
  useEffect(() => {
    if (currentSceneVideo) {
      setShowVideo(true);
    }
  }, [currentSceneVideo]);

  function toggleFullscreen() {
    if (!containerRef.current) return;
    if (!isFullscreen) {
      containerRef.current.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
    setIsFullscreen(!isFullscreen);
  }

  const activeImage = combat?.is_active && currentBattleMap ? currentBattleMap : currentSceneImage;

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full rounded-lg overflow-hidden bg-genesis-bg border border-genesis-border"
    >
      {/* Scene Image */}
      <AnimatePresence mode="wait">
        {activeImage && (
          <motion.img
            key={activeImage}
            src={activeImage}
            alt="Scene"
            initial={{ opacity: 0, scale: 1.05 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.2 }}
            className="absolute inset-0 w-full h-full object-cover"
          />
        )}
      </AnimatePresence>

      {/* Empty State */}
      {!activeImage && !showVideo && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center">
            <div className="w-16 h-16 rounded-full border-2 border-genesis-border flex items-center justify-center mx-auto mb-4">
              <Play className="w-6 h-6 text-genesis-text-dim" />
            </div>
            <p className="text-genesis-text-dim text-sm font-display tracking-wider">
              Your adventure awaits
            </p>
            <p className="text-genesis-text-dim/50 text-xs mt-1">
              Scenes will appear here as the story unfolds
            </p>
          </div>
        </div>
      )}

      {/* Video Overlay */}
      <AnimatePresence>
        {showVideo && currentSceneVideo && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 z-20 bg-black"
          >
            <video
              ref={videoPlayerRef}
              src={currentSceneVideo}
              autoPlay
              className="w-full h-full object-contain"
              onEnded={() => setShowVideo(false)}
            />
            <button
              onClick={() => setShowVideo(false)}
              className="absolute top-3 right-3 w-8 h-8 rounded-full bg-black/60 flex items-center justify-center
                         text-white/70 hover:text-white transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Gradient overlay for readability */}
      {activeImage && (
        <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-genesis-bg/80 to-transparent pointer-events-none" />
      )}

      {/* Controls */}
      <div className="absolute top-3 right-3 flex gap-2 z-10">
        <button
          onClick={toggleFullscreen}
          className="w-8 h-8 rounded-lg bg-black/40 backdrop-blur-sm flex items-center justify-center
                     text-white/60 hover:text-white transition-colors"
        >
          {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
        </button>
      </div>

      {/* Combat Round Indicator */}
      {combat?.is_active && (
        <div className="absolute top-3 left-3 z-10">
          <div className="px-3 py-1.5 rounded-lg bg-genesis-red/90 backdrop-blur-sm text-white text-xs font-display tracking-wider">
            COMBAT — Round {combat.round_number}
          </div>
        </div>
      )}
    </div>
  );
}
