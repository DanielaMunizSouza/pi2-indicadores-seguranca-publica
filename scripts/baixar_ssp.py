"""Baixa as bases XLSX da SSP-SP e converte as abas de dados em CSV (';', UTF-8 com BOM).

Saídas (em --destino, padrão data/raw/ssp):
  xlsx/                  download em andamento; cada XLSX é apagado depois de convertido (economiza disco)
  csv/                   uma CSV por aba de dados, pronta para scripts/carregar_ssp.py
  dicionarios/           abas de metodologia/dicionário de dados, em CSV
  manifesto.json         Last-Modified/tamanho de cada fonte; só baixa de novo se mudou

Uso: uv run scripts/baixar_ssp.py --desde 2022
"""
import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, time as hora
from pathlib import Path

BASE = "https://www.ssp.sp.gov.br/assets/estatistica/transparencia"
AGENTE = {"User-Agent": "Mozilla/5.0 (geohabita-pipeline)"}
# fontes anuais: um arquivo por ano, o do ano corrente é atualizado pela SSP periodicamente
FONTES_ANUAIS = {
    "ObjetosSubtraidos": "baseDados/objetosSub/ObjetosSubtraidos_{ano}.xlsx",
    "VeiculosSubtraidos": "baseDados/veiculosSub/VeiculosSubtraidos_{ano}.xlsx",
    "CelularesSubtraidos": "baseDados/celularesSub/CelularesSubtraidos_{ano}.xlsx",
    "SPDadosCriminais": "spDados/SPDadosCriminais_{ano}.xlsx",
    "DadosProdutividade": "spDados/DadosProdutividade_{ano}.xlsx",
}
# MDIP (mortes por intervenção policial): um único arquivo 2013-hoje, nomeado com o ano corrente
MDIP = "spDados/MDIP_{ano}.xlsx"
ABAS_DOCUMENTACAO = re.compile(r"^(METODOLOGIA|DICIONARIO|CAMPOS)", re.I)


def requisitar(url, metodo="GET", cabecalhos=None):
    req = urllib.request.Request(url, method=metodo, headers={**AGENTE, **(cabecalhos or {})})
    return urllib.request.urlopen(req, timeout=120)


def cabecalho_remoto(url):
    """(last_modified, tamanho) ou None se o arquivo não existe (ex.: ano futuro)."""
    try:
        with requisitar(url, "HEAD") as r:
            return r.headers.get("Last-Modified"), int(r.headers.get("Content-Length", 0))
    except urllib.error.HTTPError as erro:
        if erro.code in (403, 404):
            return None
        raise


def xlsx_integro(caminho, tamanho):
    return caminho.stat().st_size == tamanho and zipfile.is_zipfile(caminho)


def baixar(url, destino, tamanho, tentativas=12):
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
        except Exception as erro:
            print(f"  conexão interrompida ({erro}); tentativa {n + 1}/{tentativas}", file=sys.stderr)
            time.sleep(min(2 ** n, 30))
    if not (parcial.exists() and xlsx_integro(parcial, tamanho)):
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
        return repr(v)
    return str(v).strip()


def slug(nome):
    return re.sub(r"[^A-Za-z0-9]+", "_", nome).strip("_")


def converter(xlsx, pasta_csv, pasta_dic):
    """Converte cada aba para CSV, em fluxo (os arquivos passam de 400 MB). Retorna os CSVs de dados."""
    import openpyxl
    gerados = []
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            doc = bool(ABAS_DOCUMENTACAO.match(ws.title.strip()))
            sufixo = "" if len(wb.worksheets) == 1 else f"__{slug(ws.title)}"
            destino = (pasta_dic if doc else pasta_csv) / f"{xlsx.stem}{sufixo}.csv"
            tmp = destino.with_suffix(".tmp")
            linhas = 0
            with tmp.open("w", encoding="utf-8-sig", newline="") as saida:
                w = csv.writer(saida, delimiter=";", lineterminator="\n")
                larguras = None
                for i, linha in enumerate(ws.iter_rows(values_only=True)):
                    valores = [texto(v) for v in linha]
                    if not any(valores):
                        continue
                    if not doc:
                        if larguras is None:  # cabeçalho: limpa espaços (ex.: 'DP_CIRCUNSCRICAO ')
                            valores = [v.strip() for v in valores]
                            larguras = len(valores)
                        else:
                            valores = (valores + [""] * larguras)[:larguras]
                    w.writerow(valores)
                    linhas += 1
            tmp.replace(destino)
            if not doc:
                gerados.append(destino.name)
            print(f"  aba {ws.title!r}: {linhas - 1 if not doc else linhas:,} linhas -> {destino.parent.name}/{destino.name}")
    finally:
        wb.close()
    return gerados


