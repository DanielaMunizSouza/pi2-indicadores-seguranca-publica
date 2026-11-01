"""Consulta de CEP com serviço de contingência e cache.

Cobre a validação prévia do CEP sem chamada externa (RF01, RN01), a mensagem
de CEP inexistente (RN02), o acionamento do serviço de contingência quando o
principal falha ou excede 3 segundos (RN03; RNF06) e o cache de 30 dias
(RN04). Os provedores são adaptadores da camada de infraestrutura.
"""

from __future__ import annotations

from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from datetime import datetime

from geohabita.domain.cep import CEP_NOT_FOUND_MESSAGE, require_valid_cep
from geohabita.domain.freshness import is_cache_fresh

PRIMARY_TIMEOUT_S = 3.0


@dataclass(frozen=True)
class Address:
    """Endereço devolvido por um serviço de CEP."""

    cep: str
    street: str
    neighbourhood: str
    city: str
    ibge_code: str
    latitude: float | None = None
    longitude: float | None = None


class ProviderError(Exception):
    """Falha do serviço externo, inclusive tempo de resposta excedido."""


class CepNotFoundError(LookupError):
    """Nenhum serviço reconheceu o CEP (RN02)."""


# Um provedor recebe o CEP normalizado e o tempo limite, em segundos, e
# devolve o endereço, ``None`` para CEP inexistente ou levanta ProviderError.
Provider = Callable[[str, float], "Address | None"]


class CepLookup:
    """Consulta o provedor principal, recorre à contingência e guarda em cache."""

    def __init__(
        self,
        primary: Provider,
        fallback: Provider,
        cache: MutableMapping[str, tuple[datetime, Address]] | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.cache = {} if cache is None else cache
        self.clock = clock

    def lookup(self, raw_cep: str) -> Address:
        """Endereço do CEP; levanta InvalidCepError ou CepNotFoundError."""
        cep = require_valid_cep(raw_cep)
        now = self.clock()
        cached = self.cache.get(cep)
        if cached is not None and is_cache_fresh(cached[0], now):
            return cached[1]
        try:
            address = self.primary(cep, PRIMARY_TIMEOUT_S)
        except ProviderError:
            # RN03: falha ou atraso do principal aciona a contingência.
            address = self.fallback(cep, PRIMARY_TIMEOUT_S)
        if address is None:
            raise CepNotFoundError(CEP_NOT_FOUND_MESSAGE)
        self.cache[cep] = (now, address)
        return address
