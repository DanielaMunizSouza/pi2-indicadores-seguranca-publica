"""Testes das regras de proximidade (RN12, RN13, RN14, RN15; RF23).

Os vetores reproduzem os casos CT17, CT18, CT19 e CT20 da especificação.
"""

import pytest

from geohabita.domain.proximity import (
    WALK_SPEED_M_PER_MINUTE,
    category_note,
    proximity_note,
    walking_time_minutes,
)


def test_note_is_maximum_within_ideal_distance():
    # distance <= a_j -> 100 (RN13)
    assert proximity_note(300, ideal_m=300, max_m=800) == pytest.approx(100)


def test_note_is_zero_at_or_beyond_max_distance():
    # distance >= b_j -> 0 (RN13, RN15)
    assert proximity_note(800, ideal_m=300, max_m=800) == pytest.approx(0)
    assert proximity_note(1200, ideal_m=300, max_m=800) == pytest.approx(0)


def test_note_is_linear_between_thresholds():
    # CT18: ponto de ônibus a 550 m (a=300, b=800) -> 50
    assert proximity_note(550, ideal_m=300, max_m=800) == pytest.approx(50)


def test_missing_equipment_scores_zero():
    # RN15: nenhum equipamento do tipo dentro do raio máximo
    assert proximity_note(None, ideal_m=300, max_m=800) == pytest.approx(0)


def test_category_note_is_mean_of_type_notes():
    assert category_note([100, 50, 0]) == pytest.approx(50)


@pytest.mark.parametrize(
    ("distance_m", "expected_minutes"),
    [(80, 1), (81, 2), (160, 2), (650, 9)],
)
def test_walking_time_rounds_up_to_whole_minute(distance_m, expected_minutes):
    # RN14 / CT19: 650 m -> 9 minutos
    assert walking_time_minutes(distance_m) == expected_minutes


def test_walking_speed_constant():
    assert WALK_SPEED_M_PER_MINUTE == 80
