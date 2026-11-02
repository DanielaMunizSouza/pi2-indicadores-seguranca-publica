"""Adaptadores HTTP de CEP (ViaCEP e BrasilAPI): parse e tradução de falhas (RN02, RN03).

Os testes trocam ``_get_json``, então nunca há rede; verifica-se o que cada
adaptador devolve diante de cada resposta e erro reais.
"""

from urllib.error import HTTPError, URLError

import pytest

from geohabita.application.cep_lookup import Address, ProviderError
from geohabita.domain.territory import SAO_PAULO_IBGE_CODE
from geohabita.infrastructure import cep_providers as cp


def viacep_ok(dados):
    return Address(cep="01310100", street="Avenida Paulista", neighbourhood="Bela Vista",
                   city="São Paulo", ibge_code=SAO_PAULO_IBGE_CODE, **dados)


@pytest.mark.parametrize("resposta", [
    None,                                # HTTP 404/400
    {"erro": True},                      # CEP inexistente
    {},
])
def test_viacep_nao_encontrado_devolve_none(monkeypatch, resposta):
    monkeypatch.setattr(cp, "_get_json", lambda url, t: resposta)
    assert cp.viacep("01310100", 3.0) is None


def test_viacep_parseia_o_endereco_e_o_ibge(monkeypatch):
    capturado = {}

    def _get_json(url, t):
        capturado["url"] = url
        return {"cep": "01310-100", "logradouro": "Avenida Paulista", "bairro": "Bela Vista",
                "localidade": "São Paulo", "ibge": "3550308"}

    monkeypatch.setattr(cp, "_get_json", _get_json)
    endereco = cp.viacep("01310100", 3.0)
    assert capturado["url"] == cp.VIACEP_URL.format(cep="01310100")
    assert endereco == Address("01310100", "Avenida Paulista", "Bela Vista", "São Paulo", "3550308")


@pytest.mark.parametrize("erro", [
    HTTPError("http://x", 500, "erro", None, None),
    URLError("recusada"),
    TimeoutError(),
])
def test_falha_de_rede_vira_provider_error(monkeypatch, erro):
    def urlopen(*a, **k):
        raise erro

    monkeypatch.setattr(cp, "urlopen", urlopen)
    with pytest.raises(ProviderError):
        cp.viacep("01310100", 3.0)


def test_http_400_e_404_devolvem_none_sem_falhar(monkeypatch):
    for codigo in (400, 404):
        def urlopen(*a, **k):
            raise HTTPError("http://x", codigo, "não achado", None, None)
        monkeypatch.setattr(cp, "urlopen", urlopen)
        assert cp.viacep("01310100", 3.0) is None


@pytest.mark.parametrize("dados, ibge, cidade", [
    ({"city": "São Paulo", "state": "SP"}, SAO_PAULO_IBGE_CODE, "São Paulo"),
    ({"city": "Guarulhos", "state": "SP"}, "", "Guarulhos"),
])
def test_brasilapi_deduz_o_ibge_so_para_a_capital(dados, ibge, cidade):
    endereco = cp.parse_brasilapi({"cep": "01310-100", "street": "Rua X", "neighborhood": "Centro", **dados})
    assert endereco.ibge_code == ibge and endereco.city == cidade


def test_brasilapi_coordenadas_ausentes_vazias_ou_centro_da_cidade_sao_descartadas():
    assert cp.parse_brasilapi({"cep": "01310100"}).latitude is None
    vazio = cp.parse_brasilapi({"cep": "01310100", "location": {"coordinates": {"latitude": "", "longitude": ""}}})
    assert vazio.latitude is None and vazio.longitude is None
    centro = cp.parse_brasilapi({"cep": "01310100", "location": {"coordinates": {
        "latitude": cp.SAO_PAULO_CITY_CENTRE[0], "longitude": cp.SAO_PAULO_CITY_CENTRE[1]}}})
    assert (centro.latitude, centro.longitude) == cp.SAO_PAULO_CITY_CENTRE


def test_brasilapi_parseia_coordenadas_validas():
    endereco = cp.parse_brasilapi({"cep": "01310-100", "location": {
        "coordinates": {"latitude": -23.6989, "longitude": -46.7561}}})
    assert endereco.latitude == -23.6989 and endereco.longitude == -46.7561


def test_brasilapi_coordinates_descarta_o_centro_da_cidade(monkeypatch):
    monkeypatch.setattr(cp, "brasilapi", lambda cep, t: cp.parse_brasilapi({"cep": cep, "location": {
        "coordinates": {"latitude": cp.SAO_PAULO_CITY_CENTRE[0], "longitude": cp.SAO_PAULO_CITY_CENTRE[1]}}}))
    assert cp.brasilapi_coordinates("01310100") is None


def test_viacep_street_filtra_fora_de_sao_paulo(monkeypatch):
    monkeypatch.setattr(cp, "_get_json", lambda url, t: [
        {"cep": "01310-100", "logradouro": "Avenida Paulista", "ibge": "3550308"},
        {"cep": "07000-000", "logradouro": "Rua de Guarulhos", "ibge": "3518800"},
    ])
    ceps = cp.viacep_street("paulista")
    assert [c.cep for c in ceps] == ["01310100"]
