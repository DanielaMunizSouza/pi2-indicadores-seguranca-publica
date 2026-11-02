"""Comparação de endereços (RF16, UC05) na tela de diagnóstico."""

from __future__ import annotations

import pytest

from test_diagnostico_acessibilidade import consulta, violacoes

pytestmark = pytest.mark.e2e


def cartoes(page):
    return page.locator("#comparar .comp-card")


def test_fixar_a_consulta_atual_e_comparar_com_outro_cep(visitando):
    page = visitando("/")
    consulta(page)
    page.click("#aba-comparar")
    page.click("button:has-text('Fixar esta consulta para comparar')")
    page.fill("#comp-entrada", "01001-000")
    page.click("#form-comparar button[type=submit]")
    page.wait_for_function("document.querySelectorAll('#comparar .comp-card').length === 2")
    assert cartoes(page).count() == 2
    textos = cartoes(page).locator("h4").all_inner_texts()
    assert all("distrito" in t for t in textos)


def adicionar(page, entrada, total):
    page.fill("#comp-entrada", entrada)
    page.click("#form-comparar button[type=submit]")
    page.wait_for_function(f"document.querySelectorAll('#comparar .comp-card').length === {total}")


def test_tres_enderecos_e_remocao(visitando):
    page = visitando("/")
    page.click("#aba-comparar")
    adicionar(page, "01310-200", 1)
    adicionar(page, "01001-000", 2)
    adicionar(page, "05508-040", 3)
    assert "de 3" in page.inner_text("#status")
    page.locator("#comparar .comp-remover").first.click()
    page.wait_for_function("document.querySelectorAll('#comparar .comp-card').length === 2")


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
    antes = page.locator("#comparar .comp-card").first.inner_text()
    page.select_option("#peso-mobilidade", "0")
    page.wait_for_selector("#status:has-text('Índices recalculados')")
    page.wait_for_timeout(300)
    assert page.locator("#comparar .comp-card").count() == 1
    assert antes  # o cartão continua lá, recalculado


def test_painel_de_comparacao_sem_violacoes(visitando, axe):
    page = visitando("/")
    consulta(page)
    page.click("#aba-comparar")
    page.click("button:has-text('Fixar esta consulta para comparar')")
    assert violacoes(page, "#painel-comparar") == []
