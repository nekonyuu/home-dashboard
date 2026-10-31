"""Services de domaine : purs, déterministes, sans I/O ni horloge système."""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.model import Gap, GapCause, HeatingCycle, ScheduleTransition, WeeklySchedule
from app.domain.values import (
    Bucket,
    BucketSize,
    EquipmentId,
    ErrorKind,
    Instant,
    Measurement,
    MetricKey,
    PollOutcome,
)

PARIS = ZoneInfo("Europe/Paris")

_FIXED_WIDTH = {BucketSize.FIVE_MINUTES: 300, BucketSize.HOUR: 3600}


class ChangeDetector:
    """Décide si une mesure lue doit être enregistrée.

    Règle : on enregistre la première mesure d'une série, puis toute mesure dont
    l'instant fournisseur est plus récent. Si le fournisseur ne date pas la
    valeur (``provider_timestamped=False``), l'instant est celui du poll : on
    n'enregistre alors que si la valeur a changé. Une mesure plus ancienne ou de
    même instant n'est jamais réenregistrée (l'unicité ``(équipement, métrique,
    instant)`` est garantie en amont du stockage).
    """

    def __init__(self) -> None:
        self._last: dict[tuple[EquipmentId, MetricKey], Measurement] = {}

    def load(self, measurements: Iterable[Measurement]) -> None:
        """Recharge le cache depuis la base (sinon chaque redémarrage double les points)."""
        for m in measurements:
            prev = self._last.get(m.series_key)
            if prev is None or m.instant > prev.instant:
                self._last[m.series_key] = m

    def should_record(self, m: Measurement) -> bool:
        prev = self._last.get(m.series_key)
        if prev is None:
            return True
        if m.instant <= prev.instant:
            return False
        return m.provider_timestamped or not m.value.same_reading(prev.value)

    def accept(self, m: Measurement) -> None:
        self._last[m.series_key] = m

    def filter(self, batch: Iterable[Measurement]) -> list[Measurement]:
        """Renvoie les mesures à enregistrer et met le cache à jour."""
        kept: list[Measurement] = []
        for m in batch:
            if self.should_record(m):
                self.accept(m)
                kept.append(m)
        return kept


def bucket_bounds(
    start: Instant, end: Instant, size: BucketSize, tz: ZoneInfo = PARIS
) -> list[tuple[Instant, Instant]]:
    """Découpe ``[start, end)`` en buckets alignés.

    5 min et 1 h sont alignés sur l'epoch UTC (les décalages de Paris sont des
    heures entières). 1 j suit les minuits locaux : journées de 23 h ou 25 h aux
    changements d'heure. Le premier et le dernier bucket sont entiers, pas tronqués.
    """
    if end <= start:
        return []
    if size in _FIXED_WIDTH:
        width = _FIXED_WIDTH[size]
        t = start.epoch - start.epoch % width
        out = []
        while t < end.epoch:
            out.append((Instant(t), Instant(t + width)))
            t += width
        return out
    day = datetime.fromtimestamp(start.epoch, tz).date()
    out = []
    while True:
        lo = int(datetime(day.year, day.month, day.day, tzinfo=tz).timestamp())
        nxt = day + timedelta(days=1)
        hi = int(datetime(nxt.year, nxt.month, nxt.day, tzinfo=tz).timestamp())
        if lo >= end.epoch:
            break
        out.append((Instant(lo), Instant(hi)))
        day = nxt
    return out


@dataclass(frozen=True, slots=True)
class _Segment:
    start: int
    end: int
    value: float


def _subtract(seg: _Segment, gaps: Sequence[Gap]) -> list[_Segment]:
    pieces = [seg]
    for g in gaps:
        nxt = []
        for p in pieces:
            if g.end.epoch <= p.start or g.start.epoch >= p.end:
                nxt.append(p)
                continue
            if g.start.epoch > p.start:
                nxt.append(_Segment(p.start, g.start.epoch, p.value))
            if g.end.epoch < p.end:
                nxt.append(_Segment(g.end.epoch, p.end, p.value))
        pieces = nxt
    return pieces


