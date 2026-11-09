import { type ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useEnergy, useEquipment, useHealth, useLatest } from "../api/hooks";
import type { Latest } from "../api/types";
import { metricsOf, ProgressBar, summaryOf } from "../components/home";
import { ApplianceIcon } from "../components/home";
import { IconBolt, IconDrop, IconFlame, IconGauge } from "../components/icons";
import { ErrorState, Status, ValueText } from "../components/ui";
import { formatDay, formatLatest, formatNumber } from "../lib/format";
import { homeAppliances } from "../lib/home";
import { findMetric, indexLatest } from "../lib/latest";
import { isoDay } from "../lib/range";
import { latestEnergyDay } from "../lib/tablet";

const clockFmt = new Intl.DateTimeFormat("fr-FR", { timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit" });
const dateFmt = new Intl.DateTimeFormat("fr-FR", { timeZone: "Europe/Paris", weekday: "long", day: "numeric", month: "long" });

function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 15_000);
    return () => clearInterval(id);
  }, []);
  return now;
}

function Tile({
  to,
  label,
  icon,
  status,
  wide,
  children,
}: {
  to: string;
  label: string;
  icon: ReactNode;
  status?: ReactNode;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <Link to={to} className={`card kiosk-tile${wide ? " wide" : ""}`}>
      <div className="kiosk-label">
        {icon}
        <span>{label}</span>
        {status && <span className="kiosk-status">{status}</span>}
      </div>
      {children}
    </Link>
  );
}

function Big({ value }: { value: Latest | undefined }) {
  return (
    <div className="kiosk-value">
      <ValueText value={value} />
    </div>
  );
}

export function Tablet() {
  const now = useNow();
  const latest = useLatest();
  const equipment = useEquipment();
  const health = useHealth();
  const energy = useEnergy(isoDay(now.getTime() - 31 * 86_400_000), isoDay(now.getTime()));
  const index = indexLatest(latest.data);
  const appliances = homeAppliances(equipment.data);

  const room = findMetric(index, "room_temperature");
  const roomSetpoint = findMetric(index, "room_setpoint");
  const outdoor = findMetric(index, "outdoor_temperature");
  const heating = findMetric(index, "heating_ongoing");
  const dhwTemp = findMetric(index, "dhw_temperature");
  const dhwSetpoint = findMetric(index, "dhw_setpoint");
  const dhwStatus = findMetric(index, "dhw_status");
  const errors = typeof findMetric(index, "active_errors")?.value === "number" ? (findMetric(index, "active_errors")?.value as number) : 0;
  const day = latestEnergyDay(energy.data);
  const collect = health.data?.poller;

  return (
    <div className="kiosk">
      <header className="kiosk-head">
        <div>
          <div className="kiosk-clock">{clockFmt.format(now)}</div>
          <div className="kiosk-date">{dateFmt.format(now)}</div>
        </div>
        <div className="kiosk-head-status">
          {errors > 0 && <Status tone="critical">{`${errors} erreur(s) PAC`}</Status>}
          {collect?.stopped_reason ? (
            <Status tone="critical">Collecte arrêtée</Status>
          ) : collect?.stale ? (
            <Status tone="warning">Collecte en retard</Status>
          ) : null}
        </div>
      </header>
      {latest.isError && <ErrorState error={latest.error} />}
      <div className="kiosk-grid">
        <Tile
          to="/chauffage"
          label="Ambiance"
          icon={<IconFlame size={18} />}
          status={heating?.value === true ? <Status tone="info">Chauffe</Status> : undefined}
        >
          <Big value={room} />
          <div className="kiosk-sub">Consigne {formatLatest(roomSetpoint)}</div>
        </Tile>
        <Tile to="/chauffage" label="Extérieur" icon={<IconGauge size={18} />}>
          <Big value={outdoor} />
          <div className="kiosk-sub">{formatLatest(findMetric(index, "generator_status")) || "Pompe à chaleur"}</div>
        </Tile>
        <Tile
          to="/ecs"
          label="Chauffe-eau"
          icon={<IconDrop size={18} />}
          status={dhwStatus && dhwStatus.value !== null ? <Status tone="info">{formatLatest(dhwStatus)}</Status> : undefined}
        >
          <Big value={dhwTemp} />
          <div className="kiosk-sub">Consigne {formatLatest(dhwSetpoint)}</div>
        </Tile>
        {day && (
          <Tile to="/energie" label={`Énergie · ${formatDay(day.day)}`} icon={<IconBolt size={18} />}>
            <div className="kiosk-value">
              {formatNumber(day.total).replace(/\s?$/, "")}
              <span className="unit">kWh</span>
            </div>
            <div className="kiosk-sub">
              Chauffage {formatNumber(day.heating, "kWh")} · Eau chaude {formatNumber(day.dhw, "kWh")}
            </div>
          </Tile>
        )}
        {appliances.map((a) => {
          const s = summaryOf(a, metricsOf(index, a.id));
          return (
            <Tile
              key={a.id}
              to={`/appareils/${a.id}`}
              label={a.label}
              icon={<ApplianceIcon kind={a.kind} size={18} />}
              status={<Status tone={s.tone}>{s.status}</Status>}
            >
              <div className="kiosk-headline">{s.headline}</div>
              {s.progress !== null && <ProgressBar value={s.progress} label={`Progression du cycle, ${a.label}`} />}
              {s.detail && <div className="kiosk-sub">{s.detail}</div>}
            </Tile>
          );
        })}
      </div>
    </div>
  );
}
