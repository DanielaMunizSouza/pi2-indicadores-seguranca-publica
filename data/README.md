# Dados SSP-SP

Os CSVs fonte ficam localmente em \`data/raw/Dados Segurança Publica/SSP.SP/CSV\`. Os 13 arquivos somam cerca de 959 MB; arquivos brutos/processados e o banco local de vários GB não são enviados ao GitHub.

- [Consultas SSP-SP](https://www.ssp.sp.gov.br/estatistica/consultas)
- [Dados mensais SSP-SP](https://www.ssp.sp.gov.br/estatistica/dados-mensais)
- [Transparência SSP-SP](https://www.ssp.sp.gov.br/transparenciassp/Consultas.aspx)

Baixe os CSVs dos períodos disponíveis e salve-os com os nomes originais na pasta indicada. O importador mapeia os campos analíticos comuns e preserva as colunas próprias de cada arquivo em JSONB. Para produzir cópias com as colunas da planilha OBJETOS_01_TRIM_2025.csv sem alterar as fontes, use scripts/padronizar_csvs_ssp.py; as saídas locais ficam em data/processed.
