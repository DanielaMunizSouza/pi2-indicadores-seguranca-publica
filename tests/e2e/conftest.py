"""Infraestrutura dos testes de interface (Playwright).

As rotas `/api/*` são interceptadas com respostas gravadas em `data/tmp/e2e`
(geradas por `scripts/capturar_respostas.py` a partir de um banco real), para que
os testes de acessibilidade dependam do contrato da API, não do conteúdo dos
dados — assim a suíte roda mesmo com o banco vazio.

    uv run --env-file .env scripts/capturar_respostas.py --cep 01310-200 --numero 1578
    uv run pytest -m e2e
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PASTA = RAIZ / "data" / "tmp" / "e2e"
AXE = RAIZ / "tests" / "vendor" / "axe.min.js"

pytestmark = pytest.mark.e2e

# rota -> (arquivo em data/tmp/e2e, content-type)
ROTAS = {
    "/api/status": ("status", "application/json"),
    "/api/categories": ("categories", "application/json"),
    "/api/areas/geometry": ("geometry", "application/geo+json"),
    "/api/areas": ("areas", "application/json"),
    "/api/summary": ("summary", "application/json"),
    "/api/diagnostico": ("diagnostico", "application/json"),
    "/api/enderecos": ("enderecos", "application/json"),
    "/api/distritos/": ("limite", "application/geo+json"),
}

# Diagnósticos alternativos, escolhidos pelo parâmetro `cep` da consulta.
DIAGNOSTICOS = {"01001000": "diagnostico-se", "05508040": "diagnostico-pinheiros"}


def porta_livre() -> int:
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    """Sobe a aplicação em porta própria; nenhuma rota de dados é realmente lida."""
    if not (PASTA / "status.json").is_file():
        pytest.skip("rode scripts/capturar_respostas.py para gerar as respostas simuladas")
    porta = porta_livre()
    processo = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", str(porta),
         "--log-level", "warning"],
        cwd=RAIZ, env={**os.environ, "PYTHONPATH": str(RAIZ)},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for _ in range(80):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=1):
                break
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.25)
    else:
        processo.terminate()
        pytest.fail("a aplicação não respondeu a tempo")
    yield f"http://127.0.0.1:{porta}"
    processo.terminate()
    try:
        processo.wait(timeout=5)
    except subprocess.TimeoutExpired:
        processo.kill()


_CONTEUDO: dict[Path, bytes] = {}


def lido(nome: Path) -> bytes:
    """Lê o arquivo uma vez: a geometria dos distritos tem megabytes."""
    if nome not in _CONTEUDO:
        _CONTEUDO[nome] = nome.read_bytes()
    return _CONTEUDO[nome]


def simular(base_url: str, alvo) -> None:
    """Responde `/api/*` com os arquivos locais; o resto é bloqueado."""
    def despachar(route):
        caminho = route.request.url.split("?", 1)[0].replace(base_url, "")
        entrada = next((v for k, v in ROTAS.items() if caminho.startswith(k)), None)
        if entrada is None:
            route.abort()
            return
        nome, tipo = entrada
        if caminho == "/api/diagnostico":
            consulta = dict(pair.split("=", 1) for pair in route.request.url.split("?", 1)[-1].split("&")
                            if "=" in pair)
            nome = DIAGNOSTICOS.get(consulta.get("cep", "").replace("-", ""), nome)
        arquivo = PASTA / f"{nome}.json"
        if not arquivo.is_file():
            arquivo = PASTA / "diagnostico.json"
        route.fulfill(status=200, content_type=tipo, body=lido(arquivo))

    alvo.route("**/api/**", despachar)


@pytest.fixture
def api(base_url, page):
    """Página com as rotas simuladas; `page.base_url` serve para montar endereços."""
    simular(base_url, page)
    page.base_url = base_url
    return page


@pytest.fixture
def visitando(api):
    """Abre uma tela já com as rotas simuladas."""
    def abre(rota: str = "/"):
        api.goto(f"{api.base_url}{rota}")
        api.wait_for_selector("main, #conteudo")
        return api
    return abre


@pytest.fixture
def axe(visitando):
    """axe-core (cópia em tests/vendor) carregado na página já aberta.

    Depende de ``visitando`` de propósito: o fixture é declarado antes da ação do
    teste, então a página já está navegada quando a rota é registrada.
    """
    if not AXE.is_file():
        pytest.skip("rode scripts/preparar_axe.py para baixar o axe-core")
    page = visitando()
    # init script (e não add_script_tag): sobrevive às navegações do teste.
    page.route("**/axe.min.js", lambda route: route.fulfill(
        status=200, content_type="application/javascript", body=AXE.read_bytes()))
    page.add_init_script("fetch('/axe.min.js').then(r => r.text()).then((c) => (0, eval)(c));")
    page.reload(wait_until="load")
    page.wait_for_function("window.axe !== undefined")
    return page


def pytest_report_header(config):
    estado = "ok" if (PASTA / "status.json").is_file() else "faltam (scripts/capturar_respostas.py)"
    return f"GeoHabita e2e: fixtures {estado}; axe-core {'ok' if AXE.is_file() else 'faltando'}"
