"""Plusieurs fournisseurs derrière le port ``EquipmentGateway``."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from app.application.ports import EquipmentGateway, MetricCatalog, MetricInfo
from app.domain.errors import ProviderError
from app.domain.model import Equipment
from app.domain.values import EquipmentId, Measurement

log = logging.getLogger(__name__)


class CompositeGateway:
    """Fournisseur principal + fournisseurs secondaires.

    Le principal décide de la santé de la collecte : son erreur remonte telle quelle (journal des cycles, trous,
    politique de retry du scheduler). Un secondaire en panne est journalisé puis ignoré pour le cycle : ses
    équipements gardent leurs dernières valeurs et ne bloquent pas la collecte du principal. Un secondaire en erreur
    à ``list_equipment`` (premier appel du cycle) n'est plus sollicité jusqu'au cycle suivant.
    """

    def __init__(
        self,
        primary: EquipmentGateway,
        secondaries: Sequence[EquipmentGateway] = (),
        catalogs: Sequence[MetricCatalog] = (),
    ) -> None:
        self._primary = primary
        self._secondaries = tuple(secondaries)
        self._catalogs = tuple(catalogs)
        self._failed: set[int] = set()

    async def list_equipment(self) -> list[Equipment]:
        self._failed.clear()
        out = await self._primary.list_equipment()
        for index, gw in enumerate(self._secondaries):
            try:
                out += await gw.list_equipment()
            except ProviderError as exc:
                self._failed.add(index)
                log.warning("Fournisseur secondaire ignoré pour ce cycle : %s: %s", type(exc).__name__, exc)
        return out

    async def read_measurements(self, equipment_ids: list[EquipmentId] | None = None) -> list[Measurement]:
        out = await self._primary.read_measurements(equipment_ids)
        for gw in self._healthy():
            try:
                out += await gw.read_measurements(equipment_ids)
            except ProviderError as exc:
                log.warning("Lecture secondaire ignorée : %s: %s", type(exc).__name__, exc)
        return out

    async def availability(self) -> dict[EquipmentId, bool]:
        out = await self._primary.availability()
        for gw in self._healthy():
            try:
                out |= await gw.availability()
            except ProviderError as exc:
                log.warning("Disponibilité secondaire ignorée : %s: %s", type(exc).__name__, exc)
        return out

    async def describe(self) -> list[MetricInfo]:
        return [info for catalog in self._catalogs for info in await catalog.describe()]

    def _healthy(self) -> list[EquipmentGateway]:
        return [gw for i, gw in enumerate(self._secondaries) if i not in self._failed]
