# LG ThinQ : découverte et plan d'intégration

Statut : **sonde exécutée (§6), adaptateur non commencé.** Ne modifie pas `PLAN.md` (réservé au propriétaire).
Appareils visés : une machine à laver et un frigo LG. Découverte faite par recherche web uniquement, **aucun appel réel**.

## 1. Renommage du dépôt en `home-dashboard`

**Fait** : dépôt renommé par le propriétaire, références à l'image ghcr, README, CLAUDE.md et remote mises à jour. Reste côté NAS : pointer `PAC_IMAGE` vers `ghcr.io/nekonyuu/home-dashboard` (et vérifier la visibilité privée du nouveau paquet). Rappel des effets de bord :
- image ancienne `ghcr.io/nekonyuu/atlantic-dashboard` (CI `.github/workflows/ci.yml`, `docker-compose.yml`, variable `PAC_IMAGE`) ; le NAS devra pointer vers la nouvelle image ;
- `README.md`, `CLAUDE.md`, nom du paquet backend s'il porte l'ancien nom ;
- `CLAUDE.md` mentionne Magellan comme seule source : à reformuler pour un projet multi-fournisseurs.

GitHub redirige l'ancien nom du dépôt, mais pas forcément les chemins ghcr.io.

## 2. L'API officielle « ThinQ Connect »

Ouverte par LG en décembre 2024. Cadre officiel, contrairement à Magellan (non documenté).
- API REST serveur-à-serveur : état, commandes, abonnements push/événements.
- Authentification : **Personal Access Token (PAT)** généré avec le compte ThinQ sur le site développeur LG
  (Cloud Developer → Docs → ThinQ Connect). Le SDK demande aussi le **code pays** et un **`client_id`**
  (uuid4 généré une fois et conservé ; en créer trop peut faire bloquer les appels).
- SDK officiel Python asynchrone : `thinqconnect` (liste des appareils, états, événements).
- Temps réel : abonnement `POST /push/{device-id}` et `POST /event/{device-id}` ; le SDK reçoit les événements en MQTT (AWS IoT Core).
- Aucune limite de débit publiée trouvée. Les projets non officiels (rétro-ingénierie) peuvent casser sans préavis : ne pas s'en servir.

## 3. Ce qu'on peut remonter (d'après le README du SDK, à confirmer par la sonde)

Les pages de profils LG n'étaient pas joignables depuis le conteneur ; les profils varient légèrement selon le modèle.

**Machine à laver** : `run_state.current_state` ; `operation.washer_operation_mode` ; `remote_control_enable.remote_control_enabled`
(le pilotage à distance exige l'activation sur la machine) ; `timer` (remain/total/relative start/stop, en heures et minutes) ;
`detergent.detergent_setting` ; `cycle.cycle_count`.

**Frigo** : `temperature.target_temperature_c|f` + `temperature_unit` ; `door_status.door_state` ; `power_save`, `eco_friendly`,
`sabbath`, `refrigeration` (rapid_freeze, express_mode, express_fridge, fresh_air_filter + `remain_percent`) ;
`water_filter_info` (état, temps d'usage, % restant par filtre).

**Limites connues** : pas de mesure de consommation électrique vue dans ces profils ; le frigo expose la consigne, pas forcément la
température réelle ; lecture seule vs écriture non documentée dans le README.

## 4. Plan proposé

1. **Sonde** `backend/scripts/discover_thinq.py`, sur le modèle de `discover_magellan.py` :
   - identifiants lus dans `../.env` (`THINQ_PAT`, `THINQ_COUNTRY`, `THINQ_CLIENT_ID`), **jamais en ligne de commande** ;
   - dump brut des appareils et de leurs profils/états (hors git : `backend/discover_*output.json` est déjà ignoré) ;
   - option `--refixture` : fixture anonymisée sans appel réseau (pas de `deviceId`, alias, adresses).
2. **Revue des résultats** (⏸ montrer au propriétaire) : propriétés réellement exposées par les deux modèles, lecture/écriture, présence d'une énergie.
3. **Adaptateur** `backend/app/adapters/outbound/thinq/` (`client.py`, `mapping.py`, `gateway.py`, `semantics.yaml`), mêmes ports
   que Magellan (`EquipmentGateway`, `MetricCatalog`) ; tests de contrat sur la fixture anonymisée.
   Démarrer par du **polling** (comme Magellan) ; MQTT plus tard si utile.
4. **Domaine/API** : généraliser la notion d'équipement par fournisseur (le front ne voit jamais d'identifiant fournisseur).
5. **Front** : pages ou cartes pour le lave-linge (état du cycle, temps restant) et le frigo (porte ouverte, consigne, filtres),
   en respectant les règles dataviz du `CLAUDE.md`.
6. **Renommage** dans le code et la CI, après celui du dépôt.

## 5. Points ouverts

- Propriétés et unités réelles des deux modèles (la sonde tranchera).
- Conserver la consigne seule ou trouver une température mesurée du frigo.
- Fréquence de collecte et politique d'erreur (PAT révoqué = arrêt définitif, à l'image de `CredentialsRejected`).
- Commandes éventuelles : hors périmètre tant que la lecture n'est pas stabilisée.

