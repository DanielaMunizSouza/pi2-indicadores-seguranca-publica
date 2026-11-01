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


# --- Grupos de natureza, tendência e aviso (RF10) ---------------------------

from geohabita.domain.rates import (  # noqa: E402
    OCCURRENCE_GROUPS,
    SUBNOTIFICATION_NOTICE,
    TREND_TOLERANCE,
    occurrence_group,
    trend_direction,
)


def test_specification_lists_five_occurrence_groups():
    assert set(OCCURRENCE_GROUPS) == {"roubo", "furto", "roubo_celular", "roubo_veiculo", "crimes_contra_vida"}


@pytest.mark.parametrize(
    ("natureza", "grupo"),
    [
        ("ROUBO - OUTROS", "roubo"),
        ("ROUBO DE CARGA", "roubo"),
        ("ROUBO DE VEÍCULO", "roubo_veiculo"),
        ("Roubo de Veículo", "roubo_veiculo"),
        ("FURTO - OUTROS", "furto"),
        ("FURTO DE VEÍCULO", "furto"),
        ("HOMICÍDIO DOLOSO", "crimes_contra_vida"),
        ("LATROCÍNIO", "crimes_contra_vida"),
        ("LESÃO CORPORAL SEGUIDA DE MORTE", "crimes_contra_vida"),
        ("LESÃO CORPORAL DOLOSA", None),
        ("HOMICÍDIO CULPOSO POR ACIDENTE DE TRÂNSITO", None),
        ("TRÁFICO DE ENTORPECENTES", None),
    ],
)
def test_criminal_naturezas_map_to_groups(natureza, grupo):
    assert occurrence_group("criminal", natureza, None) == grupo


def test_phone_robbery_comes_from_the_rubrica_of_the_phone_dataset():
    assert occurrence_group("celulares_subtraidos", "Código Penal", "Roubo (art. 157)") == "roubo_celular"
    assert occurrence_group("celulares_subtraidos", "Código Penal", "Furto (art. 155)") is None
    assert occurrence_group("celulares_subtraidos", "Não Criminal", "Perda/Extravio") is None


def test_other_datasets_do_not_feed_the_rates():
    assert occurrence_group("mdip", "MORTE DECORRENTE DE INTERVENÇÃO POLICIAL", None) is None


def test_trend_compares_last_year_with_first():
    assert trend_direction([100, 105, 130]) == "alta"
    assert trend_direction([100, 95, 70]) == "queda"
    assert trend_direction([100, 140, 105]) == "estável"


def test_trend_tolerance_is_ten_percent():
    assert TREND_TOLERANCE == pytest.approx(0.10)
    assert trend_direction([100, 110]) == "alta"
    assert trend_direction([100, 109]) == "estável"


def test_trend_from_zero_is_rising_only_if_it_grows():
    assert trend_direction([0, 0, 5]) == "alta"
    assert trend_direction([0, 0, 0]) == "estável"


def test_trend_needs_at_least_two_points():
    with pytest.raises(ValueError):
        trend_direction([100])


def test_subnotification_notice_is_present():
    assert "subnotifica" in SUBNOTIFICATION_NOTICE.lower()
