from app.domain.model import Gap, GapCause
from app.domain.services import CycleDetector
from app.domain.values import EquipmentId, Instant, MetricKey
from tests.builders import COUNTER, m

STATUS = MetricKey("dhw_status")
HP = EquipmentId("heat_pump")
det = CycleDetector()


def status(t, value):
    return m(t, value, key=STATUS)


def energy(t, value):
    return m(t, value, eq=HP, key=COUNTER)


def run(readings, **kw):
    kw.setdefault("window_start", Instant(0))
    return det.detect(readings, **kw)


def test_a_cycle_is_bounded_by_the_valve_transitions():
    [c] = run([status(1000, 1), status(3000, 0)])
    assert (c.start, c.end, c.duration, c.ongoing) == (Instant(1000), Instant(3000), 2000, False)


def test_open_cycle_is_ongoing():
    [c] = run([status(1000, 1)])
    assert c.ongoing and c.duration is None


def test_repeated_ecs_readings_do_not_split_a_cycle():
    assert len(run([status(1000, 1), status(1300, 1), status(3000, 0)])) == 1


def test_two_cycles():
    cycles = run([status(1000, 1), status(2000, 0), status(9000, 1), status(9500, 0)])
    assert [c.start.epoch for c in cycles] == [1000, 9000]


def test_cycle_in_progress_when_window_opens_starts_at_prior_reading():
    [c] = run([status(5000, 0)], prior_status=status(1000, 1), window_start=Instant(3000))
    assert (c.start, c.end) == (Instant(1000), Instant(5000))


def test_cycle_ended_before_window_is_dropped():
    assert run([status(1000, 1), status(2000, 0)], window_start=Instant(3000)) == []


def test_gap_does_not_change_the_provider_dated_bounds():
    gap = Gap(Instant(1100), Instant(1900), GapCause.DOWNTIME)
    [c] = run([status(2000, 1), status(4000, 0)], prior_status=status(1000, 0), gaps=[gap])
    assert (c.start, c.end) == (Instant(2000), Instant(4000))


def test_gap_during_the_cycle_hides_its_energy():
    gap = Gap(Instant(2000), Instant(3000), GapCause.DOWNTIME)
    [c] = run(
        [status(1000, 1), status(4000, 0)],
        energy=[energy(900, 100), energy(4100, 900)],
        gaps=[gap],
    )
    assert c.energy_wh is None


def test_old_gap_does_not_hide_energy():
    gap = Gap(Instant(100), Instant(500), GapCause.DOWNTIME)
    [c] = run([status(1000, 1), status(3000, 0)], energy=[energy(50, 100), energy(3100, 900)], gaps=[gap])
    assert c.energy_wh == 800.0


def test_energy_and_temperatures_are_read_around_the_cycle():
    [c] = run(
        [status(1000, 1), status(3000, 0)],
        temperatures=[m(900, 40.0), m(2900, 50.0), m(3500, 55.0), m(9000, 52.0)],
        energy=[energy(800, 1000), energy(1500, 1400), energy(3400, 2200), energy(9000, 5000)],
    )
    assert (c.start_temperature, c.end_temperature) == (40.0, 55.0)
    assert c.energy_wh == 1200.0  # 2200 (30 min après la fin) - 1000 (avant le début)


def test_energy_stops_at_the_next_cycle():
    first, _ = run(
        [status(1000, 1), status(2000, 0), status(2500, 1), status(3000, 0)],
        energy=[energy(900, 0), energy(1900, 100), energy(2600, 400)],
    )
    assert first.energy_wh == 100.0


def test_unknown_values_stay_unknown():
    [c] = run([status(1000, 1), status(3000, 0)])
    assert c.start_temperature is None and c.end_temperature is None and c.energy_wh is None
