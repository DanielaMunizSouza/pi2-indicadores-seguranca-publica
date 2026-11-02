"""Busca por endereço e busca reversa do CEP (RF03; RN02).

O munícipe informa o logradouro e, se quiser, o número. O ViaCEP devolve os CEPs
do logradouro; com o número, os trechos de numeração apontam o CEP certo em
avenidas longas. Como o ViaCEP devolve no máximo 50 CEPs, e muitos são de
prédios ("grandes usuários"), o trecho certo pode faltar na lista: nesse caso,
o CEP do número vem do OpenStreetMap (Nominatim). Se o ViaCEP não achar nada
ou estiver fora do ar, a busca livre do Nominatim devolve pontos, que podem ser
diagnosticados pela coordenada. Os resultados do ViaCEP ficam 30 dias em cache (RN04).
"""

from __future__ import annotations

from collections.abc import Callable, MutableMapping
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from geohabita.application.cep_lookup import ProviderError
from geohabita.domain.address import building_number, matches_number, normalize_number, require_street
from geohabita.domain.freshness import is_cache_fresh

NOT_FOUND_MESSAGE = "Nenhum endereço encontrado em São Paulo. Confira o nome da rua."
NUMBER_HINT = "Informe o número do imóvel para encontrar o CEP do trecho certo."
MAX_CANDIDATES = 20


@dataclass(frozen=True)
class StreetCep:
    """Um CEP do logradouro, com o trecho de numeração descrito pelo ViaCEP."""

    cep: str
    street: str
    complement: str
    neighbourhood: str
    unit: str = ""  # nome do prédio, nos CEPs exclusivos


StreetProvider = Callable[[str], list[StreetCep]]
FreeSearch = Callable[[str], "list[dict[str, Any]] | None"]

_ORDER = {True: 0, None: 1, False: 2}


def _candidate(c: StreetCep, number: str) -> dict[str, Any]:
    return {"cep": c.cep, "logradouro": c.street, "complemento": c.complement, "bairro": c.neighbourhood,
            "predio": c.unit, "numero": number, "corresponde_numero": matches_number(c.complement, number),
            "latitude": None, "longitude": None, "fonte": "viacep"}


class AddressSearch:
    def __init__(self, by_street: StreetProvider, free_search: FreeSearch,
                 cache: MutableMapping[str, tuple[datetime, list[dict[str, str]]]] | None = None,
                 clock: Callable[[], datetime] = datetime.now) -> None:
        self.by_street, self.free_search = by_street, free_search
        self.cache = {} if cache is None else cache
        self.clock = clock

    def _street_ceps(self, street: str) -> list[StreetCep]:
        key = street.casefold()
        now = self.clock()
        cached = self.cache.get(key)
        if cached is not None and is_cache_fresh(cached[0], now):
            return [StreetCep(**item) for item in cached[1]]
        ceps = self.by_street(street)  # ProviderError sobe: falha passageira não entra no cache
        self.cache[key] = (now, [asdict(c) for c in ceps])
        return ceps

    def _points(self, street: str, number: str) -> list[dict[str, Any]]:
        pontos = self.free_search(f"{street} {number}".strip()) or []
        return [{**p, "complemento": "", "predio": "",
                 "numero": p.get("numero") or number,
                 "corresponde_numero": (number in (p.get("numeros") or [p.get("numero")])) if number else True,
                 "fonte": "openstreetmap"} for p in pontos]

    def search(self, street: str, number: str | None = None) -> dict[str, Any]:
        """Candidatos para o endereço; ``sugerido`` é o índice do único que serve, se houver."""
        street, number = require_street(street), normalize_number(number)
        try:
            ceps = self._street_ceps(street)
        except ProviderError:
            ceps = []
        if not ceps:
            candidatos = self._points(street, number)
            return {"fonte": "openstreetmap", "logradouro": street, "numero": number, "candidatos": candidatos,
                    "sugerido": 0 if len(candidatos) == 1 else None,
                    "mensagem": None if candidatos else NOT_FOUND_MESSAGE}
        if not number:
            # Sem número, os CEPs de prédios só atrapalham a escolha.
            gerais = [c for c in ceps if building_number(c.complement) is None]
            ceps = gerais or ceps
        candidatos = sorted((_candidate(c, number) for c in ceps), key=lambda c: _ORDER[c["corresponde_numero"]])
        exatos = [c for c in candidatos if c["corresponde_numero"] is True]
        pontos_osm = []
        if number and not exatos:
            # O trecho do número não veio do ViaCEP (a lista corta em 50 CEPs): o
            # OpenStreetMap informa o CEP do próprio número.
            exatos = [p for p in self._points(street, number) if p["corresponde_numero"] and p.get("cep")][:1]
            pontos_osm = exatos
        servem = [c for c in candidatos if c["corresponde_numero"] is not False]
        if pontos_osm:
            candidatos = pontos_osm + candidatos[:MAX_CANDIDATES - 1]
            sugerido = 0
        else:
            candidatos = candidatos[:MAX_CANDIDATES]
            # Com número, o único trecho que o inclui é a resposta; sem número,
            # sugere-se quando há apenas um CEP servindo.
            if number:
                indices = [i for i, c in enumerate(candidatos) if c["corresponde_numero"] is True]
                if not indices:
                    # Nenhum trecho confirma o número (a lista do ViaCEP corta em 50 CEPs):
                    # se só um CEP serve, ele continua sendo a sugestão.
                    indices = [i for i, c in enumerate(candidatos) if c["corresponde_numero"] is not False]
            else:
                indices = [i for i, c in enumerate(candidatos) if c["corresponde_numero"] is not False]
            sugerido = indices[0] if len(indices) == 1 else None
        varias_ruas = len({c["logradouro"] for c in candidatos}) > 1
        mensagem = NUMBER_HINT if not number and sugerido is None and not varias_ruas else None
        return {"fonte": "viacep", "logradouro": street, "numero": number,
                "candidatos": candidatos, "sugerido": sugerido, "mensagem": mensagem}
