import pytest

from app.domain.services import TariffSplitter, TimeWindow
from app.domain.values import EquipmentId, MetricKey
from tests.builders import m, paris

HP = EquipmentId("heat_pump")
KEY = MetricKey("energy_heating_cumulative")
# heures creuses 01:38-06:38 et 14:08-17:08
split = TariffSplitter([TimeWindow(98, 398), TimeWindow(848, 1028)])


def c(t, wh):
    return m(t, wh, eq=HP, key=KEY)


def day(points, *, prior=None, start=None, end=None):
    return split.split(points, prior=prior, start=start or paris(2026, 10, 28), end=end or paris(2026, 10, 29))


def test_interval_inside_off_peak():
    [d] = day([c(paris(2026, 10, 28, 3), 1000), c(paris(2026, 10, 28, 3, 10), 1600)]).days
    assert (d.off_peak_wh, d.peak_wh, d.unassigned_wh, d.covered_seconds) == (600, 0, 0, 600)


def test_interval_straddling_a_boundary_is_prorated():
    # 06:30 -> 06:40 : 8 min creuses, 2 min pleines
    r = day([c(paris(2026, 10, 28, 6, 30), 0), c(paris(2026, 10, 28, 6, 40), 1000)])
    [d] = r.days
    assert d.off_peak_wh == pytest.approx(800) and d.peak_wh == pytest.approx(200)
    assert r.hourly_off_peak_wh[6] == pytest.approx(800) and r.hourly_peak_wh[6] == pytest.approx(200)


def test_long_interval_is_not_assigned_to_a_tariff():
    [d] = day([c(paris(2026, 10, 28, 8), 0), c(paris(2026, 10, 28, 12), 400)]).days
    assert (d.off_peak_wh, d.peak_wh, d.unassigned_wh, d.covered_seconds) == (0, 0, 400, 0)


def test_long_idle_interval_counts_as_covered():
    [d] = day([c(paris(2026, 10, 28, 8), 400), c(paris(2026, 10, 28, 12), 400)]).days
    assert (d.off_peak_wh, d.peak_wh, d.unassigned_wh, d.covered_seconds) == (0, 0, 0, 4 * 3600)


def test_interval_crossing_midnight_is_split_between_days_and_clipped_to_window():
    prior = c(paris(2026, 10, 27, 23, 50), 0)
    r = day([c(paris(2026, 10, 28, 0, 10), 200)], prior=prior)
    [d] = r.days  # la part du 27 est hors fenêtre
    assert d.day.isoformat() == "2026-10-28" and d.peak_wh == pytest.approx(100)


def test_negative_delta_is_ignored():
    assert day([c(paris(2026, 10, 28, 3), 1000), c(paris(2026, 10, 28, 3, 10), 10)]).days == ()


def test_window_crossing_midnight():
    w = TimeWindow(22 * 60, 6 * 60)
    assert w.contains(23 * 60) and w.contains(60) and not w.contains(12 * 60)


def test_dst_fall_back_day_has_25_hours():
    # 25/10/2026 : l'heure 02:00-03:00 existe deux fois ; un compteur régulier couvre bien 25 h
    pts = [c(paris(2026, 10, 25).epoch + i * 600, i * 10) for i in range(25 * 6 + 1)]
    [d] = split.split(pts, prior=None, start=paris(2026, 10, 25), end=paris(2026, 10, 26)).days
    assert d.covered_seconds == 25 * 3600
    assert d.off_peak_wh + d.peak_wh == pytest.approx(1500)
    assert d.off_peak_wh == pytest.approx(10 * 6 * 5 + 60 + 10 * 6 * 3)  # 5 h + l'heure doublée + 3 h
