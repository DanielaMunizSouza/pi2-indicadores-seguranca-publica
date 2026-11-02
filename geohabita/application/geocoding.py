"""Geocodificação com cache de 30 dias (RN04).

Envolve qualquer geocodificador ``Address -> (lat, lon) | None`` para que a
mesma consulta não volte a chamar o serviço externo dentro da validade.
Resultados vazios também ficam em cache, para não repetir buscas sem resposta;
falhas do serviço (ProviderError) não, porque são passageiras.
"""

from __future__ import annotations

from collections.abc import Callable, MutableMapping
from datetime import datetime
from typing import Any

from geohabita.application.cep_lookup import Address, ProviderError
from geohabita.domain.freshness import is_cache_fresh

Point = tuple[float, float]
Geocoder = Callable[[Address], "Point | None"]


def address_key(address: Address) -> str:
    """Chave do cache: CEP, logradouro e número, que determinam a coordenada."""
    return "|".join((address.cep, address.street.casefold(), address.number))


def encode_point(point: Point | None) -> list[float] | None:
    return list(point) if point is not None else None


def decode_point(value: Any) -> Point | None:
    return (float(value[0]), float(value[1])) if value else None


class CachedGeocoder:
    def __init__(self, geocode: Geocoder, cache: MutableMapping[str, tuple[datetime, Point | None]],
                 key: Callable[[Address], str] = address_key,
                 clock: Callable[[], datetime] = datetime.now) -> None:
        self.geocode, self.cache, self.key, self.clock = geocode, cache, key, clock

    def __call__(self, address: Address) -> Point | None:
        key = self.key(address)
        now = self.clock()
        cached = self.cache.get(key)
        if cached is not None and is_cache_fresh(cached[0], now):
            return cached[1]
        try:
            point = self.geocode(address)
        except ProviderError:
            return None
        self.cache[key] = (now, point)
        return point
