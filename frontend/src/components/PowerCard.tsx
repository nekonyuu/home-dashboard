import { useMemo, useState } from "react";

import { usePower } from "../api/hooks";
import { formatDay, formatNumber } from "../lib/format";
import { peakKw, powerSeries } from "../lib/power";
import { isoDay } from "../lib/range";
import { Legend, LineChart } from "./Chart";
import { IconChart, IconTable } from "./icons";
import { Card, ErrorState } from "./ui";

const HEIGHT = 260;
const hm = new Intl.DateTimeFormat("fr-FR", { timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit" });
const time = (epoch: number) => hm.format(new Date(epoch * 1000));

function shiftDay(day: string, delta: number): string {
  const d = new Date(`${day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + delta);
  return d.toISOString().slice(0, 10);
}

/** Puissance moyenne entre deux relevés des compteurs cumulés (chauffage, eau chaude), sur une journée. */
export function PowerCard() {
  const today = isoDay(Date.now());
  const [day, setDay] = useState(today);
  const [asTable, setAsTable] = useState(false);
  const { data, isPending, error } = usePower(day);
  const series = useMemo(() => (data ? powerSeries(data) : []), [data]);
  const xRange = useMemo<[number, number] | undefined>(() => (data ? [data.from, data.to] : undefined), [data]);
  const empty = series.every((s) => s.points.every((p) => p.avg === null));
  const rows = useMemo(() => {
    if (!data) return [];
    const starts = [...new Set(data.series.flatMap((s) => s.intervals.map((i) => i.start)))].sort((a, b) => b - a);
    return starts.map((start) => {
      const cells = data.series.map((s) => s.intervals.find((i) => i.start === start));
      return { start, end: Math.max(...cells.map((c) => c?.end ?? 0)), cells };
    });
  }, [data]);

  return (
    <Card
      title="Puissance sur la journée"
      subtitle="Puissance moyenne entre deux relevés des compteurs de la PAC (environ 10 min), pas une mesure instantanée"
      aside={
        <div className="topbar-actions">
          <div className="seg" role="group" aria-label="Jour">
            <button type="button" aria-label="Jour précédent" onClick={() => setDay(shiftDay(day, -1))}>
              ‹
            </button>
            <button type="button" aria-pressed={day === today} onClick={() => setDay(today)}>
              {day === today ? "Aujourd'hui" : formatDay(day)}
            </button>
            <button
              type="button"
              aria-label="Jour suivant"
              disabled={day >= today}
              onClick={() => setDay(shiftDay(day, 1))}
            >
              ›
            </button>
          </div>
          <button
            type="button"
            className="btn icon"
            onClick={() => setAsTable((v) => !v)}
            aria-label={asTable ? "Afficher la courbe" : "Afficher le tableau"}
            title={asTable ? "Afficher la courbe" : "Afficher le tableau"}
          >
            {asTable ? <IconChart /> : <IconTable />}
          </button>
        </div>
      }
    >
      {error && <ErrorState error={error} />}
      {series.length > 0 && (
        <div className="split-figures">
          {series.map((s) => {
            const peak = peakKw(s);
            return (
              <div key={s.metric}>
                <div className="tile-label">{s.label} · pic</div>
                <div className="split-value">{peak === null ? "—" : formatNumber(peak, "kW")}</div>
              </div>
            );
          })}
        </div>
      )}
      {isPending ? (
        <div className="skeleton" style={{ height: HEIGHT }} />
      ) : empty ? (
        <div className="chart-empty" style={{ minHeight: HEIGHT }}>
          <span>Aucun relevé des compteurs ce jour-là</span>
        </div>
      ) : asTable ? (
        <div className="table-wrap" style={{ maxHeight: HEIGHT + 40, overflowY: "auto" }}>
          <table className="table">
            <thead>
              <tr>
                <th>Intervalle</th>
                {series.map((s) => (
                  <th key={s.metric} className="num">
                    {s.label} (kW)
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.start}>
                  <td>
                    {time(r.start)} – {time(r.end)}
                  </td>
                  {r.cells.map((c, i) => (
                    <td key={series[i].metric} className="num">
                      {c === undefined ? "—" : c.watts === null ? "non réparti" : formatNumber(c.watts / 1000, null)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <LineChart series={series} height={HEIGHT} step yFromZero xRange={xRange} />
      )}
      {series.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <Legend series={series} showGaps={false} />
        </div>
      )}
      <p className="note">
        Calculée à partir des deltas des compteurs cumulés. Un intervalle de plus d'une heure n'est pas réparti : la courbe reste vide (le compteur de l'eau chaude, mis à jour surtout après une chauffe, est souvent dans ce cas).
      </p>
    </Card>
  );
}
