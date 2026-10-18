"""Índice de Vitalidade do Espaço Público (IVEP).

Cobre a equação do IVEP: média ponderada dos percentis das seis categorias
de equipamentos entre os 96 distritos (RN06; RF08, RF09). Os pesos são
inteiros de 0 a 5, com padrão igual a 1, ajustáveis pelo usuário.
"""

from __future__ import annotations

from collections.abc import Sequence

DEFAULT_WEIGHT = 1
MIN_WEIGHT = 0
MAX_WEIGHT = 5


def is_valid_weight(weight: float) -> bool:
    """Indica se o peso é um inteiro entre 0 e 5 (RN06)."""
    raise NotImplementedError


def public_space_vitality_index(
    percentiles: Sequence[float], weights: Sequence[float]
) -> float:
    """IVEP do distrito: média ponderada dos percentis por categoria (RN06).

    Levanta ``ValueError`` quando as listas têm tamanhos diferentes ou quando
    a soma dos pesos é zero, casos em que o índice não está definido.
    """
    raise NotImplementedError
