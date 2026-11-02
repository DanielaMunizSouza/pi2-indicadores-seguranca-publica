"""Rotas sem cobertura anterior: /api/cep, /api/status, limite, geometria, mapa e resumo."""

import pytest
from fastapi.testclient import TestClient

import backend.app as api
from geohabita.application.cep_lookup import Address, CepNotFoundError, ProviderError
from geohabita.domain.cep import InvalidCepError


@pytest.fixture
def client(monkeypatch):
    api.rate_limiter._requests.clear()
    return TestClient(api.app)


# ---------- /api/cep (RF02, RF06; RN02, RN03) ----------

def _cep_dentro():
    return Address("01310100", "Avenida Paulista", "Bela Vista", "São Paulo", "3550308")


def test_api_cep_devolve_o_endereco_e_o_distrito(monkeypatch, client):
    monkeypatch.setattr(api.cep_service, "lookup", lambda cep: _cep_dentro())
    r = client.get("/api/cep/01310-100")
    assert r.status_code == 200
    assert r.json()["logradouro"] == "Avenida Paulista" and r.json()["dentro_sao_paulo"] is True
    assert r.json()["aviso"] is None


def test_api_cep_fora_de_sao_paulo_traz_o_aviso(monkeypatch, client):
    monkeypatch.setattr(api.cep_service, "lookup",
                        lambda cep: Address("07000000", "Rua X", "Centro", "Guarulhos", "3518800"))
    corpo = client.get("/api/cep/07000-000").json()
    assert corpo["dentro_sao_paulo"] is False
    assert "fora do município" in corpo["aviso"]


@pytest.mark.parametrize("cep", ["1234", "abcdefgh", "123456789"])
def test_api_cep_formato_invalido_e_400_sem_provedor(monkeypatch, client, cep):
    from geohabita.application.cep_lookup import CepLookup

    chamados = []
    def provedor(*a):
        chamados.append(a)
        return None

    monkeypatch.setattr(api, "cep_service", CepLookup(provedor, provedor))
    assert client.get(f"/api/cep/{cep}").status_code == 400
    assert chamados == []  # a validação acontece antes de qualquer chamada externa


def test_api_cep_inexistente_e_404(monkeypatch, client):
    monkeypatch.setattr(api.cep_service, "lookup",
                        lambda cep: (_ for _ in ()).throw(CepNotFoundError("CEP não encontrado")))
    r = client.get("/api/cep/99999-999")
    assert r.status_code == 404 and "CEP não encontrado" in r.json()["detail"]


def test_api_cep_servicos_indisponiveis_e_503(monkeypatch, client):
    monkeypatch.setattr(api.cep_service, "lookup", lambda cep: (_ for _ in ()).throw(ProviderError()))
    assert client.get("/api/cep/01310100").status_code == 503


# ---------- /api/status, limite, geometria, mapa, resumo ----------

class Repo:
    def status(self):
        return {"postgis": "3.5", "tem_registros": True}

    def district_boundary(self, codigo):
        return None if codigo == "XX" else {"type": "Feature", "properties": {"codigo": codigo}}

    def summary(self, filtro):
        return {"total": {"total": 1, "com_cep": 1, "com_coordenada": 1, "latitude": 0, "longitude": 0},
                "mensal": [], "categorias": []}

    def district_counts(self, filtro):
        return []

    def cep_main_district(self, cep):
        return None

    def map_cells(self, filtro, w, s, e, n):
        return []


def test_api_status_informa_o_postgis(monkeypatch, client):
    monkeypatch.setattr(api, "occurrence_repository", Repo())
    assert client.get("/api/status").json()["postgis"] == "3.5"


def test_limite_inexistente_e_404(monkeypatch, client):
    monkeypatch.setattr(api, "occurrence_repository", Repo())
    assert client.get("/api/distritos/XX/limite").status_code == 404


def test_mapa_com_area_invalida_e_400(monkeypatch, client):
    monkeypatch.setattr(api, "occurrence_repository", Repo())
    r = client.get("/api/map", params={"west": 10, "south": -24, "east": 0, "north": -23})
    assert r.status_code == 400


def test_resumo_com_cep_invalido_e_400(monkeypatch, client):
    monkeypatch.setattr(api, "occurrence_repository", Repo())
    assert client.get("/api/summary", params={"cep": "123"}).status_code == 400


def test_resumo_devolve_as_chaves_da_interface(monkeypatch, client):
    monkeypatch.setattr(api, "occurrence_repository", Repo())
    corpo = client.get("/api/summary", params={"start": "2025-01-01", "end": "2025-12-31"}).json()
    assert corpo["total"] == 1 and "periodo" in corpo


def test_geometria_ausente_e_503(monkeypatch, client, tmp_path):
    monkeypatch.setattr(api, "ROOT", tmp_path)  # sem data/reference/distritos_sp.geojson
    assert client.get("/api/areas/geometry").status_code == 503
