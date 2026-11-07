import pytest

from app.domain.services import PowerDeriver, PowerInterval
from app.domain.values import EquipmentId, MetricKey
from tests.builders import m, paris

KEY = MetricKey("energy_heating_cumulative")
HP = EquipmentId("heat_pump")
power = PowerDeriver()


def c(t, wh):
    return m(t, wh, eq=HP, key=KEY)


def derive(points, *, prior=None, start=None, end=None):
    return power.derive(points, prior=prior, start=start or paris(2026, 10, 28), end=end or paris(2026, 10, 29))


def test_delta_over_ten_minutes_gives_average_watts():
    t = paris(2026, 10, 28, 3).epoch
    assert derive([c(t, 1000), c(t + 600, 1600)]) == [PowerInterval(t, t + 600, 3600.0)]


def test_long_interval_with_energy_is_not_distributed():
    t = paris(2026, 10, 28, 8).epoch
    assert derive([c(t, 0), c(t + 4 * 3600, 400)]) == [PowerInterval(t, t + 4 * 3600, None)]


def test_long_idle_interval_is_zero_watts():
    t = paris(2026, 10, 28, 8).epoch
    assert derive([c(t, 400), c(t + 4 * 3600, 400)]) == [PowerInterval(t, t + 4 * 3600, 0.0)]


def test_negative_delta_is_ignored():
    t = paris(2026, 10, 28, 8).epoch
    assert derive([c(t, 500), c(t + 600, 10)]) == []


def test_prior_reading_gives_the_first_interval_and_window_clips_it():
    midnight = paris(2026, 10, 28)
    prior = c(midnight.epoch - 300, 0)
    [i] = derive([c(midnight.epoch + 300, 600)], prior=prior)
    # 600 Wh sur 600 s = 3600 W, mais seule la partie dans la fenêtre est conservée
    assert i == PowerInterval(midnight.epoch, midnight.epoch + 300, pytest.approx(3600.0))


def test_interval_after_the_window_is_dropped():
    t = paris(2026, 10, 29, 1).epoch
    assert derive([c(t, 0), c(t + 600, 100)]) == []
