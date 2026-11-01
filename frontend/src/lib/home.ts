import type { Equipment, Latest } from "../api/types";
import type { Tone } from "../components/ui";

/** Appareils de la maison (LG ThinQ), par opposition à l'installation Atlantic (PAC, ballon, circuits). */
export const HOME_KINDS = ["washer", "dishwasher", "fridge"];

export const isHomeKind = (kind: string): boolean => HOME_KINDS.includes(kind);

/** Appareils de la maison, dans l'ordre d'affichage. */
export function homeAppliances(equipment: Equipment[] | undefined): Equipment[] {
  return (equipment ?? [])
    .filter((e) => isHomeKind(e.kind))
    .sort((a, b) => HOME_KINDS.indexOf(a.kind) - HOME_KINDS.indexOf(b.kind) || a.id.localeCompare(b.id));
}

export type CyclePhase = "off" | "idle" | "running" | "paused" | "done" | "error" | "unknown";

// Codes d'état stables définis dans backend/.../thinq/semantics.yaml (lave-linge et lave-vaisselle).
const RUNNING = new Set([2, 6, 7, 8, 10, 11, 12, 13, 14, 22]);
const IDLE = new Set([1, 9, 15, 21]);

/** Phase d'un cycle de lavage d'après le code d'état numérique (jamais d'après le libellé). */
export function cyclePhase(code: unknown): CyclePhase {
  if (typeof code !== "number") return "unknown";
  if (code === 0) return "off";
  if (RUNNING.has(code)) return "running";
  if (code === 3) return "paused";
  if (code === 4) return "done";
  if (code === 5 || code === 20) return "error";
  if (IDLE.has(code)) return "idle";
  return "unknown";
}

export const PHASE_TONE: Record<CyclePhase, Tone> = {
  off: "neutral",
  idle: "neutral",
  running: "info",
  paused: "warning",
  done: "good",
  error: "critical",
  unknown: "neutral",
};

/** Progression d'un cycle (0 à 1) d'après le temps restant et la durée totale, `null` si inconnue. */
export function cycleProgress(remaining: number | null, total: number | null): number | null {
  if (remaining === null || total === null || total <= 0) return null;
  return Math.min(Math.max(1 - remaining / total, 0), 1);
}

/** « 1 h 22 », « 45 min », « 2 h ». */
export function formatMinutes(minutes: number): string {
  const m = Math.round(minutes);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  return m % 60 === 0 ? `${h} h` : `${h} h ${String(m % 60).padStart(2, "0")}`;
}

const clock = new Intl.DateTimeFormat("fr-FR", { timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit" });

/** Heure de fin estimée : le temps restant est celui de la lecture (`at`), pas celui d'aujourd'hui. */
export function formatEndTime(readAt: number, remainingMinutes: number): string {
  return clock.format(new Date((readAt + remainingMinutes * 60) * 1000));
}

export function num(l: Latest | undefined): number | null {
  return l && typeof l.value === "number" ? l.value : null;
}
