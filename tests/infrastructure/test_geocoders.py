"""Testes dos geocodificadores usados quando o ViaCEP não traz coordenadas (RF04; RN04).

A rede é substituída por dublês: nenhum teste acessa a BrasilAPI ou o Nominatim.
"""

from datetime import datetime, timedelta

from geohabita.application.cep_lookup import Address, ProviderError
from geohabita.infrastructure import cep_providers
from geohabita.infrastructure.nominatim import NominatimGeocoder

NOVA_ARCADIA = Address("04929000", "Avenida Nova Arcádia", "Alto da Riviera", "São Paulo", "3550308")


def brasilapi_devolvendo(lat, lon, monkeypatch):
    endereco = Address("04929000", "Avenida Nova Arcádia", "", "São Paulo", "3550308", lat, lon)
    monkeypatch.setattr(cep_providers, "brasilapi", lambda cep, timeout: endereco)


def test_brasilapi_coordinates_are_used_when_specific(monkeypatch):
    brasilapi_devolvendo(-23.6989, -46.7561, monkeypatch)
    assert cep_providers.brasilapi_coordinates("04929000") == (-23.6989, -46.7561)


def test_brasilapi_city_centre_placeholder_is_rejected(monkeypatch):
    # Sem a posição do CEP, a BrasilAPI devolve o centro da cidade, que cai na Sé.
    brasilapi_devolvendo(-23.5475, -46.63611, monkeypatch)
    assert cep_providers.brasilapi_coordinates("04929000") is None


def test_brasilapi_failure_yields_no_coordinates(monkeypatch):
    def falha(cep, timeout):
        raise ProviderError("fora do ar")
    monkeypatch.setattr(cep_providers, "brasilapi", falha)
    assert cep_providers.brasilapi_coordinates("04929000") is None


class Relogio:
    def __init__(self):
        self.agora = datetime(2026, 11, 1, 12, 0)
        self.monotonico = 0.0
        self.esperas = []

    def now(self):
        return self.agora

    def monotonic(self):
        return self.monotonico

    def sleep(self, segundos):
        self.esperas.append(segundos)
        self.monotonico += segundos


def geocoder(respostas, relogio=None):
    chamadas = []

    def buscar(params):
        chamadas.append(params)
        return respostas.pop(0) if respostas else []
    relogio = relogio or Relogio()
    g = NominatimGeocoder(fetch=buscar, clock=relogio.now, monotonic=relogio.monotonic, sleep=relogio.sleep)
    return g, chamadas, relogio


def test_nominatim_searches_street_and_city():
    g, chamadas, _ = geocoder([[{"lat": "-23.6985", "lon": "-46.7579"}]])
    assert g(NOVA_ARCADIA) == (-23.6985, -46.7579)
    assert chamadas[0]["street"] == "Avenida Nova Arcádia" and chamadas[0]["city"] == "São Paulo"


def test_nominatim_without_street_is_not_called():
    g, chamadas, _ = geocoder([])
    assert g(Address("01000000", "", "", "São Paulo", "3550308")) is None
    assert chamadas == []


def test_nominatim_result_is_cached_for_30_days():
    g, chamadas, relogio = geocoder([[{"lat": "-23.6", "lon": "-46.7"}], [{"lat": "-1", "lon": "-1"}]])
    g(NOVA_ARCADIA)
    relogio.agora += timedelta(days=29)
    assert g(NOVA_ARCADIA) == (-23.6, -46.7)
    assert len(chamadas) == 1
    relogio.agora += timedelta(days=2)
    assert g(NOVA_ARCADIA) == (-1.0, -1.0)


def test_nominatim_waits_one_second_between_requests():
    outro = Address("01310100", "Avenida Paulista", "", "São Paulo", "3550308")
    g, _, relogio = geocoder([[{"lat": "-23.6", "lon": "-46.7"}], [{"lat": "-23.5", "lon": "-46.6"}]])
    g(NOVA_ARCADIA)
    g(outro)
    assert relogio.esperas and abs(sum(relogio.esperas) - 1.0) < 1e-9


def test_nominatim_failure_or_empty_result_yields_none():
    def falha(params):
        raise OSError("rede")
    g = NominatimGeocoder(fetch=falha)
    assert g(NOVA_ARCADIA) is None
    g2, _, _ = geocoder([[]])
    assert g2(NOVA_ARCADIA) is None


