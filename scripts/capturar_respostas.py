"""Gera as respostas simuladas usadas pelos testes de interface (Playwright).

Lê uma API real (banco com o pipeline executado) e grava em `data/tmp/e2e` os
JSONs de cada rota, para um conjunto fixo de endereços, para que a suíte `e2e` rode
sem banco. Rode antes da primeira execução dos testes:

    uv run --env-file .env scripts/capturar_respostas.py --cep 01310-200 --numero 1578

Os arquivos são versionados (só dados públicos agregados); regrave quando o
contrato da API mudar. A geometria dos distritos já está em data/reference.
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DESTINO = Path(__file__).resolve().parents[1] / "tests" / "e2e" / "respostas"
BASE = "http://127.0.0.1:8000"


def buscar(url):
    with urllib.request.urlopen(url, timeout=60) as resposta:
        return resposta.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=BASE, help="endereço da aplicação em execução")
    parser.add_argument("--cep", default="01310-200", help="CEP consultado (com número, se houver)")
    parser.add_argument("--numero", default="", help="número do imóvel da consulta de exemplo")
    parser.add_argument("--logradouro", default="Avenida Paulista", help="logradouro da busca de endereço")
    args = parser.parse_args()

    DESTINO.mkdir(parents=True, exist_ok=True)
    consulta = {"cep": args.cep}
    if args.numero:
        consulta["numero"] = args.numero
    endereco = {"cep": args.cep.replace("-", ""), "logradouro": args.logradouro}
    alternativos = {cep: args.base + "/api/diagnostico?cep=" + cep for cep in
                    [c.replace("-", "") for c in (args.cep, "01001-000", "05508-040")]}
    arquivos = {
        "status.json": "/api/status",
        "categories.json": "/api/categories",
        "diagnostico.json": "/api/diagnostico",
        "enderecos.json": "/api/enderecos",
        "summary.json": "/api/summary",
        "areas.json": "/api/areas",
        "limite.json": None,  # preenchido abaixo, com o código do distrito consultado
    }

    for nome, rota in arquivos.items():
        if rota is None:
            continue
        url = args.base + rota
        if rota == "/api/diagnostico":
            url += "?" + "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in consulta.items())
        elif rota == "/api/enderecos":
            url += f"?logradouro={urllib.parse.quote(args.logradouro)}"
        elif rota in ("/api/summary", "/api/areas"):
            url += "?start=2023-01-01&end=2025-12-31"
        conteudo = buscar(url)
        (DESTINO / nome).write_bytes(conteudo)
        print(f"{nome}: {len(conteudo):,} bytes")

    nomes = {"01001000": "diagnostico-se", "05508040": "diagnostico-pinheiros"}
    for cep, url in alternativos.items():
        if cep == args.cep.replace("-", ""):
            continue
        arquivo = DESTINO / f"{nomes.get(cep, 'diagnostico-' + cep)}.json"
        arquivo.write_bytes(buscar(url))
        print(f"{arquivo.name}: {arquivo.stat().st_size:,} bytes")

    diagnostico = json.loads((DESTINO / "diagnostico.json").read_text(encoding="utf-8"))
    codigo = diagnostico.get("local", {}).get("distrito", {}).get("codigo")
    if codigo:
        limite = buscar(f"{args.base}/api/distritos/{codigo}/limite")
        (DESTINO / "limite.json").write_bytes(limite)
        print(f"limite.json ({codigo}): {len(limite):,} bytes")
    else:
        (DESTINO / "limite.json").write_text(json.dumps(
            {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": []}}))
        print("limite.json: vazio (nenhum distrito na consulta)")
    print(f"Respostas gravadas em {DESTINO}. Rode: uv run pytest -m e2e")


if __name__ == "__main__":
    import urllib.parse  # noqa: PLC0415

    main()
