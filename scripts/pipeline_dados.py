"""Pipeline de dados: baixa fontes públicas e popula o banco.

Sem argumentos, executa TODAS as etapas. Use `--etapas` para rodar só algumas.
As etapas rodam em paralelo quando não dependem umas das outras:

  distritos ──> ibge-populacao ─────────────────────────────┐
  geosampa-baixar ──> geosampa-carregar ────────────────────┤
  ssp-baixar ──> ssp-carregar ──> resumo ──> indicadores <──┘

  distritos          importa os 96 distritos (data/reference)
  ibge-populacao     baixa o Censo 2022 por distrito (IBGE) e grava distrito_municipal_sp.populacao_2022
  geosampa-baixar    baixa camadas do GeoSampa (WFS, GeoJSON EPSG:4326) em data/raw/geosampa
  geosampa-carregar  carrega equipamentos em public.equipamento_publico
  ssp-baixar         baixa os XLSX da SSP-SP (só o que mudou), filtra a capital e converte em CSV
  ssp-carregar       importa os CSVs da SSP-SP em registro_ocorrencia (só os que mudaram)
  resumo             grava o distrito das ocorrências novas e recalcula os resumos do mapa
  indicadores        pré-calcula percentis do IVEP e ocorrências por natureza (indicador_distrito)

Escopo padrão da SSP: SPDadosCriminais, CelularesSubtraidos e MDIP, últimos três anos completos,
só o município de São Paulo. Amplie com --fontes, --desde/--ate, --com-ano-corrente, --todo-estado.

Exemplo: uv run --env-file .env scripts/pipeline_dados.py --etapas geosampa-baixar geosampa-carregar
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import baixar_ssp  # noqa: E402
import carregar_ssp  # noqa: E402
from progresso import Progresso  # noqa: E402

WFS = "https://wfs.geosampa.prefeitura.sp.gov.br/geoserver/ows"
RAIZ = Path(__file__).resolve().parent.parent
PAGINA = 5000
LOTE = 20000
DOWNLOADS_GEOSAMPA = 4  # requisições simultâneas ao WFS da Prefeitura

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



class ErroDefinitivo(Exception):
    pass


def requisitar(url, progresso=None, tentativas=3, json_=True):
    for n in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "geohabita-pipeline/0.1"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r) if json_ else r.read().decode("utf-8", "replace")
        except Exception as erro:
            if n == tentativas - 1 or getattr(erro, "code", 0) in (400, 500):  # erros HTTP do GeoSampa são determinísticos
                raise
            if progresso:
                progresso.log(f"  nova tentativa ({erro})")
            time.sleep(2 ** (n + 1))


def url_wfs(camada, **extra):
    params = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": f"geoportal:{camada}",
              "outputFormat": "application/json", "srsName": "EPSG:4326", **extra}
    return f"{WFS}?{urllib.parse.urlencode(params)}"


def total_feicoes(camada):
    xml = requisitar(url_wfs(camada, resultType="hits", outputFormat="text/xml; subtype=gml/3.2"), json_=False)
    achado = re.search(r'numberMatched="(\d+)"', xml)
    return int(achado.group(1)) if achado else None


def baixar_camada(camada, destino, progresso):
    """Baixa a camada em páginas. Camadas sem chave primária exigem `sortBy` para paginar:
    nesse caso usa o primeiro atributo (um identificador nas camadas do GeoSampa)."""
    chave = f"wfs:{camada}"
    try:
        total = total_feicoes(camada)
    except Exception:
        total = None
    progresso.inicio(chave, f"baixando {camada}", total=total, silencioso=bool(total and total <= PAGINA))
    features, inicio, ordem = [], 0, {}
    try:
        while True:
            try:
                lote = requisitar(url_wfs(camada, count=PAGINA, startIndex=inicio, **ordem), progresso)["features"]
            except urllib.error.HTTPError as erro:
                if erro.code != 400 or ordem:
                    raise
                amostra = requisitar(url_wfs(camada, count=1), progresso)["features"]
                ordem = {"sortBy": next(iter(amostra[0]["properties"]))}
                continue
            features += lote
            progresso.avanco(chave, feito=len(features))
            if len(lote) < PAGINA:
                break
            inicio += PAGINA
            time.sleep(0.5)
        if ordem:  # com ordenação por campo, valores repetidos poderiam duplicar/perder linhas entre páginas
            chaves = [json.dumps(f, sort_keys=True) for f in features]
            if len(set(chaves)) != len(chaves):
                raise RuntimeError(f"feições repetidas na paginação (campo {ordem['sortBy']} não é único)")
    except Exception as erro:
        progresso.fim(chave, f"{camada}: PULADA ({erro})", erro=True)
        raise
    tmp = destino.with_suffix(".tmp")
    tmp.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    tmp.replace(destino)
    progresso.fim(chave, f"{camada}: {len(features):,} feições")
    return len(features)


def etapa_geosampa_baixar(args, progresso):
    pasta = RAIZ / "data/raw/geosampa"
    pasta.mkdir(parents=True, exist_ok=True)
    pendentes = []
    for camada in CAMADAS:
        destino = pasta / f"{camada}.geojson"
        if destino.exists() and not args.refazer:
            continue
        pendentes.append((camada, destino))
    if len(pendentes) < len(CAMADAS):
        progresso.log(f"  {len(CAMADAS) - len(pendentes)} camadas já baixadas (use --refazer para baixar de novo)")
    falhas = []
    with ThreadPoolExecutor(min(DOWNLOADS_GEOSAMPA, args.workers + 1)) as pool:
        tarefas = {pool.submit(baixar_camada, c, d, progresso): c for c, d in pendentes}
        for t in as_completed(tarefas):
            if t.exception():  # uma camada fora do ar não deve impedir as demais
                falhas.append(tarefas[t])
    if falhas:
        progresso.log(f"  camadas não baixadas (erro no servidor do GeoSampa; rode de novo mais tarde): {', '.join(falhas)}")


def primeiro(props, *nomes):
    for nome in nomes:
        valor = props.get(nome)
        if valor not in (None, ""):
            return str(valor).strip()
    return None


def cep_limpo(valor):
    digitos = "".join(c for c in (valor or "") if c.isdigit())
    return digitos if len(digitos) == 8 and digitos != "00000000" else None


SQL_EQUIPAMENTO = (
    "INSERT INTO public.equipamento_publico (categoria,tipo,camada,identificador,nome,endereco,cep,geometria) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326))) "
    "ON CONFLICT (camada,identificador) DO UPDATE SET categoria=EXCLUDED.categoria,tipo=EXCLUDED.tipo,"
    "nome=EXCLUDED.nome,endereco=EXCLUDED.endereco,cep=EXCLUDED.cep,geometria=EXCLUDED.geometria,importado_em=now()")


def carregar_camada(camada, categoria, tipo, arquivo, progresso):
    import psycopg
    feicoes = json.loads(arquivo.read_text(encoding="utf-8"))["features"]
    linhas = []
    for i, f in enumerate(feicoes):
        if not f.get("geometry"):
            continue
        p = f["properties"]
        ident = primeiro(p, "cd_identificador", "cd_identificador_ponto_onibus", "cd_identificador_ciclovia",
                         "cd_identificador_iluminacao_publica", "cd_equipamento") or f.get("id") or str(i)
        linhas.append((categoria, tipo, camada, ident,
                       primeiro(p, "nm_equipamento", "nm_ponto_onibus", "nm_estacao_metro_trem",
                                "nm_trecho_via_bicicleta", "cd_placa", "nm_parque", "nm_terminal_onibus"),
                       primeiro(p, "tx_endereco_equipamento", "tx_endereco_ponto_onibus", "tx_endereco"),
                       cep_limpo(primeiro(p, "cd_cep_equipamento")), json.dumps(f["geometry"])))
    chave = f"eq:{camada}"
    progresso.inicio(chave, f"carregando {camada}", total=len(linhas), silencioso=len(linhas) <= LOTE)
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for i in range(0, len(linhas), LOTE):  # lotes: a iluminação tem ~663 mil linhas
            with conn.transaction(), conn.cursor() as cur:
                cur.executemany(SQL_EQUIPAMENTO, linhas[i:i + LOTE])
            progresso.avanco(chave, feito=min(i + LOTE, len(linhas)))
    progresso.fim(chave, f"{camada}: {len(linhas):,} equipamentos")


def etapa_geosampa_carregar(args, progresso):
    pasta = RAIZ / "data/raw/geosampa"
    presentes = [(c, *ct, pasta / f"{c}.geojson") for c, ct in CAMADAS.items() if (pasta / f"{c}.geojson").is_file()]
    presentes.sort(key=lambda x: -x[3].stat().st_size)  # maiores primeiro
    with ThreadPoolExecutor(args.workers) as pool:
        for t in [pool.submit(carregar_camada, *x, progresso) for x in presentes]:
            t.result()


IBGE = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/Agregados_por_Distrito_csv/"
COD_SAO_PAULO = "3550308"


def sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.upper()) if unicodedata.category(c) != "Mn").strip()


def etapa_ibge_populacao(args, progresso):
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
    progresso.log(f"População 2022 gravada em {len(distritos)} distritos (total {sum(ibge.values()):,}).")


def zipfile_nomes(url):
    req = urllib.request.Request(url, headers={"User-Agent": "geohabita-pipeline/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", "replace")
    return re.findall(r'href="(Agregados_por_distritos_basico_BR[^"]*\.zip)"', html)


def etapa_distritos(args, progresso):
    import importar_distritos_sp
    importar_distritos_sp.main()


def etapa_resumo(args, progresso):
    import atualizar_resumo_distritos
    atualizar_resumo_distritos.main()


def etapa_indicadores(args, progresso):
    import atualizar_indicadores
    atualizar_indicadores.main()


def etapa_ssp_baixar(args, progresso):
    argv = ["--destino", args.ssp_destino, "--workers", str(args.workers), "--fontes", *args.fontes]
    if args.desde is not None:
        argv += ["--desde", str(args.desde)]
    if args.ate is not None:
        argv += ["--ate", str(args.ate)]
    argv += [f for f, ligado in (("--com-ano-corrente", args.com_ano_corrente), ("--todo-estado", args.todo_estado),
                                 ("--forcar", args.refazer)) if ligado]
    falhas = baixar_ssp.executar(baixar_ssp.argumentos(argv), progresso)
    if falhas:
        raise RuntimeError(f"fontes da SSP com falha: {', '.join(falhas)}")


def etapa_ssp_carregar(args, progresso):
    ns = argparse.Namespace(manifesto=str(Path(args.ssp_destino) / "manifesto.json"), diretorio=None,
                            dsn=os.environ["DATABASE_URL"], workers=args.workers, refazer=args.refazer)
    _, falhas = carregar_ssp.executar(ns, progresso)
    if falhas:
        raise RuntimeError(f"arquivos com falha: {', '.join(falhas)}")


ETAPAS = {
    "distritos": etapa_distritos,
    "ibge-populacao": etapa_ibge_populacao,
    "geosampa-baixar": etapa_geosampa_baixar,
    "geosampa-carregar": etapa_geosampa_carregar,
    "ssp-baixar": etapa_ssp_baixar,
    "ssp-carregar": etapa_ssp_carregar,
    "resumo": etapa_resumo,
    "indicadores": etapa_indicadores,
}
DEPENDE = {
    "ibge-populacao": ["distritos"],
    "geosampa-carregar": ["geosampa-baixar"],
    "ssp-carregar": ["ssp-baixar"],
    "resumo": ["distritos", "ssp-carregar"],
    "indicadores": ["ibge-populacao", "geosampa-carregar", "resumo"],
}


def executar(etapas, args, progresso):
    """Roda as etapas escolhidas respeitando DEPENDE (só entre as escolhidas). Retorna {etapa: situação}."""
    situacao, prontos = {}, {e: threading.Event() for e in etapas}

    def rodar(etapa):
        try:
            for dep in DEPENDE.get(etapa, []):
                if dep in prontos:
                    prontos[dep].wait()
                    if situacao[dep] != "ok":
                        situacao[etapa] = f"não executada ({dep} falhou)"
                        progresso.log(f"⏭ {etapa}: não executada porque {dep} falhou")
                        return
            progresso.inicio(f"etapa:{etapa}", f"etapa {etapa}")
            try:
                ETAPAS[etapa](args, progresso)
                situacao[etapa] = "ok"
                progresso.fim(f"etapa:{etapa}", f"etapa {etapa} concluída")
            except BaseException as erro:  # inclui SystemExit das etapas
                situacao[etapa] = f"falhou: {erro}"
                progresso.fim(f"etapa:{etapa}", f"etapa {etapa} falhou: {erro}", erro=True)
        finally:
            prontos[etapa].set()

    with ThreadPoolExecutor(len(etapas)) as pool:
        for t in [pool.submit(rodar, e) for e in etapas]:
            t.result()
    return situacao


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapas", nargs="+", choices=ETAPAS, default=list(ETAPAS), help="padrão: todas")
    p.add_argument("--workers", type=int, default=max(2, (os.cpu_count() or 2) - 1),
                   help="processos/conexões simultâneos por etapa (padrão: núcleos - 1)")
    p.add_argument("--refazer", action="store_true", help="baixa e recarrega mesmo o que não mudou")
    p.add_argument("--sem-progresso", action="store_true", help="só linhas de log, mesmo em terminal")
    p.add_argument("--ssp-destino", default=str(RAIZ / "data/raw/ssp"), help="pasta de trabalho da SSP")
    p.add_argument("--fontes", nargs="+", choices=[*baixar_ssp.TODAS_FONTES, "todas"],
                   default=baixar_ssp.FONTES_PADRAO, help=f"fontes da SSP (padrão: {' '.join(baixar_ssp.FONTES_PADRAO)})")
    p.add_argument("--desde", type=int, help="primeiro ano da SSP (padrão: ano corrente - 3)")
    p.add_argument("--ate", type=int, help="último ano da SSP (padrão: último ano completo)")
    p.add_argument("--com-ano-corrente", action="store_true", help="inclui o ano corrente (incompleto)")
    p.add_argument("--todo-estado", action="store_true", help="não filtra o município de São Paulo")
    args = p.parse_args()
    etapas = [e for e in ETAPAS if e in args.etapas]
    inicio = time.monotonic()
    with Progresso(visual=False if args.sem_progresso else None) as progresso:
        progresso.log(f"Pipeline: {', '.join(etapas)} (workers={args.workers})")
        situacao = executar(etapas, args, progresso)
        progresso.log(f"Resumo ({(time.monotonic() - inicio) / 60:.1f} min):")
        for etapa in etapas:
            progresso.log(f"  {etapa:<18} {situacao.get(etapa, '?')}")
    if any(s != "ok" for s in situacao.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
