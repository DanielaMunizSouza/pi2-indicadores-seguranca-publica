"""Baixa o axe-core usado pelos testes de acessibilidade (manutenção do ambiente).

    uv run python scripts/preparar_axe.py

O arquivo vai para `tests/vendor/axe.min.js` e é versionado: assim os testes não
dependem de acessar um CDN no momento da execução.
"""
import sys
import urllib.request
from pathlib import Path

VERSION = "4.10.2"
DESTINO = Path(__file__).resolve().parents[1] / "tests" / "vendor" / "axe.min.js"
URL = f"https://cdn.jsdelivr.net/npm/axe-core@{VERSION}/axe.min.js"


def main() -> None:
    if DESTINO.is_file() and "--refazer" not in sys.argv:
        print(f"{DESTINO} já existe ({DESTINO.stat().st_size:,} bytes). Use --refazer para baixar de novo.")
        return
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(URL, headers={"User-Agent": "geohabita-testes/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        conteudo = response.read()
    DESTINO.write_bytes(conteudo)
    print(f"axe-core {VERSION} em {DESTINO} ({len(conteudo):,} bytes, MIT).")


if __name__ == "__main__":
    main()
