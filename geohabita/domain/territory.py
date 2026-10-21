"""Delimitação territorial da consulta.

Cobre o aviso de endereço fora do município de São Paulo (RF06), com base no
código IBGE devolvido pelo serviço de CEP, e o aviso de que a coordenada
obtida pelo CEP é aproximada (RN05).
"""

from __future__ import annotations

SAO_PAULO_IBGE_CODE = "3550308"
OUT_OF_CITY_MESSAGE = "O endereço informado fica fora do município de São Paulo."
APPROXIMATE_LOCATION_NOTICE = (
    "A localização obtida pelo CEP é aproximada: ela identifica o distrito, "
    "mas não a posição exata do imóvel."
)


def is_sao_paulo(ibge_code: str | None) -> bool:
    """Indica se o código IBGE do município corresponde a São Paulo (RF06).

    Um código ausente não permite afirmar que o endereço está no município e,
    portanto, resulta em ``False``.
    """
    raise NotImplementedError
