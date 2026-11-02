import type { TariffSplit } from "../api/types";
import type { Column } from "../components/ColumnChart";
import { formatDay, formatNumber } from "./format";

// Mêmes couleurs que la ventilation « par tarif » de la page Énergie.
export const TARIFF_SEGMENTS = [
  { key: "off_peak", label: "Heures creuses", color: "--series-3" },
  { key: "peak", label: "Heures pleines", color: "--series-4" },
  { key: "unassigned", label: "Non réparti", color: "--series-7" },
] as const;

export interface TariffTotals {
  offPeak: number;
  peak: number;
  unassigned: number;
  days: number;
}

export function tariffTotals(split: TariffSplit): TariffTotals {
  return split.days.reduce(
    (a, d) => ({
      offPeak: a.offPeak + d.off_peak_kwh,
      peak: a.peak + d.peak_kwh,
      unassigned: a.unassigned + d.unassigned_kwh,
      days: a.days + 1,
    }),
    { offPeak: 0, peak: 0, unassigned: 0, days: 0 },
  );
}

/** Une colonne par jour : heures creuses, heures pleines, et l'énergie qu'on n'a pas pu placer (jamais devinée). */
export function dayColumns(split: TariffSplit): Column[] {
  return split.days.map((d) => ({
    key: d.day,
    label: d.day.slice(8, 10) + "/" + d.day.slice(5, 7),
    title: formatDay(d.day),
    segments: [
      { ...TARIFF_SEGMENTS[0], value: d.off_peak_kwh },
      { ...TARIFF_SEGMENTS[1], value: d.peak_kwh },
      { ...TARIFF_SEGMENTS[2], value: d.unassigned_kwh },
    ].filter((s) => s.key !== "unassigned" || s.value > 0),
  }));
}

/** Profil horaire : consommation moyenne par jour pour chaque heure locale. */
export function hourColumns(split: TariffSplit): Column[] {
  const n = Math.max(split.days.length, 1);
  return split.hourly.map((h) => ({
    key: String(h.hour),
    label: `${h.hour} h`,
    title: `De ${h.hour} h à ${h.hour + 1} h (moyenne sur ${n} jour${n > 1 ? "s" : ""})`,
    segments: [
      { ...TARIFF_SEGMENTS[0], value: h.off_peak_kwh / n },
      { ...TARIFF_SEGMENTS[1], value: h.peak_kwh / n },
    ],
  }));
}

/** "01:38-06:38" -> "1 h 38 – 6 h 38" */
export function formatWindow(w: string): string {
  return w
    .split("-")
    .map((t) => {
      const [h, m] = t.split(":").map(Number);
      return m ? `${h} h ${String(m).padStart(2, "0")}` : `${h} h`;
    })
    .join(" – ");
}

export function share(part: number, total: number): string {
  return total > 0 ? formatNumber((part / total) * 100, null) : "—";
}
