import type { PowerDay, Series } from "../api/types";

/** Puissance moyenne en kW d'un intervalle sur lequel ``x`` tombe, ``null`` hors intervalle ou non répartie. */
function valueAt(intervals: PowerDay["series"][number]["intervals"], x: number): number | null {
  const hit = intervals.find((i) => i.start <= x && x < i.end);
  return hit && hit.watts !== null ? hit.watts / 1000 : null;
}

/**
 * Séries de puissance (kW) alignées sur les bornes de tous les intervalles : chaque valeur est tenue jusqu'au point
 * suivant (tracé en escalier). Hors intervalle, ou intervalle non réparti, la valeur est vide : jamais interpolée.
 */
export function powerSeries(data: PowerDay): Series[] {
  const xs = [...new Set(data.series.flatMap((s) => s.intervals.flatMap((i) => [i.start, i.end])))].sort((a, b) => a - b);
  return data.series.map((s) => {
    return {
      equipment: "heat_pump",
      metric: `power_${s.key}`,
      label: s.label,
      unit: "kW",
      cumulative: false,
      bucket: "5m",
      from: data.from,
      to: data.to,
      points: xs.map((x, k) => {
        const v = valueAt(s.intervals, x);
        return {
          start: x,
          end: xs[k + 1] ?? x,
          avg: v,
          min: v,
          max: v,
          last: v,
          samples: v === null ? 0 : 1,
          covered_seconds: 0,
          delta: null,
          delta_spans_gap: false,
        };
      }),
      gaps: [], // un intervalle non réparti n'est pas une panne de collecte : il reste vide, sans hachures
    };
  });
}

/** Puissance moyenne maximale (kW) d'une série, ``null`` si aucun intervalle réparti. */
export function peakKw(series: Series): number | null {
  const values = series.points.map((p) => p.avg).filter((v): v is number => v !== null);
  return values.length ? Math.max(...values) : null;
}
