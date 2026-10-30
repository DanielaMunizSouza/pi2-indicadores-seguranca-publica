"""Testes da conferência de logradouro usada na reserva de geocodificação.

Em parte dos registros da SSP o CEP não é o do local do fato (ex.: CEP da Mooca
em ocorrências de Pinheiros); só contam os registros na mesma rua do CEP.
"""

import pytest

from geohabita.infrastructure.postgis import same_street, street_core


@pytest.mark.parametrize(("viacep", "core"), [
    ("Avenida Nova Arcádia", "NOVA ARCADIA"),
    ("Rua Luís Antônio dos Santos", "LUIS ANTONIO DOS SANTOS"),
    ("Praça da Sé", "SE"),
    ("Avenida Brigadeiro Faria Lima", "BRIGADEIRO FARIA LIMA"),
])
def test_street_core_drops_type_and_accents(viacep, core):
    assert street_core(viacep) == core


@pytest.mark.parametrize(("viacep", "ssp", "esperado"), [
    ("Avenida Nova Arcádia", "AVENIDA NOVA ARCADIA", True),
    ("Avenida Nova Arcádia", "AV NOVA ARCÁDIA", True),
    ("Rua Joá", "RUA GIRASSOL", False),
    ("Rua Joá", "AVENIDA EUSÉBIO MATOSO", False),
    ("Rua Joá", "RUA JOAQUIM NABUCO", False),  # o nome tem de bater por palavras inteiras
    ("Rua Joá", None, False),
    ("", "RUA JOA", False),
])
def test_same_street(viacep, ssp, esperado):
    assert same_street(viacep, ssp) is esperado
