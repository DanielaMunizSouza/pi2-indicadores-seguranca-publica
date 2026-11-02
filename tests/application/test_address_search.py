"""Busca por endereço e busca reversa do CEP (RF03; RN02, RN04).

ViaCEP e Nominatim são substituídos por dublês.
"""

from datetime import datetime, timedelta

import pytest

from geohabita.application.address_search import NOT_FOUND_MESSAGE, AddressSearch, StreetCep
from geohabita.application.cep_lookup import ProviderError
from geohabita.domain.address import InvalidAddressError

PAULISTA = [
    StreetCep("01310100", "Avenida Paulista", "de 1 a 610 - lado par", "Bela Vista"),
    StreetCep("01311200", "Avenida Paulista", "de 1047 a 1865 - lado ímpar", "Bela Vista"),
    StreetCep("01310200", "Avenida Paulista", "de 612 a 1510 - lado par", "Bela Vista"),
    StreetCep("08190461", "Viela Paulista", "", "Vila Itaim"),
]
PONTO = {"logradouro": "Rua Sem CEP", "numero": "10", "bairro": "Sé", "cep": None,
         "latitude": -23.55, "longitude": -46.63, "rotulo": "Rua Sem CEP, 10"}


def busca(ceps=PAULISTA, pontos=None, **kw):
    chamadas = {"viacep": [], "osm": []}

    def por_rua(rua):
        chamadas["viacep"].append(rua)
        if isinstance(ceps, Exception):
            raise ceps
        return list(ceps)

    def livre(texto):
        chamadas["osm"].append(texto)
        return pontos
    return AddressSearch(por_rua, livre, **kw), chamadas


def test_number_picks_the_cep_of_its_stretch():
    s, _ = busca()
    r = s.search("Avenida Paulista", "1300")
    assert r["fonte"] == "viacep"
    assert r["candidatos"][r["sugerido"]]["cep"] == "01310200"
    # Os trechos que não incluem o número vão para o fim da lista.
    assert [c["corresponde_numero"] for c in r["candidatos"]] == [True, None, False, False]


def test_without_number_several_streets_need_a_choice():
    s, _ = busca()
    r = s.search("Paulista")
    assert r["sugerido"] is None and len(r["candidatos"]) == 4


def test_single_cep_street_is_suggested_even_without_number():
    s, _ = busca(ceps=PAULISTA[3:])
    assert busca(ceps=PAULISTA[3:])[0].search("Viela Paulista")["sugerido"] == 0
    assert s.search("Viela Paulista", "15")["sugerido"] == 0  # sem trecho no complemento, serve


def test_viacep_without_results_falls_back_to_openstreetmap():
    s, chamadas = busca(ceps=[], pontos=[PONTO])
    r = s.search("Rua Sem CEP", "10")
    assert r["fonte"] == "openstreetmap" and r["sugerido"] == 0
    assert r["candidatos"][0]["latitude"] == -23.55 and r["candidatos"][0]["corresponde_numero"] is True
    assert chamadas["osm"] == ["Rua Sem CEP 10"]


def test_viacep_failure_falls_back_and_is_not_cached():
    cache = {}
    s, _ = busca(ceps=ProviderError("fora do ar"), pontos=[], cache=cache)
    r = s.search("Avenida Paulista")
    assert r["candidatos"] == [] and r["mensagem"] == NOT_FOUND_MESSAGE
    assert cache == {}


def test_street_ceps_are_cached_for_thirty_days():
    agora = [datetime(2026, 11, 1)]
    s, chamadas = busca(clock=lambda: agora[0])
    s.search("Avenida Paulista", "10")
    agora[0] += timedelta(days=30)
    s.search("avenida paulista", "1300")
    assert len(chamadas["viacep"]) == 1
    agora[0] += timedelta(days=1)
    s.search("Avenida Paulista")
    assert len(chamadas["viacep"]) == 2


@pytest.mark.parametrize(("rua", "numero"), [("Av", None), ("Avenida Paulista", "12A")])
def test_invalid_input_is_rejected_before_any_call(rua, numero):
    s, chamadas = busca()
    with pytest.raises(InvalidAddressError):
        s.search(rua, numero)
    assert chamadas == {"viacep": [], "osm": []}


PREDIOS = [StreetCep("01310915", "Avenida Paulista", "1294", "Bela Vista", "Edifício Eluma"),
           StreetCep("01311940", "Avenida Paulista", "2073", "Bela Vista", "Conjunto Nacional")]


def test_building_cep_matches_only_its_own_number():
    s, chamadas = busca(ceps=PAULISTA[:3] + PREDIOS)
    r = s.search("Avenida Paulista", "2073")
    assert r["candidatos"][r["sugerido"]]["cep"] == "01311940"
    assert r["candidatos"][r["sugerido"]]["predio"] == "Conjunto Nacional"
    assert chamadas["osm"] == []


def test_building_ceps_are_hidden_without_number():
    s, _ = busca(ceps=PAULISTA[:3] + PREDIOS)
    r = s.search("Avenida Paulista")
    assert {c["cep"] for c in r["candidatos"]} == {"01310100", "01311200", "01310200"}
    assert r["mensagem"] is not None  # pede o número para escolher o trecho


def test_missing_stretch_is_completed_with_the_openstreetmap_cep():
    # O ViaCEP corta em 50 CEPs: o trecho do 1578 (par, acima de 1512) não veio.
    masp = {**PONTO, "logradouro": "Avenida Paulista", "numero": "1578", "cep": "01310200"}
    s, chamadas = busca(ceps=PAULISTA[:2] + PREDIOS, pontos=[masp])
    r = s.search("Avenida Paulista", "1578")
    escolhido = r["candidatos"][r["sugerido"]]
    assert escolhido["cep"] == "01310200" and escolhido["fonte"] == "openstreetmap"
    assert chamadas["osm"] == ["Avenida Paulista 1578"]
