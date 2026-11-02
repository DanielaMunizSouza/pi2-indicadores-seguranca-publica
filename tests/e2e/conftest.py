"""Infraestrutura dos testes de interface (Playwright).

As rotas `/api/*` são interceptadas com respostas gravadas em `data/tmp/e2e`
(geradas por `scripts/capturar_respostas.py` a partir de um banco real), para que
os testes de acessibilidade dependam do contrato da API, não do conteúdo dos
dados. Assim a suíte roda mesmo com o banco vazio.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
PASTA = RAIZ / "data" / "tmp" / "e2e"
AXE = RAIZ / "tests" / "vendor" / "axe.min.js"

pytestmark = pytest.mark.e2e


def porta_livre() -> int:
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    """Sobe a aplicação em porta própria; sem banco, porque as rotas são simuladas."""
    if not (PASTA / "status.json").is_file():
        pytest.skip("rode scripts/capturar_respostas.py para gerar as respostas simuladas")
    porta = porta_livre()
    ambiente = {**os.environ, "PYTHONPATH": str(RAIZ)}
    processo = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", str(porta),
         "--log-level", "warning"],
        cwd=RAIZ, env=ambiente, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    import urllib.request
    import urllib.error
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/categories", timeout=1):
                break
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.2)
    else:
        processo.terminate()
        pytest.fail("a aplicação não respondeu a tempo")
    yield f"http://127.0.0.1:{porta}"
    processo.terminate()
    try:
        processo.wait(timeout=5)
    except subprocess.TimeoutExpired:
        processo.kill()


@pytest.fixture
def api(base_url, page):
    """Página com as rotas `/api/*` respondidas pelos arquivos de `data/tmp/e2e`."""
    rotas = {
        "/api/status": ("status", "application/json"),
        "/api/categories": ("categories", "application/json"),
        "/api/areas/geometry": ("geometry", "application/geo+json"),
        "/api/areas": ("areas", "application/json"),
        "/api/summary": ("summary", "application/json"),
        "/api/diagnostico": ("diagnostico", "application/json"),
        "/api/enderecos": ("enderecos", "application/json"),
        "/api/distritos/": ("limite", "application/geo+json"),
    }

    def despachar(route):
        caminho = route.request.url.split("?", 1)[0].replace(base_url, "")
        entrada = next((v for k, v in rotas.items() if caminho.startswith(k)), None)
        if entrada is None:
            route.abort()
            return
        nome, tipo = entrada
        route.fulfill(status=200, content_type=tipo, body=(PASTA / f"{nome}.json").read_bytes())

    page.route("**/api/**", despachar)
    page.base_url = base_url  # type: ignore[attr-defined]
    return page


@pytest.fixture
def visitando(api):
    """Abre uma tela já com as rotas simuladas."""
    def abre(rota: str = "/"):
        api.goto(f"{api.base_url}{rota}")
        return api
    return abre


@pytest.fixture
def axe(api):
    """Injeta o axe-core (cópia local) na página aberta."""
    if not AXE.is_file():
        pytest.skip("rode scripts/preparar_axe.py para baixar o axe-core")
    api.add_script_tag(path=str(AXE))
    return api
