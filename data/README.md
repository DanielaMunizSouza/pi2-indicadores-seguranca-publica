# Dados SSP-SP

Os CSVs fonte ficam localmente em \`data/raw/Dados Segurança Publica/SSP.SP/CSV\`. Os 13 arquivos somam cerca de 959 MB; arquivos brutos/processados e o banco local de vários GB não são enviados ao GitHub.

- [Consultas SSP-SP](https://www.ssp.sp.gov.br/estatistica/consultas)
- [Dados mensais SSP-SP](https://www.ssp.sp.gov.br/estatistica/dados-mensais)
- [Transparência SSP-SP](https://www.ssp.sp.gov.br/transparenciassp/Consultas.aspx)

Baixe os CSVs dos períodos disponíveis e salve-os com os nomes originais na pasta indicada. O importador mapeia os campos analíticos comuns e preserva as colunas próprias de cada arquivo em JSONB. Para produzir cópias com as colunas da planilha OBJETOS_01_TRIM_2025.csv sem alterar as fontes, use scripts/padronizar_csvs_ssp.py; as saídas locais ficam em data/processed.

## Pipeline automatizado

`uv run --env-file .env scripts/pipeline_dados.py` executa, em ordem: download das camadas do GeoSampa (`data/raw/geosampa`), importação dos distritos, carga dos equipamentos em `public.equipamento_publico`, download e conversão das bases da SSP-SP (`data/raw/ssp`), importação dos CSVs e atualização dos resumos. Use `--etapas` para rodar partes, por exemplo `--etapas ssp-baixar ssp-carregar`.

### Bases da SSP-SP

`scripts/baixar_ssp.py` baixa os XLSX de `https://www.ssp.sp.gov.br/assets/estatistica/transparencia/` e converte cada aba de dados em CSV (abas de metodologia e dicionário vão para `data/raw/ssp/dicionarios/`):

| Padrão do arquivo | Conteúdo | `categoria_dado` |
|---|---|---|
| `baseDados/objetosSub/ObjetosSubtraidos_{ano}.xlsx` | objetos subtraídos | `objetos` |
| `baseDados/veiculosSub/VeiculosSubtraidos_{ano}.xlsx` | veículos subtraídos | `veiculos` |
| `baseDados/celularesSub/CelularesSubtraidos_{ano}.xlsx` | celulares subtraídos | `celulares_subtraidos` |
| `spDados/SPDadosCriminais_{ano}.xlsx` | ocorrências criminais (abas semestrais) | `criminal` |
| `spDados/DadosProdutividade_{ano}.xlsx` | presos, veículos recuperados, armas, entorpecentes, flagrantes, ECA, prisões (uma aba cada) | `presos_apreendidos`, `veiculos_recuperados`, `armas_apreendidas`, `entorpecentes_gramas`, `apreensao_entorpecente`, `flagrantes`, `apreensao_eca`, `prisoes` |
| `spDados/MDIP_{ano}.xlsx` | mortes decorrentes de intervenção policial, 2013 até hoje em um só arquivo (o nome leva o ano corrente) | `mdip` |

O `manifesto.json` guarda `Last-Modified` e tamanho de cada fonte; uma nova execução só baixa e reconverte o que a SSP atualizou (normalmente o ano corrente). Os arquivos grandes passam de 400 MB e a conversão leva vários minutos. Para atualizar periodicamente, agende o pipeline, por exemplo semanalmente: `0 3 * * 1 cd /caminho/do/projeto && uv run --env-file .env scripts/pipeline_dados.py --etapas ssp-baixar ssp-carregar resumo`.

Cuidados com os dados:

- A SSP escreve `NULL` nos campos vazios e grava latitude/longitude `0,0` quando não há coordenada; o importador trata ambos como ausentes.
- Em crimes sensíveis o logradouro vem como "VEDAÇÃO DA DIVULGAÇÃO DOS DADOS RELATIVOS" e é descartado.
- O município vem como `S.PAULO`; o importador normaliza para `São Paulo`. O CEP vem como número sem o zero à esquerda e é completado para 8 dígitos.
- Placa, data de nascimento e profissão não são guardados no JSONB.
- Cada boletim pode gerar várias linhas (veículos, objetos, pessoas), como a própria SSP avisa na aba de metodologia. As contagens são de linhas, não de boletins.
- Se você já importou CSVs antigos (por exemplo `OBJETOS_01_TRIM_2025.csv`) que cobrem o mesmo período dos arquivos novos, apague os antigos do banco para não contar duas vezes: `DELETE FROM registro_ocorrencia WHERE arquivo_origem = '...'`.

### Outras fontes

A população por distrito (Censo 2022, IBGE) entra com `--etapas ibge-populacao --populacao-csv arquivo.csv` (colunas `codigo_distrito;populacao`), pois o IBGE não publica esse total por distrito em tabela pronta: some os setores censitários. O modelo de dados está em `database/modelo_er.mmd`, com a comparação com o relatório em `database/modelo_er.md`.
