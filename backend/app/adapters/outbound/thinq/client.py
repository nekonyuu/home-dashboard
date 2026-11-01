"""Client HTTP LG ThinQ Connect (API officielle, lecture seule).

Auth par Personal Access Token ; routes, en-têtes et clé d'API publique reprises de la documentation et du SDK
officiel (voir ``docs/thinq-discovery.md``). Aucun secret (PAT, ``client_id``, ``deviceId``) dans les messages d'erreur.
"""

from __future__ import annotations

import base64
import logging
import uuid
from typing import Any

import aiohttp

from app.domain.errors import CredentialsRejected, ProviderThrottled, ProviderUnavailable

log = logging.getLogger(__name__)

# Clé d'API publique de la plateforme (identique pour tous les clients, présente dans le SDK officiel).
API_KEY = "v6GFvkweNo7DK7yD3ylIZ9w52aKBU0eJ7wLXkSR3"
REGIONS = frozenset({"kic", "aic", "eic"})
TIMEOUT = aiohttp.ClientTimeout(total=30)
DEFAULT_THROTTLE = 300

# Codes d'erreur ThinQ qui signifient « PAT / client à revoir » : arrêt définitif des tentatives.
AUTH_ERRORS = frozenset({"1103", "1201", "1202", "1203", "1218", "1301", "1302"})
QUOTA_ERRORS = frozenset({"1306"})
NOT_CONNECTED = "1222"


class DeviceOffline(Exception):
    """L'appareil est hors ligne côté LG (code 1222) : pas une panne du fournisseur."""


class ThinQClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        pat: str,
        country: str,
        client_id: str,
        *,
        region: str = "eic",
        base_url: str | None = None,
    ) -> None:
        if region not in REGIONS:
            raise ValueError(f"région ThinQ inconnue : {region!r}")
        self._session = session
        self._pat = pat
        self._country = country
        self._client_id = client_id
        self._base = (base_url or f"https://api-{region}.lgthinq.com").rstrip("/")

    async def devices(self) -> list[dict[str, Any]]:
        body = await self._get("devices")
        if not isinstance(body, list):
            raise ProviderUnavailable("devices : réponse inattendue")
        return [d for d in body if isinstance(d, dict)]

    async def state(self, device_id: str) -> dict[str, Any] | list[Any]:
        """État courant ; lève ``DeviceOffline`` si l'appareil est hors ligne."""
        body = await self._get(f"devices/{device_id}/state")
        if not isinstance(body, dict | list):
            raise ProviderUnavailable("state : réponse inattendue")
        return body

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._pat}",
            "x-country": self._country,
            "x-message-id": base64.urlsafe_b64encode(uuid.uuid4().bytes)[:-2].decode(),
            "x-client-id": self._client_id,
            "x-api-key": API_KEY,
            "x-service-phase": "OP",
        }

    async def _get(self, path: str) -> Any:
        route = "devices/…/state" if path.endswith("/state") else path
        try:
            async with self._session.get(f"{self._base}/{path}", headers=self._headers(), timeout=TIMEOUT) as r:
                try:
                    payload = await r.json(content_type=None)
                except ValueError:
                    payload = None
                if r.ok:
                    return (payload or {}).get("response") if isinstance(payload, dict) else None
                error = payload.get("error") if isinstance(payload, dict) else None
                code = str((error or {}).get("code", ""))
                if r.status == 429 or code in QUOTA_ERRORS:
                    header = r.headers.get("Retry-After", "")
                    raise ProviderThrottled(
                        f"{route} : limite d'appels", retry_after=int(header) if header.isdigit() else DEFAULT_THROTTLE
                    )
                if r.status in (401, 403) or code in AUTH_ERRORS:
                    raise CredentialsRejected(f"{route} : PAT refusé (HTTP {r.status}, code {code or '?'})")
                if code == NOT_CONNECTED:
                    raise DeviceOffline(route)
                raise ProviderUnavailable(f"{route} : HTTP {r.status}, code {code or '?'}")
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise ProviderUnavailable(f"{route} : {type(exc).__name__}") from None
