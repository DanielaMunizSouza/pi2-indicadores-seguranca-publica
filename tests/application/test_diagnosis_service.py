"""Testes do diagnóstico socioespacial (UC02; RF07, RF08, RF10, RF23, RF24; RN07).

O repositório e a consulta de CEP são dublês: os testes verificam como o caso
de uso combina as regras de domínio, sem banco nem rede.
"""

from datetime import date

import pytest

from geohabita.application.cep_lookup import Address
from geohabita.application.diagnosis import (
    DiagnosisService,
    District,
    LocationNotFoundError,
)
from geohabita.domain.diagnosis import DIAGNOSIS_BLOCKS
from geohabita.domain.equipment import NearbyEquipment
from geohabita.domain.rates import INSUFFICIENT_DATA_MESSAGE
from geohabita.domain.territory import APPROXIMATE_LOCATION_NOTICE, OUT_OF_CITY_MESSAGE
from geohabita.domain.thresholds import CATEGORIES

SE = District("01", "SÉ", "Centro")
CATEGORIAS = list(CATEGORIES)


def indicadores(percentis_por_distrito, ocorrencias=None):
    dados = {}
    for codigo, percentis in percentis_por_distrito.items():
        linha = dados.setdefault(codigo, {})
        for categoria, p in zip(CATEGORIAS, percentis):
            linha[("percentil", categoria, 0)] = p
            linha[("equipamentos", categoria, 0)] = 10
            linha[("densidade_km2", categoria, 0)] = 1.0
            linha[("densidade_10k_hab", categoria, 0)] = 2.0
    for (codigo, grupo, ano), n in (ocorrencias or {}).items():
        dados.setdefault(codigo, {})[("ocorrencias", grupo, ano)] = n
    return dados


class FakeRepository:
    def __init__(self, district=SE, available=None, nearest=(), within=(), indicators=None,
                 populations=None, centroid=None):
        self.district = district
        self.available = available if available is not None else {
            "parque_area_verde", "ponto_onibus", "estacao_metro_trem", "unidade_basica_saude"}
        self.nearest = list(nearest)
        self.within = list(within)
        self.indicators = indicators or indicadores({"01": [50] * 6, "02": [10] * 6, "03": [90] * 6})
        self.populations_ = populations or {"01": 100_000, "02": 100_000, "03": 200_000}
        self.centroid = centroid

    def district_at(self, lat, lon):
        return self.district

    def available_types(self):
        return set(self.available)

    def nearest_by_type(self, lat, lon, types):
        return [e for e in self.nearest if e.type in types]

    def equipment_within(self, lat, lon, radius_m, types):
        return [e for e in self.within if e.type in types and e.distance_m <= radius_m]

    def district_indicators(self):
        return self.indicators

    def populations(self):
        return self.populations_

    def cep_centroid(self, cep):
        return self.centroid


class FakeCepLookup:
    def __init__(self, address):
        self.address = address

    def lookup(self, cep):
        return self.address


def service(repo=None, address=None, geocoders=()):
    return DiagnosisService(repo or FakeRepository(), FakeCepLookup(address), geocoders=geocoders,
                            today=lambda: date(2026, 11, 1))


# --- localização ------------------------------------------------------------

def test_cep_with_coordinates_from_the_cep_service_is_used_directly():
    endereco = Address("01001000", "Praça da Sé", "Sé", "São Paulo", "3550308", -23.55, -46.63)
    resultado = service(address=endereco).diagnose_cep("01001-000")
    assert resultado["local"]["origem_coordenada"] == "servico_cep"
    assert resultado["local"]["aviso_localizacao"] == APPROXIMATE_LOCATION_NOTICE
    assert resultado["local"]["distrito"]["codigo"] == "01"


def test_fallback_geocoder_supplies_missing_coordinates():
    endereco = Address("01001000", "Praça da Sé", "Sé", "São Paulo", "3550308")
    s = service(address=endereco, geocoders=[("vazio", lambda cep: None), ("reserva", lambda cep: (-23.5, -46.6))])
    assert s.diagnose_cep("01001000")["local"]["origem_coordenada"] == "reserva"


