"""Vocabulário das bases da SSP-SP usado na exploração das ocorrências."""

from __future__ import annotations

# Formas do município gravadas nas bases; "São Paulo" é a usada pelo importador.
SAO_PAULO_NAMES: tuple[str, ...] = ("São Paulo", "S.PAULO", "SAO PAULO", "SÃO PAULO")

# categoria_dado -> rótulo exibido na interface.
DATASET_LABELS: dict[str, str] = {
    "objetos": "Objetos",
    "celulares_subtraidos": "Celulares subtraídos",
    "apreensao_entorpecente": "Apreensão de entorpecentes",
    "entorpecentes_gramas": "Entorpecentes (gramas)",
    "veiculos": "Veículos subtraídos",
    "veiculos_recuperados": "Veículos recuperados",
    "criminal": "Dados criminais (SPDados)",
    "mdip": "Mortes decorrentes de intervenção policial",
    "prisoes": "Prisões efetuadas",
    "presos_apreendidos": "Presos e apreendidos",
    "armas_apreendidas": "Armas de fogo apreendidas",
    "flagrantes": "Flagrantes lavrados",
    "apreensao_eca": "Apreensões (art. 173 ECA)",
    "outros": "Outros",
}


def rate_per_100k(count: int, population: int | None) -> float | None:
    """Registros por cem mil habitantes no período, ou ``None`` sem população."""
    if not population:
        return None
    return count / population * 100_000
