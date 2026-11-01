"""Gateway ThinQ : cycle de lecture, hors ligne, PAT refusé, limite d'appels."""

import pytest

from app.adapters.outbound.system import FixedClock
from app.adapters.outbound.thinq.gateway import ThinQGateway
from app.adapters.outbound.thinq.mapping import Semantics
from app.domain.errors import CredentialsRejected, ProviderThrottled, ProviderUnavailable
from app.domain.values import EquipmentId, Instant
from tests import thinq_fixture as fx

NOW = Instant(fx.fixture()["generated_at"])


class Mono:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def env():
    client, mono = fx.FixtureClient(), Mono()
    return client, mono, ThinQGateway(client, Semantics.load(), FixedClock(NOW), monotonic=mono)


async def test_one_cycle_reads_devices_once_and_each_state_once(env):
    client, _, gw = env
    await gw.list_equipment()
    await gw.read_measurements()
    await gw.availability()
    assert client.calls.count("devices") == 1 and client.calls.count("state") == 3


async def test_next_cycle_rereads_states_but_keeps_device_list(env):
    client, mono, gw = env
    await gw.list_equipment()
    mono.t += 300
    await gw.list_equipment()
    assert client.calls.count("devices") == 1 and client.calls.count("state") == 6
    mono.t += 3600
    await gw.list_equipment()
    assert client.calls.count("devices") == 2


async def test_offline_device_is_unavailable_without_measurements(env):
    client, _, gw = env
    client.offline.add(fx.device_id_of("DEVICE_WASHER"))
    await gw.list_equipment()
    availability = await gw.availability()
    assert availability[EquipmentId("washer")] is False and availability[EquipmentId("fridge")] is True
    measured = {m.equipment_id for m in await gw.read_measurements()}
    assert EquipmentId("washer") not in measured and EquipmentId("fridge") in measured


async def test_describe_is_empty_before_first_read_then_lists_metrics(env):
    _, _, gw = env
    assert await gw.describe() == []
    await gw.list_equipment()
    infos = {(str(i.equipment_id), str(i.metric_key)): i for i in await gw.describe()}
    assert infos[("fridge", "fridge_setpoint")].unit == "°C"
    assert infos[("washer", "run_state")].enum[2] == "En cours"


async def test_rejected_pat_stops_all_further_calls(env):
    client, mono, gw = env
    client.fail_with = CredentialsRejected("PAT refusé")
    with pytest.raises(CredentialsRejected):
        await gw.list_equipment()
    calls = len(client.calls)
    client.fail_with = None
    mono.t += 3600
    with pytest.raises(CredentialsRejected):
        await gw.list_equipment()
    assert len(client.calls) == calls


async def test_throttle_suspends_calls_for_retry_after(env):
    client, mono, gw = env
    client.fail_with = ProviderThrottled("limite", retry_after=120)
    with pytest.raises(ProviderThrottled):
        await gw.list_equipment()
    calls = len(client.calls)
    client.fail_with = None
    mono.t += 60
    with pytest.raises(ProviderThrottled) as exc:
        await gw.list_equipment()
    assert len(client.calls) == calls and 0 < exc.value.retry_after <= 61
    mono.t += 61
    assert await gw.list_equipment()


async def test_unavailable_is_retried_next_cycle(env):
    client, _, gw = env
    client.fail_with = ProviderUnavailable("down")
    with pytest.raises(ProviderUnavailable):
        await gw.list_equipment()
    client.fail_with = None
    assert await gw.list_equipment()