def test_cep_without_any_coordinate_cannot_be_diagnosed():
    endereco = Address("01001000", "Praça da Sé", "Sé", "São Paulo", "3550308")
    with pytest.raises(LocationNotFoundError):
        service(address=endereco, geocoders=[("vazio", lambda cep: None)]).diagnose_cep("01001000")


def test_cep_outside_the_city_returns_warning_without_diagnosis():
    endereco = Address("06010000", "Rua X", "Centro", "Osasco", "3534401", -23.53, -46.79)
    resultado = service(address=endereco).diagnose_cep("06010000")
    assert resultado["diagnostico"] is None
    assert resultado["aviso"] == OUT_OF_CITY_MESSAGE


def test_point_outside_every_district_returns_warning():
    resultado = service(FakeRepository(district=None)).diagnose_point(-23.0, -46.0)
    assert resultado["diagnostico"] is None
    assert resultado["aviso"] == OUT_OF_CITY_MESSAGE


# --- composição (RN07) ------------------------------------------------------

def test_diagnosis_has_exactly_the_three_independent_blocks():
    resultado = service().diagnose_point(-23.55, -46.63)
    assert tuple(resultado["diagnostico"]) == DIAGNOSIS_BLOCKS


# --- proximidade (RF07, RF23, RF24; RN12, RN15) -----------------------------

def test_type_note_walking_time_and_radius_counts():
    perto = [NearbyEquipment("ponto_onibus", "Ponto A", 200.0),
             NearbyEquipment("ponto_onibus", "Ponto B", 700.0)]
    repo = FakeRepository(nearest=perto[:1], within=perto)
    tipo = service(repo).diagnose_point(-23.55, -46.63)["diagnostico"]["proximidade"]["tipos"]["ponto_onibus"]
    assert tipo["nota"] == 100.0  # 200 m < ideal de 300 m
    assert tipo["tempo_caminhada_min"] == 3  # 200 / 80 arredondado para cima
    assert (tipo["ate_500m"], tipo["ate_1km"]) == (1, 2)
    assert tipo["aviso"] is None


def test_type_beyond_the_maximum_distance_gets_zero_and_a_message():
    repo = FakeRepository(nearest=[NearbyEquipment("unidade_basica_saude", "UBS", 2500.0)])
    tipo = service(repo).diagnose_point(-23.55, -46.63)["diagnostico"]["proximidade"]["tipos"]["unidade_basica_saude"]
    assert tipo["nota"] == 0.0
    assert tipo["aviso"] == "nenhum equipamento deste tipo a menos de 2000 metros"


def test_type_without_source_data_is_left_out_of_the_index():
    bloco = service().diagnose_point(-23.55, -46.63)["diagnostico"]["proximidade"]
    assert bloco["tipos"]["praca"]["disponivel"] is False
    assert bloco["tipos"]["praca"]["nota"] is None
    # comércio de rua não tem nenhum tipo com dados no dublê: fica fora do IPL
    assert bloco["categorias"]["comercio_rua"]["nota"] is None
    assert "comercio_rua" not in bloco["categorias_no_indice"]


def test_ipl_is_the_weighted_mean_of_available_categories():
    repo = FakeRepository(available={"parque_area_verde", "ponto_onibus"},
                          nearest=[NearbyEquipment("parque_area_verde", "Parque", 100.0),
                                   NearbyEquipment("ponto_onibus", "Ponto", 900.0)])
    pesos = {c: 1 for c in CATEGORIAS} | {"lazer_convivencia": 3}
    bloco = service(repo).diagnose_point(-23.55, -46.63, pesos)["diagnostico"]["proximidade"]
    # lazer = 100 (peso 3); mobilidade = 0 (peso 1) -> 75
    assert bloco["ipl"] == pytest.approx(75.0)
    assert bloco["medida"] == "distância em linha reta"


