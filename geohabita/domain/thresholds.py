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


# Limiares iniciais por tipo de equipamento (Quadro de limiares; RN13).
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
