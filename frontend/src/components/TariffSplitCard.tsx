import { useState } from "react";

import { ApiError } from "../api/client";
import { useTariffSplit } from "../api/hooks";
import { formatNumber } from "../lib/format";
import { dayColumns, formatWindow, hourColumns, share, TARIFF_SEGMENTS, tariffTotals } from "../lib/tariff";
import { type Column, ColumnChart } from "./ColumnChart";
import { IconChart, IconTable } from "./icons";
import { Card, ErrorState, Segmented } from "./ui";

const VIEWS = [
  { id: "day", label: "Par jour" },
  { id: "hour", label: "Profil horaire" },
];

/** Chauffage réparti heures creuses / pleines à partir du compteur de la PAC (relevé toutes les ~10 min). */
export function TariffSplitCard({ from, to }: { from: string; to: string }) {
  const { data, isPending, error } = useTariffSplit(from, to);
  const [view, setView] = useState("day");
  const [asTable, setAsTable] = useState(false);
  if (error instanceof ApiError && error.status === 404) return null; // plages non configurées
  const columns: Column[] = data ? (view === "day" ? dayColumns(data) : hourColumns(data)) : [];
  const t = data ? tariffTotals(data) : null;
  const assigned = t ? t.offPeak + t.peak : 0;
  const keys = TARIFF_SEGMENTS.filter((s) => s.key !== "unassigned" || (view === "day" && (t?.unassigned ?? 0) > 0));

  return (
    <Card
      title="Chauffage : heures creuses et heures pleines"
      subtitle={
        data
          ? `Compteur de la PAC, heures creuses ${data.off_peak_hours.map(formatWindow).join(" et ")}`
          : "Compteur de la PAC"
      }
      aside={
        <div className="topbar-actions">
          <Segmented label="Vue" options={VIEWS} value={view} onChange={setView} />
          <button
            type="button"
            className="btn icon"
            onClick={() => setAsTable((v) => !v)}
            aria-label={asTable ? "Afficher le graphique" : "Afficher le tableau"}
          >
            {asTable ? <IconChart /> : <IconTable />}
          </button>
        </div>
      }
    >
      {error && <ErrorState error={error} />}
      {t && (
        <div className="split-figures">
          <div>
            <div className="tile-label">Heures creuses</div>
            <div className="split-value">
              {formatNumber(t.offPeak, "kWh")} <span className="meta">· {share(t.offPeak, assigned)} %</span>
            </div>
          </div>
          <div>
            <div className="tile-label">Heures pleines</div>
            <div className="split-value">
              {formatNumber(t.peak, "kWh")} <span className="meta">· {share(t.peak, assigned)} %</span>
            </div>
          </div>
          <div>
            <div className="tile-label">Non réparti</div>
            <div className="split-value">{formatNumber(t.unassigned, "kWh")}</div>
          </div>
        </div>
      )}
      {isPending ? (
        <div className="skeleton" style={{ height: 240 }} />
      ) : columns.length === 0 || (t && t.offPeak + t.peak + t.unassigned === 0) ? (
        <div className="chart-empty">Aucun relevé du compteur sur la période</div>
      ) : asTable ? (
        <div className="table-wrap" style={{ maxHeight: 340, overflowY: "auto" }}>
          <table className="table">
            <thead>
              <tr>
                <th>{view === "day" ? "Jour" : "Heure (moyenne par jour)"}</th>
                {keys.map((s) => (
                  <th key={s.key} className="num">
                    {s.label} (kWh)
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(view === "day" ? [...columns].reverse() : columns).map((col) => (
                <tr key={col.key}>
                  <td>{view === "day" ? col.title : `${col.label} – ${Number(col.key) + 1} h`}</td>
                  {keys.map((s) => (
                    <td key={s.key} className="num">
                      {formatNumber(col.segments.find((x) => x.key === s.key)?.value ?? 0, null)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <ColumnChart columns={columns} unit="kWh" />
      )}
      <div className="legend" style={{ marginTop: 12 }}>
        {keys.map((s) => (
          <span className="legend-key" key={s.key}>
            <i className="swatch-sq" style={{ background: `var(${s.color})` }} />
            {s.label}
          </span>
        ))}
      </div>
      <p className="note">
        L'énergie entre deux relevés est répartie au prorata du temps passé dans chaque plage. Un intervalle de plus
        d'une heure (trou de collecte, relevé tardif) n'est pas réparti. Le compteur ne voit pas toute la consommation
        déclarée par Atlantic : l'écart porte surtout sur les heures pleines.
      </p>
    </Card>
  );
}