def test_surroundings_are_grouped_by_category_and_sorted():
    perto = [NearbyEquipment("ponto_onibus", "B", 700.0), NearbyEquipment("ponto_onibus", "A", 100.0),
             NearbyEquipment("parque_area_verde", "Parque", 400.0)]
    bloco = service(FakeRepository(within=perto)).diagnose_point(-23.55, -46.63)["diagnostico"]["proximidade"]
    assert [e["nome"] for e in bloco["entorno"]["mobilidade"]] == ["A", "B"]
    assert bloco["entorno"]["lazer_convivencia"][0]["distancia_m"] == 400.0


# --- vitalidade (RF08; RN06) ------------------------------------------------

def test_ivep_with_default_weights_and_municipal_median():
    bloco = service().diagnose_point(-23.55, -46.63)["diagnostico"]["vitalidade"]
    assert bloco["ivep"] == pytest.approx(50.0)
    assert bloco["mediana_municipal"] == pytest.approx(50.0)
    assert bloco["categorias"]["mobilidade"]["percentil"] == 50


def test_ivep_follows_user_weights():
    percentis = indicadores({"01": [100, 0, 0, 0, 0, 0], "02": [0] * 6})
    pesos = {c: 0 for c in CATEGORIAS} | {"lazer_convivencia": 1}
    bloco = service(FakeRepository(indicators=percentis)).diagnose_point(-23.55, -46.63, pesos)["diagnostico"]["vitalidade"]
    assert bloco["ivep"] == pytest.approx(100.0)


@pytest.mark.parametrize("peso", [6, -1, 1.5, True])
def test_invalid_weight_is_rejected(peso):
    with pytest.raises(ValueError):
        service().diagnose_point(-23.55, -46.63, {"mobilidade": peso})


def test_all_zero_weights_are_rejected():
    with pytest.raises(ValueError):
        service().diagnose_point(-23.55, -46.63, {c: 0 for c in CATEGORIAS})


# --- ocorrências (RF10; RN08, RN09) -----------------------------------------

def test_rate_trend_and_municipal_rate_over_the_complete_years_window():
    ocorrencias = {("01", "furto", 2023): 100, ("01", "furto", 2024): 100, ("01", "furto", 2025): 130,
                   ("01", "furto", 2026): 999,  # ano corrente, fora da janela
                   ("02", "furto", 2023): 50, ("02", "furto", 2024): 50, ("02", "furto", 2025): 50}
    repo = FakeRepository(indicators=indicadores({"01": [50] * 6, "02": [50] * 6}, ocorrencias),
                          populations={"01": 100_000, "02": 100_000})
    bloco = service(repo).diagnose_point(-23.55, -46.63)["diagnostico"]["ocorrencias"]
    furto = bloco["naturezas"]["furto"]
    assert bloco["janela"] == [2023, 2025]
    assert furto["ocorrencias"] == 330
    assert furto["taxa_100k_ano"] == pytest.approx(110.0)
    assert furto["tendencia"] == "alta"
    assert furto["taxa_municipal_100k_ano"] == pytest.approx(480 / (200_000 * 3) * 100_000)
    assert "subnotifica" in bloco["aviso_subnotificacao"].lower()


def test_group_below_minimum_shows_message_without_rate_or_trend():
    ocorrencias = {("01", "crimes_contra_vida", 2024): 12}
    repo = FakeRepository(indicators=indicadores({"01": [50] * 6}, ocorrencias), populations={"01": 100_000})
    grupo = service(repo).diagnose_point(-23.55, -46.63)["diagnostico"]["ocorrencias"]["naturezas"]["crimes_contra_vida"]
    assert grupo["ocorrencias"] == 12
    assert grupo["taxa_100k_ano"] is None and grupo["tendencia"] is None
    assert grupo["mensagem"] == INSUFFICIENT_DATA_MESSAGE
