"""Découverte de la station météo Netatmo via Netatmo Connect (lecture seule).

Voir docs/netatmo-discovery.md. Routes et paramètres tirés de la documentation publique
(dev.netatmo.com) : à confirmer par cette sonde, rien n'est supposé.

Usage (depuis backend/, identifiants dans ../.env, jamais en ligne de commande) :
    set -a && source ../.env && set +a && uv run python scripts/discover_netatmo.py

Variables :
- NETATMO_CLIENT_ID      identifiant de l'application créée sur dev.netatmo.com
- NETATMO_CLIENT_SECRET  secret de l'application
- NETATMO_REFRESH_TOKEN  jeton de renouvellement (scope read_station), généré par le « token generator »

ATTENTION : Netatmo émet un NOUVEAU refresh token à chaque renouvellement et invalide l'ancien.
La sonde enregistre donc le nouveau dans backend/.netatmo_refresh_token (600, hors git) et
l'utilise en priorité sur NETATMO_REFRESH_TOKEN aux essais suivants. Ne pas relancer en boucle.

Appels, espacés :
- POST /oauth2/token (renouvellement)
- GET /api/getstationsdata
- GET /api/getmeasure (un par module, dernières 24 h, pas de 30 min) : vérifie l'historique
Un 429 ou un jeton refusé (invalid_grant) arrête la sonde immédiatement, sans nouvelle tentative.

Sorties : discover_netatmo_output.json (BRUT, hors git, 600) et
tests/fixtures/netatmo_anonymized.json (à relire avant commit).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import aiohttp

BASE = "https://api.netatmo.com"
PAUSE = 2.0  # secondes entre deux appels
MEASURE_WINDOW = 24 * 3600
MEASURE_SCALE = "30min"

BACKEND_DIR = Path(__file__).resolve().parent.parent
RAW_OUTPUT = BACKEND_DIR / "discover_netatmo_output.json"
FIXTURE_OUTPUT = BACKEND_DIR / "tests" / "fixtures" / "netatmo_anonymized.json"
TOKEN_FILE = BACKEND_DIR / ".netatmo_refresh_token"

_SENSITIVE_KEYS = {
    "station_name",
    "home_name",
    "module_name",
    "name",
    "place",
    "city",
    "country",
    "timezone",
    "altitude",
    "location",
    "email",
    "user",
    "administrative",
}


class Stop(Exception):
    """Arrêt de la sonde (jeton refusé ou limitation)."""


def anonymize(node: Any, pseudo: dict[str, str] | None = None) -> Any:
    """Masque les champs identifiants ; `_id` (adresses MAC) et `main_device` sont pseudonymisés."""
    pseudo = {} if pseudo is None else pseudo
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k in ("_id", "main_device", "device_id", "module_id") and isinstance(v, str):
                out[k] = pseudo.setdefault(v, f"device-{len(pseudo) + 1}")
            elif k in _SENSITIVE_KEYS and v not in (None, ""):
                out[k] = "MASKED"
            else:
                out[k] = anonymize(v, pseudo)
        return out
    if isinstance(node, list):
        return [anonymize(i, pseudo) for i in node]
    if isinstance(node, str):
        return re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "user@example.invalid", node)
    return node


def anonymized(out: dict[str, Any]) -> dict[str, Any]:
    """Même pseudonyme partout, y compris dans les clés du dictionnaire des mesures."""
    pseudo: dict[str, str] = {}
    result = {k: v for k, v in out.items() if k != "measures"}
    result["stations"] = anonymize(out.get("stations"), pseudo)
    result["measures"] = {
        pseudo.setdefault(mid, f"device-{len(pseudo) + 1}"): anonymize(body, pseudo)
        for mid, body in (out.get("measures") or {}).items()
    }
    return result


def write_fixture(out: dict[str, Any]) -> None:
    FIXTURE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_OUTPUT.write_text(json.dumps(anonymized(out), indent=2, ensure_ascii=False))


async def _json(r: aiohttp.ClientResponse) -> Any:
    try:
        return await r.json(content_type=None)
    except ValueError:
        return None


async def refresh(session: aiohttp.ClientSession, client_id: str, secret: str, token: str) -> dict[str, Any]:
    await asyncio.sleep(PAUSE)
    data = {"grant_type": "refresh_token", "refresh_token": token, "client_id": client_id, "client_secret": secret}
    async with session.post(f"{BASE}/oauth2/token", data=data) as r:
        payload = await _json(r) or {}
        if r.status == 429:
            raise Stop(f"429 sur /oauth2/token; Retry-After={r.headers.get('Retry-After')}")
        if not r.ok or "access_token" not in payload:
            raise Stop(f"jeton refusé (HTTP {r.status}, {payload.get('error', '?')})")
        return payload


async def _get(session: aiohttp.ClientSession, access: str, path: str, params: dict[str, Any] | None = None) -> Any:
    await asyncio.sleep(PAUSE)
    async with session.get(f"{BASE}{path}", params=params, headers={"Authorization": f"Bearer {access}"}) as r:
        payload = await _json(r)
        if r.status == 429:
            raise Stop(f"429 sur {path}; Retry-After={r.headers.get('Retry-After')}")
        if r.status in (401, 403):
            raise Stop(f"accès refusé (HTTP {r.status}) sur {path}")
        if r.ok:
            return {"status": r.status, "body": (payload or {}).get("body")}
        return {"status": r.status, "error": (payload or {}).get("error")}


def _modules(stations: list[dict[str, Any]]):
    """Itère (device_id, module_id|None, data_type) : la base, puis ses modules rattachés."""
    for st in stations:
        yield st["_id"], None, st.get("data_type") or []
        for m in st.get("modules") or []:
            yield st["_id"], m.get("_id"), m.get("data_type") or []


async def discover() -> int:
    client_id = os.environ.get("NETATMO_CLIENT_ID")
    secret = os.environ.get("NETATMO_CLIENT_SECRET")
    token = (TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else None) or os.environ.get("NETATMO_REFRESH_TOKEN")
    if not client_id or not secret or not token:
        print("NETATMO_CLIENT_ID / NETATMO_CLIENT_SECRET / NETATMO_REFRESH_TOKEN requis", file=sys.stderr)
        return 2

    out: dict[str, Any] = {"generated_at": int(time.time())}
    exit_code = 0
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        try:
            tok = await refresh(session, client_id, secret, token)
            # Ancien jeton désormais invalide : on conserve le nouveau avant tout autre appel.
            TOKEN_FILE.write_text(tok["refresh_token"])
            os.chmod(TOKEN_FILE, 0o600)
            out["token"] = {"expires_in": tok.get("expires_in"), "scope": tok.get("scope")}

            listing = await _get(session, tok["access_token"], "/api/getstationsdata", {"get_favorites": "false"})
            out["stations_raw"] = listing
            body = listing.get("body")
            stations = (body or {}).get("devices") if isinstance(body, dict) else None
            if not isinstance(stations, list):
                print(f"Réponse inattendue : {listing.get('error') or listing.get('status')}", file=sys.stderr)
                exit_code = 5
                stations = []
            out["stations"] = stations
            print(f"{len(stations)} station(s).")

            out["measures"] = {}
            now = int(time.time())
            for device_id, module_id, types in _modules(stations):
                if not types:
                    continue
                params = {
                    "device_id": device_id,
                    "scale": MEASURE_SCALE,
                    "type": ",".join(types),
                    "date_begin": now - MEASURE_WINDOW,
                    "date_end": now,
                    "real_time": "true",
                }
                if module_id:
                    params["module_id"] = module_id
                out["measures"][module_id or device_id] = await _get(
                    session, tok["access_token"], "/api/getmeasure", params
                )
        except Stop as exc:
            out["stopped"] = str(exc)
            print(f"Arrêt, pas de nouvelle tentative : {exc}", file=sys.stderr)
            exit_code = 3

    out.pop("stations_raw", None)
    RAW_OUTPUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    os.chmod(RAW_OUTPUT, 0o600)
    write_fixture(out)
    _print_summary(out)
    print(f"\nBrut : {RAW_OUTPUT} (hors git)\nFixture anonymisée : {FIXTURE_OUTPUT} (à relire avant commit)")
    return exit_code


def _print_summary(out: dict[str, Any]) -> None:
    print("\n=== Modules ===")
    for st in out.get("stations") or []:
        print(
            f"base type={st.get('type')} données={','.join(st.get('data_type') or [])} joignable={st.get('reachable')}"
        )
        for m in st.get("modules") or []:
            print(
                f"  module type={m.get('type')} données={','.join(m.get('data_type') or [])} "
                f"joignable={m.get('reachable')} batterie%={m.get('battery_percent')}"
            )
        print(f"  dashboard_data : {', '.join(sorted(st.get('dashboard_data') or {}))}")
    print("\n=== Historique (getmeasure, 24 h) ===")
    for mid, res in (out.get("measures") or {}).items():
        body = res.get("body")
        print(
            f"{mid[:8]}… : {len(body) if isinstance(body, list) else 0} points"
            if "body" in res
            else f"{mid[:8]}… : erreur {res.get('error') or res.get('status')}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refixture", action="store_true", help="régénère la fixture depuis le dump, sans réseau")
    args = parser.parse_args()
    if args.refixture:
        write_fixture(json.loads(RAW_OUTPUT.read_text()))
        return 0
    return asyncio.run(discover())


if __name__ == "__main__":
    sys.exit(main())
