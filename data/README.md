# Dados SSP-SP

Os CSVs fonte ficam localmente em \`data/raw/Dados Segurança Publica/SSP.SP/CSV\`. Os 13 arquivos somam cerca de 959 MB; arquivos brutos/processados e o banco local de vários GB não são enviados ao GitHub.

- [Consultas SSP-SP](https://www.ssp.sp.gov.br/estatistica/consultas)
- [Dados mensais SSP-SP](https://www.ssp.sp.gov.br/estatistica/dados-mensais)
- [Transparência SSP-SP](https://www.ssp.sp.gov.br/transparenciassp/Consultas.aspx)

Baixe os CSVs dos períodos disponíveis e salve-os com os nomes originais na pasta indicada. O importador mapeia os campos analíticos comuns e preserva as colunas próprias de cada arquivo em JSONB. Para produzir cópias com as colunas da planilha OBJETOS_01_TRIM_2025.csv sem alterar as fontes, use scripts/padronizar_csvs_ssp.py; as saídas locais ficam em data/processed.

## Pipeline automatizado

`uv run --env-file .env scripts/pipeline_dados.py` executa, em ordem: download das camadas do GeoSampa (WFS, `data/raw/geosampa`), importação dos distritos, carga dos equipamentos em `public.equipamento_publico`, importação dos CSVs da SSP-SP (download manual) e atualização dos resumos. Use `--etapas` para rodar partes (por exemplo `--etapas geosampa-baixar geosampa-carregar`). A população por distrito (Censo 2022, IBGE) entra com `--etapas ibge-populacao --populacao-csv arquivo.csv` (colunas `codigo_distrito;populacao`), pois o IBGE não publica esse total por distrito em tabela pronta: some os setores censitários.
