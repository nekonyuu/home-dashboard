import { describe, expect, it } from "vitest";

import type { PowerDay } from "../api/types";
import { peakKw, powerSeries } from "./power";

const day: PowerDay = {
  day: "2026-10-28",
  from: 0,
  to: 2000,
  series: [
    {
      key: "heating",
      label: "Chauffage",
      intervals: [
        { start: 100, end: 700, watts: 3600 },
        { start: 700, end: 1300, watts: 1200 },
        { start: 1300, end: 1900, watts: null },
      ],
    },
    { key: "dhw", label: "Eau chaude", intervals: [{ start: 400, end: 1000, watts: 6000 }] },
  ],
};

describe("powerSeries", () => {
  const [heating, dhw] = powerSeries(day);

  it("tient chaque valeur en kW jusqu'au point suivant", () => {
    const at = (s: typeof heating, x: number) => s.points.find((p) => p.start === x)?.avg;
    expect(at(heating, 100)).toBe(3.6);
    expect(at(heating, 400)).toBe(3.6); // borne d'un autre intervalle : valeur maintenue
    expect(at(heating, 700)).toBe(1.2);
  });

  it("laisse vide hors intervalle et sur un intervalle non réparti (jamais interpolé)", () => {
    const at = (s: typeof heating, x: number) => s.points.find((p) => p.start === x)?.avg;
    expect(at(heating, 1300)).toBeNull();
    expect(at(dhw, 100)).toBeNull();
    expect(at(dhw, 1000)).toBeNull();
    expect(at(dhw, 700)).toBe(6);
  });

  it("donne le pic", () => {
    expect(peakKw(heating)).toBe(3.6);
    expect(peakKw(dhw)).toBe(6);
    expect(peakKw(powerSeries({ ...day, series: [{ key: "x", label: "x", intervals: [] }] })[0])).toBeNull();
  });
});
