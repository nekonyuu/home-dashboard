"""Implémentation ThinQ des ports ``EquipmentGateway`` et ``MetricCatalog``."""

from __future__ import annotations

import logging
import time
from typing import Protocol

from app.adapters.outbound.thinq.client import DeviceOffline
from app.adapters.outbound.thinq.mapping import (
    ResolvedEquipment,
    Semantics,
    measurements_of,
    normalize_state,
    resolve_equipment,
)
from app.application.ports import Clock, MetricInfo
from app.domain.errors import CredentialsRejected, ProviderError, ProviderThrottled
from app.domain.model import Equipment
from app.domain.values import EquipmentId, Instant, Measurement

log = logging.getLogger(__name__)

DEVICES_MAX_AGE = 3600
SNAPSHOT_REUSE_SECONDS = 30


class ThinQApi(Protocol):
    async def devices(self) -> list[dict]: ...

    async def state(self, device_id: str) -> dict | list: ...


class ThinQGateway:
    """Une lecture d'état par appareil et par cycle ; la liste des appareils est gardée une heure.

    ``list_equipment``, ``read_measurements`` et ``availability`` réutilisent la même lecture tant qu'elle a moins de
    ``SNAPSHOT_REUSE_SECONDS``. Un PAT refusé arrête définitivement les appels (comme ``CredentialsRejected`` côté
    Magellan) ; une limite d'appels suspend les lectures pour la durée demandée.
    """

    def __init__(self, client: ThinQApi, semantics: Semantics, clock: Clock, *, monotonic=time.monotonic) -> None:
        self._client = client
        self._semantics = semantics
        self._clock = clock
        self._monotonic = monotonic
        self._devices: tuple[float, list[dict]] | None = None
        self._snapshot: tuple[float, Instant, list[ResolvedEquipment]] | None = None
        self._rejected = False
        self._blocked_until = 0.0

    async def list_equipment(self) -> list[Equipment]:
        _, _, resolved = await self._read()
        return [r.equipment for r in resolved]

    async def read_measurements(self, equipment_ids: list[EquipmentId] | None = None) -> list[Measurement]:
        _, polled_at, resolved = await self._read()
        wanted = set(equipment_ids) if equipment_ids is not None else None
        return [
            m for r in resolved if wanted is None or r.equipment.id in wanted for m in measurements_of(r, polled_at)
        ]

    async def availability(self) -> dict[EquipmentId, bool]:
        _, _, resolved = await self._read()
        return {r.equipment.id: bool(r.equipment.available) for r in resolved}

    async def describe(self) -> list[MetricInfo]:
        """Port ``MetricCatalog`` : depuis la dernière lecture, sans appel réseau."""
        if self._snapshot is None:
            return []
        return [
            MetricInfo(
                equipment_id=r.equipment.id,
                metric_key=m.key,
                label=m.label,
                unit=m.unit,
                enum=m.enum_labels,
            )
            for r in self._snapshot[2]
            for m in r.spec.metrics
        ]

    async def _read(self) -> tuple[float, Instant, list[ResolvedEquipment]]:
        now = self._monotonic()
        if self._snapshot is not None and now - self._snapshot[0] < SNAPSHOT_REUSE_SECONDS:
            return self._snapshot
        if self._rejected:
            raise CredentialsRejected("PAT ThinQ refusé : appels arrêtés jusqu'au redémarrage")
        if now < self._blocked_until:
            raise ProviderThrottled("ThinQ : limite d'appels", retry_after=int(self._blocked_until - now) + 1)
        try:
            devices = await self._device_list(now)
            resolved = []
            for r in resolve_equipment(devices, self._semantics):
                try:
                    state = normalize_state(await self._client.state(r.device_id))
                except DeviceOffline:
                    state = None
                r.equipment.available = state is not None
                resolved.append(ResolvedEquipment(r.equipment, r.spec, r.device_id, state))
        except CredentialsRejected:
            self._rejected = True
            raise
        except ProviderThrottled as exc:
            self._blocked_until = now + (exc.retry_after or 0)
            raise
        except ProviderError:
            self._devices = None
            raise
        self._snapshot = (now, self._clock.now(), resolved)
        return self._snapshot

    async def _device_list(self, now: float) -> list[dict]:
        if self._devices is None or now - self._devices[0] >= DEVICES_MAX_AGE:
            self._devices = (now, await self._client.devices())
        return self._devices[1]
