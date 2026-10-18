"""Validação e normalização de CEP.

Cobre a regra de negócio RN01 (oito dígitos numéricos; hífens, pontos e
espaços removidos antes da validação) e apoia RF01 (consulta por CEP) e
RF02 (CEP inexistente libera a consulta por endereço textual).
"""

from __future__ import annotations

import re

CEP_DIGITS = 8
CEP_NOT_FOUND_MESSAGE = "CEP não encontrado"
INVALID_CEP_MESSAGE = "O CEP deve ter 8 dígitos"

_NON_DIGIT = re.compile(r"\D")
_INVALID_CHAR = re.compile(r"[^\d.\-\s]")


class InvalidCepError(ValueError):
    """CEP não possui exatamente oito dígitos numéricos (RN01)."""


def normalize_cep(value: str) -> str:
    """Remove hífens, pontos e espaços, preservando apenas os dígitos (RN01)."""
    return _NON_DIGIT.sub("", value)


def is_valid_cep(value: str) -> bool:
    """Indica se o CEP normalizado possui exatamente oito dígitos (RN01)."""
    # Letras ou outros símbolos invalidam o CEP; apenas separadores são aceitos.
    if _INVALID_CHAR.search(value):
        return False
    return len(normalize_cep(value)) == CEP_DIGITS


def require_valid_cep(value: str) -> str:
    """Normaliza e valida o CEP; levanta InvalidCepError quando inválido (RN01).

    Deve ser chamada antes de qualquer consulta externa, de modo que um
    formato inválido nunca gere requisição a serviços de terceiros (RF01).
    """
    if not is_valid_cep(value):
        raise InvalidCepError(INVALID_CEP_MESSAGE)
    return normalize_cep(value)