class SeriesAggregator:
    """Agrège une série numérique en buckets.

    - Moyenne **pondérée par la durée** : chaque valeur vaut jusqu'à la suivante
      (LOCF), interrompue par les trous et par ``known_until`` (dernier poll réussi).
    - ``prior`` : dernière mesure avant ``start``, pour reporter sa valeur au début.
    - Compteurs cumulés : ``delta`` = somme des incréments entre mesures
      successives, attribuée au bucket de la mesure la plus récente ; une remise à
      zéro (valeur qui baisse) compte la nouvelle valeur comme incrément. Un
      incrément qui enjambe un trou est conservé en entier (niveau B) et signalé.
    """

    def __init__(self, tz: ZoneInfo = PARIS) -> None:
        self._tz = tz

    def aggregate(
        self,
        points: Sequence[Measurement],
        start: Instant,
        end: Instant,
        size: BucketSize,
        *,
        gaps: Sequence[Gap] = (),
        prior: Measurement | None = None,
        known_until: Instant | None = None,
        cumulative: bool = False,
    ) -> list[Bucket]:
        series = sorted(
            (m for m in points if m.value.is_numeric and start <= m.instant < end),
            key=lambda m: m.instant,
        )
        if prior is not None and prior.value.is_numeric and prior.instant < start:
            series = [prior, *series]
        horizon = min(end, known_until) if known_until is not None else end

        segments: list[_Segment] = []
        for i, m in enumerate(series):
            seg_end = series[i + 1].instant.epoch if i + 1 < len(series) else horizon.epoch
            lo, hi = max(m.instant.epoch, start.epoch), min(seg_end, horizon.epoch)
            if hi > lo:
                segments.extend(_subtract(_Segment(lo, hi, m.value.number), gaps))

        increments: list[tuple[int, float, bool]] = []
        if cumulative:
            for prev, cur in itertools.pairwise(series):
                diff = cur.value.number - prev.value.number
                inc = diff if diff >= 0 else cur.value.number
                spans = any(g.overlaps(prev.instant, cur.instant) for g in gaps)
                increments.append((cur.instant.epoch, inc, spans))

        buckets = []
        for lo, hi in bucket_bounds(start, end, size, self._tz):
            weighted = covered = 0.0
            values: list[float] = []
            last: float | None = None
            for s in segments:
                a, b = max(s.start, lo.epoch), min(s.end, hi.epoch)
                if b > a:
                    weighted += s.value * (b - a)
                    covered += b - a
                    values.append(s.value)
                    last = s.value
            samples = sum(1 for m in series if lo <= m.instant < hi)
            delta: float | None = None
            spans_gap = False
            if cumulative:
                inside = [(inc, sp) for t, inc, sp in increments if lo.epoch <= t < hi.epoch]
                if inside:
                    delta = round(sum(inc for inc, _ in inside), 9)
                    spans_gap = any(sp for _, sp in inside)
            buckets.append(
                Bucket(
                    start=lo,
                    end=hi,
                    avg=weighted / covered if covered else None,
                    min=min(values) if values else None,
                    max=max(values) if values else None,
                    last=last,
                    samples=samples,
                    covered_seconds=int(covered),
                    delta=delta,
                    delta_spans_gap=spans_gap,
                )
            )
        return buckets


class GapDetector:
    """Produit des ``Gap`` à partir de l'historique des ``PollOutcome``.

    Il y a trou quand deux polls réussis consécutifs sont espacés de plus de
    ``tolerance * interval``. Le trou commence au poll attendu après le dernier
    succès et finit au succès suivant. Sa cause dépend des échecs intermédiaires :
    identifiants > erreur fournisseur > arrêt (aucun poll, ex. conteneur arrêté).
    """

    def __init__(self, interval: int, tolerance: float = 2.0) -> None:
        if interval <= 0:
            raise ValueError("intervalle de poll invalide")
        self._interval = interval
        self._threshold = interval * tolerance

    def between(self, last_ok: Instant, next_ok: Instant, failures: Sequence[PollOutcome] = ()) -> Gap | None:
        """Trou éventuel entre deux succès (ou entre le dernier succès et maintenant)."""
        if next_ok - last_ok <= self._threshold:
            return None
        start = last_ok + self._interval
        if start >= next_ok:
            return None
        return Gap(start=start, end=next_ok, cause=self._cause(failures))

    def detect(self, outcomes: Sequence[PollOutcome]) -> list[Gap]:
        gaps: list[Gap] = []
        last_ok: Instant | None = None
        failures: list[PollOutcome] = []
        for o in sorted(outcomes, key=lambda o: o.at):
            if not o.ok:
                failures.append(o)
                continue
            if last_ok is not None:
                gap = self.between(last_ok, o.at, failures)
                if gap is not None:
                    gaps.append(gap)
            last_ok, failures = o.at, []
        return gaps

    def ongoing(self, last_ok: Instant | None, now: Instant, failures: Sequence[PollOutcome] = ()) -> Gap | None:
        """Trou en cours (non persisté) : affiché tant qu'aucun poll ne réussit."""
        if last_ok is None:
            return None
        return self.between(last_ok, now, failures)

    @staticmethod
    def _cause(failures: Sequence[PollOutcome]) -> GapCause:
        kinds = {f.error_kind for f in failures}
        if ErrorKind.CREDENTIALS in kinds:
            return GapCause.CREDENTIALS
        if kinds & {ErrorKind.THROTTLED, ErrorKind.UNAVAILABLE}:
            return GapCause.PROVIDER_ERROR
        if kinds:
            return GapCause.UNKNOWN
        return GapCause.DOWNTIME


