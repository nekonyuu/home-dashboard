# Station météo Netatmo : découverte et plan d'intégration

Statut : **sonde écrite, jamais exécutée ; adaptateur non commencé.** Ne modifie pas `PLAN.md` (réservé au propriétaire).
Tout ce qui suit vient de la documentation publique Netatmo Connect, **aucun appel réel** n'a été fait : à confirmer par la sonde.

## 1. API

- Application à créer sur `dev.netatmo.com` (compte Netatmo habituel) : `client_id` + `client_secret`.
- Jeton `read_station` généré par le « token generator » de la console : `access_token` (3 h) + `refresh_token`.
- `POST https://api.netatmo.com/oauth2/token` (`grant_type=refresh_token`) renvoie un **nouveau refresh token à chaque appel** et
  invalide l'ancien. Il faudra donc le **persister en base** (migration SQLite), `NETATMO_REFRESH_TOKEN` ne servant qu'à l'amorçage.
  `invalid_grant` = arrêt définitif des tentatives (comme Atlantic et ThinQ).
- Lecture : `GET /api/getstationsdata` (base + modules, `dashboard_data` par module, `reachable`, `battery_percent`).
- Historique : `GET /api/getmeasure` (`device_id`, `module_id`, `scale`, `type`, `date_begin`, `limit` ≤ 1024). Contrairement à
  Atlantic, un vrai rattrapage au démarrage est possible (`HistorySource`).
- Limites annoncées : ~50 requêtes / 10 s et ~500 / h par utilisateur. La station publie environ toutes les 10 min.

## 2. Mesures attendues (selon les modules possédés)

Base intérieure : température, humidité, CO₂, bruit, pression. Extérieur : température, humidité. Pluviomètre : pluie
(instantanée, 1 h, 24 h). Anémomètre : vent, direction, rafales. À confirmer par la sonde.

## 3. Plan

1. Exécuter la sonde (ci-dessous) ; relire la fixture anonymisée avant de la commiter.
2. `adapters/outbound/netatmo/` : `client.py`, `mapping.py`, `gateway.py`, `semantics.yaml` (mêmes ports que ThinQ), contrat
   import-linter d'indépendance vis-à-vis de Magellan et ThinQ.
3. Fournisseur **secondaire** dans `application/composite.py` (panne journalisée et ignorée).
4. Config optionnelle `NETATMO_*` (`config.py`), table de persistance du refresh token.
5. Front : carte « Météo » sur la page Maison, éventuellement une page dédiée ; couleurs dans `palette.ts`.

## 4. Lancer la sonde

```
cd backend && set -a && source ../.env && set +a && uv run python scripts/discover_netatmo.py
```

Le nouveau refresh token est écrit dans `backend/.netatmo_refresh_token` (600, hors git) et prioritaire sur le `.env` aux
essais suivants. `--refixture` régénère la fixture depuis le dump sans réseau.

## 5. Plan de travail (à coller comme prompt sur le Mac)

```
Lis CLAUDE.md et docs/netatmo-discovery.md. Objectif : intégrer ma station météo Netatmo (fournisseur secondaire,
lecture seule). Ne modifie pas PLAN.md. Travaille par étapes, lint + tests verts avant chaque commit, et arrête-toi aux
points ⏸ pour me montrer le résultat.

Étape 0 ⏸ Sonde. J'ai renseigné NETATMO_* dans .env. Lance backend/scripts/discover_netatmo.py (une seule fois : le refresh
  token tourne), relis la fixture anonymisée (aucun nom, MAC, lieu, coordonnées), complète docs/netatmo-discovery.md avec
  les modules réellement présents, les types de mesures, les unités, la fréquence de publication et la profondeur de
  getmeasure. Montre-moi le résumé avant de continuer.
Étape 1. Migration SQLite + port pour persister le refresh token (NETATMO_REFRESH_TOKEN = amorçage seulement ; écrire le
  nouveau token AVANT tout autre appel suivant le renouvellement). invalid_grant = arrêt définitif (CredentialsRejected).
Étape 2. adapters/outbound/netatmo/ : client.py (jeton, 429 -> ProviderThrottled, 5xx/timeout -> ProviderUnavailable),
  mapping.py, gateway.py (EquipmentGateway, MetricCatalog), semantics.yaml. Équipements reconnus par type de module, pas par nom.
  Contrat import-linter : indépendant de Magellan et ThinQ. Tests sur la fixture (même esprit que test_magellan_mapping).
Étape 3. Config optionnelle (config.py, .env.example, README), branchement dans composite.py comme fournisseur secondaire,
  intervalle de lecture ~10 min, composition root dans main.py.
Étape 4. HistorySource via getmeasure (rattrapage au démarrage, trous conservés, jamais de donnée inventée) + test de contrat.
Étape 5 ⏸ Front : carte Météo sur la page Maison (+ page dédiée si pertinent), couleurs fixes dans palette.ts, textes en
  français (format.ts), vue tableau, module hors ligne en gris. Vérifier sur la démo (ajouter des données synthétiques
  Netatmo dans scripts/demo_server.py uniquement) : desktop 1440 px, mobile 390 px, clair et sombre.
Étape 6. Mettre à jour CLAUDE.md (section Netatmo) et le statut de docs/netatmo-discovery.md.
```
