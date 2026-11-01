import { type ReactNode, useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useEnergy, useEquipment, useHealth } from "../api/hooks";
import { formatAge } from "../lib/format";
import { homeAppliances } from "../lib/home";
import { isoDay } from "../lib/range";
import { ApplianceIcon } from "./home";
import { IconAppliances, IconAuto, IconBolt, IconChart, IconDrop, IconFlame, IconHome, IconMoon, IconSun } from "./icons";
import { StatusBanner } from "./StatusBanner";
import { Status } from "./ui";

type Theme = "auto" | "light" | "dark";
const THEME_KEY = "pac-theme";

function readTheme(): Theme {
  try {
    const t = localStorage.getItem(THEME_KEY);
    return t === "light" || t === "dark" ? t : "auto";
  } catch {
    return "auto";
  }
}

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(readTheme);
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* stockage indisponible : le choix vaut pour la session */
    }
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "auto" ? "light" : t === "light" ? "dark" : "auto"))];
}

const THEME = {
  auto: { icon: <IconAuto />, label: "Thème : système" },
  light: { icon: <IconSun />, label: "Thème : clair" },
  dark: { icon: <IconMoon />, label: "Thème : sombre" },
};

interface NavItem {
  to: string;
  label: string;
  short: string;
  icon: ReactNode;
}

/** Navigation centrée sur la maison : l'accueil, puis ses éléments (pompe à chaleur, électroménager), puis les vues transverses. */
function useNav() {
  const now = Date.now();
  // la page Énergie n'apparaît que si le fournisseur déclare des consommations
  const energy = useEnergy(isoDay(now - 31 * 86_400_000), isoDay(now));
  const equipment = useEquipment();
  const appliances = homeAppliances(equipment.data);
  const home: NavItem = { to: "/", label: "Maison", short: "Maison", icon: <IconHome /> };
  const heatPump: NavItem[] = [
    { to: "/chauffage", label: "Chauffage", short: "Chauffage", icon: <IconFlame /> },
    { to: "/ecs", label: "Chauffe-eau", short: "ECS", icon: <IconDrop /> },
  ];
  const devices: NavItem[] = appliances.map((a) => ({
    to: `/appareils/${a.id}`,
    label: a.label,
    short: a.label,
    icon: <ApplianceIcon kind={a.kind} size={18} />,
  }));
  const views: NavItem[] = [{ to: "/historique", label: "Historique", short: "Historique", icon: <IconChart /> }];
  if ((energy.data?.length ?? 0) > 0) views.push({ to: "/energie", label: "Énergie", short: "Énergie", icon: <IconBolt /> });
  // mobile : un onglet par ensemble ; les appareils partagent l'onglet « Appareils » (puces dans la page)
  const tabs: NavItem[] = [
    home,
    ...heatPump,
    ...(appliances.length ? [{ to: "/appareils", label: "Appareils", short: "Appareils", icon: <IconAppliances /> }] : []),
    ...views,
  ];
  return { home, heatPump, devices, views, tabs };
}

function NavGroup({ label, items }: { label: string; items: NavItem[] }) {
  if (items.length === 0) return null;
  return (
    <div className="nav-group" role="group" aria-label={label}>
      <div className="nav-group-label">{label}</div>
      {items.map((i) => (
        <NavLink key={i.to} to={i.to} className="nav-link">
          {i.icon}
          {i.label}
        </NavLink>
      ))}
    </div>
  );
}

function CollectStatus() {
  const { data, isError } = useHealth();
  if (isError) return <Status tone="critical">Serveur injoignable</Status>;
  if (!data) return null;
  if (data.poller.stopped_reason) return <Status tone="critical">Collecte arrêtée</Status>;
  if (data.poller.stale) return <Status tone="warning">Collecte en retard</Status>;
  return <Status tone="good">Collecte active</Status>;
}

export function Layout() {
  const [theme, nextTheme] = useTheme();
  const nav = useNav();
  const health = useHealth();
  const last = health.data?.poller.last_success;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <IconHome size={17} />
          </span>
          <span>
            Ma maison<small>Tableau de bord</small>
          </span>
        </div>
        <nav aria-label="Pages">
          <NavLink to={nav.home.to} end className="nav-link">
            {nav.home.icon}
            {nav.home.label}
          </NavLink>
          <NavGroup label="Pompe à chaleur" items={nav.heatPump} />
          <NavGroup label="Électroménager" items={nav.devices} />
          <NavGroup label="Vues" items={nav.views} />
        </nav>
        <div className="sidebar-foot">
          <CollectStatus />
          {last ? <span>Dernière collecte {formatAge(Date.now() / 1000 - last)}</span> : null}
          <button type="button" className="btn" onClick={nextTheme} aria-label={THEME[theme].label}>
            {THEME[theme].icon}
            {THEME[theme].label}
          </button>
        </div>
      </aside>

      <div className="main">
        <div className="mobile-brand">
          <span className="brand-mark">
            <IconHome size={17} />
          </span>
          <span style={{ marginRight: "auto" }}>Ma maison</span>
          <CollectStatus />
          <button type="button" className="btn icon" onClick={nextTheme} aria-label={THEME[theme].label}>
            {THEME[theme].icon}
          </button>
        </div>
        <StatusBanner />
        <Outlet />
      </div>

      <nav className="tabbar" aria-label="Pages">
        {nav.tabs.map((i) => (
          <NavLink key={i.to} to={i.to} end={i.to === "/" || i.to === "/appareils"}>
            {i.icon}
            {i.short}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
