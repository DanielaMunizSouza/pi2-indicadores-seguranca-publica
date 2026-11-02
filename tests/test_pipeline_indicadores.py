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
