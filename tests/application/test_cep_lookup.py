"""Testes da consulta de CEP (RF01, RF02; RN01 a RN04; RNF06).

Os provedores são dublês, de modo que os casos CT01 (formato inválido sem
chamada externa), CT02 (endereço preenchido), CT03 (CEP inexistente) e CT04
(contingência após atraso do serviço principal) não dependem da rede.
"""

from datetime import datetime, timedelta

import pytest

from geohabita.application.cep_lookup import (
    PRIMARY_TIMEOUT_S,
    Address,
    CepLookup,
    CepNotFoundError,
    ProviderError,
)
from geohabita.domain.cep import CEP_NOT_FOUND_MESSAGE, InvalidCepError

PAULISTA = Address("01310100", "Avenida Paulista", "Bela Vista", "São Paulo", "3550308")


class FakeProvider:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def __call__(self, cep, timeout):
        self.calls.append((cep, timeout))
        if self.error:
            raise self.error
        return self.result


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 10, 1, 12, 0)

    def __call__(self):
        return self.now


def test_primary_timeout_is_three_seconds():
    assert PRIMARY_TIMEOUT_S == 3.0


@pytest.mark.parametrize("cep", ["1234", "abcdefgh", "123456789"])
def test_ct01_invalid_cep_never_reaches_providers(cep):
    primary, fallback = FakeProvider(PAULISTA), FakeProvider(PAULISTA)
    with pytest.raises(InvalidCepError):
        CepLookup(primary, fallback).lookup(cep)
    assert primary.calls == fallback.calls == []


def test_ct02_address_comes_from_primary_with_normalized_cep():
    primary, fallback = FakeProvider(PAULISTA), FakeProvider()
    assert CepLookup(primary, fallback).lookup("01310-100") == PAULISTA
    assert primary.calls == [("01310100", PRIMARY_TIMEOUT_S)]
    assert fallback.calls == []


def test_ct03_unknown_cep_raises_not_found_with_message():
    lookup = CepLookup(FakeProvider(None), FakeProvider(None))
    with pytest.raises(CepNotFoundError, match=CEP_NOT_FOUND_MESSAGE):
        lookup.lookup("99999-999")


def test_ct04_fallback_answers_when_primary_times_out():
    primary = FakeProvider(error=ProviderError("tempo excedido"))
    fallback = FakeProvider(PAULISTA)
    assert CepLookup(primary, fallback).lookup("01310100") == PAULISTA
    assert len(fallback.calls) == 1


def test_fallback_is_not_used_when_primary_says_cep_does_not_exist():
    # RN03: a contingência cobre falhas, não respostas negativas
    primary, fallback = FakeProvider(None), FakeProvider(PAULISTA)
    with pytest.raises(CepNotFoundError):
        CepLookup(primary, fallback).lookup("99999999")
    assert fallback.calls == []


def test_failure_of_both_providers_is_reported():
    lookup = CepLookup(FakeProvider(error=ProviderError()), FakeProvider(error=ProviderError()))
    with pytest.raises(ProviderError):
        lookup.lookup("01310100")


def test_cached_address_is_reused_within_thirty_days():
    # RN04
    primary, clock = FakeProvider(PAULISTA), FakeClock()
    lookup = CepLookup(primary, FakeProvider(), clock=clock)
    lookup.lookup("01310100")
    clock.now += timedelta(days=30)
    assert lookup.lookup("01310-100") == PAULISTA
    assert len(primary.calls) == 1


def test_cache_expires_after_thirty_days():
    primary, clock = FakeProvider(PAULISTA), FakeClock()
    lookup = CepLookup(primary, FakeProvider(), clock=clock)
    lookup.lookup("01310100")
    clock.now += timedelta(days=31)
    lookup.lookup("01310100")
    assert len(primary.calls) == 2


def test_not_found_is_not_cached():
    primary = FakeProvider(None)
    lookup = CepLookup(primary, FakeProvider())
    for _ in range(2):
        with pytest.raises(CepNotFoundError):
            lookup.lookup("99999999")
    assert len(primary.calls) == 2
