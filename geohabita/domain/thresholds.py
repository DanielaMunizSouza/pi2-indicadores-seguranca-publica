"""Limiares de distância por tipo de equipamento.

Transcreve o Quadro "Limiares iniciais de distância por tipo de equipamento"
da especificação (RN13). A distância ideal ``a_j`` é aquela até a qual a nota
é máxima; a distância máxima ``b_j`` é aquela a partir da qual a nota é nula.
Os valores são parâmetros de configuração e podem ser revistos com base nos
testes com moradores, sem alteração de código.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DistanceThreshold:
    """Par de limiares ``a_j`` (ideal) e ``b_j`` (máxima), em metros."""

    ideal_m: int
    max_m: int


# Seis categorias de equipamentos do modelo de indicadores.
CATEGORIES: tuple[str, ...] = (
    "lazer_convivencia",
    "cultura_esporte",
    "mobilidade",
    "comercio_rua",
    "servicos_essenciais",
    "conectividade",
)


# Iluminação pública não entra neste quadro: ela é medida pela densidade de
# pontos no entorno (geohabita/domain/lighting.py), porque a distância até a
# luminária mais próxima não distinguiria um distrito de outro.

# Tipos medidos por densidade, que não têm par de limiares de distância.
DENSITY_TYPES: frozenset[str] = frozenset({"iluminacao_publica"})

# Todos os tipos do modelo de indicadores, na ordem de exibição: os medidos por
# densidade vêm antes dos de distância dentro da sua categoria.
EQUIPMENT_TYPES: dict[str, str] = {
    "praca": "lazer_convivencia",
    "parque_area_verde": "lazer_convivencia",
    "biblioteca_centro_cultural": "cultura_esporte",
    "ceu_equipamento_esportivo": "cultura_esporte",
    "ponto_onibus": "mobilidade",
    "estacao_metro_trem": "mobilidade",
    "ciclovia": "mobilidade",
    "feira_mercado_municipal": "comercio_rua",
    "unidade_basica_saude": "servicos_essenciais",
    "escola_publica": "servicos_essenciais",
    "iluminacao_publica": "conectividade",
    "wifi_publico": "conectividade",
}

# Limiares iniciais por tipo de equipamento medido por distância (Quadro de
# limiares; RN13).
EQUIPMENT_THRESHOLDS: dict[str, DistanceThreshold] = {
    "praca": DistanceThreshold(400, 1200),
    "parque_area_verde": DistanceThreshold(400, 1200),
    "biblioteca_centro_cultural": DistanceThreshold(800, 2000),
    "ceu_equipamento_esportivo": DistanceThreshold(800, 2000),
    "ponto_onibus": DistanceThreshold(300, 800),
    "estacao_metro_trem": DistanceThreshold(800, 2000),
    "ciclovia": DistanceThreshold(800, 2000),
    "feira_mercado_municipal": DistanceThreshold(800, 1500),
    "unidade_basica_saude": DistanceThreshold(800, 2000),
    "escola_publica": DistanceThreshold(800, 2000),
    "wifi_publico": DistanceThreshold(400, 1200),
}
