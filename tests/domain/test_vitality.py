"""Testes do Índice de Vitalidade do Espaço Público (RN06; RF08, RF09).

Os vetores reproduzem os casos CT08 (média aritmética com pesos iguais) e
CT09 (peso de mobilidade igual a 5) da especificação.
"""

import pytest

from geohabita.domain.vitality import (
    DEFAULT_WEIGHT,
    MAX_WEIGHT,
    MIN_WEIGHT,
    is_valid_weight,
    public_space_vitality_index,
)


def test_ivep_is_arithmetic_mean_with_equal_weights():
    # CT08
    percentiles = [100, 50, 0, 80, 60, 40]
    weights = [1, 1, 1, 1, 1, 1]
    assert public_space_vitality_index(percentiles, weights) == pytest.approx(55)


def test_ivep_applies_category_weights():
    # CT09: peso de mobilidade igual a 5 e demais iguais a 1
    percentiles = [0, 0, 100, 0, 0, 0]
    weights = [1, 1, 5, 1, 1, 1]
    assert public_space_vitality_index(percentiles, weights) == pytest.approx(50)


def test_ivep_is_bounded_by_percentiles():
    assert public_space_vitality_index([0, 0, 0, 0, 0, 0], [1] * 6) == pytest.approx(0)
    assert public_space_vitality_index([100] * 6, [1] * 6) == pytest.approx(100)


def test_ivep_requires_one_weight_per_category():
    with pytest.raises(ValueError):
        public_space_vitality_index([50, 60], [1])


def test_default_weight_is_one():
    assert DEFAULT_WEIGHT == 1


@pytest.mark.parametrize(
    ("weight", "expected"),
    [(0, True), (1, True), (5, True), (-1, False), (6, False), (1.5, False)],
)
def test_weight_must_be_integer_between_zero_and_five(weight, expected):
    # RN06
    assert is_valid_weight(weight) is expected


def test_weight_bounds():
    assert (MIN_WEIGHT, MAX_WEIGHT) == (0, 5)


# --- Percentis entre distritos (RN06) ---------------------------------------

from geohabita.domain.vitality import category_percentile, percentile_ranks  # noqa: E402


def test_percentile_ranks_spread_from_zero_to_hundred():
    ranks = percentile_ranks({"a": 1.0, "b": 2.0, "c": 3.0})
    assert ranks == {"a": 0.0, "b": 50.0, "c": 100.0}


def test_percentile_ranks_give_ties_the_same_mid_rank():
    ranks = percentile_ranks({"a": 1.0, "b": 2.0, "c": 2.0, "d": 3.0})
    assert ranks["b"] == ranks["c"] == pytest.approx(50.0)
    assert ranks["a"] == 0.0 and ranks["d"] == 100.0


def test_single_district_is_at_the_top():
    assert percentile_ranks({"a": 5.0}) == {"a": 100.0}


def test_percentile_ranks_of_empty_input_is_empty():
    assert percentile_ranks({}) == {}


def test_category_percentile_averages_area_and_population_densities():
    assert category_percentile(80.0, 40.0) == pytest.approx(60.0)
