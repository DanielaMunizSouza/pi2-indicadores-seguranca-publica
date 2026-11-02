"""Configuração: proxies confiáveis para o IP do visitante (RNF08) e leitura do .env."""

import os

import pytest

from geohabita.config import is_trusted, load_env_file, parse_networks


@pytest.mark.parametrize(("address", "esperado"), [
    ("127.0.0.1", True), ("::1", True), ("172.28.0.5", True),
    ("172.29.0.5", False), ("200.1.2.3", False), ("não-é-ip", False), (None, False),
])
def test_trusted_proxies_accept_ips_and_cidr_networks(address, esperado):
    redes = parse_networks("127.0.0.1, ::1,172.28.0.0/16,")
    assert is_trusted(address, redes) is esperado


def test_env_file_does_not_override_the_environment(tmp_path, monkeypatch):
    arquivo = tmp_path / ".env"
    arquivo.write_text("# comentário\nGEOHABITA_X='do arquivo'\nGEOHABITA_Y=1\n", encoding="utf-8")
    monkeypatch.setenv("GEOHABITA_Y", "do ambiente")
    monkeypatch.delenv("GEOHABITA_X", raising=False)
    load_env_file(arquivo)
    assert os.environ["GEOHABITA_X"] == "do arquivo"
    assert os.environ["GEOHABITA_Y"] == "do ambiente"
    monkeypatch.delenv("GEOHABITA_X")
