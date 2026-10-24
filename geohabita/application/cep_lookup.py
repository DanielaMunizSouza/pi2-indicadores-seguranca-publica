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
        raise NotImplementedError
