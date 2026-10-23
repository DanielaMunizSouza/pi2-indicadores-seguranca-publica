"""Testes da composição do diagnóstico (RN07; RNF18).

O caso CT12 da especificação verifica, na resposta do diagnóstico, a
ausência de qualquer campo que combine os dois conjuntos de indicadores.
"""

from geohabita.domain.diagnosis import DIAGNOSIS_BLOCKS, build_diagnosis

PROXIMITY = {"ipl": 72.5, "categorias": {"mobilidade": 90.0}}
VITALITY = {"ivep": 61.0, "percentis": {"mobilidade": 80.0}}
OCCURRENCES = {"taxas": {"roubo": 412.3}, "media_municipal": {"roubo": 380.0}}


def test_ct12_response_has_only_one_block_per_indicator():
    diagnosis = build_diagnosis(PROXIMITY, VITALITY, OCCURRENCES)
    assert tuple(diagnosis) == DIAGNOSIS_BLOCKS


def test_blocks_are_kept_unchanged():
    diagnosis = build_diagnosis(PROXIMITY, VITALITY, OCCURRENCES)
    assert diagnosis["proximidade"] == PROXIMITY
    assert diagnosis["vitalidade"] == VITALITY
    assert diagnosis["ocorrencias"] == OCCURRENCES


def test_occurrence_block_never_carries_infrastructure_indicators():
    diagnosis = build_diagnosis(PROXIMITY, VITALITY, OCCURRENCES)
    assert not {"ipl", "ivep"} & set(diagnosis["ocorrencias"])


def test_blocks_are_copies():
    diagnosis = build_diagnosis(PROXIMITY, VITALITY, OCCURRENCES)
    diagnosis["vitalidade"]["ivep"] = 0
    assert VITALITY["ivep"] == 61.0
