"""Validade de dados em cache e atualidade dos indicadores.

Cobre a permanência de resultados de CEP e geocodificação em cache por até
30 dias (RN04) e o aviso "dado desatualizado" para indicadores cuja data de
referência supere 24 meses (RN11; RF12).
"""

from __future__ import annotations

from datetime import date, datetime

CACHE_MAX_AGE_DAYS = 30
OUTDATED_AFTER_MONTHS = 24
OUTDATED_MESSAGE = "dado desatualizado"


def is_cache_fresh(
    cached_at: datetime, now: datetime, max_age_days: int = CACHE_MAX_AGE_DAYS
) -> bool:
    """Indica se um resultado em cache ainda pode ser usado (RN04).

    O resultado é válido enquanto sua idade for de até ``max_age_days`` dias,
    inclusive.
    """
    raise NotImplementedError


def is_outdated(
    reference_date: date, today: date, max_months: int = OUTDATED_AFTER_MONTHS
) -> bool:
    """Indica se o indicador deve receber o aviso "dado desatualizado" (RN11).

    A idade é contada em meses de calendário; um indicador com exatamente
    ``max_months`` meses ainda não é considerado desatualizado.
    """
    raise NotImplementedError
