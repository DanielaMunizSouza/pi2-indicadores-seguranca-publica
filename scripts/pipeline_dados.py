"""Pipeline de dados: baixa fontes públicas e popula o banco.

Sem argumentos, executa TODAS as etapas, na ordem abaixo. Use `--etapas` para rodar só algumas:
  distritos          importa os 96 distritos (data/reference)
  geosampa-baixar    baixa camadas do GeoSampa (WFS, GeoJSON EPSG:4326) em data/raw/geosampa
  geosampa-carregar  carrega equipamentos em public.equipamento_publico
  ibge-populacao     baixa o Censo 2022 por distrito (IBGE) e grava distrito_municipal_sp.populacao_2022
  ssp-baixar         baixa os XLSX da SSP-SP (só o que mudou) e converte as abas em CSV (data/raw/ssp)
  ssp-carregar       importa os CSVs convertidos da SSP-SP em registro_ocorrencia
  resumo             recalcula as tabelas de resumo usadas pelo mapa

Exemplo: uv run --env-file .env scripts/pipeline_dados.py --etapas geosampa-baixar geosampa-carregar
"""
import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

WFS = "https://wfs.geosampa.prefeitura.sp.gov.br/geoserver/ows"
RAIZ = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
PAGINA = 5000
LOTE = 20000

# camada GeoSampa -> (categoria do IVEP, tipo de equipamento). Categorias e tipos seguem
# geohabita/domain/thresholds.py. Fora da lista: "praca" (a camada GEOSAMPA_v_praca_largo falha
# no servidor do GeoSampa por erro de certificado; tente de novo mais tarde).
CAMADAS = {
    "pde_parque_municipal": ("lazer_convivencia", "parque_area_verde"),
    "GEOSAMPA_cadparcs_parque_unidade_conservacao": ("lazer_convivencia", "parque_area_verde"),
    "equipamento_cultura_bibliotecas": ("cultura_esporte", "biblioteca_centro_cultural"),
    "equipamento_cultura_espacos_culturais": ("cultura_esporte", "biblioteca_centro_cultural"),
    "equipamento_educacao_ceu": ("cultura_esporte", "ceu_equipamento_esportivo"),
    "equipamento_esporte_centro_esportivo": ("cultura_esporte", "ceu_equipamento_esportivo"),
    "equipamento_esporte_clubes": ("cultura_esporte", "ceu_equipamento_esportivo"),
    "ponto_onibus": ("mobilidade", "ponto_onibus"),
    "terminal_onibus": ("mobilidade", "ponto_onibus"),
    "estacao_metro": ("mobilidade", "estacao_metro_trem"),
    "estacao_trem": ("mobilidade", "estacao_metro_trem"),
    "via_bicicleta": ("mobilidade", "ciclovia"),
    "equipamento_feira_livre": ("comercio_rua", "feira_mercado_municipal"),
    "equipamento_mercados_municipais": ("comercio_rua", "feira_mercado_municipal"),
    "equipamento_saude_ubs_posto_centro": ("servicos_essenciais", "unidade_basica_saude"),
    "equipamento_educacao_rede_publica": ("servicos_essenciais", "escola_publica"),
    "equipamento_praca_wifi": ("conectividade", "wifi_publico"),
    # ~663 mil pontos; "iluminacao_publica" ainda não tem limiares em thresholds.py, então
    # é carregada mas não entra nos cálculos de IPL/IVEP.
    "iluminacao_publica": ("conectividade", "iluminacao_publica"),
}


def requisitar(url, tentativas=3):
    for n in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "geohabita-pipeline/0.1"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception as erro:
            if n == tentativas - 1 or getattr(erro, "code", 0) in (400, 500):  # erros HTTP do GeoSampa são determinísticos
                raise
            print(f"  nova tentativa ({erro})", file=sys.stderr)
            time.sleep(2 ** (n + 1))


def url_wfs(camada, **extra):
    params = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": f"geoportal:{camada}",
              "outputFormat": "application/json", "srsName": "EPSG:4326", **extra}
    return f"{WFS}?{urllib.parse.urlencode(params)}"


def baixar_camada(camada, destino):
    """Baixa a camada em páginas. Camadas sem chave primária exigem `sortBy` para paginar:
    nesse caso usa o primeiro atributo (um identificador nas camadas do GeoSampa)."""
    features, inicio, ordem = [], 0, {}
    while True:
        try:
            lote = requisitar(url_wfs(camada, count=PAGINA, startIndex=inicio, **ordem))["features"]
        except urllib.error.HTTPError as erro:
            if erro.code != 400 or ordem:
                raise
            amostra = requisitar(url_wfs(camada, count=1))["features"]
            ordem = {"sortBy": next(iter(amostra[0]["properties"]))}
            print(f"  {camada}: paginando com sortBy={ordem['sortBy']}")
            continue
        features += lote
        if len(lote) < PAGINA:
            break
        inicio += PAGINA
        time.sleep(1)
    if ordem:  # com ordenação por campo, valores repetidos poderiam duplicar/perder linhas entre páginas
        chaves = [json.dumps(f, sort_keys=True) for f in features]
        if len(set(chaves)) != len(chaves):
            raise RuntimeError(f"{camada}: feições repetidas na paginação (campo {ordem['sortBy']} não é único)")
    tmp = destino.with_suffix(".tmp")
    tmp.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    tmp.replace(destino)
    return len(features)


