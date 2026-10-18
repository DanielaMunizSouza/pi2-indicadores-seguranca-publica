"""Testes do Quadro de limiares de distância (RN13).

Os valores conferem os limiares iniciais ``a_j`` e ``b_j`` do Quadro da
especificação para os tipos de equipamento usados pelos demais testes.
"""

import pytest

from geohabita.domain.thresholds import CATEGORIES, EQUIPMENT_THRESHOLDS


def test_model_has_six_categories():
    assert len(CATEGORIES) == 6


@pytest.mark.parametrize(
    ("slug", "ideal_m", "max_m"),
    [
        ("praca", 400, 1200),
        ("parque_area_verde", 400, 1200),
        ("biblioteca_centro_cultural", 800, 2000),
        ("ceu_equipamento_esportivo", 800, 2000),
        ("ponto_onibus", 300, 800),
        ("estacao_metro_trem", 800, 2000),
        ("ciclovia", 800, 2000),
        ("feira_mercado_municipal", 800, 1500),
        ("unidade_basica_saude", 800, 2000),
        ("escola_publica", 800, 2000),
        ("wifi_publico", 400, 1200),
    ],
)
def test_thresholds_match_specification(slug, ideal_m, max_m):
    threshold = EQUIPMENT_THRESHOLDS[slug]
    assert (threshold.ideal_m, threshold.max_m) == (ideal_m, max_m)


def test_ideal_distance_is_never_greater_than_maximum():
    for threshold in EQUIPMENT_THRESHOLDS.values():
        assert threshold.ideal_m < threshold.max_m
