"""Testes do Índice de Proximidade Local (equação do IPL; RF24, RN16).

O caso CT21 da especificação usa notas de categoria 100, 50, 0, 80, 60 e 40
com pesos iguais, resultando em IPL igual a 55.
"""

import pytest

from geohabita.domain.proximity import local_proximity_index


def test_ipl_is_weighted_mean_of_category_notes():
    notes = [100, 50, 0, 80, 60, 40]
    weights = [1, 1, 1, 1, 1, 1]
    assert local_proximity_index(notes, weights) == pytest.approx(55)


def test_ipl_reflects_adjusted_weights():
    assert local_proximity_index([100, 0], [1, 1]) == pytest.approx(50)
    assert local_proximity_index([100, 0], [3, 1]) == pytest.approx(75)


def test_ipl_is_undefined_without_weights():
    with pytest.raises(ValueError):
        local_proximity_index([100, 50], [0, 0])


def test_ipl_requires_one_weight_per_category():
    with pytest.raises(ValueError):
        local_proximity_index([100, 50], [1])
