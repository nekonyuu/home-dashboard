import { describe, expect, it } from "vitest";

import type { TariffSplit } from "../api/types";
import { dayColumns, formatWindow, hourColumns, tariffTotals } from "./tariff";

const split: TariffSplit = {
  off_peak_hours: ["01:38-06:38", "14:08-17:08"],
  days: [
    { day: "2026-10-28", off_peak_kwh: 13.3, peak_kwh: 0.8, unassigned_kwh: 0, covered_seconds: 40000 },
    { day: "2026-10-29", off_peak_kwh: 10.8, peak_kwh: 0.7, unassigned_kwh: 0.3, covered_seconds: 40000 },
  ],
  hourly: Array.from({ length: 24 }, (_, hour) => ({ hour, off_peak_kwh: hour === 3 ? 4 : 0, peak_kwh: 1 })),
};

describe("tariff split", () => {
  it("totalise", () => {
    const t = tariffTotals(split);
    expect(t.days).toBe(2);
    expect(t.offPeak).toBeCloseTo(24.1);
    expect(t.unassigned).toBeCloseTo(0.3);
  });
  it("n'affiche « non réparti » que s'il existe", () => {
    const [a, b] = dayColumns(split);
    expect(a.segments.map((s) => s.key)).toEqual(["off_peak", "peak"]);
    expect(b.segments.map((s) => s.key)).toEqual(["off_peak", "peak", "unassigned"]);
    expect(a.label).toBe("28/10");
  });
  it("moyenne le profil horaire par jour", () => {
    const cols = hourColumns(split);
    expect(cols).toHaveLength(24);
    expect(cols[3].segments[0].value).toBe(2);
    expect(cols[3].segments[1].value).toBe(0.5);
  });
  it("formate les plages", () => {
    expect(formatWindow("01:38-06:38")).toBe("1 h 38 – 6 h 38");
    expect(formatWindow("22:00-06:00")).toBe("22 h – 6 h");
  });
});
