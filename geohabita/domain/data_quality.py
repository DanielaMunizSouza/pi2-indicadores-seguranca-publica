"""Validação das coordenadas importadas.

Cobre o descarte, na carga, de registros da SSP-SP com coordenadas nulas,
iguais a zero ou fora do município, e a contagem dos descartes no relatório
de validação (RN10; RF20). O teste exato de pertencimento ao município é
feito no banco geoespacial; aqui usa-se o retângulo envolvente como filtro.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

# Retângulo envolvente do município de São Paulo (graus decimais, WGS 84).
SAO_PAULO_BBOX = (-46.83, -24.01, -46.36, -23.36)  # oeste, sul, leste, norte

MISSING = "coordenada ausente"
ZERO = "coordenada zerada"
OUTSIDE = "fora do município"


def discard_reason(lat: float | None, lon: float | None) -> str | None:
    """Motivo do descarte da coordenada, ou ``None`` se ela for utilizável."""
    raise NotImplementedError


@dataclass
class ValidationReport:
    """Resumo de uma carga: registros aceitos e descartados por motivo."""

    accepted: int = 0
    discarded: Counter = field(default_factory=Counter)

    @property
    def total_discarded(self) -> int:
        raise NotImplementedError


def validate_coordinates(
    rows: Iterable[tuple[float | None, float | None]],
) -> ValidationReport:
    """Classifica cada par (latitude, longitude) e devolve o relatório (RN10)."""
    raise NotImplementedError
