"""Testes das regras de validação de CEP (RN01, RF01).

Os vetores de entrada reproduzem o caso de teste CT01 da especificação
("1234", "abcdefgh" e "123456789").
"""

import pytest

from geohabita.domain.cep import (
    InvalidCepError,
    is_valid_cep,
    normalize_cep,
    require_valid_cep,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("01310-100", "01310100"),
        ("01310.100", "01310100"),
        (" 01310100 ", "01310100"),
        ("01310100", "01310100"),
    ],
)
def test_normalize_cep_removes_separators(raw, expected):
    assert normalize_cep(raw) == expected


@pytest.mark.parametrize("value", ["01310-100", "01310100", "01310.100"])
def test_is_valid_cep_accepts_eight_digits(value):
    assert is_valid_cep(value) is True


@pytest.mark.parametrize(
    "value",
    ["1234", "abcdefgh", "123456789", "0131010", "0131010a", ""],
)
def test_is_valid_cep_rejects_anything_but_eight_digits(value):
    assert is_valid_cep(value) is False


def test_require_valid_cep_returns_normalized_digits():
    assert require_valid_cep("01310-100") == "01310100"


@pytest.mark.parametrize("value", ["1234", "abcdefgh", "123456789"])
def test_require_valid_cep_raises_for_invalid_format(value):
    with pytest.raises(InvalidCepError):
        require_valid_cep(value)