def alvos(desde, ate, so_mdip, sem_mdip):
    for ano in range(desde, ate + 1):
        if not so_mdip:
            for nome, modelo in FONTES_ANUAIS.items():
                yield f"{nome}_{ano}", f"{BASE}/{modelo.format(ano=ano)}"
    if not sem_mdip:
        # o nome do MDIP carrega o ano corrente; se o deste ano ainda não saiu, usa o anterior
        for ano in (ate, ate - 1):
            url = f"{BASE}/{MDIP.format(ano=ano)}"
            if cabecalho_remoto(url):
                yield f"MDIP_{ano}", url
                break


def main():
    hoje = date.today()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--destino", type=Path, default=Path("data/raw/ssp"))
    p.add_argument("--desde", type=int, default=2022, help="primeiro ano (padrão 2022)")
    p.add_argument("--ate", type=int, default=hoje.year, help="último ano (padrão: ano corrente)")
    p.add_argument("--so-mdip", action="store_true")
    p.add_argument("--sem-mdip", action="store_true")
    p.add_argument("--forcar", action="store_true", help="ignora o manifesto e baixa de novo")
    a = p.parse_args()

    xlsx_dir, csv_dir, dic_dir = (a.destino / d for d in ("xlsx", "csv", "dicionarios"))
    for d in (xlsx_dir, csv_dir, dic_dir):
        d.mkdir(parents=True, exist_ok=True)
    manifesto_path = a.destino / "manifesto.json"
    manifesto = json.loads(manifesto_path.read_text()) if manifesto_path.exists() else {}

    falhas = []
    for chave, url in alvos(a.desde, a.ate, a.so_mdip, a.sem_mdip):
        print(f"{chave}")
        try:
            remoto = cabecalho_remoto(url)
            if remoto is None:
                print("  não publicado ainda")
                continue
            modificado, tamanho = remoto
            anterior = manifesto.get(chave, {})
            em_dia = (anterior.get("last_modified") == modificado and anterior.get("tamanho") == tamanho
                      and all((csv_dir / c).exists() for c in anterior.get("csvs", [])) and anterior.get("csvs"))
            if em_dia and not a.forcar:
                print("  em dia")
                continue
            destino = xlsx_dir / url.rsplit("/", 1)[1]
            if not (destino.exists() and xlsx_integro(destino, tamanho)) or a.forcar:
                print(f"  baixando {tamanho / 1e6:.0f} MB")
                baixar(url, destino, tamanho)
            csvs = converter(destino, csv_dir, dic_dir)
            manifesto[chave] = {"url": url, "last_modified": modificado, "tamanho": tamanho,
                                "csvs": csvs, "processado_em": datetime.now().astimezone().isoformat(timespec="seconds")}
            manifesto_path.write_text(json.dumps(manifesto, indent=1, ensure_ascii=False))
            destino.unlink()  # só depois de CSVs e manifesto gravados; o manifesto evita baixar de novo
        except Exception as erro:  # uma fonte com problema não derruba as demais
            print(f"  FALHA: {erro}", file=sys.stderr)
            falhas.append(chave)
    if falhas:
        raise SystemExit(f"Falharam: {', '.join(falhas)}")


if __name__ == "__main__":
    main()
