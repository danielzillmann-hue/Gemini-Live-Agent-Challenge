"use client";

import { useState } from "react";
import { Map, MapPin, Eye, EyeOff, X, Maximize2 } from "lucide-react";
import { useGameStore } from "@/hooks/useGameStore";
import { formatTimeOfDay, formatWeather } from "@/lib/utils";

export default function WorldMapPanel() {
  const { worldMapUrl, world } = useGameStore();
  const [fullscreen, setFullscreen] = useState(false);

  const locations = world ? Object.values(world.locations) : [];
  const visited = locations.filter((l) => l.visited);
  const unvisited = locations.filter((l) => !l.visited);

  return (
    <>
      {/* Fullscreen Map Overlay */}
      {fullscreen && worldMapUrl && (
        <div
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center cursor-zoom-out"
          onClick={() => setFullscreen(false)}
        >
          <button
            onClick={() => setFullscreen(false)}
            className="absolute top-4 right-4 w-10 h-10 rounded-lg bg-black/60 flex items-center justify-center text-white/70 hover:text-white transition-colors z-10"
          >
            <X className="w-5 h-5" />
          </button>
          <img
            src={worldMapUrl}
            alt="World Map"
            className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}

      <div className="h-full flex flex-col">
        <div className="genesis-panel-header flex items-center gap-2">
          <Map className="w-4 h-4" />
          <span>World Map</span>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-3">
          {/* Map Image */}
          {worldMapUrl ? (
            <div
              className="rounded-lg overflow-hidden border border-genesis-border cursor-pointer relative group"
              onClick={() => setFullscreen(true)}
            >
              <img
                src={worldMapUrl}
                alt="World Map"
                className="w-full object-cover"
              />
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-all flex items-center justify-center">
                <Maximize2 className="w-6 h-6 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
            </div>
          ) : (
            <div className="genesis-panel p-6 text-center">
              <Map className="w-8 h-8 text-genesis-text-dim mx-auto mb-2 opacity-30" />
              <p className="text-genesis-text-dim text-xs">
                Map generating...
              </p>
            </div>
          )}

          {/* World Info */}
          {world && (
            <div className="genesis-panel p-3 space-y-1.5">
              <div className="flex justify-between text-xs">
                <span className="text-genesis-text-dim">Day</span>
                <span className="text-genesis-text font-mono">{world.day_count}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-genesis-text-dim">Time</span>
                <span className="text-genesis-text capitalize">{formatTimeOfDay(world.time_of_day)}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-genesis-text-dim">Weather</span>
                <span className="text-genesis-text">{formatWeather(world.weather)}</span>
              </div>
            </div>
          )}

          {/* Visited Locations */}
          {visited.length > 0 && (
            <div>
              <div className="text-genesis-accent text-[10px] tracking-[0.2em] uppercase mb-1.5 flex items-center gap-1">
                <Eye className="w-3 h-3" /> Discovered
              </div>
              <div className="space-y-1">
                {visited.map((loc) => (
                  <div
                    key={loc.id}
                    className="flex items-start gap-2 px-3 py-2 bg-genesis-bg/30 rounded-lg"
                  >
                    <MapPin className="w-3.5 h-3.5 text-genesis-accent shrink-0 mt-0.5" />
                    <div>
                      <span className="text-genesis-text text-xs block">{loc.name}</span>
                      <span className="text-genesis-text-dim text-[10px] capitalize">{loc.location_type}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Unvisited (fog of war) */}
          {unvisited.length > 0 && (
            <div>
              <div className="text-genesis-text-dim text-[10px] tracking-[0.2em] uppercase mb-1.5 flex items-center gap-1">
                <EyeOff className="w-3 h-3" /> Unknown ({unvisited.length})
              </div>
              <div className="space-y-1">
                {unvisited.map((loc) => (
                  <div
                    key={loc.id}
                    className="px-3 py-2 bg-genesis-bg/20 rounded-lg"
                  >
                    <span className="text-genesis-text-dim text-xs italic">???</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {/* Factions */}
          {world?.factions && Object.keys(world.factions).length > 0 && (
            <div>
              <div className="text-genesis-accent text-[10px] tracking-[0.2em] uppercase mb-1.5">
                Factions
              </div>
              <div className="space-y-1">
                {Object.values(world.factions as Record<string, any>).map((faction: any) => (
                  <div key={faction.id || faction.name} className="genesis-panel p-2">
                    <div className="text-genesis-text text-xs font-display tracking-wider">
                      {faction.name}
                    </div>
                    {faction.description && (
                      <div className="text-genesis-text-dim text-[10px] mt-0.5 line-clamp-1">
                        {faction.description}
                      </div>
                    )}
                    {faction.reputation && Object.keys(faction.reputation).length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {Object.entries(faction.reputation as Record<string, number>).map(([char, rep]) => (
                          <span
                            key={char}
                            className={`text-[9px] px-1 py-0.5 rounded ${
                              (rep as number) > 0
                                ? "bg-genesis-green/15 text-genesis-green"
                                : (rep as number) < 0
                                  ? "bg-genesis-red/15 text-genesis-red"
                                  : "bg-genesis-bg text-genesis-text-dim"
                            }`}
                          >
                            {char}: {(rep as number) > 0 ? "+" : ""}{rep as number}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
