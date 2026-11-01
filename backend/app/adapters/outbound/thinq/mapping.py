"""Traduction de l'état ThinQ vers le domaine (couche anti-corruption)."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.domain.model import Equipment
from app.domain.values import EquipmentId, Instant, Measurement, MeasurementValue, MetricKey

log = logging.getLogger(__name__)

SEMANTICS_PATH = Path(__file__).with_name("semantics.yaml")
KINDS = frozenset({"number", "bool", "enum", "minutes"})
_SEGMENT = re.compile(r"^(\w+)(?:\[(\w+)\])?$")


@dataclass(frozen=True, slots=True)
class MetricSpec:
    key: MetricKey
    label: str
    kind: str
    path: str
    unit: str | None = None
    true_value: str | None = None
    hour: str | None = None
    minute: str | None = None
    enum: Mapping[str, tuple[int, str]] = field(default_factory=dict)

    @property
    def enum_labels(self) -> dict[int, str]:
        return {code: label for code, label in self.enum.values()}


@dataclass(frozen=True, slots=True)
class EquipmentSpec:
    id: str
    kind: str
    label: str
    device_type: str
    single: bool
    metrics: tuple[MetricSpec, ...]


@dataclass(frozen=True, slots=True)
class Semantics:
    equipment: tuple[EquipmentSpec, ...]

    @classmethod
    def load(cls, path: Path = SEMANTICS_PATH) -> Semantics:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        specs = []
        for e in raw["equipment"]:
            metrics = []
            for key, v in e["metrics"].items():
                if v["type"] not in KINDS:
                    raise ValueError(f"type de métrique inconnu : {v['type']!r}")
                enum = {str(name): (int(code), str(label)) for name, (code, label) in (v.get("enum") or {}).items()}
                if len({code for code, _ in enum.values()}) != len(enum):
                    raise ValueError(f"codes d'enum en double pour {e['id']}/{key}")
                metrics.append(
                    MetricSpec(
                        MetricKey(key),
                        str(v["label"]),
                        v["type"],
                        str(v["path"]),
                        v.get("unit"),
                        v.get("true_value"),
                        v.get("hour"),
                        v.get("minute"),
                        enum,
                    )
                )
            specs.append(
                EquipmentSpec(e["id"], e["kind"], e["label"], e["device_type"], bool(e.get("single")), tuple(metrics))
            )
        return cls(tuple(specs))


@dataclass(frozen=True, slots=True)
class ResolvedEquipment:
    """Appareil ThinQ reconnu ; ``state`` vaut ``None`` s'il est hors ligne."""

    equipment: Equipment
    spec: EquipmentSpec
    device_id: str
    state: Mapping[str, Any] | None = None


def resolve_equipment(devices: Iterable[Mapping[str, Any]], semantics: Semantics) -> list[ResolvedEquipment]:
    """Associe les appareils de ``GET /devices`` aux équipements de ``semantics.yaml``.

    Un type non décrit est ignoré (journalisé sans identifiant) ; l'alias n'est jamais utilisé.
    """
    by_type: dict[str, list[str]] = {}
    for d in devices:
        info = d.get("deviceInfo") or {}
        if isinstance(d.get("deviceId"), str) and isinstance(info.get("deviceType"), str):
            by_type.setdefault(info["deviceType"], []).append(d["deviceId"])
    known = {s.device_type for s in semantics.equipment}
    for device_type in sorted(set(by_type) - known):
        log.info("Appareil ThinQ non décrit dans semantics.yaml ignoré (%s)", device_type)

    out = []
    for spec in semantics.equipment:
        ids = sorted(by_type.get(spec.device_type, []))
        if spec.single and len(ids) > 1:
            log.warning("%d appareils pour %s (single) : seul le premier est lu", len(ids), spec.id)
            ids = ids[:1]
        for index, device_id in enumerate(ids, start=1):
            eq_id = spec.id if spec.single else f"{spec.id}_{index}"
            label = spec.label if spec.single else f"{spec.label} {index}"
            equipment = Equipment(
                id=EquipmentId(eq_id), label=label, kind=spec.kind, provider_ref={"device_id": device_id}
            )
            out.append(ResolvedEquipment(equipment, spec, device_id))
    return out


def normalize_state(raw: Any) -> dict[str, Any] | None:
    """Certains appareils renvoient une liste d'états (un par emplacement) : on lit le premier."""
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    return raw if isinstance(raw, dict) else None


def lookup(state: Mapping[str, Any], path: str) -> Any:
    """Valeur à ``path`` (voir semantics.yaml), ``None`` si absente."""
    node: Any = state
    for segment in path.split("."):
        m = _SEGMENT.match(segment)
        if m is None or not isinstance(node, dict):
            return None
        node = node.get(m.group(1))
        if m.group(2) is not None:
            if not isinstance(node, list):
                return None
            node = next((i for i in node if isinstance(i, dict) and i.get("locationName") == m.group(2)), None)
        if node is None:
            return None
    return node


def _is_number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def parse_value(raw: Any, spec: MetricSpec) -> MeasurementValue | None:
    """Valeur ThinQ -> ``MeasurementValue`` ; ``None`` si absente ou inexploitable (jamais inventée)."""
    if raw is None:
        return None
    if spec.kind == "number":
        return MeasurementValue.of_number(raw, spec.unit) if _is_number(raw) else None
    if spec.kind == "bool":
        if isinstance(raw, bool):
            return MeasurementValue.of_bool(raw)
        return MeasurementValue.of_bool(raw == spec.true_value) if isinstance(raw, str) and spec.true_value else None
    if spec.kind == "enum":
        entry = spec.enum.get(raw) if isinstance(raw, str) else None
        return (
            None
            if entry is None
            else MeasurementValue(MeasurementValue.of_number(entry[0]).type, number=float(entry[0]))
        )
    if spec.kind == "minutes":
        if not isinstance(raw, dict):
            return None
        hours, minutes = raw.get(spec.hour or ""), raw.get(spec.minute or "")
        if not (_is_number(hours) and _is_number(minutes)):
            return None
        return MeasurementValue.of_number(int(hours) * 60 + int(minutes), "min")
    return None


def measurements_of(resolved: ResolvedEquipment, polled_at: Instant) -> list[Measurement]:
    """Mesures de l'état courant. ThinQ ne date pas les valeurs : l'instant est celui du poll."""
    if resolved.state is None:
        return []
    out = []
    for metric in resolved.spec.metrics:
        raw = lookup(resolved.state, metric.path)
        value = parse_value(raw, metric)
        if value is None:
            if raw is not None:
                log.warning("Valeur inattendue ignorée pour %s/%s", resolved.equipment.id, metric.key)
            continue
        out.append(
            Measurement(
                equipment_id=resolved.equipment.id,
                metric_key=metric.key,
                instant=polled_at,
                value=value,
                source=metric.path,
                polled_at=polled_at,
                provider_timestamped=False,
            )
        )
    return out
