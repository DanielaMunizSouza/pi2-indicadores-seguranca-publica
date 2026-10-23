"""Composição do diagnóstico socioespacial.

Cobre a regra de que os indicadores de infraestrutura (IPL e IVEP) e os
indicadores oficiais de ocorrências são apresentados lado a lado e nunca
combinados em uma pontuação única (RN07; RNF18). A resposta tem exatamente
um bloco por indicador.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DIAGNOSIS_BLOCKS: tuple[str, ...] = ("proximidade", "vitalidade", "ocorrencias")


def build_diagnosis(
    proximity: Mapping[str, Any],
    vitality: Mapping[str, Any],
    occurrences: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Monta o diagnóstico com um bloco independente por indicador (RN07).

    Cada bloco é copiado sem alteração; nenhum campo derivado de mais de um
    bloco é acrescentado.
    """
    raise NotImplementedError
