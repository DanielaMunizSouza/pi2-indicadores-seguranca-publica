"""Tela de diagnóstico: acessibilidade (RNF03, RNF04; CT14, CT15) e consulta (CT01, RF03)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

REGRAS_AXE = {"wcag2a", "wcag2aa", "wcag21a", "wcag21aa"}


def violacoes(page, seletor: str | None = None) -> list[dict]:
    """Violações WCAG AA reportadas pelo axe-core (críticas, sérias e moderadas)."""
    page.wait_for_function("window.axe !== undefined")
    resultado = page.evaluate(
        """([alvo, tags]) => new Promise((resolve) => axe.run(alvo || document,
              {runOnly: {type: 'tag', values: tags}, resultTypes: ['violations']})
              .then(r => resolve(r.violations)))""",
        [seletor, sorted(REGRAS_AXE)])
    return [{"id": v["id"], "impacto": v["impact"], "alvos": [n["target"] for n in v["nodes"]]}
            for v in resultado if v.get("impact") in {"critical", "serious", "moderate"}]


def consulta(page, cep="01310-200", numero=None):
    """Preenche o formulário e espera o diagnóstico aparecer."""
    page.fill("#cep", cep)
    if numero:
        page.fill("#numero", numero)
    page.click("#consultar")
    page.wait_for_function("document.getElementById('local-distrito').textContent.startsWith('Distrito:')")
    page.wait_for_function("document.querySelectorAll('#tipos tr td').length > 3")


def test_pagina_inicial_sem_violacoes_criticas(visitando, axe):
    page = visitando("/")
    page.wait_for_selector("#consulta")
    assert violacoes(page) == []


def test_diagnostico_exibido_sem_violacoes_criticas(visitando, axe):
    page = visitando("/")
    consulta(page)
    page.wait_for_selector("#tipos tr")
    assert violacoes(page) == []


def test_contraste_e_fonte_persistem_e_sao_anunciados(visitando, axe):
    page = visitando("/")
    page.click("#btn-contraste")
    page.wait_for_selector("#status:has-text('Alto contraste ligado')")
    assert page.get_attribute("#btn-contraste", "aria-pressed") == "true"
    assert page.evaluate("document.documentElement.classList.contains('alto-contraste')")
    page.click("#btn-fonte-maior")
    tamanho = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--fonte-base')")
    assert tamanho.strip() == "112.5%"
    page.wait_for_selector("#status:has-text('Fonte')")
    assert "113%" in page.inner_text("#status")  # 112,5% arredondado na anúncio
    page.reload()
    page.wait_for_selector("#btn-contraste")
    assert page.evaluate("document.documentElement.classList.contains('alto-contraste')")
    assert page.evaluate("localStorage.getItem('geohabita.fonte')") == "2"


def test_navegacao_por_teclado_entre_as_abas(visitando):
    # Sem axe: aqui o que se verifica é a operabilidade por teclado (RNF04).
    page = visitando("/")
    page.focus("#aba-proximidade")
    page.keyboard.press("ArrowRight")
    assert page.evaluate("document.activeElement.id") == "aba-vitalidade"
    assert not page.locator("#painel-vitalidade").is_hidden()
    page.keyboard.press("End")
    assert page.evaluate("document.activeElement.id") == "aba-tabela"
    page.keyboard.press("ArrowRight")
    assert page.evaluate("document.activeElement.id") == "aba-proximidade"


def test_ct15_andamento_e_erro_sao_anunciados_na_regiao_viva(visitando):
    page = visitando("/")
    assert page.get_attribute("#status", "role") == "status"
    assert page.get_attribute("#status", "aria-live") == "polite"
    page.fill("#cep", "01310-200")
    page.click("#consultar")
    page.wait_for_function("document.getElementById('status').textContent.includes('Diagnóstico')")


def test_ct01_formato_invalido_nao_chama_a_api(visitando):
    page = visitando("/")
    chamadas = []
    page.route("**/api/diagnostico**", lambda route: (chamadas.append(route.request.url), route.abort()))
    page.fill("#cep", "1234")
    page.click("#consultar")
    assert "8 números" in page.inner_text("#status")
    assert chamadas == []


def test_consulta_por_cep_com_numero_mostra_o_distrito_e_o_aviso(visitando):
    page = visitando("/")
    consulta(page, numero="1578")
    assert "Distrito:" in page.inner_text("#local-distrito")
    assert page.inner_text("#local-aviso")
    assert "numero=1578" in page.url


def test_iluminacao_aparece_como_densidade_na_tabela(visitando):
    page = visitando("/")
    consulta(page)
    linha = page.locator("#tipos tr", has_text="Iluminação pública")
    linha.wait_for()
    celulas = linha.locator("th, td").all_inner_texts()
    assert "pontos" in celulas[1] and "/km²" in celulas[1]
    assert celulas[2] == "—"  # sem distância: a medida é a densidade do entorno


def test_pesos_recalculam_sem_recarregar_a_pagina(visitando):
    page = visitando("/")
    consulta(page)
    antes = page.inner_text("#ipl")
    navegacoes = page.evaluate("performance.getEntriesByType('navigation').length")
    page.select_option("#peso-mobilidade", "0")
    page.wait_for_selector("#status:has-text('Índices recalculados')")
    assert page.evaluate("performance.getEntriesByType('navigation').length") == navegacoes
    assert antes != ""


def test_busca_por_endereco_offerece_os_trechos_de_numeracao(visitando):
    page = visitando("/")
    page.fill("#logradouro", "Avenida Paulista")
    page.click("#consultar")
    page.wait_for_selector("#candidatos:not([hidden]) ul li button, #resultado:not([hidden])", timeout=5000)
    if not page.locator("#resultado:not([hidden])").count():
        botoes = page.locator("#candidatos button.candidato")
        assert botoes.count() > 0
        assert "CEP" in botoes.first.inner_text()
        botoes.first.click()
        page.wait_for_selector("#resultado:not([hidden])")


def test_reflow_em_360_pixels_sem_violacoes(visitando, axe):
    page = visitando("/")
    page.set_viewport_size({"width": 360, "height": 740})
    consulta(page)
    assert page.evaluate("document.documentElement.scrollWidth") <= 372
    assert violacoes(page) == []


def test_baixar_csv_produz_arquivo_legivel(visitando):
    page = visitando("/")
    consulta(page)
    with page.expect_download() as captura:
        page.click("button:has-text('Baixar diagnóstico em CSV')")
    download = captura.value
    assert download.suggested_filename.startswith("geohabita-")
    caminho = download.path()
    conteudo = Path(caminho).read_text(encoding="utf-8-sig")
    assert conteudo.splitlines()[0].startswith("bloco;indicador;")
    linhas = conteudo.splitlines()
    assert any(linha.startswith("proximidade;IPL;") for linha in linhas)
    assert any(linha.startswith("vitalidade;IVEP;") for linha in linhas)
    assert any(linha.startswith("ocorrencias;natureza;") for linha in linhas)
    assert any(linha.startswith("fontes;") for linha in linhas)
    ilum = [linha for linha in linhas if linha.startswith("proximidade;tipo;iluminacao_publica;")]
    assert ilum and "pontos no raio de 300 m" in ilum[0]
    assert "Diagnóstico concluído" in page.inner_text("#status") or "CSV" in page.inner_text("#status")
