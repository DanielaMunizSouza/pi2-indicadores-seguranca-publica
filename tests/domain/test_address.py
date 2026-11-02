"""Faixas de numeração dos CEPs e validação do número do imóvel (RF03)."""

import pytest

from geohabita.domain.address import (
    InvalidAddressError,
    NumberRange,
    matches_number,
    normalize_number,
    parse_number_range,
    require_street,
)


@pytest.mark.parametrize(("complemento", "esperado"), [
    ("até 610 - lado par", NumberRange(None, 610, "par")),
    ("de 612 a 1510 - lado par", NumberRange(612, 1510, "par")),
    ("de 1047 a 1865 - lado ímpar", NumberRange(1047, 1865, "impar")),
    ("de 1001 ao fim - lado ímpar", NumberRange(1001, None, "impar")),
    ("de 1001/1002 ao fim", NumberRange(1001, None, None)),
    ("até 999/1000", NumberRange(None, 1000, None)),
    ("lado par", NumberRange(None, None, "par")),
    ("", None), (None, None), ("Bloco A", None),
])
def test_viacep_complement_is_read_as_a_number_range(complemento, esperado):
    assert parse_number_range(complemento) == esperado


@pytest.mark.parametrize(("complemento", "numero", "esperado"), [
    ("de 1047 a 1865 - lado ímpar", "1578", False),  # par, mas o trecho é ímpar
    ("de 1047 a 1865 - lado ímpar", "1579", True),
    ("de 612 a 1510 - lado par", "1510", True),
    ("até 610 - lado par", "612", False),
    ("de 1001 ao fim - lado ímpar", "99999", True),
    ("", "10", None),
    ("de 1 a 99", "", True),
])
def test_number_is_matched_against_the_cep_range(complemento, numero, esperado):
    assert matches_number(complemento, numero) is esperado


@pytest.mark.parametrize(("valor", "esperado"), [(" 1578 ", "1578"), ("", ""), (None, ""), ("007", "7")])
def test_number_is_normalized(valor, esperado):
    assert normalize_number(valor) == esperado


@pytest.mark.parametrize("valor", ["12A", "s/n", "1234567", "-3"])
def test_non_numeric_number_is_rejected(valor):
    with pytest.raises(InvalidAddressError):
        normalize_number(valor)


def test_street_needs_three_characters():
    assert require_street("  Av   Paulista ") == "Av Paulista"
    with pytest.raises(InvalidAddressError):
        require_street("Av")


@pytest.mark.parametrize(("complemento", "numero", "esperado"), [
    ("1294", "1294", True), ("1374 12 Andar", "1374", True), ("1294", "1296", False),
])
def test_building_cep_matches_only_its_number(complemento, numero, esperado):
    assert matches_number(complemento, numero) is esperado
