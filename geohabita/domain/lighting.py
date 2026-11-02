"""Iluminação pública: nota pela densidade de pontos, não pela distância.

O município tem cerca de 663 mil pontos cadastrados no GeoSampa: em quase todo
lugar há uma luminária a poucas dezenas de metros, de modo que a distância até
a mais próxima não distinguiria um distrito do outro. A medição que faz sentido
é a densidade no entorno do endereço, comparada com as densidades distritais da
cidade (Equação da nota aplicada ao lugar, não a um único ponto). É o eixo nº 1
apontado pelos munícipes na escuta (iluminação e fluxo de pedestres).
"""

from __future__ import annotations

import math

from geohabita.domain.thresholds import DENSITY_THRESHOLDS, LIGHTING_TYPE

def lighting_thresholds() -> tuple[int, float, float]:
    """(raio em metros, densidade zero, densidade cem) da iluminação pública."""
    valores = DENSITY_THRESHOLDS[LIGHTING_TYPE]
    return valores.radius_m, valores.zero_per_km2, valores.full_per_km2


def lighting_density(count: int, radius_m: float | None = None) -> float:
    """Pontos de iluminação por km² no círculo de ``radius_m`` em torno do endereço."""
    raio = lighting_thresholds()[0] if radius_m is None else radius_m
    return count / (math.pi * raio**2 / 1e6)


def lighting_note(density: float, zero: float | None = None, full: float | None = None) -> float:
    """Nota de 0 a 100 da densidade de iluminação, na forma da nota por tipo (RN13).

    Abaixo de ``zero`` pontos por km² a nota é 0; acima de ``full``, é 100; no
    meio, cresce linearmente. Densidade ausente (``None``) resulta em 0.
    """
    _, padrao_zero, padrao_cem = lighting_thresholds()
    zero = padrao_zero if zero is None else zero
    full = padrao_cem if full is None else full
    if density is None:
        return 0.0
    if density <= zero:
        return 0.0
    if density >= full:
        return 100.0
    return 100 * (density - zero) / (full - zero)
