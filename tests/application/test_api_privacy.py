"""Testes de privacidade e do IP do cliente atrás do túnel (RNF08, RNF15).

Pelo túnel da Cloudflare toda conexão chega de 127.0.0.1; o IP real vem do
cabeçalho CF-Connecting-IP, que só é confiável quando a conexão é local.
O log de acesso não pode guardar o CEP consultado junto do IP (LGPD).
"""

import logging

import pytest
from starlette.requests import Request

import backend.app as api


def request(peer, headers=None):
    scope = {"type": "http", "method": "GET", "path": "/api/x", "query_string": b"",
             "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
             "client": (peer, 5000) if peer else None}
    return Request(scope)


def test_header_is_trusted_from_the_local_tunnel():
    assert api.client_ip(request("127.0.0.1", {"CF-Connecting-IP": "200.1.2.3"})) == "200.1.2.3"
    assert api.client_ip(request("::1", {"CF-Connecting-IP": "2804::1"})) == "2804::1"


def test_header_is_ignored_from_remote_peers():
    # Quem acessa direto não pode escolher o próprio IP e driblar o limite.
    assert api.client_ip(request("10.42.1.7", {"CF-Connecting-IP": "1.1.1.1"})) == "10.42.1.7"


def test_local_peer_without_header_keeps_its_address():
    assert api.client_ip(request("127.0.0.1")) == "127.0.0.1"


def test_missing_peer_has_a_placeholder():
    assert api.client_ip(request(None)) == "desconhecido"


def test_each_visitor_behind_the_tunnel_has_its_own_limit(monkeypatch):
    api.rate_limiter._requests.clear()
    allowed = []
    monkeypatch.setattr(api.rate_limiter, "allow", lambda client: allowed.append(client) or True)
    from fastapi.testclient import TestClient
    TestClient(api.app, client=("127.0.0.1", 1234)).get("/api/categories", headers={"CF-Connecting-IP": "200.9.9.9"})
    assert allowed == ["200.9.9.9"]


@pytest.mark.parametrize(("path", "esperado"), [
    ("/api/diagnostico?cep=01001000&peso_mobilidade=3", "/api/diagnostico"),
    ("/api/cep/01001000", "/api/cep/<cep>"),
    ("/", "/"),
])
def test_access_log_drops_query_and_cep(path, esperado):
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1,
                               '%s - "%s %s HTTP/%s" %d', ("200.1.2.3:5000", "GET", path, "1.1", 200), None)
    assert api.AccessLogWithoutQuery().filter(record) is True
    assert record.args[2] == esperado
