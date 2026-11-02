"""Cache persistente no PostgreSQL (RN04): sobrevive a uma nova instância da aplicação."""

import uuid
from dataclasses import asdict
from datetime import datetime

import pytest

from geohabita.application.cep_lookup import Address
from geohabita.infrastructure.cache import PersistentCache

pytestmark = pytest.mark.integracao


def test_entry_is_read_back_by_a_new_cache(connect):
    espaco = f"teste-{uuid.uuid4()}"
    endereco = Address("01310100", "Avenida Paulista", "Bela Vista", "São Paulo", "3550308")
    agora = datetime(2026, 11, 1, 12, 0)
    PersistentCache(connect, espaco, encode=asdict)["01310100"] = (agora, endereco)
    try:
        lido = PersistentCache(connect, espaco, decode=lambda d: Address(**d)).get("01310100")
        assert lido == (agora, endereco)
    finally:
        with connect() as conn:
            conn.execute("DELETE FROM public.cache_consulta WHERE espaco = %s", (espaco,))


def test_unreachable_database_falls_back_to_memory():
    def recusa():
        raise OSError("sem banco")
    cache = PersistentCache(recusa, "x")
    assert cache.get("a") is None
    cache["a"] = (datetime(2026, 1, 1), 1)
    assert cache["a"] == (datetime(2026, 1, 1), 1)
