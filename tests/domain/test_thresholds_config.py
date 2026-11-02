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
    originals = dict(EQUIPMENT_THRESHOLDS)
    yield
    EQUIPMENT_THRESHOLDS.clear()
    EQUIPMENT_THRESHOLDS.update(originals)


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


def test_iluminacao_publica_tem_limiar_proprio_por_densidade():
    from geohabita.domain.lighting import lighting_density, lighting_note
    from geohabita.domain.thresholds import DENSITY_THRESHOLDS, LIGHTING_TYPE

    raio, zero, cem = DENSITY_THRESHOLDS[LIGHTING_TYPE].radius_m, \
        DENSITY_THRESHOLDS[LIGHTING_TYPE].zero_per_km2, DENSITY_THRESHOLDS[LIGHTING_TYPE].full_per_km2
    assert raio == 300 and zero == 150 and cem == 1500
    nota = lighting_note(lighting_density(0))
    assert nota == 0.0 and lighting_note(lighting_density(424)) > 99.0
