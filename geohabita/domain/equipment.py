"""Equipamentos públicos do entorno do endereço consultado.

Cobre a escolha do equipamento mais próximo de cada tipo (RN12; RF23), a
listagem dos equipamentos a até 500 metros e a até 1 quilômetro agrupados
pelas seis categorias (RF07) e a mensagem de tipo ausente (RN15). As
distâncias geodésicas são calculadas pelo banco e chegam já em metros.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

LISTING_RADII_M: tuple[int, ...] = (500, 1000)

# Categoria de cada tipo de equipamento do Quadro de limiares.
EQUIPMENT_CATEGORY: dict[str, str] = {
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
    "wifi_publico": "conectividade",
}


@dataclass(frozen=True)
class NearbyEquipment:
    """Equipamento encontrado no entorno, com distância em linha reta (RN12)."""

    type: str
    name: str
    distance_m: float


def nearest_by_type(items: Iterable[NearbyEquipment]) -> dict[str, NearbyEquipment]:
    """Equipamento mais próximo de cada tipo presente na lista (RN12)."""
    nearest: dict[str, NearbyEquipment] = {}
    for item in items:
        current = nearest.get(item.type)
        if current is None or item.distance_m < current.distance_m:
            nearest[item.type] = item
    return nearest


def within_radius(
    items: Iterable[NearbyEquipment], radius_m: float
) -> dict[str, list[NearbyEquipment]]:
    """Equipamentos a até ``radius_m`` metros, agrupados por categoria (RF07).

    Cada grupo é ordenado da menor para a maior distância.
    """
    groups: dict[str, list[NearbyEquipment]] = {}
    for item in sorted(items, key=lambda e: e.distance_m):
        if item.distance_m <= radius_m:
            groups.setdefault(EQUIPMENT_CATEGORY[item.type], []).append(item)
    return groups


def missing_type_message(max_m: int) -> str:
    """Mensagem para tipo sem equipamento a menos de ``max_m`` metros (RN15)."""
    return f"nenhum equipamento deste tipo a menos de {max_m} metros"
