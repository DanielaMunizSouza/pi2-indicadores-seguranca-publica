"""Conexão com o PostgreSQL/PostGIS."""

from __future__ import annotations

from collections.abc import Callable

import psycopg
from psycopg.rows import dict_row


class DatabaseUnavailable(RuntimeError):
    """O banco não respondeu ou recusou a conexão."""


def connector(url: str, timeout_s: int = 5) -> Callable[[], psycopg.Connection]:
    """Fábrica de conexões com linhas em dicionário."""
    def connect() -> psycopg.Connection:
        try:
            return psycopg.connect(url, connect_timeout=timeout_s, row_factory=dict_row)
        except psycopg.Error as exc:
            raise DatabaseUnavailable(str(exc)) from exc
    return connect
