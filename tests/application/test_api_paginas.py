"""Páginas e arquivos estáticos: versão no endereço e revalidação do cache.

Atrás da borda da Cloudflare, CSS e JavaScript sem Cache-Control ficariam horas
no cache depois de um deploy; o endereço versionado e o no-cache evitam isso.
"""

import re

import pytest
from fastapi.testclient import TestClient

import backend.app as api


@pytest.fixture
def client():
    api.rate_limiter._requests.clear()
    return TestClient(api.app)


@pytest.mark.parametrize("rota", ["/", "/explorar"])
def test_pages_link_versioned_assets_and_are_revalidated(client, rota):
    resposta = client.get(rota)
    assert resposta.status_code == 200
    assert resposta.headers["cache-control"] == "no-cache"
    locais = re.findall(r'(?:href|src)="(/static/[^"]+)"', resposta.text)
    assert locais and all(f"?v={api.ASSET_VERSION}" in url for url in locais)
    for url in locais:
        assert client.get(url).status_code == 200


def test_static_files_are_revalidated(client):
    resposta = client.get("/static/js/util.js")
    assert resposta.status_code == 200
    assert resposta.headers["cache-control"] == "no-cache"
    assert "etag" in resposta.headers


def test_version_changes_when_a_file_changes(tmp_path):
    (tmp_path / "css").mkdir()
    arquivo = tmp_path / "css" / "a.css"
    arquivo.write_text("a{}", encoding="utf-8")
    antes = api.asset_version(tmp_path)
    arquivo.write_text("a{color:red}", encoding="utf-8")
    assert api.asset_version(tmp_path) != antes
