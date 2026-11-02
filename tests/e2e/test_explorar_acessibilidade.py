"""Tela de exploração: acessibilidade (RNF03, RNF04) e escala não estigmatizante (RNF18)."""

from __future__ import annotations

import re

import pytest

from test_diagnostico_acessibilidade import violacoes  # mesmo helper de auditoria

pytestmark = pytest.mark.e2e


def espera_dados(page):
    page.wait_for_function("document.querySelectorAll('#area-table tr th').length > 10")


def test_pagina_sem_violacoes_wcag_aa(visitando, axe):
    page = visitando("/explorar")
    espera_dados(page)
    assert violacoes(page) == []


def test_legenda_nao_usa_escala_de_alarme(visitando):
    page = visitando("/explorar")
    espera_dados(page)
    cores = page.evaluate("() => [...document.querySelectorAll('.legend-chip')].map(c => c.style.backgroundColor)")
    assert len(cores) == 6
    # nenhum tom avermelhado: matiz dominante não pode estar na faixa do vermelho
    def matiz(cor):
        r, g, b = (int(v) for v in re.findall(r"\d+", cor)[:3])
        maximo, minimo = max(r, g, b), min(r, g, b)
        if maximo == minimo:
            return 0
        if maximo == r:
            return (60 * ((g - b) / (maximo - minimo)) + 360) % 360
        if maximo == g:
            return 60 * ((b - r) / (maximo - minimo)) + 120
        return 60 * ((r - g) / (maximo - minimo)) + 240
    assert all(80 <= matiz(c) <= 260 for c in cores), cores


def test_tabela_de_distritos_nao_e_um_ranking(visitando):
    page = visitando("/explorar")
    espera_dados(page)
    nomes = page.locator("#area-table th").all_inner_texts()
    assert nomes == sorted(nomes, key=lambda n: n.casefold())


def test_taxa_e_a_medida_padrao_e_troca_a_legenda(visitando):
    page = visitando("/explorar")
    espera_dados(page)
    assert "100 mil" in page.inner_text("#legend-title")
    primeira = page.locator("#area-table tr td").nth(3).inner_text()
    assert primeira not in ("", "—")
    page.check("input[name=medida][value=registros]")
    assert "100 mil" not in page.inner_text("#legend-title")
    assert page.inner_text("#map-subtitle").startswith("Cor pela contagem")


def test_populacao_e_taxa_aparecem_na_tabela(visitando):
    page = visitando("/explorar")
    espera_dados(page)
    cabecalhos = " ".join(page.locator("thead th").all_inner_texts()).casefold()
    assert "população" in cabecalhos and "por 100 mil" in cabecalhos
    celulas = page.locator("#area-table tr").first.locator("td, th").all_inner_texts()
    assert celulas[1] != "" and celulas[2] != "" and celulas[3] not in ("", "—")


def test_contraste_e_atalhos_funcionam_na_exploracao(visitando, axe):
    page = visitando("/explorar")
    espera_dados(page)
    page.click("#btn-contraste")
    assert page.evaluate("document.documentElement.classList.contains('alto-contraste')")
    assert violacoes(page, "#consulta") == []
    page.keyboard.press("Alt+3")
    assert page.evaluate("() => document.activeElement.closest('#consulta') !== null")
