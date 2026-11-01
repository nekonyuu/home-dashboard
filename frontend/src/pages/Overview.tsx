import { Link } from "react-router-dom";

import { useEquipment, useHealth, useLatest } from "../api/hooks";
import type { Latest, Series } from "../api/types";
import { Sparkline } from "../components/charts";
import { ApplianceCard } from "../components/home";
import { IconGauge } from "../components/icons";
import { Card, ErrorState, Freshness, PageHeader, Status, ValueText } from "../components/ui";
import { formatAge, formatBytes, formatDuration, formatLatest, formatNumber, GAP_CAUSES } from "../lib/format";
import { homeAppliances, isHomeKind } from "../lib/home";
import { findMetric, indexLatest } from "../lib/latest";
import { useTrends } from "../lib/useTrends";

const KIND_ORDER = ["heat_pump", "generator", "dhw", "circuit", "room"];

// Échelle de la jauge du ballon (°C)
const TANK_MIN = 10;
const TANK_MAX = 65;

function tankLevel(t: number | null): number {
  if (t === null) return 0;
  return Math.min(Math.max((t - TANK_MIN) / (TANK_MAX - TANK_MIN), 0), 1);
}

function num(l: Latest | undefined): number | null {
  return l && typeof l.value === "number" ? l.value : null;
}

function DhwHero({ index }: { index: Map<string, Latest> }) {
  const temp = findMetric(index, "dhw_temperature");
  const setpoint = findMetric(index, "dhw_setpoint");
  const status = findMetric(index, "dhw_status");
  const boost = findMetric(index, "dhw_boost");
  const charge = findMetric(index, "dhw_charge_setpoint");
  const on = findMetric(index, "dhw_on");
  const t = num(temp);
  const sp = num(setpoint);
  const reached = t !== null && sp !== null && t >= sp - 2;

  return (
    <section className="card card-col">
      <div className="hero">
        <div className="tank" role="img" aria-label={`Ballon : ${formatLatest(temp)} pour une consigne de ${formatLatest(setpoint)}`}>
          <div className="tank-fill" style={{ height: `${tankLevel(t) * 100}%` }} />
          {sp !== null && <div className="tank-mark" style={{ bottom: `${tankLevel(sp) * 100}%` }} title="Consigne" />}
        </div>
        <div>
          <div className="hero-label">
            Chauffe-eau
            {on && on.value === false ? (
              <Status tone="critical">Désactivée</Status>
            ) : reached ? (
              <Status tone="good">Consigne atteinte</Status>
            ) : (
              <Status tone="info">En dessous de la consigne</Status>
            )}
          </div>
          <div className="hero-value">
            <ValueText value={temp} />
          </div>
          <Freshness value={temp} />
          <div className="hero-meta">
            <span>
              Consigne <b>{formatLatest(setpoint)}</b>
            </span>
            {status && (
              <span>
                Production <b>{formatLatest(status)}</b>
              </span>
            )}
            {charge && (
              <span>
                Charge cible <b>{formatLatest(charge)}</b>
              </span>
            )}
            {boost && boost.value !== null && (
              <span>
                Boost <b>{boost.value ? "actif" : "inactif"}</b>
              </span>
            )}
          </div>
        </div>
      </div>
      <div className="card-foot">
        <Link to="/ecs" className="card-link">
          Voir le chauffe-eau
        </Link>
      </div>
    </section>
  );
}

