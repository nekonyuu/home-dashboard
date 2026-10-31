import pytest

from app.domain.model import ScheduleTransition as T
from app.domain.model import WeeklySchedule
from app.domain.services import parse_transitions, schedule_state
from tests.builders import paris

SAME = (T(240, 21), T(360, 20), T(900, 21), T(1080, 20), T(1320, 19))


def week(*days):
    return WeeklySchedule(tuple(days))


def test_setpoint_before_first_transition_comes_from_previous_day():
    s = week(*([SAME] * 7))
    assert s.setpoint_at(0, 0) == 19  # lundi 00:00 : 19 °C posé dimanche 22:00
    assert s.setpoint_at(0, 240) == 21  # transition incluse à sa minute
    assert s.setpoint_at(0, 1000) == 21


def test_empty_days_carry_the_last_setpoint_over():
    s = week((T(480, 20),), (), (), (), (), (), ())
    assert s.setpoint_at(3, 600) == 20
    assert s.next_transition(3, 600) == (4, T(480, 20))
    assert week((), (), (), (), (), (), ()).setpoint_at(0, 0) is None
    assert week((), (), (), (), (), (), ()).next_transition(0, 0) is None


def test_next_transition_wraps_to_same_day_next_week():
    s = week((T(480, 20),), (), (), (), (), (), ())
    assert s.next_transition(0, 600) == (7, T(480, 20))


def test_state_in_paris_time_across_dst_change():
    s = week(*([SAME] * 7))
    # samedi 24/10/2026 23:00 ; le passage à l'heure d'hiver a lieu dans la nuit
    st = schedule_state(s, paris(2026, 10, 24, 23))
    assert st.setpoint == 19
    assert st.next_at == paris(2026, 10, 25, 4) and st.next_setpoint == 21


def test_validation():
    with pytest.raises(ValueError):
        T(1440, 20)
    with pytest.raises(ValueError):
        WeeklySchedule(((),))
    assert parse_transitions([{"minute": 360, "setpoint": 20}, {"minute": 240, "setpoint": 21}]) == (
        T(240, 21),
        T(360, 20),
    )
    assert parse_transitions([{"minute": "x"}]) is None
    assert parse_transitions(None) is None
