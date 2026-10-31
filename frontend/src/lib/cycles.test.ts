import { describe, expect, it } from "vitest";

import type { Cycle } from "../api/types";
import { summarizeCycles } from "./cycles";

const cycle = (over: Partial<Cycle>): Cycle => ({
  start: 0,
  end: 1800,
  duration_seconds: 1800,
  ongoing: false,
  start_temperature: 45,
  end_temperature: 55,
  energy_wh: 1200,
  ...over,
});

describe("summarizeCycles", () => {
  it("ne calcule rien sans cycle", () => {
    expect(summarizeCycles([], 7)).toEqual({ count: 0, meanDuration: null, meanEnergyWh: null, perDay: null });
  });

  it("ignore les valeurs inconnues et les cycles en cours dans les moyennes", () => {
    const s = summarizeCycles(
      [
        cycle({}),
        cycle({ duration_seconds: 3600, energy_wh: null }),
        cycle({ end: null, duration_seconds: null, ongoing: true, energy_wh: 600 }),
      ],
      3,
    );
    expect(s.count).toBe(3);
    expect(s.meanDuration).toBe(2700);
    expect(s.meanEnergyWh).toBe(900);
    expect(s.perDay).toBe(1);
  });
});