def etapa_geosampa_baixar(args):
    pasta = RAIZ / "data/raw/geosampa"
    pasta.mkdir(parents=True, exist_ok=True)
    camadas = CAMADAS
    falhas = []
    for camada in camadas:
        destino = pasta / f"{camada}.geojson"
        if destino.exists() and not args.refazer:
            print(f"{camada}: já baixada (use --refazer)")
            continue
        try:
            print(f"{camada}: {baixar_camada(camada, destino):,} feições")
        except Exception as erro:  # uma camada fora do ar não deve impedir as demais
            print(f"{camada}: PULADA ({erro})", file=sys.stderr)
            falhas.append(camada)
    if falhas:
        print(f"Camadas não baixadas (erro no servidor do GeoSampa; rode de novo mais tarde): {', '.join(falhas)}", file=sys.stderr)


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
    camadas = CAMADAS
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
                ident = primeiro(p, "cd_identificador", "cd_identificador_ponto_onibus", "cd_identificador_ciclovia", "cd_identificador_iluminacao_publica", "cd_equipamento") or f.get("id") or str(i)
                linhas.append((categoria, tipo, camada, ident,
                               primeiro(p, "nm_equipamento", "nm_ponto_onibus", "nm_estacao_metro_trem", "nm_trecho_via_bicicleta", "cd_placa", "nm_parque", "nm_terminal_onibus"),
                               primeiro(p, "tx_endereco_equipamento", "tx_endereco_ponto_onibus", "tx_endereco"),
                               cep_limpo(primeiro(p, "cd_cep_equipamento")), json.dumps(f["geometry"])))
            for i in range(0, len(linhas), LOTE):  # lotes: a iluminação tem ~663 mil linhas
                with conn.transaction(), conn.cursor() as cur:
                    cur.executemany(sql, linhas[i:i + LOTE])
            print(f"{camada}: {len(linhas):,} equipamentos")


IBGE = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/Agregados_por_Distrito_csv/"
COD_SAO_PAULO = "3550308"


def sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.upper()) if unicodedata.category(c) != "Mn").strip()


def etapa_ibge_populacao(args):
    """População residente (variável v0001) do Censo 2022 por distrito; casa com o GeoSampa pelo nome."""
    import psycopg
    pasta = RAIZ / "data/raw/ibge"
    pasta.mkdir(parents=True, exist_ok=True)
    zips = zipfile_nomes(IBGE)
    if not zips:
        raise SystemExit("Arquivo 'distritos_basico' não encontrado na listagem do IBGE.")
    destino = pasta / zips[0]
    if args.refazer or not destino.exists():
        req = urllib.request.Request(IBGE + zips[0], headers={"User-Agent": "geohabita-pipeline/0.1"})
        with urllib.request.urlopen(req, timeout=120) as r, destino.open("wb") as f:
            f.write(r.read())
    with zipfile.ZipFile(destino) as z:
        texto = z.read(z.namelist()[0]).decode("latin-1")  # o IBGE publica em ISO-8859-1
    ibge = {sem_acento(r["NM_DIST"]): int(r["v0001"]) for r in csv.DictReader(io.StringIO(texto), delimiter=";")
            if r["CD_MUN"] == COD_SAO_PAULO}
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        distritos = cur.execute("SELECT codigo_distrito, nome_distrito FROM public.distrito_municipal_sp").fetchall()
        faltam = [nome for _, nome in distritos if sem_acento(nome) not in ibge]
        if not distritos or faltam:
            raise SystemExit(f"Distritos sem par no IBGE (rode a etapa 'distritos' antes?): {faltam or 'tabela vazia'}")
        cur.executemany("UPDATE public.distrito_municipal_sp SET populacao_2022=%s WHERE codigo_distrito=%s",
                        [(ibge[sem_acento(nome)], codigo) for codigo, nome in distritos])
    print(f"População 2022 gravada em {len(distritos)} distritos (total {sum(ibge.values()):,}).")


def zipfile_nomes(url):
    req = urllib.request.Request(url, headers={"User-Agent": "geohabita-pipeline/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", "replace")
    return re.findall(r'href="(Agregados_por_distritos_basico_BR[^"]*\.zip)"', html)


def script(nome, *argumentos):
    subprocess.run([sys.executable, str(SCRIPTS / nome), *argumentos], check=True)


def etapa_ssp_baixar(args):
    extra = ["--forcar"] if args.refazer else []
    script("baixar_ssp.py", "--destino", args.ssp_destino, "--desde", str(args.desde), *extra)


def etapa_ssp_carregar(args):
    script("carregar_ssp.py", "--diretorio", str(Path(args.ssp_destino) / "csv"))


ETAPAS = {
    "geosampa-baixar": etapa_geosampa_baixar,
    "geosampa-carregar": etapa_geosampa_carregar,
    "ibge-populacao": etapa_ibge_populacao,
    "ssp-baixar": etapa_ssp_baixar,
    "ssp-carregar": etapa_ssp_carregar,
    "distritos": lambda a: script("importar_distritos_sp.py"),
    "resumo": lambda a: script("atualizar_resumo_distritos.py"),
}
PADRAO = ["distritos", "geosampa-baixar", "geosampa-carregar", "ibge-populacao", "ssp-baixar", "ssp-carregar", "resumo"]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapas", nargs="+", choices=ETAPAS, default=PADRAO, help="padrão: todas, na ordem da lista acima")
    p.add_argument("--refazer", action="store_true", help="baixa novamente camadas já existentes")
    p.add_argument("--ssp-destino", default=str(RAIZ / "data/raw/ssp"), help="pasta de trabalho da SSP (xlsx/, csv/)")
    p.add_argument("--desde", type=int, default=2022, help="primeiro ano das bases SSP (padrão 2022)")
    args = p.parse_args()
    for etapa in args.etapas:
        print(f"== {etapa}")
        ETAPAS[etapa](args)


if __name__ == "__main__":
    main()
