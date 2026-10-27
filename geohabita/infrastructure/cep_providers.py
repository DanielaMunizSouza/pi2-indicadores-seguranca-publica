"""Provedores de CEP: ViaCEP (principal) e BrasilAPI CEP v2 (contingência).

Cada provedor segue o contrato ``Provider`` de
``geohabita.application.cep_lookup``: devolve o endereço, ``None`` para CEP
inexistente ou levanta ProviderError em falha ou tempo excedido (RN03).
"""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from geohabita.application.cep_lookup import Address, ProviderError
from geohabita.domain.territory import SAO_PAULO_IBGE_CODE

VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
BRASILAPI_URL = "https://brasilapi.com.br/api/cep/v2/{cep}"
_HEADERS = {"User-Agent": "GeoHabita/0.1 (projeto integrador UNIVESP)"}


def _get_json(url: str, timeout: float) -> dict | None:
    """JSON da URL; ``None`` para 404/400 e ProviderError para as demais falhas."""
    try:
        with urlopen(Request(url, headers=_HEADERS), timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code in (400, 404):
            return None
        raise ProviderError(f"{url}: HTTP {exc.code}") from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise ProviderError(f"{url}: {exc}") from exc


def parse_viacep(data: dict | None) -> Address | None:
    """Converte a resposta do ViaCEP; ``{"erro": true}`` indica CEP inexistente."""
    if not data or str(data.get("erro", "")).lower() == "true":
        return None
    return Address(
        cep=data["cep"].replace("-", ""),
        street=data.get("logradouro", ""),
        neighbourhood=data.get("bairro", ""),
        city=data.get("localidade", ""),
        ibge_code=data.get("ibge", ""),
    )


def parse_brasilapi(data: dict | None) -> Address | None:
    """Converte a resposta da BrasilAPI v2, que traz coordenadas mas não o código IBGE."""
    if not data:
        return None
    coordinates = (data.get("location") or {}).get("coordinates") or {}
    in_sao_paulo = data.get("city") == "São Paulo" and data.get("state") == "SP"
    return Address(
        cep=data["cep"].replace("-", ""),
        street=data.get("street") or "",
        neighbourhood=data.get("neighborhood") or "",
        city=data.get("city") or "",
        # A BrasilAPI não informa o código IBGE; ele é deduzido para a capital.
        ibge_code=SAO_PAULO_IBGE_CODE if in_sao_paulo else "",
        latitude=_as_float(coordinates.get("latitude")),
        longitude=_as_float(coordinates.get("longitude")),
    )


def _as_float(value: object) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def viacep(cep: str, timeout: float) -> Address | None:
    return parse_viacep(_get_json(VIACEP_URL.format(cep=cep), timeout))


def brasilapi(cep: str, timeout: float) -> Address | None:
    return parse_brasilapi(_get_json(BRASILAPI_URL.format(cep=cep), timeout))
