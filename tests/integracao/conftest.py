"""Banco PostGIS descartável para os testes de integração.

A sessão de testes cria, no servidor de ``DATABASE_URL``, um banco novo chamado
``geohabita_teste_<aleatório>``, aplica ``database/schema.sql``, insere os dados
fictícios de ``dados.py`` e apaga o banco no fim, mesmo se os testes falharem.
O banco de ``DATABASE_URL`` nunca é lido nem alterado: ele só indica o servidor
e as credenciais (o usuário precisa poder criar bancos). Sem ``DATABASE_URL``,
os testes de integração são pulados.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

import geohabita.config  # noqa: F401  (carrega o .env, se houver)
from geohabita.infrastructure.database import connector
from tests.integracao.dados import semear

RAIZ = Path(__file__).resolve().parents[2]
PREFIXO = "geohabita_teste_"


def _url_do_servidor() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL não definido: sem servidor PostGIS para criar o banco de teste")
    return url


@pytest.fixture(scope="session")
def url_teste():
    """URL de um banco recém-criado, com o esquema e os dados fictícios."""
    servidor = _url_do_servidor()
    nome = f"{PREFIXO}{uuid.uuid4().hex[:12]}"
    assert nome.startswith(PREFIXO) and conninfo_to_dict(servidor).get("dbname") != nome
    url = make_conninfo(servidor, dbname=nome)
    try:
        admin = psycopg.connect(servidor, autocommit=True, connect_timeout=5)
    except psycopg.OperationalError as exc:
        pytest.skip(f"servidor de DATABASE_URL inacessível: {exc}")
    with admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
        try:
            with psycopg.connect(url) as conn:
                conn.execute((RAIZ / "database" / "schema.sql").read_text(encoding="utf-8"))
                semear(conn)
            yield url
        finally:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome)))


@pytest.fixture
def connect(url_teste):
    """Fábrica de conexões com o banco de teste, como a usada pela aplicação."""
    return connector(url_teste)
