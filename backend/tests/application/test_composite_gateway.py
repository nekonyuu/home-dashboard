from app.adapters.outbound.fake import FakeEquipmentGateway
from app.application.composite import CompositeGateway
from app.domain.errors import ProviderUnavailable
from app.domain.model import Equipment
from app.domain.values import EquipmentId, MetricKey
from tests.builders import m

PRIMARY, SECONDARY = EquipmentId("heat_pump"), EquipmentId("fridge")


def gateways():
    a = FakeEquipmentGateway(
        [Equipment(PRIMARY, "PAC", "heat_pump", available=True)], [m(10, 1.0, eq=PRIMARY, key=MetricKey("t"))]
    )
    b = FakeEquipmentGateway(
        [Equipment(SECONDARY, "Frigo", "fridge", available=True)], [m(10, 3.0, eq=SECONDARY, key=MetricKey("t"))]
    )
    return a, b, CompositeGateway(a, [b])


async def test_merges_both_providers():
    _, _, gw = gateways()
    assert {e.id for e in await gw.list_equipment()} == {PRIMARY, SECONDARY}
    assert {x.equipment_id for x in await gw.read_measurements()} == {PRIMARY, SECONDARY}
    assert await gw.availability() == {PRIMARY: True, SECONDARY: True}


async def test_primary_error_propagates():
    a, _, gw = gateways()
    a.fail_with = ProviderUnavailable("down")
    try:
        await gw.list_equipment()
    except ProviderUnavailable:
        return
    raise AssertionError("l'erreur du principal doit remonter")


async def test_secondary_error_is_ignored_and_not_retried_in_the_cycle():
    _, b, gw = gateways()
    b.fail_with = ProviderUnavailable("down")
    assert [e.id for e in await gw.list_equipment()] == [PRIMARY]
    assert {x.equipment_id for x in await gw.read_measurements()} == {PRIMARY}
    assert await gw.availability() == {PRIMARY: True}
    assert b.calls == 0
    b.fail_with = None  # cycle suivant : le secondaire est de nouveau sollicité
    assert {e.id for e in await gw.list_equipment()} == {PRIMARY, SECONDARY}


async def test_secondary_error_during_read_is_ignored():
    _, b, gw = gateways()
    await gw.list_equipment()
    b.fail_with = ProviderUnavailable("down")
    assert {x.equipment_id for x in await gw.read_measurements()} == {PRIMARY}
