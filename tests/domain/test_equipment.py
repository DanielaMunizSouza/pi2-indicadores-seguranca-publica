"""Testes dos equipamentos do entorno (RF07, RF23; RN12, RN15).

Os vetores reproduzem os casos CT07 (equipamentos a 300 m, 800 m e 1,5 km)
e CT17 (duas UBS a 250 m e a 600 m) da especificação.
"""

import pytest

from geohabita.domain.equipment import (
    EQUIPMENT_CATEGORY,
    LISTING_RADII_M,
    NearbyEquipment,
    missing_type_message,
    nearest_by_type,
    within_radius,
)
from geohabita.domain.thresholds import CATEGORIES, EQUIPMENT_THRESHOLDS


def test_every_threshold_type_has_a_known_category():
    assert set(EQUIPMENT_CATEGORY) == set(EQUIPMENT_THRESHOLDS)
    assert set(EQUIPMENT_CATEGORY.values()) <= set(CATEGORIES)


def test_every_category_has_at_least_one_type():
    assert set(EQUIPMENT_CATEGORY.values()) == set(CATEGORIES)


def test_listing_radii():
    assert LISTING_RADII_M == (500, 1000)


def test_ct17_nearest_ubs_is_chosen():
    ubs_far = NearbyEquipment("unidade_basica_saude", "UBS B", 600)
    ubs_near = NearbyEquipment("unidade_basica_saude", "UBS A", 250)
    nearest = nearest_by_type([ubs_far, ubs_near])
    assert nearest["unidade_basica_saude"] == ubs_near


def test_nearest_is_reported_per_type():
    items = [
        NearbyEquipment("praca", "Praça 1", 120),
        NearbyEquipment("ponto_onibus", "Ponto 1", 90),
        NearbyEquipment("praca", "Praça 2", 80),
    ]
    nearest = nearest_by_type(items)
    assert {t: e.name for t, e in nearest.items()} == {"praca": "Praça 2", "ponto_onibus": "Ponto 1"}


def test_types_without_equipment_are_absent():
    assert nearest_by_type([]) == {}


def test_ct07_only_items_within_radius_are_listed():
    items = [
        NearbyEquipment("praca", "Praça a 300 m", 300),
        NearbyEquipment("escola_publica", "Escola a 800 m", 800),
        NearbyEquipment("ponto_onibus", "Ponto a 1,5 km", 1500),
    ]
    within_1km = within_radius(items, 1000)
    names = [e.name for group in within_1km.values() for e in group]
    assert sorted(names) == ["Escola a 800 m", "Praça a 300 m"]
    assert set(within_1km) == {"lazer_convivencia", "servicos_essenciais"}


def test_radius_is_inclusive():
    item = NearbyEquipment("praca", "Praça", 500)
    assert within_radius([item], 500) == {"lazer_convivencia": [item]}


def test_groups_are_sorted_by_distance():
    far = NearbyEquipment("praca", "Longe", 450)
    near = NearbyEquipment("parque_area_verde", "Perto", 100)
    assert within_radius([far, near], 500)["lazer_convivencia"] == [near, far]


@pytest.mark.parametrize(
    ("max_m", "expected"),
    [
        (800, "nenhum equipamento deste tipo a menos de 800 metros"),
        (2000, "nenhum equipamento deste tipo a menos de 2000 metros"),
    ],
)
def test_missing_type_message(max_m, expected):
    # RN15 / CT20
    assert missing_type_message(max_m) == expected
