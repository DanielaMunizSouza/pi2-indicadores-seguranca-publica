"""Testes da rota /api/diagnostico: parâmetros e tradução de erros em HTTP.

O serviço de diagnóstico é substituído por um dublê; nada acessa banco ou rede.
"""

import pytest
from fastapi.testclient import TestClient

import backend.app as api
from geohabita.application.cep_lookup import CepNotFoundError, ProviderError
from geohabita.application.diagnosis import LocationNotFoundError
from geohabita.domain.cep import InvalidCepError


class FakeService:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def diagnose_cep(self, cep, pesos):
        self.calls.append(("cep", cep, pesos))
        if self.error:
            raise self.error
        return {"ok": "cep"}

    def diagnose_point(self, lat, lon, pesos):
        self.calls.append(("ponto", lat, lon, pesos))
        if self.error:
            raise self.error
        return {"ok": "ponto"}


@pytest.fixture
def client(monkeypatch):
    def make(error=None):
        fake = FakeService(error)
        monkeypatch.setattr(api, "diagnosis_service", fake)
        api.rate_limiter._requests.clear()
        return TestClient(api.app), fake
    return make


def test_cep_request_passes_default_weights(client):
    c, fake = client()
    assert c.get("/api/diagnostico", params={"cep": "01001000"}).json() == {"ok": "cep"}
    assert fake.calls[0][2] == {k: 1 for k in fake.calls[0][2]} and len(fake.calls[0][2]) == 6


def test_point_request_with_custom_weight(client):
    c, fake = client()
    r = c.get("/api/diagnostico", params={"lat": -23.55, "lon": -46.63, "peso_mobilidade": 5})
    assert r.status_code == 200
    assert fake.calls[0][3]["mobilidade"] == 5


@pytest.mark.parametrize("params", [{}, {"lat": -23.5}, {"cep": "01001000", "lat": -23.5, "lon": -46.6}])
def test_requires_either_cep_or_both_coordinates(client, params):
    c, _ = client()
    assert c.get("/api/diagnostico", params=params).status_code == 400


@pytest.mark.parametrize("peso", [6, -1, 1.5])
def test_weight_out_of_range_is_rejected(client, peso):
    c, _ = client()
    r = c.get("/api/diagnostico", params={"cep": "01001000", "peso_conectividade": peso})
    assert r.status_code == 422


@pytest.mark.parametrize(("error", "status"), [
    (InvalidCepError("O CEP deve ter 8 dígitos"), 400),
    (ValueError("Ao menos uma categoria precisa de peso maior que zero."), 400),
    (CepNotFoundError("CEP não encontrado"), 404),
    (LocationNotFoundError("sem coordenadas"), 422),
    (ProviderError("fora do ar"), 503),
])
def test_errors_map_to_http_status(client, error, status):
    c, _ = client(error)
    assert c.get("/api/diagnostico", params={"cep": "01001000"}).status_code == status
