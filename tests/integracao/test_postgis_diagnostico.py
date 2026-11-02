"""Consultas espaciais do diagnóstico no PostGIS (RF05, RF07, RF23; RN12; CT05, CT07, CT17).

Os dados fictícios (``dados.py``) põem cada equipamento a uma distância conhecida
da origem; as distâncias medidas pelo banco são geodésicas, com tolerância de 1%.
"""

import pytest

from geohabita.infrastructure.postgis import PostgisDiagnosisRepository
from tests.integracao.dados import ORIGEM, deslocado

pytestmark = pytest.mark.integracao


@pytest.fixture
def repo(connect):
    return PostgisDiagnosisRepository(connect, cache_s=0)


@pytest.mark.parametrize(("ponto", "codigo"), [
    (deslocado(0, 0), "T1"),
    (deslocado(leste_m=3_000), "T2"),
    (deslocado(norte_m=3_000), "T3"),
])
def test_ct05_distrito_correto_para_pontos_em_tres_distritos(repo, ponto, codigo):
    distrito = repo.district_at(*ponto)
    assert distrito is not None and distrito.code == codigo


def test_ponto_fora_de_todos_os_distritos_nao_tem_distrito(repo):
    assert repo.district_at(*deslocado(leste_m=-5_000)) is None


def test_ct07_lista_so_os_equipamentos_dentro_do_raio(repo):
    itens = repo.equipment_within(*ORIGEM, 1_000, ["ponto_onibus"])
    assert sorted(e.name for e in itens) == ["Ponto 300", "Ponto 800"]
    distancias = sorted(e.distance_m for e in itens)
    assert distancias == [pytest.approx(300, rel=0.01), pytest.approx(800, rel=0.01)]


def test_ct17_ubs_mais_proxima_e_a_de_250_metros(repo):
    (ubs,) = repo.nearest_by_type(*ORIGEM, ["unidade_basica_saude"])
    assert ubs.name == "UBS Perto"
    assert ubs.distance_m == pytest.approx(250, rel=0.01)


def test_rn12_distancia_ao_parque_vai_ate_o_contorno(repo):
    (parque,) = repo.nearest_by_type(*ORIGEM, ["parque_area_verde"])
    assert parque.distance_m == pytest.approx(400, rel=0.01)  # o centro do parque fica a 500 m
    assert (parque.latitude, parque.longitude) == pytest.approx(deslocado(norte_m=-400), abs=1e-5)


def test_tipo_sem_equipamento_nao_aparece_no_vizinho_mais_proximo(repo):
    tipos = {e.type for e in repo.nearest_by_type(*ORIGEM, ["estacao_metro_trem", "ponto_onibus"])}
    assert tipos == {"ponto_onibus"}


def test_iluminacao_conta_os_pontos_dentro_do_raio(repo):
    assert repo.lighting_within(*ORIGEM, 300) == 5
    assert repo.lighting_within(*ORIGEM, 600) == 8


def test_iluminacao_fica_fora_da_busca_de_vizinhos(repo):
    assert repo.equipment_within(*ORIGEM, 1_000, ["iluminacao_publica"]) == []


def test_tipos_disponiveis_sao_os_carregados(repo):
    assert repo.available_types() == {"unidade_basica_saude", "ponto_onibus", "parque_area_verde",
                                      "escola_publica", "iluminacao_publica", "feira_mercado_municipal"}


def test_detalhes_de_funcionamento_chegam_com_o_equipamento(repo):
    (feira,) = repo.nearest_by_type(*ORIGEM, ["feira_mercado_municipal"])
    assert feira.details == {"dia": "domingo"}
    (no_raio,) = repo.equipment_within(*ORIGEM, 500, ["feira_mercado_municipal"])
    assert no_raio.details == {"dia": "domingo"}
    (ubs,) = repo.nearest_by_type(*ORIGEM, ["unidade_basica_saude"])
    assert ubs.details is None


def test_populacoes_e_indicadores_por_distrito(repo):
    assert repo.populations() == {"T1": 100_000, "T2": 200_000, "T3": 50_000}
    assert repo.district_indicators()["T1"][("percentil", "mobilidade", 0)] == 80.0


def test_fontes_trazem_as_datas_de_referencia(repo):
    fontes = {f["descricao"]: f for f in repo.data_sources()}
    assert str(fontes["Limites dos 96 distritos"]["data_referencia"]) == "2025-01-01"
    assert fontes["Equipamentos públicos"]["data_referencia"] is not None


def test_limite_do_distrito_em_geojson(connect):
    from geohabita.infrastructure.ocorrencias import PostgisOccurrenceRepository
    repositorio = PostgisOccurrenceRepository(connect)
    feicao = repositorio.district_boundary("T1")
    assert feicao["properties"] == {"codigo": "T1", "nome": "TESTE CENTRO"}
    assert feicao["geometry"]["type"] in {"Polygon", "MultiPolygon"}
    assert repositorio.district_boundary("XX") is None
