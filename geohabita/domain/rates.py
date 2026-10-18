"""Indicadores oficiais de ocorrências.

Cobre a equação da taxa anualizada por cem mil habitantes, em janela móvel
trienal (RN08), e a regra de comparabilidade mínima (RN09; RF10). Os dados
são contextualizados com a média municipal e advertência de subnotificação,
mas nunca fundidos com os indicadores de infraestrutura (RN07, RNF18).
"""

from __future__ import annotations

POPULATION_BASE = 100_000
DEFAULT_WINDOW_YEARS = 3
MIN_OCCURRENCES_FOR_COMPARISON = 30
INSUFFICIENT_DATA_MESSAGE = "número insuficiente para comparação"


def annual_rate_per_100k(
    count: int, population: int, years: int = DEFAULT_WINDOW_YEARS
) -> float:
    """Taxa anualizada por cem mil habitantes (equação da taxa; RN08).

    Levanta ``ValueError`` quando a população ou a janela de anos não são
    positivas, casos em que a taxa não está definida.
    """
    raise NotImplementedError


def is_comparable(
    count: int, minimum: int = MIN_OCCURRENCES_FOR_COMPARISON
) -> bool:
    """Indica se o distrito tem ocorrências suficientes para comparação (RN09).

    Naturezas com menos de 30 ocorrências na janela são exibidas como
    "número insuficiente para comparação", sem taxa nem tendência.
    """
    raise NotImplementedError
