import pandas as pd
from pathlib import Path

pasta_dados = Path("data/raw")

arquivos_excel = list(pasta_dados.rglob("*.xlsx"))

print("=" * 24)
print("INSPEÇÃO DOS ARQUIVOS EXCEL")
print("=" * 24)

if not arquivos_excel:
    print("Nenhum arquivo Excel encontrado.")
else:

    for arquivo in arquivos_excel:

        print("\n" + "=" * 24)
        print(f"ARQUIVO: {arquivo}")
        print("=" * 24)

        try:
            excel = pd.ExcelFile(arquivo)

            print("\nAbas encontradas:")

            for aba in excel.sheet_names:
                print(f"  - {aba}")

        except Exception as erro:
            print(f"Erro ao ler o arquivo: {erro}")