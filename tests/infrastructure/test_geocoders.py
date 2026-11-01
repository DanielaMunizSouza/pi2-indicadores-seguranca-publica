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
