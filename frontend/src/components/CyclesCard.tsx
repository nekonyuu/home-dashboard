import { useState } from "react";

import { useCycles } from "../api/hooks";
import { summarizeCycles } from "../lib/cycles";
import { formatDateTime, formatDuration, formatNumber } from "../lib/format";
import { IconClock } from "./icons";
import { Card, ErrorState, Segmented } from "./ui";

const PERIODS = [
  { id: "7", label: "7 jours" },
  { id: "30", label: "30 jours" },
  { id: "365", label: "1 an" },
];
const DAY = 86_400;

const kwhFormat = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const kwh = (wh: number | null) => (wh === null ? "—" : kwhFormat.format(wh / 1000));
const degrees = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const celsius = (v: number | null) => (v === null ? "—" : degrees.format(v));

/** Chauffes de l'eau chaude : bascule de la vanne 3 voies vers « ECS » (dérivées côté serveur). */
export function CyclesCard() {
  const [period, setPeriod] = useState("30");
  const days = Number(period);
  const to = Math.floor(Date.now() / 60_000) * 60;
  const { data, isPending, error } = useCycles(to - days * DAY, to);
  const cycles = data ?? [];
  const summary = summarizeCycles(cycles, days);

  return (
    <Card
      title="Cycles de chauffe"
      subtitle="Périodes où la pompe à chaleur chauffe le ballon"
      aside={<Segmented label="Période des cycles" options={PERIODS} value={period} onChange={setPeriod} />}
    >
      {error ? (
        <ErrorState error={error} />
      ) : isPending ? (
        <div className="skeleton" style={{ height: 120 }} />
      ) : cycles.length === 0 ? (
        <div className="empty-state">
          <IconClock size={28} />
          <strong style={{ color: "var(--text-2)" }}>Aucun cycle sur la période</strong>
          <span>Un cycle commence quand la vanne bascule vers l'eau chaude et finit quand elle revient au chauffage.</span>
        </div>
      ) : (
        <>
          <p className="meta" style={{ margin: "0 0 12px" }}>
            {cycles.length} cycle{cycles.length > 1 ? "s" : ""}
            {summary.meanDuration !== null && <> · durée moyenne {formatDuration(summary.meanDuration)}</>}
            {summary.meanEnergyWh !== null && <> · {kwh(summary.meanEnergyWh)} kWh en moyenne</>}
            {summary.perDay !== null && <> · {formatNumber(summary.perDay, null)} par jour</>}
          </p>
          <div className="table-wrap" style={{ maxHeight: 340, overflowY: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Début</th>
                  <th className="num">Durée</th>
                  <th className="num">Température</th>
                  <th className="num">Énergie (kWh)</th>
                </tr>
              </thead>
              <tbody>
                {[...cycles].reverse().map((c) => (
                  <tr key={c.start}>
                    <td>{formatDateTime(c.start)}</td>
                    <td className="num">{c.ongoing ? "En cours" : formatDuration(c.duration_seconds ?? 0)}</td>
                    <td className="num">
                      {celsius(c.start_temperature)} → {c.ongoing ? "…" : celsius(c.end_temperature)} °C
                    </td>
                    <td className="num">{c.ongoing ? "…" : kwh(c.energy_wh)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="meta" style={{ margin: "10px 0 0" }}>
            L'énergie est lue sur le compteur de l'eau chaude ; elle reste vide quand un trou de collecte recouvre le
            cycle.
          </p>
        </>
      )}
    </Card>
  );
}
