"""Gera cópias dos CSVs SSP com as colunas da planilha de referência."""
import argparse
import csv
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description="Padroniza cópias e preserva os arquivos fonte.")
    parser.add_argument("--origem",required=True,type=Path)
    parser.add_argument("--destino",required=True,type=Path)
    args=parser.parse_args()
    source,dest=args.origem.resolve(),args.destino.resolve()
    if source==dest or source in dest.parents: raise SystemExit("Destino deve ficar fora da pasta de origem.")
    ref=source/"OBJETOS_01_TRIM_2025.csv"
    if not ref.is_file(): raise SystemExit(f"Referência não encontrada: {ref}")
    with ref.open(encoding="utf-8-sig",newline="") as f: columns=next(csv.reader(f,delimiter=";"),None)
    if not columns: raise SystemExit("Planilha de referência vazia.")
    inputs=sorted(source.glob("*.csv"))
    if not inputs: raise SystemExit(f"Nenhum CSV encontrado em {source}")
    dest.mkdir(parents=True,exist_ok=True)
    for src in inputs:
        with src.open(encoding="utf-8-sig",newline="") as inp, (dest/src.name).open("w",encoding="utf-8-sig",newline="") as out:
            reader=csv.DictReader(inp,delimiter=";")
            if not reader.fieldnames: raise ValueError(f"Sem cabeçalho: {src.name}")
            writer=csv.DictWriter(out,fieldnames=columns,delimiter=";",extrasaction="ignore",lineterminator="\n")
            writer.writeheader(); count=0
            for row in reader:
                writer.writerow({column:row.get(column,"") or "" for column in columns}); count+=1
        print(f"{src.name}: {count:,} linhas")
if __name__=="__main__": main()
