"""Rota /api/enderecos: busca por logradouro e número, com o CEP de cada trecho (RF03)."""

import pytest
from fastapi.testclient import TestClient

import backend.app as api
from geohabita.application.address_search import StreetCep

CEPS = [StreetCep("01310000", "Avenida Paulista", "até 610 - lado par", "Bela Vista"),
        StreetCep("01310200", "Avenida Paulista", "de 612 a 1510 - lado par", "Bela Vista")]


@pytest.fixture
def client(monkeypatch):
    def make(erro=None):
        chamadas = []

        def por_rua(rua):
            chamadas.append(rua)
            if erro:
                raise erro
            return CEPS

        # Cache em memória: os testes não podem ler nem escrever o cache persistente.
        monkeypatch.setattr(api.address_search, "by_street", por_rua)
        monkeypatch.setattr(api.address_search, "free_search", lambda texto: [])
        monkeypatch.setattr(api.address_search, "cache", {})
        api.rate_limiter._requests.clear()
        return TestClient(api.app), chamadas
    return make


def test_returns_the_cep_candidates(client):
    c, chamadas = client()
    body = c.get("/api/enderecos", params={"logradouro": "avenida paulista", "numero": "700"}).json()
    assert chamadas == ["avenida paulista"]
    assert [c["corresponde_numero"] for c in body["candidatos"]] == [True, False]
    assert body["sugerido"] == 0 and body["candidatos"][0]["cep"] == "01310200"


@pytest.mark.parametrize("params", [{"logradouro": "Av"}, {"logradouro": "Avenida Paulista", "numero": "12A"},
                                    {"logradouro": "   "}])
def test_invalid_input_is_400_without_calling_the_service(client, params):
    c, chamadas = client()
    assert c.get("/api/enderecos", params=params).status_code == 400
    assert chamadas == []


def test_missing_logradouro_parameter_is_422(client):
    c, _ = client()
    assert c.get("/api/enderecos").status_code == 422
