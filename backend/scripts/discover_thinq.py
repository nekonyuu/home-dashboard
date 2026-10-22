"""Découverte via l'API officielle LG ThinQ Connect (lecture seule).

Voir docs/thinq-discovery.md. Routes, en-têtes et clé d'API publique repris de la
documentation et du SDK officiel `thinqconnect` (lu, non installé : aiohttp suffit).

Usage (depuis backend/, identifiants dans ../.env, jamais en ligne de commande) :
    set -a && source ../.env && set +a && uv run python scripts/discover_thinq.py

Variables :
- THINQ_PAT        Personal Access Token (site développeur LG)
- THINQ_COUNTRY    code pays ISO, ex. FR
- THINQ_CLIENT_ID  uuid4 généré une fois et conservé (ne pas en créer à chaque essai)
- THINQ_REGION     optionnel : kic | aic | eic (défaut eic, Europe)

Appels (tous GET), espacés :
- GET /devices
- GET /devices/<id>/profile, /devices/<id>/state, /devices/energy/<id>/profile  (par appareil)
Aucune souscription push/événement, aucune commande. Un 429 ou une erreur d'authentification
arrête la sonde immédiatement, sans nouvelle tentative.

Sorties : discover_thinq_output.json (BRUT, hors git, 600) et
tests/fixtures/thinq_anonymized.json (à relire avant commit).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import aiohttp

# Clé d'API publique de la plateforme ThinQ Connect (identique pour tous, présente dans le SDK).
API_KEY = "v6GFvkweNo7DK7yD3ylIZ9w52aKBU0eJ7wLXkSR3"
REGIONS = {"kic", "aic", "eic"}
PAUSE = 2.0  # secondes entre deux appels

# Codes d'erreur ThinQ qui signifient « identifiants à revoir » : arrêt définitif.
_AUTH_ERRORS = {"1103", "1218", "1302", "1201", "1202", "1203", "1301"}
_QUOTA_ERRORS = {"1306"}

BACKEND_DIR = Path(__file__).resolve().parent.parent
RAW_OUTPUT = BACKEND_DIR / "discover_thinq_output.json"
FIXTURE_OUTPUT = BACKEND_DIR / "tests" / "fixtures" / "thinq_anonymized.json"

_SENSITIVE_KEYS = {
    "alias",
    "ip",
    "ipAddress",
    "mac",
    "macAddress",
    "ssid",
    "serialNumber",
    "email",
    "address",
    "latitude",
    "longitude",
    "city",
    "zipCode",
    "postalCode",
    "userNo",
    "userId",
}


class Stop(Exception):
    """Arrêt de la sonde (authentification refusée ou quota atteint)."""


def anonymize(node: Any, pseudo: dict[str, str] | None = None) -> Any:
    """Masque les champs identifiants et pseudonymise les `deviceId` (cohérence conservée)."""
    pseudo = {} if pseudo is None else pseudo
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "deviceId" and isinstance(v, str):
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


def pseudonymize_keys(out: dict[str, Any]) -> dict[str, Any]:
    """Les `deviceId` sont aussi des clés des dictionnaires par appareil : mêmes pseudonymes."""
    pseudo: dict[str, str] = {}
    devices = anonymize(out.get("devices"), pseudo)
    result = {k: v for k, v in out.items() if k != "per_device"}
    result["devices"] = devices
    result["per_device"] = {
        pseudo.get(did, "device-?"): anonymize(body, pseudo) for did, body in (out.get("per_device") or {}).items()
    }
    return result


def write_fixture(out: dict[str, Any]) -> None:
    FIXTURE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_OUTPUT.write_text(json.dumps(pseudonymize_keys(out), indent=2, ensure_ascii=False))


def _message_id() -> str:
    return base64.urlsafe_b64encode(uuid.uuid4().bytes)[:-2].decode()


def _headers(pat: str, country: str, client_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {pat}",
        "x-country": country,
        "x-message-id": _message_id(),
        "x-client-id": client_id,
        "x-api-key": API_KEY,
        "x-service-phase": "OP",
    }


async def _get(session: aiohttp.ClientSession, base: str, hdrs: dict[str, str], path: str) -> dict[str, Any]:
    """Renvoie {status, response} ou {status, error}. Lève Stop sur 429, quota ou jeton refusé."""
    await asyncio.sleep(PAUSE)
    async with session.get(f"{base}/{path}", headers=hdrs | {"x-message-id": _message_id()}) as r:
        try:
            payload = await r.json(content_type=None)
        except ValueError:
            payload = None
        if r.status == 429:
            raise Stop(f"429 sur {path}; Retry-After={r.headers.get('Retry-After')}")
        if r.ok:
            return {"status": r.status, "response": (payload or {}).get("response")}
        error = (payload or {}).get("error") or {}
        code = str(error.get("code", ""))
        if r.status in (401, 403) or code in _AUTH_ERRORS:
            raise Stop(f"authentification refusée (HTTP {r.status}, code {code or '?'}) sur {path}")
        if code in _QUOTA_ERRORS:
            raise Stop(f"quota d'appels atteint (code {code}) sur {path}")
        return {"status": r.status, "error": {"code": code, "message": error.get("message")}}


async def discover() -> int:
    pat = os.environ.get("THINQ_PAT")
    country = (os.environ.get("THINQ_COUNTRY") or "").upper()
    client_id = os.environ.get("THINQ_CLIENT_ID")
    region = (os.environ.get("THINQ_REGION") or "eic").lower()
    if not pat or not country or not client_id:
        print("THINQ_PAT / THINQ_COUNTRY / THINQ_CLIENT_ID requis", file=sys.stderr)
        return 2
    if region not in REGIONS:
        print(f"THINQ_REGION doit valoir {', '.join(sorted(REGIONS))}", file=sys.stderr)
        return 2
    try:
        uuid.UUID(client_id)
    except ValueError:
        print("THINQ_CLIENT_ID doit être un uuid (ex. python -c 'import uuid; print(uuid.uuid4())')", file=sys.stderr)
        return 2

    base = f"https://api-{region}.lgthinq.com"
    hdrs = _headers(pat, country, client_id)
    out: dict[str, Any] = {"generated_at": int(time.time()), "region": region}
    timeout = aiohttp.ClientTimeout(total=30)
    exit_code = 0
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            listing = await _get(session, base, hdrs, "devices")
            out["devices"] = listing
            devices = listing.get("response")
            if not isinstance(devices, list):
                detail = listing.get("error") or listing.get("status")
                print(f"Liste d'appareils inattendue : {detail}", file=sys.stderr)
                exit_code = 5
                devices = []
            print(f"{len(devices)} appareil(s).")
            out["per_device"] = {}
            for d in devices:
                did = d.get("deviceId")
                out["per_device"][did] = {
                    "profile": await _get(session, base, hdrs, f"devices/{did}/profile"),
                    "state": await _get(session, base, hdrs, f"devices/{did}/state"),
                    "energy_profile": await _get(session, base, hdrs, f"devices/energy/{did}/profile"),
                }
        except Stop as exc:
            out["stopped"] = str(exc)
            print(f"Arrêt, pas de nouvelle tentative : {exc}", file=sys.stderr)
            exit_code = 3

    RAW_OUTPUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    os.chmod(RAW_OUTPUT, 0o600)
    write_fixture(out)
    _print_summary(out)
    print(f"\nBrut : {RAW_OUTPUT} (hors git)\nFixture anonymisée : {FIXTURE_OUTPUT} (à relire avant commit)")
    return exit_code


def _outcome(result: dict[str, Any] | None) -> str:
    r = result or {}
    return "ok" if "response" in r else f"erreur {r.get('error', {}).get('code', r.get('status', '?'))}"


def _print_summary(out: dict[str, Any]) -> None:
    devices = (out.get("devices") or {}).get("response") or []
    print("\n=== Appareils ===")
    for i, d in enumerate(devices, 1):
        info = d.get("deviceInfo") or {}
        per = (out.get("per_device") or {}).get(d.get("deviceId"), {})

        props = sorted((per.get("state") or {}).get("response") or {})
        print(
            f"#{i} type={info.get('deviceType')} modèle={info.get('modelName')} "
            f"profil={_outcome(per.get('profile'))} état={_outcome(per.get('state'))} "
            f"énergie={_outcome(per.get('energy_profile'))}"
        )
        print(f"   propriétés d'état : {', '.join(props) or '-'}")


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
