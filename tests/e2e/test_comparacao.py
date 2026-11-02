"""Comparação de endereços (RF16, UC05) na tela de diagnóstico."""

from __future__ import annotations

import pytest

from test_diagnostico_acessibilidade import consulta, violacoes

pytestmark = pytest.mark.e2e


COLUNAS = "#comparar thead th.comp-col"


def cartoes(page):
    """Uma coluna da tabela de comparação por endereço."""
    return page.locator(COLUNAS)


def test_fixar_a_consulta_atual_e_comparar_com_outro_cep(visitando):
    page = visitando("/")
    consulta(page)
    page.click("#aba-comparar")
    page.click("button:has-text('Fixar esta consulta para comparar')")
    page.fill("#comp-entrada", "01001-000")
    page.click("#form-comparar button[type=submit]")
    page.wait_for_function("document.querySelectorAll('#comparar thead th.comp-col').length === 2")
    assert cartoes(page).count() == 2
    textos = cartoes(page).all_inner_texts()
    assert all("Distrito" in t for t in textos)
    linhas = page.locator("#comparar tbody th[scope=row]").all_inner_texts()
    assert "Proximidade (IPL)" in linhas and "Iluminação pública" in linhas and "Furto" in linhas


def adicionar(page, entrada, total):
    page.fill("#comp-entrada", entrada)
    page.click("#form-comparar button[type=submit]")
    page.wait_for_function(f"document.querySelectorAll('#comparar thead th.comp-col').length === {total}")


def test_tres_enderecos_e_remocao(visitando):
    page = visitando("/")
    page.click("#aba-comparar")
    adicionar(page, "01310-200", 1)
    adicionar(page, "01001-000", 2)
    adicionar(page, "05508-040", 3)
    assert "de 3" in page.inner_text("#status")
    page.locator("#comparar .comp-remover").first.click()
    page.wait_for_function("document.querySelectorAll('#comparar thead th.comp-col').length === 2")


def test_quarto_endereco_e_recusado_com_aviso(visitando):
    page = visitando("/")
    page.click("#aba-comparar")
    for esperado, cep in enumerate(["01310-200", "01001-000", "05508-040"], start=1):
        adicionar(page, cep, esperado)
    page.fill("#comp-entrada", "04959-000")
    page.click("#form-comparar button[type=submit]")
    page.wait_for_selector("#status:has-text('aceita três')")
    assert cartoes(page).count() == 3


def test_pesos_novos_recalcram_a_comparacao(visitando):
    page = visitando("/")
    consulta(page)
    page.click("#aba-comparar")
    page.click("button:has-text('Fixar esta consulta para comparar')")
    page.click("#aba-proximidade")
    antes = cartoes(page).first.inner_text()
    page.select_option("#peso-mobilidade", "0")
    page.wait_for_selector("#status:has-text('Índices recalculados')")
    page.wait_for_timeout(300)
    assert cartoes(page).count() == 1
    assert antes  # o cartão continua lá, recalculado


def test_painel_de_comparacao_sem_violacoes(visitando, axe):
    page = visitando("/")
    consulta(page)
    page.click("#aba-comparar")
    page.click("button:has-text('Fixar esta consulta para comparar')")
    assert violacoes(page, "#painel-comparar") == []


def pedidos(page, rota):
    vistos = []
    page.on("request", lambda r: vistos.append(r.url) if rota in r.url else None)
    return vistos


def test_cep_adicionado_nao_herda_o_numero_da_consulta_principal(visitando):
    page = visitando("/")
    consulta(page, numero="1578")
    vistos = pedidos(page, "/api/diagnostico")
    page.click("#aba-comparar")
    page.fill("#comp-entrada", "01001-000")
    page.click("#form-comparar button[type=submit]")
    page.wait_for_function("document.querySelectorAll('#comparar thead th.comp-col').length === 1")
    assert "cep=01001000" in vistos[-1] and "numero=" not in vistos[-1]


def test_cep_e_rua_aceitam_o_numero_na_mesma_entrada(visitando):
    page = visitando("/")
    page.click("#aba-comparar")
    diagnosticos, enderecos = pedidos(page, "/api/diagnostico"), pedidos(page, "/api/enderecos")
    page.fill("#comp-entrada", "01001-000 120")
    page.click("#form-comparar button[type=submit]")
    page.wait_for_function("document.querySelectorAll('#comparar thead th.comp-col').length === 1")
    assert "cep=01001000" in diagnosticos[-1] and "numero=120" in diagnosticos[-1]
    page.fill("#comp-entrada", "Avenida Paulista, 1578")
    page.click("#form-comparar button[type=submit]")
    page.wait_for_timeout(500)
    assert enderecos and "numero=1578" in enderecos[-1] and "Paulista" in enderecos[-1]
    assert "1578" not in enderecos[-1].split("logradouro=")[1].split("&")[0]
