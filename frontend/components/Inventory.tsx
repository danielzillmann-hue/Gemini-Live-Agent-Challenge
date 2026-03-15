"use client";

import { Backpack, Sword, Shield, FlaskConical, Scroll, Package, Coins } from "lucide-react";
import { useGameStore } from "@/hooks/useGameStore";

const TYPE_ICONS: Record<string, typeof Sword> = {
  weapon: Sword,
  armor: Shield,
  potion: FlaskConical,
  scroll: Scroll,
  misc: Package,
};

export default function Inventory() {
  const { players } = useGameStore();
  const activePlayer = players[0]; // Primary player

  if (!activePlayer) {
    return (
      <div className="h-full flex flex-col">
        <div className="genesis-panel-header flex items-center gap-2">
          <Backpack className="w-4 h-4" /> Inventory
        </div>
        <div className="flex-1 flex items-center justify-center text-genesis-text-dim text-sm">
          No character selected
        </div>
      </div>
    );
  }

  const grouped = activePlayer.inventory.reduce<Record<string, typeof activePlayer.inventory>>(
    (acc, item) => {
      const type = item.item_type || "misc";
      (acc[type] ??= []).push(item);
      return acc;
    },
    {},
  );

  return (
    <div className="h-full flex flex-col">
      <div className="genesis-panel-header flex items-center gap-2">
        <Backpack className="w-4 h-4" />
        <span>{activePlayer.name}&apos;s Inventory</span>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {/* Gold */}
        <div className="flex items-center gap-2 px-3 py-2 bg-genesis-accent/5 rounded-lg">
          <Coins className="w-4 h-4 text-genesis-accent" />
          <span className="text-genesis-accent font-display text-sm tracking-wider">
            {activePlayer.gold} Gold
          </span>
        </div>

        {/* Items by type */}
        {Object.entries(grouped).map(([type, items]) => {
          const Icon = TYPE_ICONS[type] || Package;
          return (
            <div key={type}>
              <div className="text-genesis-text-dim text-[10px] tracking-[0.2em] uppercase mb-1.5 flex items-center gap-1">
                <Icon className="w-3 h-3" />
                {type}s
              </div>
              <div className="space-y-1">
                {items.map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center justify-between px-3 py-2 bg-genesis-bg/30 rounded-lg"
                  >
                    <div>
                      <span className="text-genesis-text text-xs">
                        {item.name}
                      </span>
                      {item.equipped && (
                        <span className="ml-1.5 text-genesis-accent text-[9px] tracking-wider uppercase">
                          Equipped
                        </span>
                      )}
                      {item.properties?.damage != null && (
                        <span className="ml-1.5 text-genesis-text-dim text-[10px] font-mono">
                          {String(item.properties.damage)}
                        </span>
                      )}
                    </div>
                    {item.quantity > 1 && (
                      <span className="text-genesis-text-dim text-[10px] font-mono">
                        x{item.quantity}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          );
        })}

        {activePlayer.inventory.length === 0 && (
          <div className="text-genesis-text-dim text-sm text-center py-8">
            Inventory is empty
          </div>
        )}
      </div>
    </div>
  );
}
