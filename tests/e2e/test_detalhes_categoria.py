"""O que conta em cada categoria: detalhes sob as barras do IPL e do IVEP (RF24, RF08; RNF04)."""

from __future__ import annotations

import json

import pytest

from tests.e2e.conftest import PASTA
from tests.e2e.test_diagnostico_acessibilidade import consulta, violacoes

pytestmark = pytest.mark.e2e

# Números por tipo acrescentados ao diagnóstico gravado, para a vitalidade.
TIPOS_LAZER = {
    "praca": {"percentil": None, "equipamentos": None, "densidade_km2": None, "densidade_10k_hab": None,
              "disponivel": False, "aviso": "camada indisponível na fonte de dados no momento"},
    "parque_area_verde": {"percentil": 70.0, "equipamentos": 4, "densidade_km2": 0.5,
                          "densidade_10k_hab": 0.8, "disponivel": True, "aviso": None},
}


@pytest.fixture
def com_tipos_na_vitalidade(api):
    resposta = json.loads((PASTA / "diagnostico.json").read_text(encoding="utf-8"))
    for categoria in resposta["diagnostico"]["vitalidade"]["categorias"].values():
        categoria["tipos"] = {}
    resposta["diagnostico"]["vitalidade"]["categorias"]["lazer_convivencia"]["tipos"] = TIPOS_LAZER
    api.route("**/api/diagnostico*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(resposta)))
    return api


def abrir_pelo_teclado(page, resumo):
    resumo.focus()
    page.keyboard.press("Enter")
    assert resumo.evaluate("(s) => s.parentElement.open")
    page.keyboard.press("Space")
    assert not resumo.evaluate("(s) => s.parentElement.open")
    page.keyboard.press("Enter")


def test_proximidade_mostra_os_tipos_e_os_mais_proximos_da_categoria(visitando):
    page = visitando("/")
    consulta(page)
    resumo = page.locator("#ipl-categorias summary", has_text="Lazer e convivência")
    abrir_pelo_teclado(page, resumo)
    detalhe = resumo.locator("xpath=..")
    texto = detalhe.inner_text()
    assert "Parque ou área verde: nota" in texto
    assert "Praça: sem dados na fonte" in texto
    assert detalhe.locator("ol li").count() >= 1  # equipamentos da categoria a até 1 km


def test_proximidade_limita_a_lista_e_aponta_a_tabela(visitando):
    page = visitando("/")
    consulta(page)
    detalhe = page.locator("#ipl-categorias details", has_text="Mobilidade")
    detalhe.locator("summary").click()
    assert detalhe.locator("ol li").count() == 5
    assert "Ver como tabela" in detalhe.inner_text()


def test_vitalidade_mostra_os_numeros_de_cada_tipo(com_tipos_na_vitalidade):
    page = com_tipos_na_vitalidade
    page.goto(f"{page.base_url}/")
    consulta(page)
    page.click("#aba-vitalidade")
    resumo = page.locator("#ivep-categorias summary", has_text="Lazer e convivência")
    abrir_pelo_teclado(page, resumo)
    texto = resumo.locator("xpath=..").inner_text()
    assert "Parque ou área verde: 4 no distrito" in texto and "posição 70 de 100" in texto
    assert "Praça: sem dados na fonte" in texto
    assert page.locator("#ivep-categorias details").count() == 1  # só categorias com tipos


def test_detalhes_abertos_sem_violacoes(visitando, axe):
    page = axe
    consulta(page)
    for resumo in page.locator("#ipl-categorias summary").all():
        resumo.click()
    assert violacoes(page, "#painel-proximidade") == []


def test_parque_de_acesso_restrito_e_identificado(api):
    resposta = json.loads((PASTA / "diagnostico.json").read_text(encoding="utf-8"))
    parque = resposta["diagnostico"]["proximidade"]["tipos"]["parque_area_verde"]
    parque |= {"nome": "Campo Cerrado", "distancia_m": 120.0, "nota": 30.0, "acesso_restrito": True,
               "aviso": "o mais próximo é parque de conservação ou natural, de acesso restrito; "
                        "conta com 30% da nota de um equipamento aberto ao público"}
    api.route("**/api/diagnostico*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(resposta)))
    api.goto(f"{api.base_url}/")
    consulta(api)
    detalhe = api.locator("#ipl-categorias details", has_text="Lazer e convivência")
    detalhe.locator("summary").click()
    texto = detalhe.inner_text()
    assert "Campo Cerrado" in texto and "acesso restrito" in texto and "30%" in texto
