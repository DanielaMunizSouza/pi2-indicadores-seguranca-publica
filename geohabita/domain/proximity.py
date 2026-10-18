"""Proximidade do endereço e Índice de Proximidade Local.

Cobre a nota por tipo de equipamento (equação da nota; RN13, RN14, RN15),
o tempo estimado de caminhada (RN14) e o Índice de Proximidade Local do
endereço (equação do IPL; RF23, RF24). A distância considerada é a distância
geodésica em linha reta (RN12).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

WALK_SPEED_M_PER_MINUTE = 80


def proximity_note(distance_m: float | None, ideal_m: float, max_m: float) -> float:
    """Nota de 0 a 100 para a distância até um tipo de equipamento.

    Implementa a equação da nota (RN13): 100 quando ``distance_m <= ideal_m``,
    0 quando ``distance_m >= max_m`` e interpolação linear no intervalo.
    Uma distância ausente (nenhum equipamento do tipo) resulta em 0 (RN15).
    """
    if distance_m is None or distance_m >= max_m:
        return 0.0
    if distance_m <= ideal_m:
        return 100.0
    return 100 * (max_m - distance_m) / (max_m - ideal_m)


def category_note(notes: Sequence[float]) -> float:
    """Nota da categoria: média aritmética das notas dos seus tipos."""
    if not notes:
        raise ValueError("A categoria precisa de ao menos uma nota de tipo.")
    return sum(notes) / len(notes)


def walking_time_minutes(distance_m: float) -> int:
    """Tempo estimado de caminhada a 80 m/min, arredondado para cima (RN14)."""
    return math.ceil(distance_m / WALK_SPEED_M_PER_MINUTE)


def weighted_index(scores: Sequence[float], weights: Sequence[float]) -> float:
    """Média ponderada de notas por pesos (equações do IPL e do IVEP).

    Levanta ``ValueError`` quando as listas têm tamanhos diferentes ou quando
    a soma dos pesos é zero, casos em que o índice não está definido.
    """
    raise NotImplementedError


def local_proximity_index(
    category_notes: Sequence[float], weights: Sequence[float]
) -> float:
    """Índice de Proximidade Local do endereço consultado (RF24)."""
    raise NotImplementedError
