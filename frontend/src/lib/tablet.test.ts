import { describe, expect, it } from "vitest";

import type { EnergyDay } from "../api/types";
import { latestEnergyDay } from "./tablet";

const d = (day: string, category: number, kwh: number, cost: number | null = null, tariff: EnergyDay["tariff"] = "peak"): EnergyDay => ({
  day,
  category,
  tariff,
  kwh,
  cost,
});

describe("latestEnergyDay", () => {
  it("renvoie null sans données", () => {
    expect(latestEnergyDay(undefined)).toBeNull();
    expect(latestEnergyDay([])).toBeNull();
  });
  it("additionne les tarifs du dernier jour, par usage", () => {
    const r = latestEnergyDay([
      d("2026-11-07", 1, 9),
      d("2026-11-08", 1, 3, 0.5, "peak"),
      d("2026-11-08", 1, 2, 0.2, "off_peak"),
      d("2026-11-08", 2, 1.5, 0.3),
    ]);
    expect(r).toEqual({ day: "2026-11-08", heating: 5, dhw: 1.5, total: 6.5, cost: 1 });
  });
  it("garde un coût inconnu inconnu", () => {
    expect(latestEnergyDay([d("2026-11-08", 1, 4)])?.cost).toBeNull();
  });
});
