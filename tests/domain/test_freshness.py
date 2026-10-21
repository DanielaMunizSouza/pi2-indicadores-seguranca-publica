"""Testes da validade do cache (RN04) e da atualidade dos indicadores (RN11)."""

from datetime import date, datetime, timedelta

import pytest

from geohabita.domain.freshness import (
    CACHE_MAX_AGE_DAYS,
    OUTDATED_AFTER_MONTHS,
    OUTDATED_MESSAGE,
    is_cache_fresh,
    is_outdated,
)

NOW = datetime(2026, 10, 1, 12, 0)


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(0), True),
        (timedelta(days=29), True),
        (timedelta(days=30), True),
        (timedelta(days=30, seconds=1), False),
        (timedelta(days=31), False),
    ],
)
def test_cache_is_fresh_for_thirty_days(age, expected):
    # RN04: resultados de CEP e geocodificação ficam em cache por 30 dias
    assert is_cache_fresh(NOW - age, NOW) is expected


def test_cache_age_limit_is_configurable():
    assert is_cache_fresh(NOW - timedelta(days=5), NOW, max_age_days=3) is False


@pytest.mark.parametrize(
    ("reference_date", "expected"),
    [
        (date(2025, 10, 1), False),  # 12 meses
        (date(2024, 11, 1), False),  # 23 meses
        (date(2024, 10, 1), False),  # 24 meses exatos
        (date(2024, 9, 30), True),  # 24 meses e 1 dia
        (date(2024, 9, 1), True),  # 25 meses
    ],
)
def test_indicator_is_outdated_after_24_months(reference_date, expected):
    # RN11
    assert is_outdated(reference_date, date(2026, 10, 1)) is expected


def test_month_count_uses_calendar_months():
    # 29/02 + 24 meses cai em 28/02 (mês sem dia 29): exatos 24 meses, sem aviso
    assert is_outdated(date(2024, 2, 29), date(2026, 2, 28)) is False
    assert is_outdated(date(2024, 2, 29), date(2026, 3, 1)) is True


def test_constants():
    assert (CACHE_MAX_AGE_DAYS, OUTDATED_AFTER_MONTHS) == (30, 24)
    assert OUTDATED_MESSAGE == "dado desatualizado"
