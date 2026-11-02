"""Geocodificação de endereço pelo Nominatim (OpenStreetMap), reserva do diagnóstico (RF04).

Segue a política de uso do serviço público: no máximo 1 requisição por segundo,
identificação no User-Agent e cache dos resultados (30 dias, RN04). Resultados
do OpenStreetMap estão sob licença ODbL e exigem atribuição.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable, MutableMapping
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


class NominatimClient:
    """Acesso ao Nominatim com no máximo 1 requisição por segundo, compartilhado por todos os usos."""

    def __init__(self, fetch: Callable[[dict[str, str]], list[dict[str, Any]]] = _fetch,
                 monotonic: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.fetch, self.monotonic, self.sleep = fetch, monotonic, sleep
        self._lock = threading.Lock()
        self._last: float | None = None

    def search(self, params: dict[str, str]) -> list[dict[str, Any]] | None:
        """Resultados da busca, ou ``None`` se o serviço falhar ou demorar."""
        with self._lock:  # serializa as chamadas para respeitar 1 requisição por segundo
            if self._last is not None:
                wait = MIN_INTERVAL_S - (self.monotonic() - self._last)
                if wait > 0:
                    self.sleep(wait)
            try:
                return self.fetch({"format": "jsonv2", "countrycodes": "br", **params})
            except Exception:  # serviço fora do ar ou lento: quem chama trata como "não localizado"
                return None
            finally:
                self._last = self.monotonic()


class NominatimGeocoder:
    """Coordenada do logradouro; com ``house_number``, só aceita o ponto do próprio número.

    O modo por número serve para CEPs que cobrem trechos longos: o ponto do CEP
    pode ficar a centenas de metros do imóvel. Se o OpenStreetMap não tiver o
    número cadastrado, devolve ``None`` e o diagnóstico usa os outros geocodificadores.
    """

    def __init__(self, fetch: Callable[[dict[str, str]], list[dict[str, Any]]] = _fetch,
                 clock: Callable[[], datetime] = datetime.now,
                 monotonic: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 cache: MutableMapping[str, tuple[datetime, tuple[float, float] | None]] | None = None,
                 client: NominatimClient | None = None, house_number: bool = False) -> None:
        self.client = client or NominatimClient(fetch, monotonic, sleep)
        self.clock = clock
        self.cache = {} if cache is None else cache  # persistente na aplicação (RN04)
        self.house_number = house_number

    def __call__(self, address: Address) -> tuple[float, float] | None:
        if not address.street or (self.house_number and not address.number):
            return None
        number = address.number if self.house_number else ""
        key = f"{number}|{address.street}|{address.city}"
        cached = self.cache.get(key)
        if cached and is_cache_fresh(cached[0], self.clock()):
            return cached[1]
        street = f"{number} {address.street}" if number else address.street
        results = self.client.search({"limit": "1", "addressdetails": "1", "street": street,
                                      "city": address.city, "state": "SP"})
        if results is None:
            return None  # falha passageira: não entra no cache
        point = None
        if results:
            found = results[0]
            if not number or (found.get("address") or {}).get("house_number") == number:
                point = (float(found["lat"]), float(found["lon"]))
        self.cache[key] = (self.clock(), point)
        return point


# Retângulo do município (oeste, norte, leste, sul) que limita a busca livre.
SAO_PAULO_VIEWBOX = "-46.83,-23.36,-46.36,-24.01"


def free_search(client: NominatimClient, query: str, limit: int = 5) -> list[dict[str, Any]] | None:
    """Busca livre de endereço no município (reserva da busca por logradouro; RF03)."""
    results = client.search({"q": f"{query}, São Paulo, SP", "limit": str(limit), "addressdetails": "1",
                             "viewbox": SAO_PAULO_VIEWBOX, "bounded": "1"})
    if results is None:
        return None
    found = []
    for r in results:
        a = r.get("address") or {}
        cep = "".join(ch for ch in a.get("postcode", "") if ch.isdigit())
        # O número pedido pode aparecer só no display_name ("..., 1578, 1600, ..."),
        # quando o portão atende por mais de um número.
        texto = f"{a.get('house_number') or ''} {r.get('name') or ''} {r.get('display_name') or ''}"
        numeros = [n for n in re.findall(r"(?<!\d)\d{1,6}(?!\d)", texto)]
        found.append({"logradouro": a.get("road") or r.get("name") or "",
                      "numero": (a.get("house_number") or "").split(",")[0].strip(), "numeros": numeros,
                      "bairro": a.get("suburb") or a.get("neighbourhood") or a.get("city_district") or "",
                      "cep": cep if len(cep) == 8 else None,
                      "latitude": float(r["lat"]), "longitude": float(r["lon"]),
                      "rotulo": r.get("display_name", "")})
    return found
