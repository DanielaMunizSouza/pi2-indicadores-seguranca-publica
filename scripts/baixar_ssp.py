"""Baixa as bases XLSX da SSP-SP e converte as abas de dados em CSV (';', UTF-8 com BOM).

Escopo padrão (o que os indicadores usam, RF10/RN08):
  - fontes: SPDadosCriminais (furto, roubo, veículos, crimes contra a vida), CelularesSubtraidos
    (o SPDados não separa roubo de celular) e MDIP (mortes por intervenção policial);
  - anos: os três últimos anos completos (janela trienal; o ano corrente incompleto não entra);
  - só ocorrências do município de São Paulo (as bases cobrem o estado inteiro).
Use --fontes, --desde/--ate, --com-ano-corrente e --todo-estado para ampliar.

Saídas (em --destino, padrão data/raw/ssp):
  xlsx/            download em andamento; cada XLSX é apagado depois de convertido
  csv/             uma CSV por aba de dados, pronta para scripts/carregar_ssp.py
  dicionarios/     abas de metodologia/dicionário de dados
  manifesto.json   fontes do escopo atual, com Last-Modified/tamanho; só baixa de novo o que mudou
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as hora
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from progresso import Progresso, ProgressoRemoto  # noqa: E402

BASE = "https://www.ssp.sp.gov.br/assets/estatistica/transparencia"
AGENTE = {"User-Agent": "Mozilla/5.0 (geohabita-pipeline)"}
# fontes anuais: um arquivo por ano; o do ano corrente é atualizado pela SSP periodicamente
FONTES_ANUAIS = {
    "criminais": ("SPDadosCriminais", "spDados/SPDadosCriminais_{ano}.xlsx"),
    "celulares": ("CelularesSubtraidos", "baseDados/celularesSub/CelularesSubtraidos_{ano}.xlsx"),
    "veiculos": ("VeiculosSubtraidos", "baseDados/veiculosSub/VeiculosSubtraidos_{ano}.xlsx"),
    "objetos": ("ObjetosSubtraidos", "baseDados/objetosSub/ObjetosSubtraidos_{ano}.xlsx"),
    "produtividade": ("DadosProdutividade", "spDados/DadosProdutividade_{ano}.xlsx"),
}
# MDIP: um único arquivo 2013-hoje, nomeado com o ano corrente (pequeno; não é recortado por ano)
MDIP = "spDados/MDIP_{ano}.xlsx"
FONTES_PADRAO = ["criminais", "celulares", "mdip"]
TODAS_FONTES = [*FONTES_ANUAIS, "mdip"]
PREFIXOS = tuple(n for n, _ in FONTES_ANUAIS.values()) + ("MDIP",)
COD_SAO_PAULO = "3550308"
DOWNLOADS_SIMULTANEOS = 2  # o servidor da SSP corta conexões; mais que isso piora


def normalizado(texto):
    texto = unicodedata.normalize("NFD", str(texto).upper())
    return re.sub(r"[^A-Z0-9]", "", "".join(c for c in texto if unicodedata.category(c) != "Mn"))


def aba_de_documentacao(titulo):
    return normalizado(titulo).startswith(("METODOLOGIA", "DICIONARIO", "CAMPOS"))


def requisitar(url, metodo="GET", cabecalhos=None):
    req = urllib.request.Request(url, method=metodo, headers={**AGENTE, **(cabecalhos or {})})
    return urllib.request.urlopen(req, timeout=120)


def cabecalho_remoto(url, tentativas=4):
    """(last_modified, tamanho) ou None se o arquivo não existe (ex.: ano ainda não publicado).
    O servidor da SSP derruba conexões com frequência, então erros de rede são tentados de novo."""
    for n in range(tentativas):
        try:
            with requisitar(url, "HEAD") as r:
                return r.headers.get("Last-Modified"), int(r.headers.get("Content-Length", 0))
        except urllib.error.HTTPError as erro:
            if erro.code in (403, 404):
                return None
            if n == tentativas - 1:
                raise
        except (urllib.error.URLError, OSError):
            if n == tentativas - 1:
                raise
        time.sleep(2 * 2 ** n)


def xlsx_integro(caminho, tamanho):
    return caminho.exists() and caminho.stat().st_size == tamanho and zipfile.is_zipfile(caminho)


def baixar(url, destino, tamanho, progresso, chave, tentativas=12):
    """Download com retomada (o servidor às vezes corta conexões longas)."""
    parcial = destino.with_suffix(".part")
    for n in range(tentativas):
        atual = parcial.stat().st_size if parcial.exists() else 0
        if atual >= tamanho:
            break
        try:
            with requisitar(url, cabecalhos={"Range": f"bytes={atual}-"} if atual else None) as r:
                if atual and r.status != 206:  # servidor ignorou o Range: recomeça
                    atual = 0
                with parcial.open("ab" if atual else "wb") as f:
                    while bloco := r.read(1 << 20):
                        f.write(bloco)
                        atual += len(bloco)
                        progresso.avanco(chave, feito=atual)
        except Exception as erro:
            progresso.log(f"  {destino.stem}: conexão interrompida ({erro}); tentativa {n + 1}/{tentativas}")
            time.sleep(min(2 ** n, 30))
    if not xlsx_integro(parcial, tamanho):
        raise RuntimeError(f"download incompleto ou corrompido: {url}")
    parcial.replace(destino)


def texto(v):
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d") if v.time() == hora(0) else v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, hora):
        return v.strftime("%H:%M:%S")
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() and abs(v) < 1e15 else repr(v)
    return str(v).strip()


def slug(nome):
    return re.sub(r"[^A-Za-z0-9]+", "_", nome).strip("_")


def filtro_capital(cabecalho):
    """Função linha -> bool que mantém só o município de São Paulo, ou None se não há coluna para filtrar.
    Usa o código IBGE do local do fato; o MDIP não tem esse código e usa o município da circunscrição."""
    nomes = [normalizado(c) for c in cabecalho]
    for i, n in enumerate(nomes):
        if n in ("CDIBGE", "CODIBGE"):
            return lambda linha, i=i: linha[i].split(".")[0] == COD_SAO_PAULO
    for i, n in enumerate(nomes):
        if n.startswith(("MUNICIPIOCIRC", "NOMEMUNICIPIOCIRC")):
            return lambda linha, i=i: normalizado(linha[i]) in ("SPAULO", "SAOPAULO")
    return None


def converter(xlsx, pasta_csv, pasta_dic, so_capital, fila=None):
    """Converte cada aba para CSV, em fluxo (alguns arquivos passam de 400 MB). Roda em processo filho.
    Retorna a lista de CSVs de dados gerados."""
    import warnings
    import openpyxl
    warnings.filterwarnings("ignore", module="openpyxl")
    progresso = ProgressoRemoto(fila) if fila is not None else None
    xlsx, pasta_csv, pasta_dic = Path(xlsx), Path(pasta_csv), Path(pasta_dic)
    gerados = []
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            doc = aba_de_documentacao(ws.title)
            sufixo = "" if len(wb.worksheets) == 1 else f"__{slug(ws.title)}"
            destino = (pasta_dic if doc else pasta_csv) / f"{xlsx.stem}{sufixo}.csv"
            chave = f"conv:{destino.name}"
            if progresso and not doc:
                progresso.inicio(chave, f"convertendo {destino.stem}", total=ws.max_row)
            tmp = destino.with_suffix(".tmp")
            lidas = mantidas = 0
            with tmp.open("w", encoding="utf-8-sig", newline="") as saida:
                w = csv.writer(saida, delimiter=";", lineterminator="\n")
                largura, manter = None, None
                for linha in ws.iter_rows(values_only=True):
                    lidas += 1
                    if progresso and not doc and lidas % 20000 == 0:
                        progresso.avanco(chave, feito=lidas)
                    valores = [texto(v) for v in linha]
                    if not any(valores):
                        continue
                    if not doc:
                        if largura is None:  # cabeçalho: limpa espaços (ex.: 'DP_CIRCUNSCRICAO ')
                            valores = [v.strip() for v in valores]
                            largura = len(valores)
                            if so_capital:
                                manter = filtro_capital(valores)
                                if manter is None and progresso:
                                    progresso.log(f"  {destino.stem}: sem coluna de município, aba mantida inteira")
                        else:
                            valores = (valores + [""] * largura)[:largura]
                            if manter is not None and not manter(valores):
                                continue
                    w.writerow(valores)
                    mantidas += 1
            tmp.replace(destino)
            if not doc:
                gerados.append(destino.name)
                if progresso:
                    progresso.fim(chave, f"{destino.name}: {mantidas - 1:,} linhas"
                                         + (f" de {lidas - 1:,}" if so_capital else ""))
    finally:
        wb.close()
    return gerados


def alvos(fontes, desde, ate):
    hoje = date.today().year
    for ano in range(desde, ate + 1):
        for fonte in fontes:
            if fonte in FONTES_ANUAIS:
                nome, modelo = FONTES_ANUAIS[fonte]
                yield f"{nome}_{ano}", f"{BASE}/{modelo.format(ano=ano)}"
    if "mdip" in fontes:
        # o nome do MDIP carrega o ano corrente; se o deste ano ainda não saiu, usa o anterior
        for ano in (hoje, hoje - 1):
            url = f"{BASE}/{MDIP.format(ano=ano)}"
            if cabecalho_remoto(url):
                yield f"MDIP_{ano}", url
                return


def argumentos(argv=None):
    hoje = date.today().year
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--destino", type=Path, default=Path("data/raw/ssp"))
    p.add_argument("--fontes", nargs="+", choices=[*TODAS_FONTES, "todas"], default=FONTES_PADRAO,
                   help=f"padrão: {' '.join(FONTES_PADRAO)}")
    p.add_argument("--desde", type=int, default=hoje - 3, help="primeiro ano (padrão: ano corrente - 3)")
    p.add_argument("--ate", type=int, default=hoje - 1, help="último ano (padrão: último ano completo)")
    p.add_argument("--com-ano-corrente", action="store_true", help="inclui o ano corrente (incompleto)")
    p.add_argument("--todo-estado", action="store_true", help="não filtra o município de São Paulo")
    p.add_argument("--workers", type=int, default=max(2, (os.cpu_count() or 2) - 1),
                   help="conversões simultâneas (processos)")
    p.add_argument("--forcar", action="store_true", help="ignora o manifesto e baixa/converte de novo")
    a = p.parse_args(argv)
    if "todas" in a.fontes:
        a.fontes = TODAS_FONTES
    if a.com_ano_corrente:
        a.ate = hoje
    return a


def executar(a, progresso):
    xlsx_dir, csv_dir, dic_dir = (a.destino / d for d in ("xlsx", "csv", "dicionarios"))
    for d in (xlsx_dir, csv_dir, dic_dir):
        d.mkdir(parents=True, exist_ok=True)
    manifesto_path = a.destino / "manifesto.json"
    antigo = json.loads(manifesto_path.read_text()) if manifesto_path.exists() else {}
    filtro = "estado" if a.todo_estado else "capital"
    lista = list(alvos(a.fontes, a.desde, a.ate))
    escopo = {chave for chave, _ in lista}
    manifesto = {k: v for k, v in antigo.items() if k in escopo}
    progresso.log(f"SSP: {len(lista)} arquivos no escopo ({', '.join(a.fontes)}; {a.desde}–{a.ate}; {filtro})")

    def preparar(chave, url):
        anterior = manifesto.get(chave, {})
        convertido = (anterior.get("filtro") == filtro and anterior.get("csvs")
                      and all((csv_dir / c).exists() for c in anterior["csvs"]))
        try:
            remoto = cabecalho_remoto(url)
        except Exception as erro:
            if convertido:  # SSP fora do ar: segue com a versão já convertida em vez de falhar
                return "anterior", str(erro)
            raise
        if remoto is None:
            return "ausente", None
        modificado, tamanho = remoto
        em_dia = convertido and anterior.get("last_modified") == modificado and anterior.get("tamanho") == tamanho
        if em_dia and not a.forcar:
            return "em_dia", None
        destino = xlsx_dir / url.rsplit("/", 1)[1]
        if a.forcar or not xlsx_integro(destino, tamanho):
            progresso.inicio(f"dl:{chave}", f"baixando {chave}", total=tamanho)
            try:
                baixar(url, destino, tamanho, progresso, f"dl:{chave}")
            except Exception:
                progresso.fim(f"dl:{chave}", f"{chave}: download falhou", erro=True)
                raise
            progresso.fim(f"dl:{chave}", f"{chave}: {tamanho / 1e6:.0f} MB baixados")
        return "converter", {"url": url, "last_modified": modificado, "tamanho": tamanho, "xlsx": destino}

    falhas = []
    fila = progresso.fila() if hasattr(progresso, "fila") else None
    with ThreadPoolExecutor(DOWNLOADS_SIMULTANEOS) as rede, ProcessPoolExecutor(a.workers) as cpu:
        downloads = {rede.submit(preparar, chave, url): chave for chave, url in lista}
        conversoes = {}
        for f in as_completed(downloads):
            chave = downloads[f]
            try:
                situacao, info = f.result()
            except Exception as erro:  # uma fonte com problema não derruba as demais
                progresso.log(f"✖ {chave}: {erro}")
                falhas.append(chave)
                continue
            if situacao == "ausente":
                progresso.log(f"  {chave}: não publicado")
            elif situacao == "em_dia":
                progresso.log(f"  {chave}: em dia")
            elif situacao == "anterior":
                progresso.log(f"⚠ {chave}: SSP não respondeu ({info}); usando a versão já convertida")
            else:
                for velho in manifesto.get(chave, {}).get("csvs", []):
                    (csv_dir / velho).unlink(missing_ok=True)
                cf = cpu.submit(converter, str(info["xlsx"]), str(csv_dir), str(dic_dir), not a.todo_estado, fila)
                conversoes[cf] = (chave, info)
        for cf in as_completed(conversoes):
            chave, info = conversoes[cf]
            try:
                csvs = cf.result()
            except Exception as erro:
                progresso.log(f"✖ {chave}: conversão falhou ({erro})")
                falhas.append(chave)
                continue
            xlsx = info.pop("xlsx")
            manifesto[chave] = {**info, "filtro": filtro, "csvs": csvs,
                                "processado_em": datetime.now().astimezone().isoformat(timespec="seconds")}
            manifesto_path.write_text(json.dumps(manifesto, indent=1, ensure_ascii=False))
            xlsx.unlink()  # só depois de CSVs e manifesto gravados; o manifesto evita baixar de novo

    manifesto_path.write_text(json.dumps(manifesto, indent=1, ensure_ascii=False))
    # CSVs gerados pelo pipeline que saíram do escopo (outra fonte/ano/filtro) não devem ser carregados
    ativos = {c for v in manifesto.values() for c in v["csvs"]}
    for arquivo in csv_dir.glob("*.csv"):
        if arquivo.name.startswith(PREFIXOS) and arquivo.name not in ativos:
            arquivo.unlink()
            progresso.log(f"  removido (fora do escopo): {arquivo.name}")
    for arquivo in csv_dir.glob("*.tmp"):
        arquivo.unlink()
    return falhas


def main(argv=None):
    a = argumentos(argv)
    with Progresso() as progresso:
        falhas = executar(a, progresso)
    if falhas:
        raise SystemExit(f"Falharam: {', '.join(falhas)}")


if __name__ == "__main__":
    main()
