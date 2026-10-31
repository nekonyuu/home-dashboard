import { useState } from "react";

import { ApiError } from "../api/client";
import { useSchedule } from "../api/hooks";
import type { Schedule } from "../api/types";
import { formatAge, formatDuration, formatNumber, translateEnum } from "../lib/format";
import { DAY_LONG, formatMinute, groupDays, intensity, parisNow } from "../lib/schedule";
import { IconChart, IconClock, IconTable } from "./icons";
import { Card, ErrorState, Status } from "./ui";

const TICKS = [0, 360, 720, 1080, 1440];
const celsius = (v: number) => formatNumber(v, "°C");

function relative(epoch: number): string {
  const s = Math.max(0, epoch - Date.now() / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  return h ? `${h} h ${String(m).padStart(2, "0")}` : `${m} min`;
}

function nextLabel(s: Schedule): string | null {
  if (!s.next) return null;
  const at = parisNow(s.next.at * 1000);
  const day = at.weekday === parisNow().weekday ? "" : `${DAY_LONG[at.weekday].toLowerCase()} `;
  return `${celsius(s.next.setpoint)} ${day}à ${formatMinute(at.minute)}`;
}

/** Mode de consigne et dérogation : icône + libellé. */
export function ScheduleStatus({ schedule }: { schedule: Schedule }) {
  if (schedule.override?.active) {
    const left = schedule.override.remaining_minutes;
    return (
      <Status tone="warning">
        Dérogation{left ? `, encore ${formatDuration(left * 60)}` : ""}
      </Status>
    );
  }
  if (schedule.mode === 1) return <Status tone="info">Programme suivi</Status>;
  return <Status tone="neutral">{schedule.mode_display ? translateEnum(schedule.mode_display) : "Mode inconnu"}</Status>;
}

/** Prochain changement programmé, pour la tuile « Ambiance » ; vide si le programme n'est pas suivi. */
export function useNextChange(): string | null {
  const { data } = useSchedule();
  if (!data?.next || data.mode !== 1 || data.override?.active) return null;
  return nextLabel(data);
}

function Bars({ schedule }: { schedule: Schedule }) {
  const groups = groupDays(schedule);
  const all = schedule.days.flatMap((d) => d.transitions.map((t) => t.setpoint));
  const min = Math.min(...all);
  const max = Math.max(...all);
  const now = parisNow();
  return (
    <div className="sched" role="img" aria-label="Programme hebdomadaire du chauffage (vue tableau disponible)">
      {groups.map((g) => {
        const today = g.weekdays.includes(now.weekday);
        return (
          <div className="sched-row" key={g.label}>
            <div className={`sched-day${today ? " today" : ""}`}>{g.label}</div>
            <div className="sched-track">
              {g.segments.map((s) => (
                <div
                  key={s.start}
                  className={`sched-seg${s.setpoint === null ? " unknown" : ""}`}
                  style={{
                    left: `${(s.start / 1440) * 100}%`,
                    width: `${((s.end - s.start) / 1440) * 100}%`,
                    ["--k" as string]: String(Math.round(25 + 55 * intensity(s.setpoint, min, max))),
                  }}
                  title={`${formatMinute(s.start)}–${formatMinute(s.end % 1440)} : ${
                    s.setpoint === null ? "consigne de la veille" : celsius(s.setpoint)
                  }`}
                >
                  {s.end - s.start >= 90 && (
                    <span>{s.setpoint === null ? "veille" : formatNumber(s.setpoint, null)}</span>
                  )}
                </div>
              ))}
              {today && (
                <div className="sched-now" style={{ left: `${(now.minute / 1440) * 100}%` }} title="Maintenant" />
              )}
            </div>
          </div>
        );
      })}
      <div className="sched-row">
        <div />
        <div className="sched-axis">
          {TICKS.map((t) => (
            <span key={t} style={{ left: `${(t / 1440) * 100}%` }}>
              {t === 1440 ? "24 h" : `${t / 60} h`}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function ScheduleTable({ schedule }: { schedule: Schedule }) {
  return (
    <div className="table-wrap" style={{ maxHeight: 340, overflowY: "auto" }}>
      <table className="table">
        <thead>
          <tr>
            <th>Jour</th>
            <th>Changements de consigne</th>
          </tr>
        </thead>
        <tbody>
          {schedule.days.map((d) => (
            <tr key={d.weekday}>
              <td>{DAY_LONG[d.weekday]}</td>
              <td>
                {d.transitions.length
                  ? d.transitions.map((t) => `${formatMinute(t.minute)} → ${celsius(t.setpoint)}`).join(" · ")
                  : "Aucun (consigne de la veille)"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Semaine type du thermostat : plages de consigne par jour, jours identiques regroupés. */
export function ScheduleCard() {
  const { data, isPending, error } = useSchedule();
  const [asTable, setAsTable] = useState(false);
  const notYet = error instanceof ApiError && error.status === 404;
  return (
    <Card
      title="Programme de chauffage"
      subtitle={
        data
          ? `Consigne ambiante programmée, heure de Paris · modifié ${formatAge(Math.round(Date.now() / 1000) - data.updated_at)}`
          : "Consigne ambiante programmée, heure de Paris"
      }
      aside={
        <div className="topbar-actions">
          {data && <ScheduleStatus schedule={data} />}
          <button
            type="button"
            className="btn icon"
            onClick={() => setAsTable((v) => !v)}
            aria-label={asTable ? "Afficher le programme" : "Afficher le tableau"}
            title={asTable ? "Afficher le programme" : "Afficher le tableau"}
          >
            {asTable ? <IconChart /> : <IconTable />}
          </button>
        </div>
      }
    >
      {notYet ? (
        <div className="empty-state">
          <IconClock size={28} />
          <strong style={{ color: "var(--text-2)" }}>Programme pas encore reçu</strong>
          <span>Il apparaîtra après la prochaine collecte réussie.</span>
        </div>
      ) : error ? (
        <ErrorState error={error} />
      ) : isPending || !data ? (
        <div className="skeleton" style={{ height: 120 }} />
      ) : asTable ? (
        <ScheduleTable schedule={data} />
      ) : (
        <>
          {data.next && (
            <p className="meta" style={{ margin: "0 0 12px" }}>
              Maintenant {data.current_setpoint === null ? "—" : celsius(data.current_setpoint)} · ensuite{" "}
              {nextLabel(data)} (dans {relative(data.next.at)})
            </p>
          )}
          <Bars schedule={data} />
          {data.mode !== null && data.mode !== 1 && (
            <p className="meta" style={{ margin: "10px 0 0" }}>
              Le thermostat n'est pas en mode programmé : ce programme n'est pas appliqué actuellement.
            </p>
          )}
        </>
      )}
    </Card>
  );
}
