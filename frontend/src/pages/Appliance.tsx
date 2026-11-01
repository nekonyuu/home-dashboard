import { Link, useParams } from "react-router-dom";

import { useEquipment, useLatest, useSeries } from "../api/hooks";
import type { Equipment, Latest } from "../api/types";
import { ChartCard } from "../components/charts";
import {
  ApplianceIcon,
  ApplianceSwitcher,
  ProgressBar,
  metricsOf,
  summaryOf,
} from "../components/home";
import { IconClock, IconDoor, IconThermo } from "../components/icons";
import { ErrorState, Freshness, PageHeader, Segmented, Status, Tile } from "../components/ui";
import { formatAge } from "../lib/format";
import { homeAppliances } from "../lib/home";
import { indexLatest } from "../lib/latest";
import { usePreset } from "../lib/usePreset";

type Get = (metric: string) => Latest | undefined;

function Hero({ equipment, get }: { equipment: Equipment; get: Get }) {
  const s = summaryOf(equipment, get);
  const anchor = get("run_state") ?? get("door_open");
  return (
    <section className="card">
      <div className="hero appliance-hero">
        <span className="appliance-icon large">
          <ApplianceIcon kind={equipment.kind} size={34} />
        </span>
        <div className="grow">
          <div className="hero-label">
            {equipment.label}
            <Status tone={s.tone}>{s.status}</Status>
          </div>
          <div className="hero-value small">{s.headline}</div>
          {s.progress !== null && <ProgressBar value={s.progress} label="Progression du cycle" />}
          <div className="hero-meta">
            {s.detail && <span>{s.detail}</span>}
            {equipment.available !== false && <Freshness value={anchor} />}
          </div>
        </div>
      </div>
    </section>
  );
}

function Tiles({ equipment, get, loading }: { equipment: Equipment; get: Get; loading: boolean }) {
  const offline = equipment.available === false;
  const only = (l: Latest | undefined) => (offline ? undefined : l); // pas de dernier état connu trompeur
  if (equipment.kind === "fridge") {
    return (
      <div className="grid-tiles">
        <Tile label="Réfrigérateur" icon={<IconThermo size={16} />} value={get("fridge_setpoint")} extra="Consigne" loading={loading} />
        <Tile label="Congélateur" icon={<IconThermo size={16} />} value={get("freezer_setpoint")} extra="Consigne" loading={loading} />
        <Tile label="Porte ouverte" icon={<IconDoor size={16} />} value={only(get("door_open"))} loading={loading} />
        <Tile label="Mode express" value={only(get("express_mode"))} loading={loading} />
        <Tile label="Mode éco" value={only(get("eco_mode"))} loading={loading} />
      </div>
    );
  }
  const isDish = equipment.kind === "dishwasher";
  return (
    <div className="grid-tiles">
      <Tile label="État du cycle" value={only(get("run_state"))} loading={loading} />
      <Tile label="Temps restant" icon={<IconClock size={16} />} value={only(get("remaining_minutes"))} loading={loading} />
      <Tile label="Durée du cycle" value={only(get("total_minutes"))} loading={loading} />
      {isDish ? (
        <>
          <Tile label="Programme" value={only(get("course"))} loading={loading} />
          <Tile label="Porte ouverte" icon={<IconDoor size={16} />} value={only(get("door_open"))} loading={loading} />
          <Tile label="Liquide de rinçage à remplir" value={only(get("rinse_refill"))} loading={loading} />
        </>
      ) : (
        <>
          <Tile label="Cycles effectués" value={get("cycle_count")} loading={loading} />
          <Tile label="Pilotage à distance" value={only(get("remote_control"))} loading={loading} />
        </>
      )}
    </div>
  );
}

function History({ equipment }: { equipment: Equipment }) {
  const fridge = equipment.kind === "fridge";
  const period = usePreset(fridge ? "30j" : "7j");
  const requests = fridge
    ? [
        { equipment: equipment.id, metric: "fridge_setpoint" },
        { equipment: equipment.id, metric: "freezer_setpoint" },
      ]
    : [{ equipment: equipment.id, metric: "remaining_minutes" }];
  const { series, loading, error } = useSeries(requests, period.range);
  return (
    <>
      {error ? <ErrorState error={error} /> : null}
      <ChartCard
        title={fridge ? "Consignes" : "Activité"}
        subtitle={
          fridge
            ? "Réglages du réfrigérateur et du congélateur, en pointillé"
            : "Temps restant du cycle : chaque descente est un lavage, les trous sont des périodes sans donnée"
        }
        series={series}
        loading={loading}
        height={260}
        actions={<Segmented label="Période" options={period.options} value={period.id} onChange={period.setId} />}
      />
    </>
  );
}

export function Appliance() {
  const { id } = useParams();
  const equipment = useEquipment();
  const latest = useLatest();
  const appliances = homeAppliances(equipment.data);
  const current = appliances.find((a) => a.id === id);
  const index = indexLatest(latest.data);

  if (equipment.isPending) {
    return <div className="card skeleton" style={{ minHeight: 220 }} />;
  }
  if (!current) {
    return (
      <>
        <PageHeader title="Électroménager" />
        <ApplianceSwitcher appliances={appliances} />
        <div className="card empty-state">
          <strong style={{ color: "var(--text-2)" }}>Appareil introuvable</strong>
          <Link to="/appareils">Retour aux appareils</Link>
        </div>
      </>
    );
  }
  const get = metricsOf(index, current.id);
  return (
    <>
      <PageHeader
        title={current.label}
        subtitle={current.last_seen ? `LG ThinQ · dernier échange ${formatAge(Date.now() / 1000 - current.last_seen)}` : "LG ThinQ"}
      />
      <ApplianceSwitcher appliances={appliances} />
      {latest.isError && <ErrorState error={latest.error} />}
      <div className="stack">
        <Hero equipment={current} get={get} />
        <Tiles equipment={current} get={get} loading={latest.isPending} />
        <History equipment={current} />
      </div>
    </>
  );
}
