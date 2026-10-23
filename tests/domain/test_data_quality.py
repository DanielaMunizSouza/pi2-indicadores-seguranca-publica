"""Testes da validação de coordenadas importadas (RN10; RF20).

O caso CT13 da especificação usa uma planilha com cinco registros de
coordenadas nulas ou zeradas, que devem ser descartados e contabilizados.
"""

import pytest

from geohabita.domain.data_quality import (
    MISSING,
    OUTSIDE,
    ZERO,
    ValidationReport,
    discard_reason,
    validate_coordinates,
)

PRACA_DA_SE = (-23.5503, -46.6339)


def test_coordinate_inside_city_is_usable():
    assert discard_reason(*PRACA_DA_SE) is None


@pytest.mark.parametrize(
    ("lat", "lon", "reason"),
    [
        (None, -46.63, MISSING),
        (-23.55, None, MISSING),
        (None, None, MISSING),
        (0, 0, ZERO),
        (0.0, -46.63, ZERO),
        (-23.55, 0.0, ZERO),
        (-22.9068, -43.1729, OUTSIDE),  # Rio de Janeiro
        (-23.69, -46.10, OUTSIDE),  # leste do retângulo do município
    ],
)
def test_unusable_coordinates_have_a_reason(lat, lon, reason):
    assert discard_reason(lat, lon) == reason


def test_ct13_null_and_zero_records_are_discarded_and_counted():
    rows = [PRACA_DA_SE, (None, None), (0, 0), (None, -46.6), (0.0, 0.0), (-23.5, None), PRACA_DA_SE]
    report = validate_coordinates(rows)
    assert report.accepted == 2
    assert report.total_discarded == 5
    assert report.discarded[MISSING] == 3
    assert report.discarded[ZERO] == 2


def test_empty_load_produces_empty_report():
    report = validate_coordinates([])
    assert (report.accepted, report.total_discarded) == (0, 0)


def test_report_starts_empty():
    assert ValidationReport().total_discarded == 0
