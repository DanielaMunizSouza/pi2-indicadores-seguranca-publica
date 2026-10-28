"""Diagnóstico socioespacial de um endereço (UC02, UC02a, UC03).

Combina as regras de domínio em três blocos independentes (RN07):
proximidade do endereço aos equipamentos e IPL (RF07, RF23, RF24), vitalidade
do distrito e IVEP (RF08, RF09) e taxas oficiais de ocorrências (RF10).

Banco e serviços externos chegam como dependências (repositório, consulta de
CEP e geocodificadores), para que os testes usem dublês.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from geohabita.application.cep_lookup import Address
from geohabita.domain.diagnosis import build_diagnosis
from geohabita.domain.equipment import (
    EQUIPMENT_CATEGORY,
    LISTING_RADII_M,
    NearbyEquipment,
    missing_type_message,
    within_radius,
)
from geohabita.domain.proximity import (
    category_note,
    local_proximity_index,
    proximity_note,
    walking_time_minutes,
)
from geohabita.domain.rates import (
    INSUFFICIENT_DATA_MESSAGE,
    OCCURRENCE_GROUPS,
    SUBNOTIFICATION_NOTICE,
    annual_rate_per_100k,
    complete_years_window,
    is_comparable,
    trend_direction,
)
from geohabita.domain.territory import (
    APPROXIMATE_LOCATION_NOTICE,
    OUT_OF_CITY_MESSAGE,
    is_sao_paulo,
)
from geohabita.domain.thresholds import CATEGORIES, EQUIPMENT_THRESHOLDS
from geohabita.domain.vitality import DEFAULT_WEIGHT, is_valid_weight, public_space_vitality_index

STRAIGHT_LINE_LABEL = "distância em linha reta"  # RN12: a interface identifica a medida
UNAVAILABLE_LAYER_MESSAGE = (
    "camada indisponível na fonte de dados no momento; o tipo fica fora do cálculo"
)
OCCURRENCE_NOTE = (
    "Contam apenas registros com coordenada dentro do distrito. Cada natureza é uma "
    "taxa à parte: o roubo de celular também está incluído em roubo."
)

Geocoder = Callable[[str], "tuple[float, float] | None"]


@dataclass(frozen=True)
class District:
    code: str
    name: str
    region: str | None = None


class LocationNotFoundError(LookupError):
    """Nenhuma fonte forneceu coordenadas para o CEP."""


class DiagnosisRepository(Protocol):
    def district_at(self, latitude: float, longitude: float) -> District | None: ...
    def available_types(self) -> set[str]: ...
    def nearest_by_type(self, latitude: float, longitude: float, types: Sequence[str]) -> list[NearbyEquipment]: ...
    def equipment_within(self, latitude: float, longitude: float, radius_m: float,
                         types: Sequence[str]) -> list[NearbyEquipment]: ...
    def district_indicators(self) -> Mapping[str, Mapping[tuple[str, str, int], float]]: ...
    def populations(self) -> Mapping[str, int]: ...


class CepLookupLike(Protocol):
    def lookup(self, raw_cep: str) -> Address: ...


def validated_weights(weights: Mapping[str, Any] | None) -> dict[str, int]:
    """Pesos das seis categorias (padrão 1); cada um deve ser inteiro de 0 a 5 (RN06)."""
    result = {category: DEFAULT_WEIGHT for category in CATEGORIES}
    for category, weight in (weights or {}).items():
        if category not in result:
            raise ValueError(f"Categoria desconhecida: {category}.")
        if not is_valid_weight(weight):
            raise ValueError(f"O peso de {category} deve ser um inteiro de 0 a 5.")
        result[category] = int(weight)
    if sum(result.values()) == 0:
        raise ValueError("Ao menos uma categoria precisa de peso maior que zero.")
    return result


class DiagnosisService:
    def __init__(self, repository: DiagnosisRepository, cep_lookup: CepLookupLike,
                 geocoders: Sequence[tuple[str, Geocoder]] = (),
                 today: Callable[[], date] = date.today) -> None:
        self.repository = repository
        self.cep_lookup = cep_lookup
        self.geocoders = list(geocoders)
        self.today = today

    # --- entradas ------------------------------------------------------------
    def diagnose_cep(self, raw_cep: str, weights: Mapping[str, Any] | None = None) -> dict[str, Any]:
        pesos = validated_weights(weights)
        address = self.cep_lookup.lookup(raw_cep)
        endereco = {"cep": address.cep, "logradouro": address.street, "bairro": address.neighbourhood,
                    "municipio": address.city}
        if not is_sao_paulo(address.ibge_code):
            return {"local": {"endereco": endereco}, "dentro_sao_paulo": False,
                    "aviso": OUT_OF_CITY_MESSAGE, "diagnostico": None}
        latitude, longitude, origem = self._locate(address)
        resultado = self._diagnose(latitude, longitude, origem, pesos)
        resultado["local"]["endereco"] = endereco
        resultado["local"]["aviso_localizacao"] = APPROXIMATE_LOCATION_NOTICE
        return resultado

    def diagnose_point(self, latitude: float, longitude: float,
                       weights: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self._diagnose(latitude, longitude, "informada", validated_weights(weights))

    def _locate(self, address: Address) -> tuple[float, float, str]:
        if address.latitude is not None and address.longitude is not None:
            return address.latitude, address.longitude, "servico_cep"
        for name, geocode in self.geocoders:
            point = geocode(address.cep)
            if point is not None:
                return point[0], point[1], name
        raise LocationNotFoundError("Não foi possível obter a localização deste CEP.")

    def _diagnose(self, latitude: float, longitude: float, origem: str, pesos: dict[str, int]) -> dict[str, Any]:
        local = {"latitude": latitude, "longitude": longitude, "origem_coordenada": origem}
        district = self.repository.district_at(latitude, longitude)
        if district is None:
            return {"local": local, "dentro_sao_paulo": False, "aviso": OUT_OF_CITY_MESSAGE, "diagnostico": None}
        local["distrito"] = {"codigo": district.code, "nome": district.name, "regiao": district.region}
        indicators = self.repository.district_indicators()
        diagnostico = build_diagnosis(
            self.proximity(latitude, longitude, pesos),
            self.vitality(district.code, indicators, pesos),
            self.occurrences(district.code, indicators),
        )
        return {"local": local, "dentro_sao_paulo": True, "aviso": None, "pesos": pesos,
                "diagnostico": diagnostico}

    # --- bloco 1: proximidade (RF07, RF23, RF24) -----------------------------
    def proximity(self, latitude: float, longitude: float, pesos: Mapping[str, int]) -> dict[str, Any]:
        available = sorted(self.repository.available_types() & set(EQUIPMENT_THRESHOLDS))
        nearest = {e.type: e for e in self.repository.nearest_by_type(latitude, longitude, available)}
        around = self.repository.equipment_within(latitude, longitude, max(LISTING_RADII_M), available)
        tipos: dict[str, dict[str, Any]] = {}
        for tipo, limiar in EQUIPMENT_THRESHOLDS.items():
            info: dict[str, Any] = {"categoria": EQUIPMENT_CATEGORY[tipo], "disponivel": tipo in available,
                                    "ideal_m": limiar.ideal_m, "maxima_m": limiar.max_m}
            if tipo not in available:
                tipos[tipo] = info | {"nota": None, "distancia_m": None, "nome": None,
                                      "tempo_caminhada_min": None, "ate_500m": None, "ate_1km": None,
                                      "aviso": UNAVAILABLE_LAYER_MESSAGE}
                continue
            mais_proximo = nearest.get(tipo)
            distancia = round(mais_proximo.distance_m, 1) if mais_proximo else None
            nota = proximity_note(distancia, limiar.ideal_m, limiar.max_m)
            fora = distancia is None or distancia >= limiar.max_m
            tipos[tipo] = info | {
                "nota": round(nota, 1),
                "distancia_m": distancia,
                "nome": mais_proximo.name if mais_proximo else None,
                "tempo_caminhada_min": walking_time_minutes(distancia) if distancia is not None else None,
                "ate_500m": sum(1 for e in around if e.type == tipo and e.distance_m <= 500),
                "ate_1km": sum(1 for e in around if e.type == tipo and e.distance_m <= 1000),
                "aviso": missing_type_message(limiar.max_m) if fora else None,
            }
        categorias: dict[str, dict[str, Any]] = {}
        notas, pesos_ipl = [], []
        for categoria in CATEGORIES:
            notas_tipo = [t["nota"] for t in tipos.values() if t["categoria"] == categoria and t["disponivel"]]
            nota = category_note(notas_tipo) if notas_tipo else None
            categorias[categoria] = {"nota": round(nota, 1) if nota is not None else None,
                                     "peso": pesos[categoria],
                                     "aviso": None if notas_tipo else UNAVAILABLE_LAYER_MESSAGE}
            if nota is not None:
                notas.append(nota)
                pesos_ipl.append(pesos[categoria])
        incluidas = [c for c in CATEGORIES if categorias[c]["nota"] is not None]
        ipl = local_proximity_index(notas, pesos_ipl) if sum(pesos_ipl) else None
        entorno = {
            categoria: [{"tipo": e.type, "nome": e.name, "distancia_m": round(e.distance_m, 1)} for e in itens]
            for categoria, itens in within_radius(around, max(LISTING_RADII_M)).items()
        }
        return {"ipl": round(ipl, 1) if ipl is not None else None, "medida": STRAIGHT_LINE_LABEL,
                "categorias_no_indice": incluidas, "categorias": categorias, "tipos": tipos, "entorno": entorno}

    # --- bloco 2: vitalidade (RF08, RF09) -------------------------------------
    def vitality(self, code: str, indicators: Mapping[str, Mapping[tuple[str, str, int], float]],
                 pesos: Mapping[str, int]) -> dict[str, Any]:
        lista_pesos = [pesos[c] for c in CATEGORIES]

        def ivep(dados: Mapping[tuple[str, str, int], float]) -> float:
            return public_space_vitality_index([dados.get(("percentil", c, 0), 0.0) for c in CATEGORIES],
                                               lista_pesos)

        dados = indicators.get(code, {})
        todos = [ivep(d) for d in indicators.values() if any(k[0] == "percentil" for k in d)]
        categorias = {c: {"percentil": dados.get(("percentil", c, 0)),
                          "equipamentos": dados.get(("equipamentos", c, 0)),
                          "densidade_km2": dados.get(("densidade_km2", c, 0)),
                          "densidade_10k_hab": dados.get(("densidade_10k_hab", c, 0)),
                          "peso": pesos[c]} for c in CATEGORIES}
        return {"ivep": round(ivep(dados), 1),
                "mediana_municipal": round(statistics.median(todos), 1) if todos else None,
                "categorias": categorias}

    # --- bloco 3: ocorrências (RF10) ------------------------------------------
    def occurrences(self, code: str,
                    indicators: Mapping[str, Mapping[tuple[str, str, int], float]]) -> dict[str, Any]:
        primeiro, ultimo = complete_years_window(self.today())
        anos = list(range(primeiro, ultimo + 1))
        populacoes = self.repository.populations()
        pop_distrito, pop_cidade = populacoes.get(code, 0), sum(populacoes.values())
        dados = indicators.get(code, {})
        naturezas = {}
        for grupo, rotulo in OCCURRENCE_GROUPS.items():
            por_ano = [int(dados.get(("ocorrencias", grupo, ano), 0)) for ano in anos]
            total = sum(por_ano)
            cidade = sum(d.get(("ocorrencias", grupo, ano), 0) for d in indicators.values() for ano in anos)
            municipal = annual_rate_per_100k(cidade, pop_cidade, len(anos)) if pop_cidade else None
            item: dict[str, Any] = {"rotulo": rotulo, "ocorrencias": total,
                                    "ocorrencias_por_ano": dict(zip(anos, por_ano)),
                                    "taxa_municipal_100k_ano": round(municipal, 1) if municipal is not None else None}
            if is_comparable(total) and pop_distrito:
                item |= {"taxa_100k_ano": round(annual_rate_per_100k(total, pop_distrito, len(anos)), 1),
                         "taxa_por_ano": {ano: round(annual_rate_per_100k(n, pop_distrito, 1), 1)
                                          for ano, n in zip(anos, por_ano)},
                         "tendencia": trend_direction(por_ano), "mensagem": None}
            else:
                item |= {"taxa_100k_ano": None, "taxa_por_ano": None, "tendencia": None,
                         "mensagem": INSUFFICIENT_DATA_MESSAGE}
            naturezas[grupo] = item
        return {"janela": [primeiro, ultimo], "populacao": pop_distrito, "naturezas": naturezas,
                "aviso_subnotificacao": SUBNOTIFICATION_NOTICE, "observacao": OCCURRENCE_NOTE}
