"""Índice de Vitalidade do Espaço Público (IVEP).

Cobre a equação do IVEP: média ponderada dos percentis das seis categorias
de equipamentos entre os 96 distritos (RN06; RF08, RF09). Os pesos são
inteiros de 0 a 5, com padrão igual a 1, ajustáveis pelo usuário.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeVar

from geohabita.domain.proximity import weighted_index

K = TypeVar("K")

DEFAULT_WEIGHT = 1
MIN_WEIGHT = 0
MAX_WEIGHT = 5


def is_valid_weight(weight: float) -> bool:
    """Indica se o peso é um inteiro entre 0 e 5 (RN06)."""
    # bool é subclasse de int, mas True/False não são pesos válidos.
    if isinstance(weight, bool) or not float(weight).is_integer():
        return False
    return MIN_WEIGHT <= weight <= MAX_WEIGHT


def public_space_vitality_index(
    percentiles: Sequence[float], weights: Sequence[float]
) -> float:
    """IVEP do distrito: média ponderada dos percentis por categoria (RN06).

    Levanta ``ValueError`` quando as listas têm tamanhos diferentes ou quando
    a soma dos pesos é zero, casos em que o índice não está definido.
    """
    return weighted_index(percentiles, weights)


def percentile_ranks(values: Mapping[K, float]) -> dict[K, float]:
    """Posição percentil (0 a 100) de cada distrito entre todos (RN06).

    O menor valor fica em 0 e o maior em 100; empates recebem a média das
    posições que ocupam, para que distritos iguais tenham o mesmo percentil.
    """
    if not values:
        return {}
    if len(values) == 1:
        return {key: 100.0 for key in values}
    ordered = sorted(values.items(), key=lambda item: item[1])
    ranks: dict[K, float] = {}
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1][1] == ordered[i][1]:
            j += 1
        mid_rank = (i + j) / 2  # posição média do grupo de empate, base 0
        for key, _ in ordered[i:j + 1]:
            ranks[key] = 100 * mid_rank / (len(ordered) - 1)
        i = j + 1
    return ranks


def category_percentile(area_percentile: float, population_percentile: float) -> float:
    """Percentil da categoria no distrito (``P_k,d``).

    A especificação mede a oferta por quilômetro quadrado e por dez mil
    habitantes; as duas posições percentis pesam igualmente.
    """
    return (area_percentile + population_percentile) / 2
