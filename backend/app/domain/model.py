"""Entités et agrégat racine."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.values import EquipmentId, Instant


@dataclass(slots=True)
class Equipment:
    """Un appareil de l'installation ; porte sa dernière disponibilité connue.

    ``provider_ref`` : identifiants fournisseur opaques (stockés, jamais loggés
    ni exposés par l'API) ; le domaine ne les interprète pas.
    """

    id: EquipmentId
    label: str
    kind: str
    available: bool | None = None
    first_seen: Instant | None = None
    last_seen: Instant | None = None
    provider_ref: Mapping[str, int | str | None] = field(default_factory=dict, repr=False)

    def seen(self, at: Instant, available: bool | None) -> None:
        if self.first_seen is None:
            self.first_seen = at
        self.last_seen = at
        self.available = available


@dataclass(slots=True)
class Installation:
    """Agrégat racine : l'ensemble PAC + ballon et ses équipements."""

    equipment: dict[EquipmentId, Equipment] = field(default_factory=dict)

    def observe(self, observed: Equipment, at: Instant) -> Equipment:
        """Intègre un équipement lu chez le fournisseur et renvoie l'entité à jour."""
        current = self.equipment.get(observed.id)
        if current is None:
            current = Equipment(id=observed.id, label=observed.label, kind=observed.kind)
            self.equipment[observed.id] = current
        current.label = observed.label
        current.kind = observed.kind
        current.provider_ref = dict(observed.provider_ref)
        current.seen(at, observed.available)
        return current

    def unavailable(self) -> list[EquipmentId]:
        return sorted(e.id for e in self.equipment.values() if e.available is False)


class GapCause(StrEnum):
    DOWNTIME = "downtime"
    PROVIDER_ERROR = "provider_error"
    CREDENTIALS = "credentials"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class Gap:
    """Intervalle ``[start, end)`` sans collecte réussie.

    ``recovered`` : l'énergie de la période a été rattrapée depuis l'historique
    fournisseur (les autres mesures ne le sont jamais).
    """

    start: Instant
    end: Instant
    cause: GapCause
    recovered: bool = False
    id: int | None = None

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("un trou doit avoir une durée positive")

    @property
    def duration(self) -> int:
        return self.end - self.start

    def overlaps(self, start: Instant, end: Instant) -> bool:
        return self.start < end and start < self.end


@dataclass(frozen=True, slots=True)
class HeatingCycle:
    """Une chauffe de l'eau chaude : la vanne 3 voies est restée sur « ECS » de ``start`` à ``end``.

    ``end`` vaut ``None`` tant que le cycle est en cours. Les bornes sont les dates de changement données par le
    fournisseur, donc exactes même si la bascule a eu lieu pendant un trou de collecte. ``energy_wh`` n'est
    renseignée que si aucun trou ne recouvre le cycle (le compteur n'y est pas connu).
    """

    start: Instant
    end: Instant | None
    start_temperature: float | None = None
    end_temperature: float | None = None
    energy_wh: float | None = None

    @property
    def ongoing(self) -> bool:
        return self.end is None

    @property
    def duration(self) -> int | None:
        return None if self.end is None else self.end - self.start


@dataclass(frozen=True, slots=True)
class ScheduleTransition:
    """À ``minute`` (depuis minuit, heure locale), la consigne passe à ``setpoint``."""

    minute: int
    setpoint: float

    def __post_init__(self) -> None:
        if not 0 <= self.minute < 1440:
            raise ValueError(f"minute hors de la journée : {self.minute}")


@dataclass(frozen=True, slots=True)
class WeeklySchedule:
    """Programme hebdomadaire : ``days[0]`` = lundi ... ``days[6]`` = dimanche, transitions triées.

    Avant la première transition d'un jour, la consigne est la dernière posée un jour précédent.
    """

    days: tuple[tuple[ScheduleTransition, ...], ...]

    def __post_init__(self) -> None:
        if len(self.days) != 7:
            raise ValueError("un programme hebdomadaire compte 7 jours")

    @property
    def empty(self) -> bool:
        return not any(self.days)

    def setpoint_at(self, weekday: int, minute: int) -> float | None:
        for back in range(8):
            day = self.days[(weekday - back) % 7]
            candidates = [t for t in day if back > 0 or t.minute <= minute]
            if candidates:
                return candidates[-1].setpoint
        return None

    def next_transition(self, weekday: int, minute: int) -> tuple[int, ScheduleTransition] | None:
        """Prochaine transition strictement après ``minute`` : (jours d'écart, transition)."""
        for ahead in range(8):
            for t in self.days[(weekday + ahead) % 7]:
                if ahead > 0 or t.minute > minute:
                    return ahead, t
        return None
