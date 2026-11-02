"""Nota de iluminação pública pela densidade de pontos no entorno (novo tipo do IPL)."""

import pytest

from geohabita.domain.lighting import (
    LIGHTING_FULL_DENSITY,
    LIGHTING_ZERO_DENSITY,
    lighting_density,
    lighting_note,
)


def test_density_is_points_per_square_kilometer_in_the_neighbourhood():
    assert round(lighting_density(283)) == 1001  # ~283 postes no raio de 300 m


@pytest.mark.parametrize("densidade,esperado", [
    (0, 0.0), (LIGHTING_ZERO_DENSITY, 0.0), (LIGHTING_FULL_DENSITY, 100.0), (5000, 100.0),
    (825, 50.0), (60, 0.0), (None, 0.0),
])
def test_note_grows_linearly_between_the_calibration_limits(densidade, esperado):
    assert lighting_note(densidade) == pytest.approx(esperado)


def test_note_is_monotonic_across_the_city_range():
    # de 20 a 430 postes no raio de 300 m: do fim da malha até o centro
    note = lambda postes: lighting_note(lighting_density(postes))
    assert note(20) < note(50) < note(120) < note(240) < note(430) == note(2000)