class CycleDetector:
    """Détecte les cycles de chauffe de l'eau chaude à partir de la vanne 3 voies.

    La vanne vaut ``ecs_value`` pendant une chauffe de l'eau chaude ; la mesure n'est enregistrée qu'à ses
    changements, donc une paire (passage à ``ecs_value``, retour à une autre valeur) borne un cycle.
    Les instants sont ceux du fournisseur (date du changement) : un trou de collecte ne les fausse pas, mais un
    cycle entièrement contenu dans un trou n'est pas vu, et l'énergie d'un cycle touché par un trou n'est pas
    calculée. Les températures et l'énergie sont lues avec une tolérance ``settle`` après la fin, car la remontée
    de température et le compteur se mettent à jour après la bascule.
    """

    def __init__(self, ecs_value: float = 1.0, settle: int = 1800) -> None:
        self._ecs = ecs_value
        self._settle = settle

    def detect(
        self,
        status: Sequence[Measurement],
        *,
        prior_status: Measurement | None = None,
        temperatures: Sequence[Measurement] = (),
        prior_temperature: Measurement | None = None,
        energy: Sequence[Measurement] = (),
        prior_energy: Measurement | None = None,
        gaps: Sequence[Gap] = (),
        window_start: Instant,
    ) -> list[HeatingCycle]:
        """Cycles dont le début est dans la fenêtre ou la chevauche (``window_start`` : début demandé)."""
        readings = sorted(status, key=lambda m: m.instant)
        spans: list[tuple[Instant, Instant | None]] = []
        start: Instant | None = None
        if prior_status is not None and self._is_ecs(prior_status):
            # déjà en cours à l'ouverture de la fenêtre : début connu seulement par la mesure précédente
            start = prior_status.instant
        for reading in readings:
            if self._is_ecs(reading):
                if start is None:
                    start = reading.instant
                # sinon : répétition de l'état « ECS », cycle déjà ouvert
            elif start is not None:
                spans.append((start, reading.instant))
                start = None
        if start is not None:
            spans.append((start, None))
        cycles = []
        for n, (begin, end) in enumerate(spans):
            following = spans[n + 1][0] if n + 1 < len(spans) else None
            cycles.append(
                self._build(begin, end, following, temperatures, prior_temperature, energy, prior_energy, gaps)
            )
        return [c for c in cycles if c.end is None or c.end > window_start]

    def _is_ecs(self, m: Measurement) -> bool:
        return m.value.number == self._ecs

    @staticmethod
    def _hidden(gaps: Sequence[Gap], a: Instant, b: Instant) -> bool:
        return any(g.overlaps(a, b) for g in gaps)

    def _build(
        self,
        start: Instant,
        end: Instant | None,
        following: Instant | None,
        temperatures: Sequence[Measurement],
        prior_temperature: Measurement | None,
        energy: Sequence[Measurement],
        prior_energy: Measurement | None,
        gaps: Sequence[Gap],
    ) -> HeatingCycle:
        horizon = None if end is None else end + self._settle
        if horizon is not None and following is not None:
            horizon = min(horizon, following)
        t_start = self._value_at(temperatures, prior_temperature, start)
        t_end = None if end is None else self._value_at(temperatures, prior_temperature, horizon or end)
        wh = None
        if end is not None and horizon is not None and not self._hidden(gaps, start, horizon):
            before = self._reading_at(energy, prior_energy, start)
            after = self._reading_at(energy, prior_energy, horizon)
            if (
                before is not None
                and after is not None
                and after.value.number is not None
                and before.value.number is not None
                and after.value.number >= before.value.number
            ):
                wh = after.value.number - before.value.number
        return HeatingCycle(start, end, t_start, t_end, wh)

    @staticmethod
    def _reading_at(series: Sequence[Measurement], prior: Measurement | None, at: Instant) -> Measurement | None:
        found = prior if prior is not None and prior.instant <= at else None
        for m in series:
            if m.instant <= at and (found is None or m.instant >= found.instant):
                found = m
        return found

    def _value_at(self, series: Sequence[Measurement], prior: Measurement | None, at: Instant) -> float | None:
        m = self._reading_at(series, prior, at)
        return None if m is None else m.value.number


@dataclass(frozen=True, slots=True)
class ScheduleState:
    setpoint: float | None
    next_at: Instant | None
    next_setpoint: float | None


def schedule_state(schedule: WeeklySchedule, now: Instant) -> ScheduleState:
    """Consigne programmée à ``now`` et prochain changement, en heure de Paris (changements d'heure compris)."""
    local = datetime.fromtimestamp(now.epoch, PARIS)
    weekday, minute = local.weekday(), local.hour * 60 + local.minute
    current = schedule.setpoint_at(weekday, minute)
    found = schedule.next_transition(weekday, minute)
    if found is None:
        return ScheduleState(current, None, None)
    ahead, t = found
    day = local.date() + timedelta(days=ahead)
    at = datetime(day.year, day.month, day.day, t.minute // 60, t.minute % 60, tzinfo=PARIS)
    return ScheduleState(current, Instant(int(at.timestamp())), t.setpoint)


def parse_transitions(raw: object) -> tuple[ScheduleTransition, ...] | None:
    """``[{minute, setpoint}]`` (forme normalisée par l'adaptateur) -> transitions triées ; ``None`` si invalide."""
    if not isinstance(raw, list):
        return None
    try:
        out = [ScheduleTransition(int(e["minute"]), float(e["setpoint"])) for e in raw]
    except (KeyError, TypeError, ValueError):
        return None
    return tuple(sorted(out, key=lambda t: t.minute))
