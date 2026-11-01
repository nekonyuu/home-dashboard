import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";

import type { Equipment, Latest } from "../api/types";
import { formatAge } from "../lib/format";
import { cyclePhase, cycleProgress, formatEndTime, formatMinutes, num, PHASE_TONE, type CyclePhase } from "../lib/home";
import { IconAppliances, IconDishwasher, IconFridge, IconWasher } from "./icons";
import { Status, type Tone } from "./ui";

export const APPLIANCE_ICON: Record<string, (p: { size?: number }) => ReactNode> = {
  washer: IconWasher,
  dishwasher: IconDishwasher,
  fridge: IconFridge,
};

export function ApplianceIcon({ kind, size = 18 }: { kind: string; size?: number }) {
  const Icon = APPLIANCE_ICON[kind] ?? IconAppliances;
  return <>{Icon({ size })}</>;
}

/** Valeurs de l'appareil, indexées par métrique. */
export function metricsOf(index: Map<string, Latest>, equipment: string) {
  return (metric: string) => index.get(`${equipment}/${metric}`);
}

const PHASE_LABEL: Record<CyclePhase, string> = {
  off: "Éteint",
  idle: "Prêt",
  running: "En cours",
  paused: "En pause",
  done: "Terminé",
  error: "Erreur",
  unknown: "État inconnu",
};

export interface Summary {
  tone: Tone;
  status: string;
  headline: string;
  progress: number | null;
  detail: string | null;
}

/** Résumé d'un lave-linge ou d'un lave-vaisselle. Un appareil hors ligne n'affiche pas son dernier cycle connu. */
export function washerSummary(e: Equipment, get: (m: string) => Latest | undefined): Summary {
  if (e.available === false) {
    return {
      tone: "neutral",
      status: "Hors ligne",
      headline: "Éteint ou hors réseau",
      progress: null,
      detail: e.last_seen ? `Dernier échange ${formatAge(Date.now() / 1000 - e.last_seen)}` : null,
    };
  }
  const state = get("run_state");
  const phase = cyclePhase(state?.value);
  const remaining = num(get("remaining_minutes"));
  const total = num(get("total_minutes"));
  const label = state?.display ?? PHASE_LABEL[phase];
  if (phase === "running" && remaining !== null && state) {
    return {
      tone: PHASE_TONE[phase],
      status: label,
      headline: `${formatMinutes(remaining)} restantes`,
      progress: cycleProgress(remaining, total),
      detail: `Fin vers ${formatEndTime(state.polled_at, remaining)}`,
    };
  }
  return { tone: PHASE_TONE[phase], status: label, headline: PHASE_LABEL[phase], progress: null, detail: null };
}

export function fridgeSummary(e: Equipment, get: (m: string) => Latest | undefined): Summary {
  if (e.available === false) {
    return { tone: "neutral", status: "Hors ligne", headline: "Pas de réponse", progress: null, detail: null };
  }
  const door = get("door_open");
  const open = door?.value === true;
  const f = num(get("fridge_setpoint"));
  const z = num(get("freezer_setpoint"));
  const fmt = (v: number | null) => (v === null ? "—" : `${v.toLocaleString("fr-FR")} °C`);
  return {
    tone: open ? "warning" : "good",
    status: open ? "Porte ouverte" : "Porte fermée",
    headline: `${fmt(f)} · ${fmt(z)}`,
    progress: null,
    detail: "Consignes réfrigérateur · congélateur",
  };
}

export function summaryOf(e: Equipment, get: (m: string) => Latest | undefined): Summary {
  return e.kind === "fridge" ? fridgeSummary(e, get) : washerSummary(e, get);
}

export function ProgressBar({ value, label }: { value: number; label: string }) {
  const pct = Math.round(value * 100);
  return (
    <div className="progress" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
      <div className="progress-fill" style={{ width: `${pct}%` }} />
    </div>
  );
}

/** Carte d'un appareil, cliquable vers son détail. */
export function ApplianceCard({ equipment, index }: { equipment: Equipment; index: Map<string, Latest> }) {
  const s = summaryOf(equipment, metricsOf(index, equipment.id));
  return (
    <Link to={`/appareils/${equipment.id}`} className="card appliance-card">
      <div className="appliance-head">
        <span className="appliance-icon">
          <ApplianceIcon kind={equipment.kind} size={22} />
        </span>
        <div>
          <h2 className="card-title">{equipment.label}</h2>
        </div>
        <Status tone={s.tone}>{s.status}</Status>
      </div>
      <div className="appliance-headline">{s.headline}</div>
      {s.progress !== null && <ProgressBar value={s.progress} label={`Progression du cycle, ${equipment.label}`} />}
      {s.detail && <div className="meta">{s.detail}</div>}
    </Link>
  );
}

/** Sélecteur d'appareil pour mobile (puces défilantes) ; sur desktop, la barre latérale joue ce rôle. */
export function ApplianceSwitcher({ appliances }: { appliances: Equipment[] }) {
  return (
    <nav className="switcher" aria-label="Appareils">
      <NavLink to="/appareils" end>
        <IconAppliances size={15} />
        Tous
      </NavLink>
      {appliances.map((a) => (
        <NavLink key={a.id} to={`/appareils/${a.id}`}>
          <ApplianceIcon kind={a.kind} size={15} />
          {a.label}
        </NavLink>
      ))}
    </nav>
  );
}
