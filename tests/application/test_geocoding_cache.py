"""Cache de geocodificação (RN04): validade de 30 dias e falhas passageiras fora do cache."""

from datetime import datetime, timedelta

from geohabita.application.cep_lookup import Address, ProviderError
from geohabita.application.geocoding import CachedGeocoder, address_key, decode_point, encode_point

ENDERECO = Address("01310200", "Avenida Paulista", "Bela Vista", "São Paulo", "3550308", number="1578")


class Relogio:
    def __init__(self):
        self.agora = datetime(2026, 11, 1)

    def __call__(self):
        return self.agora


def test_point_is_reused_within_thirty_days_and_refreshed_after():
    chamadas, relogio = [], Relogio()
    g = CachedGeocoder(lambda a: chamadas.append(a) or (-23.56, -46.65), {}, clock=relogio)
    g(ENDERECO)
    relogio.agora += timedelta(days=30)
    g(ENDERECO)
    assert len(chamadas) == 1
    relogio.agora += timedelta(days=1)
    g(ENDERECO)
    assert len(chamadas) == 2


def test_empty_result_is_cached_but_provider_failure_is_not():
    cache = {}
    assert CachedGeocoder(lambda a: None, cache)(ENDERECO) is None
    assert cache[address_key(ENDERECO)][1] is None

    def falha(a):
        raise ProviderError("fora do ar")
    outro = {}
    assert CachedGeocoder(falha, outro)(ENDERECO) is None
    assert outro == {}


def test_key_distinguishes_house_numbers():
    sem_numero = Address("01310200", "Avenida Paulista", "", "São Paulo", "3550308")
    assert address_key(sem_numero) != address_key(ENDERECO)


def test_point_round_trips_through_json():
    assert decode_point(encode_point((-23.5, -46.6))) == (-23.5, -46.6)
    assert decode_point(encode_point(None)) is None
