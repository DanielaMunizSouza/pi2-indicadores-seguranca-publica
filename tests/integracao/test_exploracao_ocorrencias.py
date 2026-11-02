"""Consultas da página de exploração no PostGIS (RF13, RNF18; /api/summary, /api/areas, /api/map)."""

from datetime import date

import pytest

from geohabita.infrastructure.ocorrencias import OccurrenceFilter, PostgisOccurrenceRepository
from tests.integracao.dados import DISTRITOS, ORIGEM, deslocado

pytestmark = pytest.mark.integracao

# 12 furtos em 2024 + 3 roubos em 2025 + 5 celulares em 2024 + 1 furto em T3 = 21 registros em SP.
TOTAL_SP = 21


@pytest.fixture
def repo(connect):
    return PostgisOccurrenceRepository(connect)


def filtro(**kwargs):
    return OccurrenceFilter(kwargs.pop("start", date(2023, 1, 1)),
                            kwargs.pop("end", date(2025, 12, 31)), **kwargs)


def test_summary_totaliza_por_periodo_categoria_e_mes(repo):
    r = repo.summary(filtro())
    assert r["total"]["total"] == TOTAL_SP
    assert r["total"]["com_cep"] == TOTAL_SP  # todos os registros fictícios têm CEP
    assert r["total"]["com_coordenada"] == TOTAL_SP
    # O agrupamento mensal não distingue categoria (a série é uma só por mês).
    mensal = {m["mes"]: m["total"] for m in r["mensal"]}
    assert mensal[date(2024, 6, 1)] == 6  # 1 furto + 5 celulares
    assert mensal[date(2025, 3, 1)] == 3
    categorias = {c["categoria_dado"]: c["total"] for c in r["categorias"]}
    assert categorias == {"criminal": 16, "celulares_subtraidos": 5}


def test_summary_respeita_o_periodo_e_a_categoria(repo):
    r = repo.summary(filtro(category="criminal", start=date(2024, 1, 1), end=date(2024, 12, 31)))
    assert r["total"]["total"] == 12  # só os furtos de 2024


def test_district_counts_soma_os_georreferenciados_por_distrito(repo):
    por_distrito = {a["codigo"]: a for a in repo.district_counts(filtro())}
    assert len(por_distrito) == len(DISTRITOS)
    assert por_distrito["T1"]["registros"] == 15 and por_distrito["T1"]["populacao"] == 100_000
    assert por_distrito["T2"]["registros"] == 5 and por_distrito["T3"]["registros"] == 1
    assert all(a["distrito"].startswith("TESTE") for a in por_distrito.values())


def test_cep_main_district_reune_o_historico_no_distrito_predominante(repo):
    assert repo.cep_main_district("01310100")["codigo"] == "T1"


def test_map_cells_agrupa_por_grade_e_respeita_a_janela(repo):
    # Todos os pontos fictícios caem a menos de 0,05° da origem: a grade soma 21.
    lat, lon = ORIGEM
    features = repo.map_cells(filtro(), lon - 0.5, lat - 0.5, lon + 0.5, lat + 0.5)
    total = sum(f["registros"] for f in features)
    assert total == 21
    assert all({"longitude", "latitude", "registros"} <= set(f) for f in features)


def test_status_informa_o_postgis_e_a_existencia_de_registros(repo):
    estado = repo.status()
    assert estado["tem_registros"] is True
    assert "GEOS=" in estado["postgis"]
