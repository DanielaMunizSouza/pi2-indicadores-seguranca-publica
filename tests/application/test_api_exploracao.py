"""Rotas da exploração de ocorrências: validação de filtros e taxa por habitante (RNF18).

O repositório PostGIS é substituído por um dublê; nada acessa o banco.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

import backend.app as api
from geohabita.infrastructure.database import DatabaseUnavailable


class FakeRepository:
    def __init__(self, error=None):
        self.error = error
        self.filters = []

    def district_counts(self, f):
        self.filters.append(f)
        if self.error:
            raise self.error
        return [{"codigo": "1", "distrito": "A", "regiao": "Centro", "populacao": 50_000, "registros": 100},
                {"codigo": "2", "distrito": "B", "regiao": "Sul", "populacao": None, "registros": 7}]

    def cep_main_district(self, cep):
        return {"codigo": "2", "distrito": "B"}


@pytest.fixture
def client(monkeypatch):
    def make(error=None):
        fake = FakeRepository(error)
        monkeypatch.setattr(api, "occurrence_repository", fake)
        api.rate_limiter._requests.clear()
        return TestClient(api.app), fake
    return make


def test_areas_carry_population_and_rate_per_100k(client):
    c, _ = client()
    areas = c.get("/api/areas").json()["areas"]
    assert areas[0]["taxa_100k"] == 200.0 and areas[0]["populacao"] == 50_000
    assert areas[1]["taxa_100k"] is None


def test_cep_filter_is_normalized_and_gathers_records_in_one_district(client):
    c, fake = client()
    body = c.get("/api/areas", params={"cep": "01001-000"}).json()
    assert fake.filters[0].cep == "01001000"
    assert body["cep_distrito"]["codigo"] == "2"
    assert [a["registros"] for a in body["areas"]] == [0, 107]


@pytest.mark.parametrize("params", [
    {"start": "2025-02-01", "end": "2025-01-01"}, {"category": "inexistente"}, {"cep": "123"}])
def test_invalid_filters_are_rejected(client, params):
    c, _ = client()
    assert c.get("/api/areas", params=params).status_code == 400


def test_default_period_reaches_the_repository(client):
    c, fake = client()
    c.get("/api/areas")
    assert (fake.filters[0].start, fake.filters[0].end) == (date(2025, 1, 1), date(2026, 12, 31))


def test_unavailable_database_is_reported_as_503(client):
    c, _ = client(DatabaseUnavailable("recusado"))
    assert c.get("/api/areas").status_code == 503
