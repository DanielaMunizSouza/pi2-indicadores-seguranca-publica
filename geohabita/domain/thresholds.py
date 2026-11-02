"""Limiares por tipo de equipamento, editáveis sem mudar o código (RN13).

Transcreve o Quadro "Limiares iniciais de distância por tipo de equipamento"
da especificação: a distância ideal ``a_j`` é aquela até a qual a nota é
máxima; a distância máxima ``b_j`` é aquela a partir da qual é nula. A
iluminação pública, medida por densidade, tem raio e faixa próprios.

O administrador altera esses números num arquivo TOML, sem tocar no código
(``config/limiares.toml``; caminho na variável ``GEOHABITA_LIMIARES``)::

    [distancia]
    ponto_onibus = { ideal_m = 300, maxima_m = 800 }

    [densidade]
    iluminacao_publica = { raio_m = 300, zero = 150, cem = 1500 }

    [acesso_restrito]
    parque_conservacao = { fator = 0.3 }
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path



@dataclass(frozen=True)
class DistanceThreshold:
    """Par de limiares ``a_j`` (ideal) e ``b_j`` (máxima), em metros."""

    ideal_m: int
    max_m: int


@dataclass(frozen=True)
class DensityThreshold:
    """Raio de contagem e faixa da nota, em pontos por km², da densidade."""

    radius_m: int
    zero_per_km2: float
    full_per_km2: float


@dataclass(frozen=True)
class RestrictedAccess:
    """Variante de acesso restrito de um tipo: conta para ele, com peso reduzido.

    A nota de um equipamento de acesso restrito é multiplicada por ``factor``
    (de 0 a 1) e, no IVEP, cada um conta como ``factor`` equipamento do tipo.
    """

    base_type: str
    factor: float
    label: str


class ThresholdConfigError(ValueError):
    """Arquivo de limiares malformado, com tipo ou valor desconhecido."""


# Nome do tipo medido por densidade (a constante vive aqui para evitar o ciclo:
# lighting.py lê os limiares, e thresholds não lê nada de lighting/equipment).
LIGHTING_TYPE = "iluminacao_publica"

# Calibração inicial da nota de iluminação, em pontos por km²: a densidade
# distrital mediana da cidade é ~655/km² e a mediana no raio de 300 m, ~400/km²;
# periferias sem cadastro ficam perto de zero e o centro passa de 2.000/km².
PADRAO_RAIO_M, PADRAO_ZERO, PADRAO_CEM = 300, 150.0, 1500.0


# Seis categorias de equipamentos do modelo de indicadores.
CATEGORIES: tuple[str, ...] = (
    "lazer_convivencia",
    "cultura_esporte",
    "mobilidade",
    "comercio_rua",
    "servicos_essenciais",
    "conectividade",
)


# Iluminação pública não entra neste quadro: ela é medida pela densidade de
# pontos no entorno (geohabita/domain/lighting.py), porque a distância até a
# luminária mais próxima não distinguiria um distrito de outro.

# Tipos medidos por densidade, que não têm par de limiares de distância.
DENSITY_TYPES: frozenset[str] = frozenset({LIGHTING_TYPE})

# Todos os tipos do modelo de indicadores, na ordem de exibição: os medidos por
# densidade vêm antes dos de distância dentro da sua categoria.
EQUIPMENT_TYPES: dict[str, str] = {
    "praca": "lazer_convivencia",
    "parque_area_verde": "lazer_convivencia",
    "biblioteca_centro_cultural": "cultura_esporte",
    "ceu_equipamento_esportivo": "cultura_esporte",
    "ponto_onibus": "mobilidade",
    "estacao_metro_trem": "mobilidade",
    "ciclovia": "mobilidade",
    "feira_mercado_municipal": "comercio_rua",
    "unidade_basica_saude": "servicos_essenciais",
    "escola_publica": "servicos_essenciais",
    "iluminacao_publica": "conectividade",
    "wifi_publico": "conectividade",
}

# Limiares iniciais por tipo de equipamento medido por distância (Quadro de
# limiares; RN13).
EQUIPMENT_THRESHOLDS: dict[str, DistanceThreshold] = {
    "praca": DistanceThreshold(400, 1200),
    "parque_area_verde": DistanceThreshold(400, 1200),
    "biblioteca_centro_cultural": DistanceThreshold(800, 2000),
    "ceu_equipamento_esportivo": DistanceThreshold(800, 2000),
    "ponto_onibus": DistanceThreshold(300, 800),
    "estacao_metro_trem": DistanceThreshold(800, 2000),
    "ciclovia": DistanceThreshold(800, 2000),
    "feira_mercado_municipal": DistanceThreshold(800, 1500),
    "unidade_basica_saude": DistanceThreshold(800, 2000),
    "escola_publica": DistanceThreshold(800, 2000),
    "wifi_publico": DistanceThreshold(400, 1200),
}

# Parques de conservação e parques naturais do Plano Diretor priorizam a proteção
# ambiental, com visitação restrita ou controlada: somam como área verde, mas com
# peso baixo, para não darem nota alta a um endereço sem parque aberto por perto.
RESTRICTED_TYPES: dict[str, RestrictedAccess] = {
    "parque_conservacao": RestrictedAccess("parque_area_verde", 0.3,
                                           "parque de conservação ou natural, de acesso restrito"),
}

# Limiares dos tipos medidos por densidade (nota da iluminação pública).
DENSITY_THRESHOLDS: dict[str, DensityThreshold] = {
    LIGHTING_TYPE: DensityThreshold(PADRAO_RAIO_M, PADRAO_ZERO, PADRAO_CEM),
}

ARQUIVO_PADRAO = Path("config/limiares.toml")


def _aplicar(distancia: dict, densidade: dict, origem: str, restrito: dict | None = None) -> None:
    if not isinstance(distancia, dict):
        raise ThresholdConfigError(f"a tabela [distancia] de {origem} é obrigatória.")
    for tipo, valores in distancia.items():
        if tipo not in EQUIPMENT_THRESHOLDS:
            raise ThresholdConfigError(f"{origem}: tipo desconhecido {tipo}.")
        if not isinstance(valores, dict):
            raise ThresholdConfigError(f"{origem}: {tipo} exige ideal_m e maxima_m.")
        ideal, maxima = valores.get("ideal_m"), valores.get("maxima_m")
        if not (isinstance(ideal, int) and isinstance(maxima, int) and 0 <= ideal < maxima):
            raise ThresholdConfigError(f"{origem}: {tipo} exige 0 <= ideal_m < maxima_m.")
        EQUIPMENT_THRESHOLDS[tipo] = DistanceThreshold(ideal, maxima)
    for tipo, valores in (densidade or {}).items():
        if tipo not in DENSITY_TYPES:
            raise ThresholdConfigError(f"{origem}: {tipo} não é medido por densidade.")
        if not isinstance(valores, dict):
            raise ThresholdConfigError(f"{origem}: {tipo} exige raio_m, zero e cem.")
        raio, zero, cem = valores.get("raio_m"), valores.get("zero"), valores.get("cem")
        if not (isinstance(raio, int) and raio > 0 and zero is not None and cem is not None
                and float(zero) < float(cem)):
            raise ThresholdConfigError(f"{origem}: {tipo} exige raio_m > 0 e zero < cem.")
        DENSITY_THRESHOLDS[tipo] = DensityThreshold(raio, float(zero), float(cem))
    for tipo, valores in (restrito or {}).items():
        if tipo not in RESTRICTED_TYPES:
            raise ThresholdConfigError(f"{origem}: {tipo} não é um tipo de acesso restrito.")
        fator = valores.get("fator") if isinstance(valores, dict) else None
        if not (isinstance(fator, (int, float)) and not isinstance(fator, bool) and 0 <= fator <= 1):
            raise ThresholdConfigError(f"{origem}: {tipo} exige fator entre 0 e 1.")
        atual = RESTRICTED_TYPES[tipo]
        RESTRICTED_TYPES[tipo] = RestrictedAccess(atual.base_type, float(fator), atual.label)


def load_thresholds(path: Path | str | None = None) -> Path | None:
    """Aplica os limiares do arquivo, se existir; devolve o caminho usado.

    Chame na inicialização do processo (API e pipeline): os dicionários são
    mutados no lugar, então todo o código que os lê passa a ver os valores novos.
    """
    from geohabita.config import THRESHOLDS_FILE  # local: evita dependência circular

    arquivo = Path(path or THRESHOLDS_FILE)
    if not arquivo.is_file():
        return None
    with arquivo.open("rb") as entrada:
        try:
            conteudo = tomllib.load(entrada)
        except tomllib.TOMLDecodeError as exc:
            raise ThresholdConfigError(f"{arquivo.name}: {exc}") from exc
    _aplicar(conteudo.get("distancia", {}), conteudo.get("densidade", {}), arquivo.name,
             conteudo.get("acesso_restrito", {}))
    return arquivo

