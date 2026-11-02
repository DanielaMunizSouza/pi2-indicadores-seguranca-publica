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

LIGHTING_TYPE = "iluminacao_publica"
LIGHTING_RADIUS_M = 300
LIGHTING_AREA_KM2 = math.pi * LIGHTING_RADIUS_M**2 / 1e6

# Densidades, em pontos por km², abaixo e acima das quais a nota é zero e cem.
# Calibradas sobre a cidade real: a densidade distrital mediana é ~655/km² e a
# mediana no raio de 300 m, ~400/km²; periferias sem cadastro ficam perto de
# zero e o centro passa de 2.000/km². São parâmetros de configuração, a rever
# com os testes com moradores (como os limiares do IPL).
LIGHTING_ZERO_DENSITY = 150
LIGHTING_FULL_DENSITY = 1500
LIGHTING_UNAVAILABLE_MESSAGE = "sem dados de iluminação na fonte para este entorno"


def lighting_density(count: int, radius_m: float = LIGHTING_RADIUS_M) -> float:
    """Pontos de iluminação por km² no círculo de ``radius_m`` em torno do endereço."""
    return count / (math.pi * radius_m**2 / 1e6)


def lighting_note(density: float, zero: float = LIGHTING_ZERO_DENSITY, full: float = LIGHTING_FULL_DENSITY) -> float:
    """Nota de 0 a 100 da densidade de iluminação, na mesma forma da nota por tipo (RN13).

    Abaixo de ``zero`` pontos por km² a nota é 0; acima de ``full``, é 100; no meio,
    cresce linearmente. Densidade ausente (``None``) resulta em 0.
    """
    if density is None:
        return 0.0
    if density <= zero:
        return 0.0
    if density >= full:
        return 100.0
    return 100 * (density - zero) / (full - zero)
