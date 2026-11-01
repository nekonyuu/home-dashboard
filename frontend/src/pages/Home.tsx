import { useEquipment, useLatest } from "../api/hooks";
import { ApplianceCard, ApplianceSwitcher } from "../components/home";
import { Alert, ErrorState, PageHeader } from "../components/ui";
import { formatAge } from "../lib/format";
import { homeAppliances } from "../lib/home";
import { indexLatest } from "../lib/latest";

/** Au-delà, LG ThinQ ne répond plus (la collecte est de 5 min) : on le dit plutôt que d'afficher d'anciens états. */
const SILENT_AFTER = 30 * 60;

export function Home() {
  const equipment = useEquipment();
  const latest = useLatest();
  const appliances = homeAppliances(equipment.data);
  const index = indexLatest(latest.data);
  const lastSeen = Math.max(0, ...appliances.map((a) => a.last_seen ?? 0));
  const silent = appliances.length > 0 && Date.now() / 1000 - lastSeen > SILENT_AFTER;

  return (
    <>
      <PageHeader title="Maison" subtitle="Électroménager connecté LG ThinQ" />
      <ApplianceSwitcher appliances={appliances} />
      {(equipment.isError || latest.isError) && <ErrorState error={equipment.error ?? latest.error} />}
      <div className="stack">
        {silent && (
          <Alert tone="warning" title="LG ThinQ ne répond plus.">
            Dernière réponse {formatAge(Date.now() / 1000 - lastSeen)}. Les états ci-dessous ne sont pas à jour ; la
            collecte Atlantic n'est pas concernée.
          </Alert>
        )}
        {equipment.isPending ? (
          <div className="grid-appliances">
            {[0, 1, 2].map((i) => (
              <div key={i} className="card skeleton" style={{ minHeight: 140 }} />
            ))}
          </div>
        ) : appliances.length === 0 ? (
          <div className="card empty-state">
            <strong style={{ color: "var(--text-2)" }}>Aucun appareil connecté</strong>
            <span>Renseignez THINQ_PAT, THINQ_COUNTRY et THINQ_CLIENT_ID dans le fichier .env puis redémarrez.</span>
          </div>
        ) : (
          <div className="grid-appliances">
            {appliances.map((a) => (
              <ApplianceCard key={a.id} equipment={a} index={index} />
            ))}
          </div>
        )}
      </div>
    </>
  );
}
