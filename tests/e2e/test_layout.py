"""Tamanho de fonte e largura das telas (RNF03, RNF12).

O controle de fonte muda o tamanho da raiz (``--fonte-base``); todo texto da
interface precisa acompanhá-lo, ou seja, nenhum tamanho pode estar fixo em px.
"""

import pytest

pytestmark = pytest.mark.e2e

# Textos de cada tela que existem antes de qualquer consulta.
TEXTOS = {
    "/": [".a11y-help", ".card h2", "label[for=cep]", "#status", ".btn", ".top-nav a"],
    "/explorar": [".a11y-help", ".card-title", ".field label", ".kpi span", ".kpi strong", "th", ".connection"],
}

TAMANHOS = """(seletores) => seletores.map((s) => {
  const e = document.querySelector(s);
  return e ? parseFloat(getComputedStyle(e).fontSize) : null;
})"""


@pytest.mark.parametrize("rota", TEXTOS)
def test_controle_de_fonte_aumenta_todos_os_textos(visitando, rota):
    page = visitando(rota)
    seletores = TEXTOS[rota]
    antes = page.evaluate(TAMANHOS, seletores)
    assert None not in antes, dict(zip(seletores, antes))
    page.click("#btn-fonte-maior")  # 112,5%
    page.click("#btn-fonte-maior")  # 125%
    depois = page.evaluate(TAMANHOS, seletores)
    for seletor, a, d in zip(seletores, antes, depois):
        assert d / a == pytest.approx(1.25, abs=0.02), f"{seletor}: {a}px -> {d}px"
