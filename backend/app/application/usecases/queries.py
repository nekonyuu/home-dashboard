"""Cas d'usage en lecture seule (API HTTP)."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date

from app.application.ports import (
    Clock,
    EnergyRepository,
    EquipmentRepository,
    GapRepository,
    MeasurementRepository,
    MetricCatalog,
    MetricInfo,
    PollLogRepository,
    StorageStats,
)
from app.domain.model import Equipment, Gap, HeatingCycle, WeeklySchedule
from app.domain.services import (
    CycleDetector,
    GapDetector,
    ScheduleState,
    SeriesAggregator,
    parse_transitions,
    schedule_state,
)
from app.domain.values import (
    BucketSize,
    EnergyDay,
    EquipmentId,
    ErrorKind,
    Instant,
    Measurement,
    MetricKey,
    PollOutcome,
    Series,
)


@dataclass(frozen=True, slots=True)
class LatestValue:
    measurement: Measurement
    age_seconds: int


class GetMetrics:
    def __init__(self, catalog: MetricCatalog) -> None:
        self._catalog = catalog

    async def run(self) -> list[MetricInfo]:
        return sorted(await self._catalog.describe(), key=lambda i: (i.equipment_id, i.metric_key))


class GetEquipment:
    def __init__(self, equipment: EquipmentRepository) -> None:
        self._equipment = equipment

    async def run(self) -> list[Equipment]:
        return sorted(await self._equipment.all(), key=lambda e: e.id)


class GetLatest:
    def __init__(self, measurements: MeasurementRepository, clock: Clock) -> None:
        self._measurements = measurements
        self._clock = clock

    async def run(self, equipment_id: EquipmentId | None = None) -> list[LatestValue]:
        now = self._clock.now()
        rows = await self._measurements.latest(equipment_id)
        return [LatestValue(m, now - m.instant) for m in sorted(rows, key=lambda m: (m.equipment_id, m.metric_key))]


@dataclass(frozen=True, slots=True)
class SeriesResult:
    series: Series
    gaps: list[Gap]


class GetSeries:
    """Série agrégée + trous de la période (y compris un trou en cours)."""

    def __init__(
        self,
        *,
        measurements: MeasurementRepository,
        gaps: GapRepository,
        poll_log: PollLogRepository,
        clock: Clock,
        gap_detector: GapDetector,
        cumulative_metrics: Collection[MetricKey] = (),
        aggregator: SeriesAggregator | None = None,
    ) -> None:
        self._measurements = measurements
        self._gaps = gaps
        self._poll_log = poll_log
        self._clock = clock
        self._gap_detector = gap_detector
        self._cumulative = set(cumulative_metrics)
        self._aggregator = aggregator or SeriesAggregator()

    async def run(
        self, equipment_id: EquipmentId, metric_key: MetricKey, start: Instant, end: Instant, size: BucketSize
    ) -> SeriesResult:
        if end <= start:
            raise ValueError("période vide")
        now = self._clock.now()
        gaps = await self._gaps.list(start, end)
        ongoing = await _ongoing_gap(self._poll_log, self._gap_detector, now)
        if ongoing is not None and ongoing.overlaps(start, end):
            gaps = [*gaps, ongoing]
        points = await self._measurements.range(equipment_id, metric_key, start, end)
        prior = await self._measurements.last_recorded(equipment_id, metric_key, start)
        buckets = self._aggregator.aggregate(
            points,
            start,
            end,
            size,
            gaps=gaps,
            prior=prior,
            known_until=now,
            cumulative=metric_key in self._cumulative,
        )
        return SeriesResult(Series(equipment_id, metric_key, size, tuple(buckets)), gaps)


class GetGaps:
    def __init__(
        self, gaps: GapRepository, poll_log: PollLogRepository, clock: Clock, gap_detector: GapDetector
    ) -> None:
        self._gaps = gaps
        self._poll_log = poll_log
        self._clock = clock
        self._gap_detector = gap_detector

    async def run(self, start: Instant, end: Instant) -> list[Gap]:
        gaps = await self._gaps.list(start, end)
        ongoing = await _ongoing_gap(self._poll_log, self._gap_detector, self._clock.now())
        if ongoing is not None and ongoing.overlaps(start, end):
            gaps.append(ongoing)
        return sorted(gaps, key=lambda g: g.start)


@dataclass(frozen=True, slots=True)
class CycleSources:
    """Où lire la vanne 3 voies, la température du ballon et le compteur d'énergie ECS."""

    status: tuple[EquipmentId, MetricKey]
    temperature: tuple[EquipmentId, MetricKey]
    energy: tuple[EquipmentId, MetricKey]


