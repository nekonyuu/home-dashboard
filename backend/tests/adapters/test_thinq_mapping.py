"""Traduction ThinQ -> domaine sur la fixture anonymisée (aucun appel réseau)."""

import pytest

from app.adapters.outbound.thinq.mapping import (
    MetricSpec,
    Semantics,
    lookup,
    measurements_of,
    normalize_state,
    parse_value,
    resolve_equipment,
)
from app.domain.values import EquipmentId, Instant, MetricKey, ValueType
from tests import thinq_fixture as fx

NOW = Instant(fx.fixture()["generated_at"])


@pytest.fixture(scope="module")
def semantics():
    return Semantics.load()


def resolved_with_state(semantics):
    out = []
    for r in resolve_equipment(fx.devices(), semantics):
        out.append(type(r)(r.equipment, r.spec, r.device_id, normalize_state(fx.state_of(r.device_id))))
    return out


def by_id(resolved):
    return {str(r.equipment.id): r for r in resolved}


def test_equipment_recognised_by_device_type_not_alias(semantics):
    resolved = by_id(resolve_equipment(fx.devices(), semantics))
    assert set(resolved) == {"washer", "dishwasher", "fridge"}
    assert resolved["fridge"].equipment.kind == "fridge"
    assert resolved["washer"].equipment.label == "Lave-linge"
    assert "MASKED" not in {r.equipment.label for r in resolved.values()}


def test_unknown_device_type_is_ignored(semantics):
    devices = [*fx.devices(), {"deviceId": "x", "deviceInfo": {"deviceType": "DEVICE_TOASTER"}}]
    assert len(resolve_equipment(devices, semantics)) == 3


def test_every_described_metric_exists_in_the_fixture_state(semantics):
    """Toute métrique décrite dans semantics.yaml doit être lisible dans la fixture (sinon mapping mort)."""
    for r in resolved_with_state(semantics):
        keys = {str(m.metric_key) for m in measurements_of(r, NOW)}
        assert keys == {str(m.key) for m in r.spec.metrics}, r.equipment.id


def test_fridge_values(semantics):
    ms = {str(m.metric_key): m for m in measurements_of(by_id(resolved_with_state(semantics))["fridge"], NOW)}
    assert ms["fridge_setpoint"].value.number == 3 and ms["fridge_setpoint"].value.unit == "°C"
    assert ms["freezer_setpoint"].value.number == -18
    assert ms["door_open"].value.type is ValueType.BOOLEAN and ms["door_open"].value.number == 0.0
    assert ms["express_mode"].value.number == 0.0


def test_washer_state_list_is_read_and_minutes_computed(semantics):
    ms = {str(m.metric_key): m for m in measurements_of(by_id(resolved_with_state(semantics))["washer"], NOW)}
    timer = normalize_state(fx.state_of(fx.device_id_of("DEVICE_WASHER")))["timer"]
    assert ms["remaining_minutes"].value.number == timer["remainHour"] * 60 + timer["remainMinute"]
    assert ms["remaining_minutes"].value.unit == "min"
    assert ms["total_minutes"].value.number == timer["totalHour"] * 60 + timer["totalMinute"]
    assert (
        ms["cycle_count"].value.number
        == normalize_state(fx.state_of(fx.device_id_of("DEVICE_WASHER")))["cycle"]["cycleCount"]
    )
    assert ms["remote_control"].value.number == 1.0
    assert ms["run_state"].value.number == 2  # RUNNING


def test_dishwasher_enum_course_and_door(semantics):
    ms = {str(m.metric_key): m for m in measurements_of(by_id(resolved_with_state(semantics))["dishwasher"], NOW)}
    assert ms["course"].value.number == 4  # TURBO
    assert ms["door_open"].value.number == 0.0
    timer = fx.state_of(fx.device_id_of("DEVICE_DISH_WASHER"))["timer"]
    assert ms["remaining_minutes"].value.number == timer["remainHour"] * 60 + timer["remainMinute"]


def test_measurements_are_not_provider_timestamped(semantics):
    for r in resolved_with_state(semantics):
        for m in measurements_of(r, NOW):
            assert m.provider_timestamped is False and m.instant == NOW == m.polled_at


def test_offline_device_yields_no_measurement(semantics):
    r = resolve_equipment(fx.devices(), semantics)[0]
    assert measurements_of(r, NOW) == []


def test_unknown_enum_value_is_skipped_not_invented(semantics):
    spec = next(m for e in semantics.equipment if e.id == "washer" for m in e.metrics if str(m.key) == "run_state")
    assert parse_value("SOMETHING_NEW", spec) is None
    assert parse_value(None, spec) is None


def test_wrong_types_are_rejected():
    num = MetricSpec(MetricKey("t"), "T", "number", "a")
    assert parse_value("3", num) is None and parse_value(True, num) is None
    flag = MetricSpec(MetricKey("d"), "D", "bool", "a", true_value="OPEN")
    assert parse_value("OPEN", flag).number == 1.0 and parse_value("CLOSE", flag).number == 0.0
    assert parse_value(1, flag) is None


def test_lookup_paths():
    state = {"temperature": [{"locationName": "FRIDGE", "targetTemperature": 3}], "a": {"b": 1}}
    assert lookup(state, "a.b") == 1
    assert lookup(state, "temperature[FRIDGE].targetTemperature") == 3
    assert lookup(state, "temperature[FREEZER].targetTemperature") is None
    assert lookup(state, "a.b.c") is None and lookup(state, "missing") is None


def test_enum_codes_are_unique_and_stable_per_equipment(semantics):
    for e in semantics.equipment:
        for m in e.metrics:
            codes = [c for c, _ in m.enum.values()]
            assert len(codes) == len(set(codes)), (e.id, m.key)


def test_no_real_identifier_in_fixture():
    assert all(str(d["deviceId"]).startswith("device-") for d in fx.devices())
    assert all(d["deviceInfo"]["alias"] == "MASKED" for d in fx.devices())
    assert EquipmentId("washer")
