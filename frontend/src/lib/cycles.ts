import type { Cycle } from "../api/types";

export interface CycleSummary {
  count: number;
  /** Cycles terminés : seuls leurs durées et gains de température sont comparables. */
  meanDuration: number | null;
  /** Énergie moyenne sur les cycles où elle est connue (Wh). */
  meanEnergyWh: number | null;
  perDay: number | null;
}

const mean = (values: number[]): number | null =>
  values.length === 0 ? null : values.reduce((a, v) => a + v, 0) / values.length;

export function summarizeCycles(cycles: Cycle[], days: number): CycleSummary {
  const done = cycles.filter((c) => c.duration_seconds !== null);
  return {
    count: cycles.length,
    meanDuration: mean(done.map((c) => c.duration_seconds as number)),
    meanEnergyWh: mean(cycles.flatMap((c) => (c.energy_wh === null ? [] : [c.energy_wh]))),
    perDay: days > 0 && cycles.length > 0 ? cycles.length / days : null,
  };
}