class GetCycles:
    """Cycles de chauffe de l'eau chaude sur une période (dérivés, jamais stockés)."""

    def __init__(
        self,
        *,
        sources: CycleSources,
        measurements: MeasurementRepository,
        gaps: GapRepository,
        poll_log: PollLogRepository,
        clock: Clock,
        gap_detector: GapDetector,
        detector: CycleDetector | None = None,
    ) -> None:
        self._sources = sources
        self._measurements = measurements
        self._gaps = gaps
        self._poll_log = poll_log
        self._clock = clock
        self._gap_detector = gap_detector
        self._detector = detector or CycleDetector()

    async def run(self, start: Instant, end: Instant) -> list[HeatingCycle]:
        if end <= start:
            raise ValueError("période vide")
        # un cycle commencé avant la fenêtre est reconnu par la mesure précédente ; la fin et l'énergie d'un
        # cycle proche de la fin de fenêtre demandent de lire un peu au-delà
        read_end = end + 3600
        gaps = await self._gaps.list(start, read_end)
        ongoing = await _ongoing_gap(self._poll_log, self._gap_detector, self._clock.now())
        if ongoing is not None and ongoing.overlaps(start, read_end):
            gaps = [*gaps, ongoing]
        series = {}
        for name, (eq, key) in (
            ("status", self._sources.status),
            ("temperature", self._sources.temperature),
            ("energy", self._sources.energy),
        ):
            series[name] = (
                await self._measurements.range(eq, key, start, read_end),
                await self._measurements.last_recorded(eq, key, start),
            )
        cycles = self._detector.detect(
            series["status"][0],
            prior_status=series["status"][1],
            temperatures=series["temperature"][0],
            prior_temperature=series["temperature"][1],
            energy=series["energy"][0],
            prior_energy=series["energy"][1],
            gaps=gaps,
            window_start=start,
        )
        return [c for c in cycles if c.start < end]


class GetEnergy:
    def __init__(self, energy: EnergyRepository) -> None:
        self._energy = energy

    async def run(self, since: date, until: date) -> list[EnergyDay]:
        return sorted(await self._energy.range(since, until), key=lambda d: d.key)


@dataclass(frozen=True, slots=True)
class Health:
    poller_stale: bool
    last_success: Instant | None
    last_errors: dict[ErrorKind, PollOutcome]
    error_counts: dict[ErrorKind, int]
    availability: dict[EquipmentId, bool | None]
    db_size_bytes: int
    recent_gaps: list[Gap] = field(default_factory=list)


class GetHealth:
    """État du poller : ``poller_stale`` si aucun succès depuis 3 intervalles."""

    RECENT_GAPS_SECONDS = 7 * 86400

    def __init__(
        self,
        *,
        poll_log: PollLogRepository,
        gaps: GapRepository,
        equipment: EquipmentRepository,
        storage: StorageStats,
        clock: Clock,
        gap_detector: GapDetector,
        poll_interval: int,
    ) -> None:
        self._poll_log = poll_log
        self._gaps = gaps
        self._equipment = equipment
        self._storage = storage
        self._clock = clock
        self._gap_detector = gap_detector
        self._interval = poll_interval

    async def run(self) -> Health:
        now = self._clock.now()
        recent = await self._poll_log.recent()
        last = await self._poll_log.last_success()
        last_errors: dict[ErrorKind, PollOutcome] = {}
        for o in recent:  # du plus récent au plus ancien
            if o.error_kind is not None and o.error_kind not in last_errors:
                last_errors[o.error_kind] = o
        counts = Counter(o.error_kind for o in recent if o.error_kind is not None)
        gaps = await self._gaps.list(Instant(now.epoch - self.RECENT_GAPS_SECONDS), now)
        ongoing = await _ongoing_gap(self._poll_log, self._gap_detector, now)
        if ongoing is not None:
            gaps.append(ongoing)
        return Health(
            poller_stale=last is None or now - last.at > 3 * self._interval,
            last_success=last.at if last else None,
            last_errors=last_errors,
            error_counts=dict(counts),
            availability={e.id: e.available for e in await self._equipment.all()},
            db_size_bytes=await self._storage.size_bytes(),
            recent_gaps=sorted(gaps, key=lambda g: g.start),
        )


async def _ongoing_gap(poll_log: PollLogRepository, detector: GapDetector, now: Instant) -> Gap | None:
    last = await poll_log.last_success()
    if last is None:
        return None
    failures = [o for o in await poll_log.since(last.at) if not o.ok]
    return detector.ongoing(last.at, now, failures)


SCHEDULE_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass(frozen=True, slots=True)
class ScheduleView:
    equipment_id: EquipmentId
    schedule: WeeklySchedule
    state: ScheduleState
    updated_at: Instant
    # dernières mesures utiles à l'affichage (mode de consigne, dérogation), absentes si jamais reçues
    context: dict[str, Measurement] = field(default_factory=dict)


class GetSchedule:
    """Programme de chauffage en place (dernière version reçue), consigne programmée et prochain changement."""

    PREFIX = "heat_schedule_"
    CONTEXT = ("setpoint_mode", "override_active", "override_remaining", "room_setpoint")

    def __init__(self, measurements: MeasurementRepository, clock: Clock, equipment_id: EquipmentId) -> None:
        self._measurements = measurements
        self._clock = clock
        self._equipment_id = equipment_id

    async def run(self) -> ScheduleView | None:
        rows = {m.metric_key.value: m for m in await self._measurements.latest(self._equipment_id)}
        days = []
        for name in SCHEDULE_DAYS:
            m = rows.get(self.PREFIX + name)
            parsed = parse_transitions(json.loads(m.value.text or "null")) if m is not None else None
            if parsed is None:
                return None  # programme incomplet : rien plutôt qu'un programme inventé
            days.append(parsed)
        schedule = WeeklySchedule(tuple(days))
        updated = max(rows[self.PREFIX + n].instant for n in SCHEDULE_DAYS)
        return ScheduleView(
            equipment_id=self._equipment_id,
            schedule=schedule,
            state=schedule_state(schedule, self._clock.now()),
            updated_at=updated,
            context={k: rows[k] for k in self.CONTEXT if k in rows},
        )
