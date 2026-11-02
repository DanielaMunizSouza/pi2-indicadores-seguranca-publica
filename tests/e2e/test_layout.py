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


BORDAS = """(seletores) => Object.fromEntries(seletores.map((s) => {
  const e = document.querySelector(s);
  const r = e.getBoundingClientRect();
  const cs = getComputedStyle(e);
  // Borda do conteúdo: descontado o padding, onde o texto e os cartões começam.
  return [s, [Math.round(r.left + parseFloat(cs.paddingLeft)), Math.round(r.right - parseFloat(cs.paddingRight))]];
}))"""


@pytest.mark.parametrize("largura", [1280, 1366, 1536, 1920])
@pytest.mark.parametrize("rota", ["/", "/explorar"])
def test_tela_cabe_na_largura_da_janela(visitando, rota, largura):
    page = visitando(rota)
    page.set_viewport_size({"width": largura, "height": 900})
    if rota == "/explorar":
        page.wait_for_selector("#area-table tr:nth-child(5)")
    assert page.evaluate("document.documentElement.scrollWidth") <= largura


@pytest.mark.parametrize("largura", [1280, 1536, 1920])
def test_exploracao_alinha_cabecalho_consulta_e_painel(visitando, largura):
    page = visitando("/explorar")
    page.set_viewport_size({"width": largura, "height": 900})
    page.wait_for_selector("#area-table tr:nth-child(5)")
    bordas = page.evaluate(BORDAS, [".head-inner", ".a11y-bar", "main"])
    caixas = page.evaluate("""() => ['#consulta', '.dashboard'].map((s) => {
      const r = document.querySelector(s).getBoundingClientRect();
      return [Math.round(r.left), Math.round(r.right)];
    })""")
    consulta, painel = caixas
    assert consulta == painel, f"consulta {consulta} e mapa+resumo {painel} com larguras diferentes"
    for nome, borda in bordas.items():
        assert borda == consulta, f"{nome} {borda} desalinhado da consulta {consulta}"
