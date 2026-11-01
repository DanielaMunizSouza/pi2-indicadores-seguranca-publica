"""Geocodificação de endereço pelo Nominatim (OpenStreetMap), reserva do diagnóstico (RF04).

Segue a política de uso do serviço público: no máximo 1 requisição por segundo,
identificação no User-Agent e cache dos resultados (30 dias, RN04). Resultados
do OpenStreetMap estão sob licença ODbL e exigem atribuição.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from geohabita.application.cep_lookup import Address
from geohabita.domain.freshness import is_cache_fresh

SEARCH_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "GeoHabita/0.1 (projeto integrador UNIVESP)"
MIN_INTERVAL_S = 1.0


def _fetch(params: dict[str, str], timeout: float = 5.0) -> list[dict[str, Any]]:
    request = Request(f"{SEARCH_URL}?{urlencode(params)}", headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


class NominatimGeocoder:
    def __init__(self, fetch: Callable[[dict[str, str]], list[dict[str, Any]]] = _fetch,
                 clock: Callable[[], datetime] = datetime.now,
                 monotonic: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.fetch, self.clock, self.monotonic, self.sleep = fetch, clock, monotonic, sleep
        self.cache: dict[tuple[str, str], tuple[datetime, tuple[float, float] | None]] = {}
        self._lock = threading.Lock()
        self._last: float | None = None

    def __call__(self, address: Address) -> tuple[float, float] | None:
        if not address.street:
            return None
        key = (address.street, address.city)
        cached = self.cache.get(key)
        if cached and is_cache_fresh(cached[0], self.clock()):
            return cached[1]
        with self._lock:  # serializa as chamadas para respeitar 1 requisição por segundo
            if self._last is not None:
                wait = MIN_INTERVAL_S - (self.monotonic() - self._last)
                if wait > 0:
                    self.sleep(wait)
            try:
                results = self.fetch({"format": "jsonv2", "limit": "1", "countrycodes": "br",
                                      "street": address.street, "city": address.city, "state": "SP"})
            except Exception:  # serviço fora do ar ou lento: o diagnóstico informa que não localizou
                return None
            finally:
                self._last = self.monotonic()
        point = (float(results[0]["lat"]), float(results[0]["lon"])) if results else None
        self.cache[key] = (self.clock(), point)
        return point
