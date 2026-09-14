import pandas as pd
from pathlib import Path

pasta_dados = Path("data/raw")

arquivos_excel = list(pasta_dados.rglob("*.xlsx"))

print("=" * 30)
print("ANÁLISE DA ESTRUTURA DOS DADOS")
print("=" * 30)

for arquivo in arquivos_excel:

    print("\n")
    print("#" * 70)
    print(f"ARQUIVO: {arquivo.name}")
    print("#" * 70)

    excel = pd.ExcelFile(arquivo)

    for aba in excel.sheet_names:

        print("\n" + "-" * 70)
        print(f"ABA: {aba}")
        print("-" * 70)

        try:

            df = pd.read_excel(
                arquivo,
                sheet_name=aba
            )

            print(f"Linhas: {df.shape[0]}")
            print(f"Colunas: {df.shape[1]}")

            print("\nNomes das colunas:")

            for coluna in df.columns:
                print(f"  - {coluna}")

            print("\nTipos de dados:")

            print(df.dtypes)

            print("\nValores vazios:")

            vazios = df.isna().sum()

            print(vazios[vazios > 0])

            print("\nPrimeiros registros:")

            print(df.head(3).to_string(index=False))

        except Exception as erro:

            print(f"Erro ao analisar a aba: {erro}")