def test_house_number_geocoder_accepts_only_the_same_number():
    paulista = Address("01310200", "Avenida Paulista", "", "São Paulo", "3550308", number="1578")
    museu = [{"lat": "-23.5615", "lon": "-46.6560", "address": {"house_number": "1578"}}]
    g = NominatimGeocoder(fetch=lambda p: museu, house_number=True)
    assert g(paulista) == (-23.5615, -46.656)

    so_a_rua = [{"lat": "-23.56", "lon": "-46.65", "address": {"road": "Avenida Paulista"}}]
    chamadas = []
    g2 = NominatimGeocoder(fetch=lambda p: chamadas.append(p) or so_a_rua, house_number=True)
    assert g2(paulista) is None
    assert chamadas[0]["street"] == "1578 Avenida Paulista"


def test_house_number_geocoder_skips_addresses_without_number():
    chamadas = []
    g = NominatimGeocoder(fetch=lambda p: chamadas.append(p) or [], house_number=True)
    assert g(NOVA_ARCADIA) is None and chamadas == []


def test_geocoders_sharing_a_client_share_the_one_second_interval():
    from geohabita.infrastructure.nominatim import NominatimClient
    relogio = Relogio()
    cliente = NominatimClient(fetch=lambda p: [], monotonic=relogio.monotonic, sleep=relogio.sleep)
    NominatimGeocoder(client=cliente)(NOVA_ARCADIA)
    NominatimGeocoder(client=cliente, house_number=True)(
        Address("01310200", "Avenida Paulista", "", "São Paulo", "3550308", number="1"))
    assert relogio.esperas == [1.0]


def test_free_search_keeps_only_full_ceps():
    from geohabita.infrastructure.nominatim import NominatimClient, free_search
    resposta = [{"lat": "-23.5", "lon": "-46.6", "display_name": "Rua A, 10",
                 "address": {"road": "Rua A", "house_number": "10", "suburb": "Sé", "postcode": "01001-000"}},
                {"lat": "-23.6", "lon": "-46.7", "display_name": "Rua B",
                 "address": {"road": "Rua B", "postcode": "01001"}}]
    pontos = free_search(NominatimClient(fetch=lambda p: resposta), "Rua A 10")
    assert [p["cep"] for p in pontos] == ["01001000", None]
    assert pontos[0]["numero"] == "10" and pontos[0]["bairro"] == "Sé"


def test_viacep_street_search_keeps_only_sao_paulo():
    dados = [{"cep": "01311-200", "logradouro": "Avenida Paulista", "complemento": "de 1047 a 1865 - lado ímpar",
              "bairro": "Bela Vista", "ibge": "3550308"},
             {"cep": "06000-000", "logradouro": "Rua Paulista", "complemento": "", "bairro": "X", "ibge": "3534401"}]
    ceps = cep_providers.parse_viacep_street(dados)
    assert [c.cep for c in ceps] == ["01311200"] and ceps[0].complement.startswith("de 1047")
    assert cep_providers.parse_viacep_street({"erro": True}) == []


def test_free_search_lists_every_house_number_of_the_gate():
    from geohabita.infrastructure.nominatim import NominatimClient, free_search
    resposta = [{"lat": "-23.56", "lon": "-46.65", "display_name": "Avenida Paulista, 1578, 1600",
                 "address": {"road": "Avenida Paulista", "house_number": "1578, 1600",
                             "suburb": "Cerqueira César", "postcode": "01311-200"}}]
    ponto = free_search(NominatimClient(fetch=lambda p: resposta), "Avenida Paulista 1578")[0]
    assert "1578" in ponto["numeros"] and "1600" in ponto["numeros"] and ponto["numero"] == "1578"


def test_free_search_recognizes_the_number_asked_even_if_registered_as_another():
    from geohabita.infrastructure.nominatim import NominatimClient, free_search
    resposta = [{"lat": "-23.56", "lon": "-46.65", "name": "Avenida Paulista, 1578",
                 "display_name": "Avenida Paulista, 1578, 1600, Avenida Paulista, São Paulo, 01311-200, Brasil",
                 "address": {"road": "Avenida Paulista", "house_number": "1600", "postcode": "01311-200"}}]
    ponto = free_search(NominatimClient(fetch=lambda p: resposta), "Avenida Paulista 1578")[0]
    assert "1578" in ponto["numeros"] and ponto["numero"] == "1600" and ponto["cep"] == "01311200"
