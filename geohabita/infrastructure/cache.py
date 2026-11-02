"""Cache persistente de consultas externas no PostgreSQL (RN04).

Guarda, por espaço (``cep``, ``geocodificacao``...), o resultado de cada chave
e o instante em que foi obtido; a validade de 30 dias é verificada por quem lê
(``geohabita.domain.freshness``). Se o banco falhar, o cache continua em
memória: uma falha do cache nunca derruba a consulta.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator, MutableMapping
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)

Encode = Callable[[Any], Any]
Decode = Callable[[Any], Any]


class PersistentCache(MutableMapping[str, tuple[datetime, Any]]):
    """Mapa ``chave -> (obtido_em, valor)`` gravado em ``public.cache_consulta``."""

    def __init__(self, connect: Callable[[], Any], namespace: str,
                 encode: Encode = lambda v: v, decode: Decode = lambda v: v) -> None:
        self.connect, self.namespace = connect, namespace
        self.encode, self.decode = encode, decode
        self._memory: dict[str, tuple[datetime, Any]] = {}

    def __getitem__(self, key: str) -> tuple[datetime, Any]:
        if key in self._memory:
            return self._memory[key]
        try:
            with self.connect() as conn:
                row = conn.execute("SELECT obtido_em, valor FROM public.cache_consulta "
                                   "WHERE espaco = %s AND chave = %s", (self.namespace, key)).fetchone()
        except Exception as exc:  # banco fora do ar: segue sem o cache persistente
            log.warning("cache %s indisponível: %s", self.namespace, exc)
            raise KeyError(key) from exc
        if row is None:
            raise KeyError(key)
        stamp, value = (row["obtido_em"], row["valor"]) if isinstance(row, dict) else row
        entry = (stamp.replace(tzinfo=None), self.decode(value))
        self._memory[key] = entry
        return entry

    def __setitem__(self, key: str, entry: tuple[datetime, Any]) -> None:
        self._memory[key] = entry
        stamp, value = entry
        try:
            with self.connect() as conn:
                conn.execute("""INSERT INTO public.cache_consulta (espaco, chave, valor, obtido_em)
                                VALUES (%s, %s, %s::jsonb, %s)
                                ON CONFLICT (espaco, chave) DO UPDATE
                                SET valor = EXCLUDED.valor, obtido_em = EXCLUDED.obtido_em""",
                             (self.namespace, key, json.dumps(self.encode(value), ensure_ascii=False), stamp))
        except Exception as exc:
            log.warning("cache %s não gravado: %s", self.namespace, exc)

    def __delitem__(self, key: str) -> None:
        self._memory.pop(key, None)
        try:
            with self.connect() as conn:
                conn.execute("DELETE FROM public.cache_consulta WHERE espaco = %s AND chave = %s",
                             (self.namespace, key))
        except Exception as exc:
            log.warning("cache %s não apagado: %s", self.namespace, exc)

    def __iter__(self) -> Iterator[str]:
        return iter(self._memory)

    def __len__(self) -> int:
        return len(self._memory)
