"""Regras que faltavam nas verificações de interface: RN02, RN15 e RF12."""

from __future__ import annotations

import json

import pytest

from tests.e2e.conftest import PASTA
from tests.e2e.test_diagnostico_acessibilidade import consulta

pytestmark = pytest.mark.e2e


def resposta_modificada(ajuste):
    corpo = json.loads((PASTA / "diagnostico.json").read_text(encoding="utf-8"))
    ajuste(corpo)
    return json.dumps(corpo)


def rota_diagnostico(api, corpo):
    api.route("**/api/diagnostico*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=corpo))


def test_rn02_cep_inexistente_anuncia_e_mantem_a_busca_por_endereco(visitando):
    page = visitando("/")
    page.route("**/api/diagnostico*", lambda route: route.fulfill(
        status=404, content_type="application/json", body='{"detail":"CEP não encontrado"}'))
    page.fill("#cep", "99999-999")
    page.click("#consultar")
    page.wait_for_function("document.getElementById('status').textContent.includes('CEP não encontrado')")
    # A busca por endereço continua disponível (RN02: libera a consulta textual).
    assert page.locator("#logradouro").is_enabled()


def test_rn15_tipo_sem_equipamento_proximo_traz_o_aviso(visitando):
    page = visitando("/")

    def escola_sem_equipamento(corpo):
        tipos = corpo["diagnostico"]["proximidade"]["tipos"]
        tipos["escola_publica"]["distancia_m"] = None
        tipos["escola_publica"]["nome"] = None
        tipos["escola_publica"]["nota"] = 0.0
        tipos["escola_publica"]["aviso"] = "nenhum equipamento deste tipo a menos de 2000 metros"
        corpo["diagnostico"]["proximidade"]["entorno"].pop("servicos_essenciais", None)

    rota_diagnostico(page, resposta_modificada(escola_sem_equipamento))
    consulta(page)
    linha = page.locator("#tipos tr", has_text="Escola pública")
    assert "nenhum equipamento deste tipo a menos de 2000 metros" in linha.inner_text()


def test_rf12_fonte_desatualizada_recebe_o_aviso(visitando):
    page = visitando("/")

    def fonte_antiga(corpo):
        for fonte in corpo["fontes"]:
            if fonte["descricao"] == "Equipamentos públicos":
                fonte["data_referencia"] = "2022-01-15"  # mais de 24 meses atrás
                break

    rota_diagnostico(page, resposta_modificada(fonte_antiga))
    consulta(page)
    assert page.locator("#lista-fontes", has_text="dado desatualizado")
