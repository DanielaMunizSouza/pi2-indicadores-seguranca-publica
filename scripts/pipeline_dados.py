"""Pipeline de dados: baixa fontes públicas e popula o banco.

Etapas (use `--etapas` para escolher; padrão: todas as automáticas):
  geosampa-baixar    baixa camadas do GeoSampa (WFS, GeoJSON EPSG:4326) em data/raw/geosampa
  geosampa-carregar  carrega equipamentos em public.equipamento_publico
  ibge-populacao     grava a população 2022 por distrito a partir de um CSV (--populacao-csv)
  ssp-carregar       importa os CSVs da SSP-SP (download manual; veja data/README.md)
  distritos          importa os 96 distritos
  resumo             recalcula as tabelas de resumo usadas pelo mapa

Exemplo: uv run --env-file .env scripts/pipeline_dados.py --etapas geosampa-baixar geosampa-carregar
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

WFS = "https://wfs.geosampa.prefeitura.sp.gov.br/geoserver/ows"
RAIZ = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
PAGINA = 5000

# camada GeoSampa -> (categoria do IVEP, tipo de equipamento)
CAMADAS = {
    "pde_parque_municipal": ("lazer_convivencia", "parque"),
    "GEOSAMPA_cadparcs_parque_unidade_conservacao": ("lazer_convivencia", "parque"),
    "equipamento_cultura_bibliotecas": ("cultura_esporte", "biblioteca_centro_cultural"),
    "equipamento_cultura_espacos_culturais": ("cultura_esporte", "biblioteca_centro_cultural"),
    "equipamento_educacao_ceu": ("cultura_esporte", "ceu_esportivo"),
    "equipamento_esporte_centro_esportivo": ("cultura_esporte", "ceu_esportivo"),
    "equipamento_esporte_clubes": ("cultura_esporte", "ceu_esportivo"),
    "ponto_onibus": ("mobilidade", "ponto_onibus"),
    "terminal_onibus": ("mobilidade", "terminal_onibus"),
    "estacao_metro": ("mobilidade", "estacao_metro_trem"),
    "estacao_trem": ("mobilidade", "estacao_metro_trem"),
    "equipamento_feira_livre": ("comercio_rua", "feira_livre"),
    "equipamento_mercados_municipais": ("comercio_rua", "mercado_municipal"),
    "equipamento_saude_ubs_posto_centro": ("servicos_essenciais", "ubs"),
    "equipamento_educacao_rede_publica": ("servicos_essenciais", "escola_publica"),
    "equipamento_praca_wifi": ("conectividade", "wifi_publico"),
}
OPCIONAIS = {"iluminacao_publica": ("conectividade", "iluminacao_publica")}  # camada muito grande


def requisitar(url, tentativas=4):
    for n in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "geohabita-pipeline/0.1"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception as erro:
            if n == tentativas - 1:
                raise
            print(f"  nova tentativa ({erro})", file=sys.stderr)
            time.sleep(2 ** (n + 1))


def baixar_camada(camada, destino):
    features, inicio = [], 0
    while True:
        params = {"service": "WFS", "version": "2.0.0", "request": "GetFeature",
                  "typeNames": f"geoportal:{camada}", "outputFormat": "application/json",
                  "srsName": "EPSG:4326", "count": PAGINA, "startIndex": inicio}
        lote = requisitar(f"{WFS}?{urllib.parse.urlencode(params)}")["features"]
        features += lote
        if len(lote) < PAGINA:
            break
        inicio += PAGINA
        time.sleep(1)
    tmp = destino.with_suffix(".tmp")
    tmp.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    tmp.replace(destino)
    return len(features)


def etapa_geosampa_baixar(args):
    pasta = RAIZ / "data/raw/geosampa"
    pasta.mkdir(parents=True, exist_ok=True)
    camadas = dict(CAMADAS, **(OPCIONAIS if args.com_iluminacao else {}))
    for camada in camadas:
        destino = pasta / f"{camada}.geojson"
        if destino.exists() and not args.refazer:
            print(f"{camada}: já baixada (use --refazer)")
            continue
        print(f"{camada}: {baixar_camada(camada, destino):,} feições")


def primeiro(props, *nomes):
    for nome in nomes:
        valor = props.get(nome)
        if valor not in (None, ""):
            return str(valor).strip()
    return None


def cep_limpo(valor):
    digitos = "".join(c for c in (valor or "") if c.isdigit())
    return digitos if len(digitos) == 8 and digitos != "00000000" else None


def etapa_geosampa_carregar(args):
    import psycopg
    pasta = RAIZ / "data/raw/geosampa"
    camadas = dict(CAMADAS, **OPCIONAIS)
    sql = ("INSERT INTO public.equipamento_publico (categoria,tipo,camada,identificador,nome,endereco,cep,geometria) "
           "VALUES (%s,%s,%s,%s,%s,%s,%s,ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326))) "
           "ON CONFLICT (camada,identificador) DO UPDATE SET categoria=EXCLUDED.categoria,tipo=EXCLUDED.tipo,"
           "nome=EXCLUDED.nome,endereco=EXCLUDED.endereco,cep=EXCLUDED.cep,geometria=EXCLUDED.geometria,importado_em=now()")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for camada, (categoria, tipo) in camadas.items():
            arquivo = pasta / f"{camada}.geojson"
            if not arquivo.is_file():
                continue
            feicoes = json.loads(arquivo.read_text(encoding="utf-8"))["features"]
            linhas = []
            for i, f in enumerate(feicoes):
                if not f.get("geometry"):
                    continue
                p = f["properties"]
                ident = primeiro(p, "cd_identificador", "cd_identificador_ponto_onibus", "cd_equipamento") or f.get("id") or str(i)
                linhas.append((categoria, tipo, camada, ident,
                               primeiro(p, "nm_equipamento", "nm_ponto_onibus", "nm_estacao_metro_trem", "nm_parque", "nm_terminal_onibus"),
                               primeiro(p, "tx_endereco_equipamento", "tx_endereco_ponto_onibus"),
                               cep_limpo(primeiro(p, "cd_cep_equipamento")), json.dumps(f["geometry"])))
            with conn.transaction(), conn.cursor() as cur:
                cur.executemany(sql, linhas)
            print(f"{camada}: {len(linhas):,} equipamentos")


def etapa_ibge_populacao(args):
    """Espera CSV com colunas `codigo_distrito` e `populacao` (soma dos setores do Censo 2022 por distrito)."""
    import psycopg
    if not args.populacao_csv:
        raise SystemExit("Informe --populacao-csv (colunas: codigo_distrito;populacao).")
    with open(args.populacao_csv, encoding="utf-8-sig", newline="") as f:
        dados = [(int(r["populacao"]), r["codigo_distrito"]) for r in csv.DictReader(f, delimiter=";")]
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.executemany("UPDATE public.distrito_municipal_sp SET populacao_2022=%s WHERE codigo_distrito=%s", dados)
    print(f"População atualizada para {len(dados)} distritos.")


def script(nome, *argumentos):
    subprocess.run([sys.executable, str(SCRIPTS / nome), *argumentos], check=True)


def etapa_ssp_carregar(args):
    script("carregar_ssp.py", "--diretorio", args.ssp_diretorio)


ETAPAS = {
    "geosampa-baixar": etapa_geosampa_baixar,
    "geosampa-carregar": etapa_geosampa_carregar,
    "ibge-populacao": etapa_ibge_populacao,
    "ssp-carregar": etapa_ssp_carregar,
    "distritos": lambda a: script("importar_distritos_sp.py"),
    "resumo": lambda a: script("atualizar_resumo_distritos.py"),
}
PADRAO = ["geosampa-baixar", "distritos", "geosampa-carregar", "ssp-carregar", "resumo"]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapas", nargs="+", choices=ETAPAS, default=PADRAO)
    p.add_argument("--refazer", action="store_true", help="baixa novamente camadas já existentes")
    p.add_argument("--com-iluminacao", action="store_true", help="inclui a camada iluminacao_publica (grande)")
    p.add_argument("--populacao-csv")
    p.add_argument("--ssp-diretorio", default=str(RAIZ / "data/raw/Dados Segurança Publica/SSP.SP/CSV"))
    args = p.parse_args()
    for etapa in args.etapas:
        print(f"== {etapa}")
        ETAPAS[etapa](args)


if __name__ == "__main__":
    main()
