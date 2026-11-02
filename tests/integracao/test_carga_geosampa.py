"""Carga das camadas do GeoSampa: só equipamentos existentes, e sem sobras de cargas antigas."""

import json

import psycopg
import pytest

pytestmark = pytest.mark.integracao


class SemProgresso:
    def inicio(self, *a, **k): ...
    def avanco(self, *a, **k): ...
    def fim(self, *a, **k): ...


def parque(ident, situacao, categoria="Parque Urbano"):
    return {"type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[-46.7, -23.6], [-46.69, -23.6], [-46.69, -23.59],
                                                             [-46.7, -23.59], [-46.7, -23.6]]]},
            "properties": {"cd_identificador": ident, "nm_parque": f"Parque {ident}",
                           "tx_tipo_situacao_projeto": situacao,
                           "tx_tipo_categoria_parque_unidade_conservacao": categoria}}


def gravar(tmp_path, feicoes):
    arquivo = tmp_path / "pde_parque_municipal.geojson"
    arquivo.write_text(json.dumps({"type": "FeatureCollection", "features": feicoes}), encoding="utf-8")
    return arquivo


@pytest.fixture
def pipeline(url_teste, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", url_teste)
    from scripts import pipeline_dados
    yield pipeline_dados
    with psycopg.connect(url_teste) as conn:
        conn.execute("DELETE FROM public.equipamento_publico WHERE camada = 'pde_parque_municipal'")


def parques_no_banco(url):
    with psycopg.connect(url) as conn:
        return sorted(r[0] for r in conn.execute(
            "SELECT nome FROM public.equipamento_publico WHERE camada = 'pde_parque_municipal'"))


def test_parques_propostos_nao_sao_carregados(pipeline, tmp_path, url_teste):
    arquivo = gravar(tmp_path, [parque(1, "Existente"), parque(2, "Proposto")])
    assert pipeline.carregar_camada("pde_parque_municipal", "lazer_convivencia", "parque_area_verde",
                                    arquivo, SemProgresso()) == 1
    assert parques_no_banco(url_teste) == ["Parque 1"]


def test_recarga_apaga_o_que_saiu_da_fonte(pipeline, tmp_path, url_teste):
    args = ("pde_parque_municipal", "lazer_convivencia", "parque_area_verde")
    pipeline.carregar_camada(*args, gravar(tmp_path, [parque(1, "Existente"), parque(3, "Existente")]), SemProgresso())
    # O parque 3 passou a constar como proposto: some do banco na carga seguinte.
    pipeline.carregar_camada(*args, gravar(tmp_path, [parque(1, "Existente"), parque(3, "Proposto")]), SemProgresso())
    assert parques_no_banco(url_teste) == ["Parque 1"]


def test_parques_de_conservacao_e_naturais_viram_tipo_restrito(pipeline, tmp_path, url_teste):
    arquivo = gravar(tmp_path, [parque(1, "Existente", "Parque Urbano"),
                                parque(2, "Existente", "Parque de Conservação"),
                                parque(3, "Existente", "Parque Natural")])
    pipeline.carregar_camada("pde_parque_municipal", "lazer_convivencia", "parque_area_verde",
                             arquivo, SemProgresso())
    with psycopg.connect(url_teste) as conn:
        tipos = dict(conn.execute("SELECT nome, tipo FROM public.equipamento_publico "
                                  "WHERE camada = 'pde_parque_municipal'").fetchall())
    assert tipos == {"Parque 1": "parque_area_verde", "Parque 2": "parque_conservacao",
                     "Parque 3": "parque_conservacao"}
