"""Testes dos indicadores oficiais de ocorrências (RN08, RN09; RF10).

Os vetores reproduzem os casos CT10 (300 ocorrências em três anos para
100 mil habitantes) e CT11 (12 ocorrências na janela) da especificação.
"""

from datetime import date

import pytest

from geohabita.domain.rates import (
    DEFAULT_WINDOW_YEARS,
    INSUFFICIENT_DATA_MESSAGE,
    MIN_OCCURRENCES_FOR_COMPARISON,
    annual_rate_per_100k,
    complete_years_window,
    is_comparable,
)


def test_rate_matches_specification_example():
    # CT10: 300 ocorrências em 3 anos, 100 000 habitantes -> 100 por cem mil ao ano
    assert annual_rate_per_100k(300, 100_000, years=3) == pytest.approx(100)


def test_rate_scales_with_population():
    assert annual_rate_per_100k(100, 50_000, years=1) == pytest.approx(200)


def test_default_window_is_three_years():
    assert DEFAULT_WINDOW_YEARS == 3


def test_rate_is_undefined_without_population():
    with pytest.raises(ValueError):
        annual_rate_per_100k(10, 0)


def test_rate_is_undefined_without_years():
    with pytest.raises(ValueError):
        annual_rate_per_100k(10, 1_000, years=0)


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, False), (12, False), (29, False), (30, True), (300, True)],
)
def test_comparability_requires_minimum_occurrences(count, expected):
    # RN09 / CT11
    assert is_comparable(count) is expected


def test_minimum_occurrences_constant():
    assert MIN_OCCURRENCES_FOR_COMPARISON == 30


def test_insufficient_data_message():
    assert INSUFFICIENT_DATA_MESSAGE == "número insuficiente para comparação"


@pytest.mark.parametrize("today", [date(2026, 1, 1), date(2026, 10, 28), date(2026, 12, 31)])
def test_window_excludes_current_incomplete_year(today):
    # RN08: três anos completos; o ano corrente não entra no cálculo
    assert complete_years_window(today) == (2023, 2025)


def test_window_length_follows_years_argument():
    assert complete_years_window(date(2026, 6, 1), years=1) == (2025, 2025)
