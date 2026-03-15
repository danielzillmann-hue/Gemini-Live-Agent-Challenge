import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function getHpColor(current: number, max: number): string {
  const pct = current / max;
  if (pct > 0.6) return "bg-genesis-green";
  if (pct > 0.3) return "bg-yellow-500";
  return "bg-genesis-red";
}

export function getHpPercentage(current: number, max: number): number {
  return Math.max(0, Math.min(100, (current / max) * 100));
}

export function formatTimeOfDay(time: string): string {
  const icons: Record<string, string> = {
    morning: "Dawn",
    afternoon: "Midday",
    evening: "Dusk",
    night: "Night",
  };
  return icons[time] || time;
}

export function formatWeather(weather: string): string {
  const labels: Record<string, string> = {
    clear: "Clear Skies",
    rain: "Rain",
    fog: "Fog",
    snow: "Snow",
    storm: "Thunderstorm",
  };
  return labels[weather] || weather;
}

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str;
  return str.slice(0, length) + "...";
}

let nextId = 0;
export function generateId(): string {
  return `${Date.now()}-${nextId++}`;
}
