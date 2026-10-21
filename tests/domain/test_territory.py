"""Testes da delimitação territorial (RF06, RN05).

O caso CT06 da especificação usa um CEP de município vizinho; no nível
unitário, verifica-se a decisão a partir do código IBGE devolvido pelo serviço.
"""

import pytest

from geohabita.domain.territory import (
    APPROXIMATE_LOCATION_NOTICE,
    OUT_OF_CITY_MESSAGE,
    SAO_PAULO_IBGE_CODE,
    is_sao_paulo,
)


def test_sao_paulo_ibge_code():
    assert SAO_PAULO_IBGE_CODE == "3550308"


def test_sao_paulo_code_is_inside_city():
    assert is_sao_paulo("3550308") is True


@pytest.mark.parametrize(
    "ibge_code",
    [
        "3548708",  # São Bernardo do Campo (CT06)
        "3518800",  # Guarulhos
        "3534401",  # Osasco
    ],
)
def test_neighbouring_cities_are_outside(ibge_code):
    assert is_sao_paulo(ibge_code) is False


@pytest.mark.parametrize("ibge_code", [None, ""])
def test_missing_code_is_not_assumed_inside(ibge_code):
    assert is_sao_paulo(ibge_code) is False


def test_out_of_city_message_mentions_sao_paulo():
    assert "fora do município de São Paulo" in OUT_OF_CITY_MESSAGE


def test_approximate_location_notice_mentions_district():
    # RN05: a coordenada do CEP identifica o distrito, não o imóvel
    assert "distrito" in APPROXIMATE_LOCATION_NOTICE
    assert "aproximada" in APPROXIMATE_LOCATION_NOTICE
