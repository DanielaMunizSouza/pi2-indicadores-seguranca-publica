"""Busca por endereço: número do imóvel e faixas de numeração dos CEPs (RF03).

Avenidas longas têm um CEP por trecho, e o ViaCEP descreve o trecho no campo
``complemento``: "até 610 - lado par", "de 612 a 1510 - lado par",
"de 1001/1002 ao fim". Com o número do imóvel, a busca reversa escolhe o CEP
do trecho certo.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MIN_STREET_CHARS = 3  # o ViaCEP exige ao menos 3 caracteres no logradouro
INVALID_NUMBER_MESSAGE = "O número do imóvel deve ter apenas dígitos (até 6)."
SHORT_STREET_MESSAGE = "Digite ao menos 3 letras do nome da rua."
NUMBER_LOCATION_NOTICE = (
    "Localização pelo número informado, segundo o OpenStreetMap; pode haver diferença "
    "de algumas dezenas de metros."
)

_NUMBER = re.compile(r"^\d{1,6}$")


class InvalidAddressError(ValueError):
    """Logradouro curto demais ou número do imóvel inválido."""


def normalize_number(value: str | None) -> str:
    """Número do imóvel sem espaços; vazio quando não informado. Levanta se não for numérico."""
    number = (value or "").strip()
    if number and not _NUMBER.match(number):
        raise InvalidAddressError(INVALID_NUMBER_MESSAGE)
    return number.lstrip("0") or ("0" if number else "")


def require_street(value: str | None) -> str:
    street = " ".join((value or "").split())
    if len(street) < MIN_STREET_CHARS:
        raise InvalidAddressError(SHORT_STREET_MESSAGE)
    return street


@dataclass(frozen=True)
class NumberRange:
    """Trecho de numeração de um CEP; ``None`` nas pontas significa sem limite."""

    first: int | None = None
    last: int | None = None
    parity: str | None = None  # "par", "impar" ou None (os dois lados)

    def contains(self, number: int) -> bool:
        if self.first is not None and number < self.first:
            return False
        if self.last is not None and number > self.last:
            return False
        if self.parity == "par":
            return number % 2 == 0
        if self.parity == "impar":
            return number % 2 == 1
        return True


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _numbers(fragment: str) -> list[int]:
    return [int(n) for n in re.findall(r"\d+", fragment)]


def parse_number_range(complement: str | None) -> NumberRange | None:
    """Trecho descrito no complemento do ViaCEP, ou ``None`` se ele não descreve numeração.

    "de 1001/1002 ao fim" e "até 999/1000" trazem o limite dos lados ímpar e par;
    usa-se o menor no início e o maior no fim, e a paridade, se houver, filtra o lado.
    """
    text = _plain(complement or "").strip()
    if not text:
        return None
    parity = "par" if "lado par" in text else "impar" if "lado impar" in text else None
    first = last = None
    if m := re.search(r"\bde\s+([\d/]+)", text):
        first = min(_numbers(m.group(1)))
    if m := re.search(r"\b(?:ate|a)\s+([\d/]+)", text):
        last = max(_numbers(m.group(1)))
    if first is None and last is None and parity is None:
        return None
    return NumberRange(first, last, parity)


def building_number(complement: str | None) -> int | None:
    """Número do prédio de um CEP exclusivo ("grande usuário"): "1294", "1374 12 Andar"."""
    m = re.match(r"\s*(\d+)\b", complement or "")
    return int(m.group(1)) if m else None


def matches_number(complement: str | None, number: str) -> bool | None:
    """O trecho do CEP inclui o número? ``None`` quando o complemento não informa trecho.

    Sem número informado, todo CEP corresponde. Um CEP exclusivo de prédio só
    corresponde ao número do próprio prédio.
    """
    if not number:
        return True
    predio = building_number(complement)
    if predio is not None:
        return predio == int(number)
    trecho = parse_number_range(complement)
    if trecho is None:
        return None
    return trecho.contains(int(number))