function EquipmentCard() {
  const { data } = useEquipment();
  return (
    <Card title="Équipements" subtitle="Disponibilité vue par le cloud Atlantic">
      <ul className="list">
        {[...(data ?? [])].filter((e) => !isHomeKind(e.kind)).sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind)).map((e) => (
          <li key={e.id}>
            <span>
              <span className="primary">{e.label}</span>
              <br />
              <span className="secondary">{e.last_seen ? `vu ${formatAge(Date.now() / 1000 - e.last_seen)}` : "jamais vu"}</span>
            </span>
            {e.available === false ? (
              <Status tone="critical">Injoignable</Status>
            ) : e.available ? (
              <Status tone="good">En ligne</Status>
            ) : (
              <Status tone="neutral">Inconnu</Status>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function CollectCard() {
  const { data } = useHealth();
  if (!data) return <div className="card skeleton" style={{ minHeight: 180 }} />;
  const gaps = data.recent_gaps;
  const errors = Object.values(data.errors.counts).reduce((a, b) => a + b, 0);
  return (
    <Card title="Collecte" subtitle="7 derniers jours">
      <ul className="list">
        <li>
          <span className="secondary">Dernière collecte réussie</span>
          <span className="kv">
            {data.poller.last_success ? formatAge(Date.now() / 1000 - data.poller.last_success) : "—"}
          </span>
        </li>
        <li>
          <span className="secondary">Interruptions</span>
          <span className="kv">
            {gaps.length === 0
              ? "Aucune"
              : `${gaps.length} · ${formatDuration(gaps.reduce((a, g) => a + g.duration_seconds, 0))}`}
          </span>
        </li>
        {gaps.slice(-2).map((g) => (
          <li key={g.start}>
            <span className="secondary">
              {GAP_CAUSES[g.cause] ?? g.cause}
              {g.ongoing ? " (en cours)" : ""}
            </span>
            <span className="kv">{formatDuration(g.duration_seconds)}</span>
          </li>
        ))}
        <li>
          <span className="secondary">Erreurs récentes</span>
          <span className="kv">{errors}</span>
        </li>
        <li>
          <span className="secondary">Base de données</span>
          <span className="kv">{formatBytes(data.db_size_bytes)}</span>
        </li>
      </ul>
    </Card>
  );
}

function HeatingCard({ index, trend }: { index: Map<string, Latest>; trend: Series | undefined }) {
  const room = findMetric(index, "room_temperature");
  const setpoint = findMetric(index, "room_setpoint");
  const errors = num(findMetric(index, "active_errors")) ?? 0;
  const rows: [string, Latest | undefined][] = [
    ["Mode thermostat", findMetric(index, "thermostat_mode")],
    ["Programmation", findMetric(index, "setpoint_mode")],
    ["Chauffe en cours", findMetric(index, "heating_ongoing")],
    ["Extérieur", findMetric(index, "outdoor_temperature")],
    ["Départ / retour d'eau", undefined],
    ["Pression du circuit", findMetric(index, "water_pressure")],
  ];
  const flow = num(findMetric(index, "flow_temperature"));
  const back = num(findMetric(index, "return_temperature"));
  return (
    <section className="card card-col">
      <div className="card-head">
        <div>
          <h2 className="card-title">Chauffage</h2>
          <p className="card-sub">Pompe à chaleur · {formatLatest(findMetric(index, "generator_status")) || "—"}</p>
        </div>
        <Status tone={errors > 0 ? "critical" : "good"}>{errors > 0 ? `${errors} erreur(s)` : "Aucune erreur"}</Status>
      </div>
      <div className="heating-main">
        <div>
          <div className="hero-label">Ambiance</div>
          <div className="hero-value small">
            <ValueText value={room} />
          </div>
          <div className="meta">Consigne {formatLatest(setpoint)}</div>
        </div>
        <Sparkline series={trend} />
      </div>
      <ul className="list">
        {rows.map(([label, v]) => (
          <li key={label}>
            <span className="secondary">{label}</span>
            <span className="kv">
              {label.startsWith("Départ")
                ? flow !== null && back !== null
                  ? `${formatNumber(flow, "°C")} / ${formatNumber(back, "°C")}`
                  : "—"
                : formatLatest(v)}
            </span>
          </li>
        ))}
      </ul>
      <div className="card-foot">
        <Link to="/chauffage" className="card-link">
          Voir le chauffage
        </Link>
      </div>
    </section>
  );
}

function SectionTitle({ title, to, linkLabel }: { title: string; to?: string; linkLabel?: string }) {
  return (
    <div className="section-title">
      <h2>{title}</h2>
      {to && (
        <Link to={to} className="card-link">
          {linkLabel}
        </Link>
      )}
    </div>
  );
}

export function Overview() {
  const latest = useLatest();
  const equipment = useEquipment();
  const index = indexLatest(latest.data);
  const trends = useTrends([{ equipment: "room_1", metric: "room_temperature" }]);
  const loading = latest.isPending;
  const appliances = homeAppliances(equipment.data);
  const updated = latest.data?.length ? Math.min(...latest.data.map((l) => l.age_seconds)) : null;

  return (
    <>
      <PageHeader
        title="Maison"
        subtitle={updated !== null ? `Dernière mesure reçue ${formatAge(updated)}` : "En attente des premières mesures"}
      />
      {latest.isError && <ErrorState error={latest.error} />}
      <div className="stack">
        <section className="stack tight">
          <SectionTitle title="Pompe à chaleur" />
          <div className="grid-2">
            {loading ? (
              <>
                <div className="card skeleton" style={{ minHeight: 320 }} />
                <div className="card skeleton" style={{ minHeight: 320 }} />
              </>
            ) : (
              <>
                <HeatingCard index={index} trend={trends.get("room_1/room_temperature")} />
                <DhwHero index={index} />
              </>
            )}
          </div>
        </section>
        {appliances.length > 0 && (
          <section className="stack tight">
            <SectionTitle title="Électroménager" to="/appareils" linkLabel="Tout voir" />
            <div className="grid-appliances">
              {appliances.map((a) => (
                <ApplianceCard key={a.id} equipment={a} index={index} />
              ))}
            </div>
          </section>
        )}
        <section className="stack tight">
          <SectionTitle title="Système" />
          <div className="grid-2">
            <EquipmentCard />
            <CollectCard />
          </div>
        </section>
        <p className="note" style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <IconGauge size={14} /> Les valeurs de la pompe à chaleur sont celles transmises par le cloud Atlantic ; elles ne
          changent que lorsque l'installation signale une évolution.
        </p>
      </div>
    </>
  );
}
