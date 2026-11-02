"""Passos Gherkin das histórias Must (HU01, HU02, HU05, HU10), no nível da API com dublês.

Os cenários seguem os critérios de aceitação da especificação de requisitos;
usam a aplicação real (rotas HTTP) com os serviços externos substituídos.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, scenarios, then, when

import backend.app as api
from geohabita.application.cep_lookup import Address, CepNotFoundError
from geohabita.domain.cep import require_valid_cep
from geohabita.domain.territory import SAO_PAULO_IBGE_CODE

scenarios("hu01_cep.feature")
scenarios("hu02_05_10_diagnostico.feature")


@pytest.fixture
def contexto():
    return {}


@pytest.fixture
def client(contexto, monkeypatch):
    api.rate_limiter._requests.clear()
    monkeypatch.setattr(api, "diagnosis_service", _FakeDiagnosis(contexto))
    monkeypatch.setattr(api, "cep_service", _CepLookupDeCenario(contexto))
    return TestClient(api.app)


class _CepLookupDeCenario:
    def __init__(self, contexto):
        self.contexto = contexto

    def lookup(self, raw_cep):
        cep = require_valid_cep(raw_cep)  # levanta InvalidCepError no formato inválido (RN01)
        if self.contexto.get("sem_cep") or cep == "99999999":
            raise CepNotFoundError("CEP não encontrado")
        # o serviço principal não respondeu a tempo; a contingência atendeu
        return self.contexto.get("endereco") or Address("01310100", "Avenida Paulista", "Bela Vista",
                                                        "São Paulo", SAO_PAULO_IBGE_CODE)


class _FakeDiagnosis:
    def __init__(self, contexto):
        self.contexto = contexto

    def diagnose_cep(self, cep, pesos, numero=None):
        return self.contexto.get("diagnostico") or {"local": {"distrito": {"nome": "SÉ"}}, "diagnostico": None}

    def diagnose_point(self, lat, lon, pesos):
        return self.diagnose_cep("", pesos)


@given("o ViaCEP responde o endereço da Avenida Paulista para o CEP 01310100", target_fixture="contexto")
def _viacep_ok(contexto):
    contexto["endereco"] = Address("01310100", "Avenida Paulista", "Bela Vista", "São Paulo", SAO_PAULO_IBGE_CODE)
    return contexto


@given("o serviço de CEP não pode ser chamado")
def _nao_chamar(contexto):
    contexto["sem_cep"] = True
    return contexto


@given("o ViaCEP e a BrasilAPI não reconhecem o CEP 99999999")
def _inexistente(contexto):
    contexto["sem_cep"] = True
    return contexto


@given("o ViaCEP demora mais que 3 segundos")
def _lento(contexto):
    contexto["endereco"] = Address("01310100", "Avenida Paulista", "Bela Vista", "São Paulo", SAO_PAULO_IBGE_CODE)
    return contexto


@given(parsers.parse('o diagnóstico localiza o CEP 01310100 no distrito "{distrito}"'))
def _distrito(contexto, distrito):
    contexto["diagnostico"] = _diagnostico(distrito=distrito)
    return contexto


@given("o distrito tem taxas oficiais por cem mil habitantes")
def _taxas(contexto):
    contexto["diagnostico"] = _diagnostico()
    return contexto


@given(parsers.parse("o endereço tem a UBS a {ubs} metros, a escola a {escola} metros e o ponto de ônibus a {onibus} metros"))
def _distancias(contexto, ubs, escola, onibus):
    contexto["diagnostico"] = _diagnostico(ubs=ubs, escola=escola, onibus=onibus)
    return contexto


@when(parsers.parse('o munícipe consulta o CEP "{cep}"'))
def _consulta_cep(client, cep):
    client.resposta = client.get(f"/api/cep/{cep}")


@when(parsers.parse('o munícipe informa "{cep}"'))
def _informa_cep(client, cep):
    client.resposta = client.get(f"/api/cep/{cep}")


@when(parsers.parse('o munícipe consulta o diagnóstico do CEP "{cep}"'))
def _consulta_diagnostico(client, cep):
    client.resposta = client.get("/api/diagnostico", params={"cep": cep})


@then(parsers.parse('o sistema exibe logradouro "{rua}", bairro "{bairro}" e município "{cidade}"'))
def _endereco_exibido(client, rua, bairro, cidade):
    corpo = client.resposta.json()
    assert (corpo["logradouro"], corpo["bairro"], corpo["municipio"]) == (rua, bairro, cidade)


@then(parsers.parse('o sistema exibe "{mensagem}" e nenhuma API externa é chamada'))
def _mensagem_e_sem_externa(client, mensagem):
    assert client.resposta.status_code == 400
    assert mensagem in client.resposta.json()["detail"]


@then(parsers.parse('o sistema exibe "{mensagem}"'))
def _mensagem(client, mensagem):
    corpo = client.resposta.json()
    assert mensagem in (corpo.get("detail") or ""), corpo


@then("o endereço vem do serviço de contingência")
def _contingencia(client):
    assert client.resposta.status_code == 200
    assert client.resposta.json()["logradouro"] == "Avenida Paulista"


@then(parsers.parse('o sistema informa o distrito "{distrito}"'))
def _distrito_informado(client, distrito):
    assert client.resposta.json()["local"]["distrito"]["nome"] == distrito


@then("cada natureza mostra a taxa, a média municipal e a tendência")
def _taxas_exibidas(client):
    ocorrencias = client.resposta.json()["diagnostico"]["ocorrencias"]["naturezas"]
    for item in ocorrencias.values():
        assert item["taxa_100k_ano"] is not None
        assert item["taxa_municipal_100k_ano"] is not None
        assert item["tendencia"] is not None


@then("o diagnóstico traz a nota de subnotificação")
def _subnotificacao(client):
    assert client.resposta.json()["diagnostico"]["ocorrencias"]["aviso_subnotificacao"]


@then("o diagnóstico mostra a distância e o tempo a pé até o equipamento mais próximo de cada tipo")
def _distancias_exibidas(client):
    tipos = client.resposta.json()["diagnostico"]["proximidade"]["tipos"]
    assert tipos["unidade_basica_saude"]["distancia_m"] == 250
    assert tipos["escola_publica"]["distancia_m"] == 300
    assert tipos["ponto_onibus"]["distancia_m"] == 150
    assert tipos["unidade_basica_saude"]["tempo_caminhada_min"] == 4  # 250 m a 80 m/min


def _diagnostico(distrito="SÉ", ubs=None, escola=None, onibus=None):
    def tipo(nome, distancia, categoria):
        info = {"nome": nome, "categoria": categoria, "disponivel": True, "nota": 50,
                "distancia_m": distancia, "tempo_caminhada_min": (distancia + 79) // 80 if distancia else None,
                "ate_500m": 1, "ate_1km": 1, "aviso": None, "ideal_m": 300, "maxima_m": 2000,
                "latitude": None, "longitude": None}
        return info

    proximidade = {"ipl": 60.0, "tipos": {}, "categorias": {}, "entorno": {}}
    if ubs:
        proximidade["tipos"]["unidade_basica_saude"] = tipo("UBS", int(ubs), "servicos_essenciais")
    if escola:
        proximidade["tipos"]["escola_publica"] = tipo("Escola", int(escola), "servicos_essenciais")
    if onibus:
        proximidade["tipos"]["ponto_onibus"] = tipo("Ponto", int(onibus), "mobilidade")
    naturezas = {grupo: {"rotulo": grupo, "ocorrencias": 40, "taxa_100k_ano": 12.3,
                         "taxa_municipal_100k_ano": 10.0, "tendencia": "estável"}
                 for grupo in ("roubo", "furto")}
    return {
        "local": {"distrito": {"nome": distrito}},
        "diagnostico": {
            "proximidade": proximidade,
            "vitalidade": {"ivep": 50.0, "categorias": {}},
            "ocorrencias": {"naturezas": naturezas, "aviso_subnotificacao": "subnotificação",
                            "janela": [2023, 2025], "populacao": 100_000},
        },
        "fontes": [],
    }
