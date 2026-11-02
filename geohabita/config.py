"""Configuração da aplicação, lida do ambiente e, quando existir, do arquivo .env.

As variáveis de ambiente têm precedência sobre o .env. O mesmo módulo atende a
API e os scripts do pipeline, para que todos usem a mesma conexão.
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DATABASE_URL = "postgresql://postgres@localhost:5432/ProjetoIntergrador_2"
# Quem pode informar o IP do visitante no cabeçalho CF-Connecting-IP: o cloudflared
# local por padrão; no Docker, a rede do contêiner do túnel.
DEFAULT_TRUSTED_PROXIES = "127.0.0.1,::1"

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def load_env_file(path: Path = ROOT / ".env") -> None:
    """Carrega ``CHAVE=valor`` do arquivo sem sobrescrever o ambiente."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() and not key.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'").strip())


def parse_networks(value: str) -> tuple[Network, ...]:
    """Lista de IPs ou redes CIDR separados por vírgula; itens vazios são ignorados."""
    return tuple(ipaddress.ip_network(item.strip(), strict=False) for item in value.split(",") if item.strip())


def is_trusted(address: str | None, networks: tuple[Network, ...]) -> bool:
    """Indica se o endereço pertence a alguma das redes confiáveis."""
    if not address:
        return False
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in networks)


load_env_file()
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
TRUSTED_PROXIES = parse_networks(os.getenv("GEOHABITA_PROXIES_CONFIAVEIS", DEFAULT_TRUSTED_PROXIES))
# Limiares de distância editáveis sem mudar o código (RN13); vazio usa os valores padrão.
THRESHOLDS_FILE = os.getenv("GEOHABITA_LIMIARES", str(ROOT / "config" / "limiares.toml"))
