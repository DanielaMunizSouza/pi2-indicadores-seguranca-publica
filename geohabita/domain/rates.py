"""Indicadores oficiais de ocorrências.

Cobre a equação da taxa anualizada por cem mil habitantes, em janela móvel
trienal (RN08), e a regra de comparabilidade mínima (RN09; RF10). Os dados
são contextualizados com a média municipal e advertência de subnotificação,
mas nunca fundidos com os indicadores de infraestrutura (RN07, RNF18).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from datetime import date

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
    if population <= 0:
        raise ValueError("A população deve ser positiva.")
    if years <= 0:
        raise ValueError("A janela deve ter ao menos um ano.")
    return count / (population * years) * POPULATION_BASE


def is_comparable(
    count: int, minimum: int = MIN_OCCURRENCES_FOR_COMPARISON
) -> bool:
    """Indica se o distrito tem ocorrências suficientes para comparação (RN09).

    Naturezas com menos de 30 ocorrências na janela são exibidas como
    "número insuficiente para comparação", sem taxa nem tendência.
    """
    return count >= minimum


def complete_years_window(
    today: date, years: int = DEFAULT_WINDOW_YEARS
) -> tuple[int, int]:
    """Primeiro e último ano completos da janela móvel (RN08).

    O ano corrente, ainda incompleto, nunca entra na janela: em qualquer data
    de 2026, a janela trienal vai de 2023 a 2025.
    """
    last_complete = today.year - 1
    return last_complete - years + 1, last_complete


SUBNOTIFICATION_NOTICE = (
    "Os registros policiais não incluem crimes não comunicados à polícia "
    "(subnotificação), que variam por tipo de crime e por região. "
    "Uma taxa menor não significa necessariamente menos crimes."
)

# Grupos de natureza exibidos (RF10). Cada grupo é uma taxa à parte e os grupos
# nunca são somados: o roubo de celular também aparece em "roubo".
OCCURRENCE_GROUPS: dict[str, str] = {
    "roubo": "Roubo (exceto de veículo)",
    "furto": "Furto",
    "roubo_celular": "Roubo de celular",
    "roubo_veiculo": "Roubo de veículo",
    "crimes_contra_vida": "Crimes contra a vida",
}
# Naturezas do SPDadosCriminais (comparadas sem acento e em maiúsculas).
_CRIMES_CONTRA_VIDA = {"HOMICIDIO DOLOSO", "LATROCINIO", "LESAO CORPORAL SEGUIDA DE MORTE"}
TREND_TOLERANCE = 0.10


def _normalized(text: str | None) -> str:
    text = unicodedata.normalize("NFD", (text or "").upper())
    return "".join(c for c in text if unicodedata.category(c) != "Mn").strip()


def occurrence_group(dataset: str, natureza: str | None, rubrica: str | None) -> str | None:
    """Grupo de natureza (RF10) de um registro, ou ``None`` se ele não entra nas taxas.

    ``dataset`` é a ``categoria_dado`` do registro: as naturezas vêm do
    SPDadosCriminais; o roubo de celular vem da rubrica da base de celulares,
    porque o SPDados não o separa.
    """
    if dataset == "celulares_subtraidos":
        return "roubo_celular" if _normalized(rubrica).startswith("ROUBO") else None
    if dataset != "criminal":
        return None
    nature = _normalized(natureza)
    if nature == "ROUBO DE VEICULO":
        return "roubo_veiculo"
    if nature.startswith("ROUBO"):
        return "roubo"
    if nature.startswith("FURTO"):
        return "furto"
    if nature in _CRIMES_CONTRA_VIDA:
        return "crimes_contra_vida"
    return None


def trend_direction(values: Sequence[float]) -> str:
    """Tendência da série anual: compara o último ano com o primeiro.

    Variação de ao menos 10% para cima é "alta", para baixo é "queda";
    abaixo disso, "estável".
    """
    if len(values) < 2:
        raise ValueError("A tendência precisa de ao menos dois anos.")
    first, last = values[0], values[-1]
    if first == 0:
        return "alta" if last > 0 else "estável"
    change = (last - first) / first
    if change >= TREND_TOLERANCE - 1e-12:
        return "alta"
    if change <= -TREND_TOLERANCE + 1e-12:
        return "queda"
    return "estável"