## 6. Résultats de la sonde (étape 1 faite)

Sonde `backend/scripts/discover_thinq.py` exécutée avec le PAT ; fixture anonymisée `backend/tests/fixtures/thinq_anonymized.json`
(à relire, non commitée). Région `eic` (FR).

| Appareil | Modèle | Profil | État | Énergie |
|---|---|---|---|---|
| Lave-linge `DEVICE_WASHER` | `F_R7_D___W.A__QEUK` | ok | 1222 « Not connected device » | 1221 non supporté |
| Lave-vaisselle `DEVICE_DISH_WASHER` | `D0200` | ok | 1222 | 1221 |
| Frigo `DEVICE_REFRIGERATOR` | `1REB1GLPX1___` | ok | ok | 1221 |

- **Frigo** : `temperature` (FRIDGE 3 °C, plage 1 à 7 ; FREEZER −18 °C, plage −23 à −15, lecture/écriture), `temperatureInUnits`,
  `doorStatus.doorState` (OPEN/CLOSE), `refrigeration.expressMode`, `ecoFriendly.ecoFriendlyMode`. Pas de filtre à eau ni de sabbat.
  Consignes seulement, pas de température mesurée.
- **Lave-linge** (profil) : `runState.currentState`, `operation.washerOperationMode`, `detergent`, `remoteControlEnable`,
  `timer` (remain/total/relativeStop), `location`, `cycle.cycleCount`.
- **Lave-vaisselle** (profil, hors périmètre initial) : `runState`, `doorStatus`, `timer`, `dishWashingCourse`, `dishWashingStatus.rinseRefill`, `preference`.
- **Énergie** : aucun profil énergie (1221) sur les trois appareils : pas de consommation côté LG.
- Les états des deux lave-* sont en 1222 (appareil hors ligne côté LG lors de la sonde).

**À faire ensuite** (reporté par le propriétaire) : relancer la sonde avec lave-linge et lave-vaisselle allumés pour obtenir de vrais
états, relire la fixture, puis trancher : lave-vaisselle dans le périmètre ? historique des ouvertures de porte du frigo ?
Ensuite seulement : étapes 3 à 5 du §4.

## Sources

- https://thinq.developer.lge.com/en/cloud/docs/thinq-connect
- https://github.com/thinq-connect/pythinqconnect
- https://pypi.org/project/thinqconnect
- https://www.cnx-software.com/2024/12/18/lg-opens-the-thinq-api-for-smart-home-devices/
- https://www.lg.com/global/newsroom/news/home-appliance-solution/lg-opens-thinq-api-to-foster-smart-home-innovation/
