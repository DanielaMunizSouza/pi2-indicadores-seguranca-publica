"""Etapa `indicadores`: percentil do tipo, média dos tipos na categoria e agregados."""

import pytest

from scripts.atualizar_indicadores import SO_AREA, equipment_rows

pytestmark = pytest.mark.integracao

DISTRITOS = {  # código -> (população, área km²)
    "01": (100_000, 10.0),
    "02": (200_000, 20.0),
}


class Conn:
    def __init__(self, contagem):
        self.contagem = contagem

    def execute(self, sql, params=None):
        if "ST_Area" in sql:
            rows = [(c, pop, area) for c, (pop, area) in DISTRITOS.items()]
        else:
            rows = [(c, t, n) for (c, t), n in self.contagem.items()]
        return iter(rows)


def test_percentil_da_categoria_e_a_media_dos_seus_tipos():
    # 01: 100 postes e 10 pontos de wi-fi; 02: 20 postes e 40 pontos de wi-fi.
    contagem = {("01", "iluminacao_publica"): 100, ("01", "wifi_publico"): 10,
                ("02", "iluminacao_publica"): 20, ("02", "wifi_publico"): 40}
    linhas = equipment_rows(Conn(contagem))

    def percentil(sub, cod):
        return next(v for c, i, s, _, v in linhas if c == cod and i == "percentil" and s == sub)
    assert percentil("iluminacao_publica", "01") == 100.0  # maior densidade de postes
    assert percentil("wifi_publico", "01") == 0.0  # menor oferta de wi-fi
    assert percentil("conectividade", "01") == pytest.approx(50.0)  # média dos dois tipos


def test_iluminacao_e_medida_so_por_area_mas_conta_na_categoria():
    linhas = equipment_rows(Conn({("01", "iluminacao_publica"): 100, ("02", "iluminacao_publica"): 20}))
    chaves = {(i, s) for _, i, s, _, _ in linhas}
    assert ("densidade_10k_hab", "iluminacao_publica") not in chaves
    assert ("densidade_km2", "iluminacao_publica") in chaves
    assert SO_AREA == {"iluminacao_publica"}
    agregado = [v for c, i, s, _, v in linhas if c == "01" and i == "equipamentos" and s == "conectividade"]
    assert agregado == [100]


def test_tipo_sem_dados_na_fonte_fica_fora_da_categoria():
    # Nenhuma praça carregada: a categoria é só o percentil dos parques, e não a
    # média com um 50 artificial (todos os distritos empatados em zero).
    linhas = equipment_rows(Conn({("01", "parque_area_verde"): 1, ("02", "parque_area_verde"): 10}))
    assert not [s for _, _, s, _, _ in linhas if s == "praca"]
    lazer = {c: v for c, i, s, _, v in linhas if i == "percentil" and s == "lazer_convivencia"}
    assert lazer == {"01": 0.0, "02": 100.0}


def test_categoria_sem_nenhum_tipo_na_fonte_nao_tem_percentil():
    linhas = equipment_rows(Conn({("01", "parque_area_verde"): 1, ("02", "parque_area_verde"): 10}))
    assert not [s for _, i, s, _, _ in linhas if s == "conectividade"]


def test_parque_de_conservacao_soma_no_parque_com_peso_reduzido():
    # 01: 1 parque aberto; 02: 2 parques de conservação (valem 0,6 parque ponderado).
    linhas = equipment_rows(Conn({("01", "parque_area_verde"): 1, ("02", "parque_conservacao"): 2}))

    def valor(indicador, sub, cod):
        return next(v for c, i, s, _, v in linhas if c == cod and i == indicador and s == sub)
    assert not [s for _, _, s, _, _ in linhas if s == "parque_conservacao"]
    assert valor("equipamentos", "parque_area_verde", "02") == 2  # a contagem exibida é inteira
    assert valor("densidade_km2", "parque_area_verde", "02") == pytest.approx(0.6 / 20.0)
    # 01: 1 parque em 10 km² (0,1/km²) > 02: 0,6 em 20 km² (0,03/km²).
    assert valor("percentil", "parque_area_verde", "01") > valor("percentil", "parque_area_verde", "02")
