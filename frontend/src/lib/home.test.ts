import { describe, expect, it } from "vitest";

import type { Equipment } from "../api/types";
import { cyclePhase, cycleProgress, delayedStartMinutes, formatMinutes, homeAppliances, isHomeKind } from "./home";

const eq = (id: string, kind: string): Equipment => ({ id, label: id, kind, available: true, last_seen: 0, metrics: [] });

describe("cyclePhase", () => {
  it("classe les codes d'état par phase", () => {
    expect(cyclePhase(0)).toBe("off");
    expect(cyclePhase(2)).toBe("running");
    expect(cyclePhase(7)).toBe("running");
    expect(cyclePhase(3)).toBe("paused");
    expect(cyclePhase(4)).toBe("done");
    expect(cyclePhase(5)).toBe("error");
    expect(cyclePhase(20)).toBe("error");
    expect(cyclePhase(1)).toBe("idle");
  });
  it("ne devine rien pour un code ou un type inconnu", () => {
    expect(cyclePhase(99)).toBe("unknown");
    expect(cyclePhase("RUNNING")).toBe("unknown");
    expect(cyclePhase(null)).toBe("unknown");
  });
});

describe("cycleProgress", () => {
  it("calcule la progression bornée", () => {
    expect(cycleProgress(45, 90)).toBe(0.5);
    expect(cycleProgress(0, 90)).toBe(1);
    expect(cycleProgress(120, 90)).toBe(0);
  });
  it("est inconnue sans durée", () => {
    expect(cycleProgress(null, 90)).toBeNull();
    expect(cycleProgress(10, 0)).toBeNull();
  });
});

describe("formatMinutes", () => {
  it("formate en heures et minutes", () => {
    expect(formatMinutes(45)).toBe("45 min");
    expect(formatMinutes(82)).toBe("1 h 22");
    expect(formatMinutes(120)).toBe("2 h");
    expect(formatMinutes(65)).toBe("1 h 05");
  });
});

describe("homeAppliances", () => {
  it("ne garde que les appareils de la maison, dans l'ordre", () => {
    const list = homeAppliances([eq("fridge", "fridge"), eq("heat_pump", "heat_pump"), eq("washer", "washer"), eq("dishwasher", "dishwasher")]);
    expect(list.map((e) => e.id)).toEqual(["washer", "dishwasher", "fridge"]);
    expect(isHomeKind("dhw")).toBe(false);
  });
  it("renvoie une liste vide sans données", () => {
    expect(homeAppliances(undefined)).toEqual([]);
  });
});

describe("delayedStartMinutes", () => {
  const l = (v: number) => ({ value: v }) as never;
  it("lave-vaisselle : délai avant départ direct", () => {
    expect(delayedStartMinutes((m) => (m === "delay_start_minutes" ? l(95) : undefined), 60)).toBe(95);
  });
  it("lave-linge : délai avant fin moins durée du cycle", () => {
    expect(delayedStartMinutes((m) => (m === "delay_end_minutes" ? l(300) : undefined), 90)).toBe(210);
    expect(delayedStartMinutes((m) => (m === "delay_end_minutes" ? l(30) : undefined), 90)).toBe(0);
  });
  it("sans donnée : null", () => {
    expect(delayedStartMinutes(() => undefined, 60)).toBeNull();
  });
});
