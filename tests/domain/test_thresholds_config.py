"""Limiares editáveis pelo administrador, sem mudança de código (RN13)."""

import pytest

from geohabita.domain.thresholds import (
    DistanceThreshold,
    EQUIPMENT_THRESHOLDS,
    ThresholdConfigError,
    load_thresholds,
)


@pytest.fixture(autouse=True)
def restaura():
    from geohabita.domain.thresholds import DENSITY_THRESHOLDS, RESTRICTED_TYPES
    originals = dict(EQUIPMENT_THRESHOLDS)
    densidades = dict(DENSITY_THRESHOLDS)
    restritos = dict(RESTRICTED_TYPES)
    yield
    RESTRICTED_TYPES.clear()
    RESTRICTED_TYPES.update(restritos)
    EQUIPMENT_THRESHOLDS.clear()
    EQUIPMENT_THRESHOLDS.update(originals)
    DENSITY_THRESHOLDS.clear()
    DENSITY_THRESHOLDS.update(densidades)


def test_sem_arquivo_os_valores_da_especificacao_prevalecem(tmp_path):
    assert load_thresholds(tmp_path / "nao-existe.toml") is None
    assert EQUIPMENT_THRESHOLDS["ponto_onibus"] == DistanceThreshold(300, 800)


def test_arquivo_troca_os_limiares_de_um_tipo(tmp_path):
    arquivo = tmp_path / "limiares.toml"
    arquivo.write_text('[distancia]\nponto_onibus = { ideal_m = 250, maxima_m = 900 }\n', encoding="utf-8")
    assert load_thresholds(arquivo) == arquivo
    assert EQUIPMENT_THRESHOLDS["ponto_onibus"] == DistanceThreshold(250, 900)
    assert EQUIPMENT_THRESHOLDS["praca"] == DistanceThreshold(400, 1200)


@pytest.mark.parametrize("conteudo", [
    '[distancia]\ntipo_inventado = { ideal_m = 1, maxima_m = 2 }\n',
    '[distancia]\npraca = { ideal_m = 400 }\n',
    '[distancia]\npraca = { ideal_m = 900, maxima_m = 400 }\n',
    '[densidade]\nwifi_publico = { raio_m = 300, zero = 1, cem = 2 }\n',
    '[distancia]\npraca = 5\n',
    'isto não é toml',
])
def test_config_invalida_e_recusada(conteudo, tmp_path):
    arquivo = tmp_path / "limiares.toml"
    arquivo.write_text(conteudo, encoding="utf-8")
    with pytest.raises((ThresholdConfigError, ValueError)):
        load_thresholds(arquivo)


def test_arquivo_ajusta_a_densidade_da_iluminacao(tmp_path):
    from geohabita.domain.thresholds import DENSITY_THRESHOLDS, LIGHTING_TYPE
    arquivo = tmp_path / "limiares.toml"
    arquivo.write_text('[densidade]\niluminacao_publica = { raio_m = 200, zero = 100, cem = 2000 }\n',
                       encoding="utf-8")
    load_thresholds(arquivo)
    assert DENSITY_THRESHOLDS[LIGHTING_TYPE].radius_m == 200
    assert DENSITY_THRESHOLDS[LIGHTING_TYPE].zero_per_km2 == 100
    assert DENSITY_THRESHOLDS[LIGHTING_TYPE].full_per_km2 == 2000


@pytest.mark.parametrize("conteudo", [
    '[densidade]\niluminacao_publica = { raio_m = 0, zero = 1, cem = 2 }\n',
    '[densidade]\niluminacao_publica = { raio_m = 300, zero = 3, cem = 2 }\n',
])
def test_densidade_invalida_e_recusada(conteudo, tmp_path):
    arquivo = tmp_path / "limiares.toml"
    arquivo.write_text(conteudo, encoding="utf-8")
    with pytest.raises(ThresholdConfigError):
        load_thresholds(arquivo)


def test_iluminacao_publica_tem_limiar_proprio_por_densidade():
    from geohabita.domain.lighting import lighting_density, lighting_note
    from geohabita.domain.thresholds import DENSITY_THRESHOLDS, LIGHTING_TYPE

    raio, zero, cem = DENSITY_THRESHOLDS[LIGHTING_TYPE].radius_m, \
        DENSITY_THRESHOLDS[LIGHTING_TYPE].zero_per_km2, DENSITY_THRESHOLDS[LIGHTING_TYPE].full_per_km2
    assert raio == 300 and zero == 150 and cem == 1500
    nota = lighting_note(lighting_density(0))
    assert nota == 0.0 and lighting_note(lighting_density(424)) > 99.0


def test_parque_de_conservacao_conta_como_parque_com_peso_baixo():
    from geohabita.domain.thresholds import RESTRICTED_TYPES
    restrito = RESTRICTED_TYPES["parque_conservacao"]
    assert restrito.base_type == "parque_area_verde"
    assert 0 < restrito.factor <= 0.5


def test_arquivo_ajusta_o_fator_do_acesso_restrito(tmp_path):
    from geohabita.domain.thresholds import RESTRICTED_TYPES
    arquivo = tmp_path / "limiares.toml"
    arquivo.write_text('[acesso_restrito]\nparque_conservacao = { fator = 0.1 }\n', encoding="utf-8")
    load_thresholds(arquivo)
    assert RESTRICTED_TYPES["parque_conservacao"].factor == 0.1


@pytest.mark.parametrize("conteudo", [
    '[acesso_restrito]\nparque_conservacao = { fator = 1.5 }\n',
    '[acesso_restrito]\nparque_conservacao = { fator = "baixo" }\n',
    '[acesso_restrito]\npraca = { fator = 0.2 }\n',
])
def test_fator_invalido_e_recusado(conteudo, tmp_path):
    arquivo = tmp_path / "limiares.toml"
    arquivo.write_text(conteudo, encoding="utf-8")
    with pytest.raises(ThresholdConfigError):
        load_thresholds(arquivo)


def test_exemplo_de_configuracao_e_valido():
    from pathlib import Path
    assert load_thresholds(Path(__file__).resolve().parents[2] / "config" / "limiares.exemplo.toml")
