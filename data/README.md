# Dados SSP-SP

Os CSVs fonte ficam localmente em \`data/raw/Dados Segurança Publica/SSP.SP/CSV\`. Os 13 arquivos somam cerca de 959 MB; arquivos brutos/processados e o banco local de vários GB não são enviados ao GitHub.

- [Consultas SSP-SP](https://www.ssp.sp.gov.br/estatistica/consultas)
- [Dados mensais SSP-SP](https://www.ssp.sp.gov.br/estatistica/dados-mensais)
- [Transparência SSP-SP](https://www.ssp.sp.gov.br/transparenciassp/Consultas.aspx)

Baixe os CSVs dos períodos disponíveis e salve-os com os nomes originais na pasta indicada. O importador mapeia os campos analíticos comuns e preserva as colunas próprias de cada arquivo em JSONB. Para produzir cópias com as colunas da planilha OBJETOS_01_TRIM_2025.csv sem alterar as fontes, use scripts/padronizar_csvs_ssp.py; as saídas locais ficam em data/processed.

## Pipeline automatizado

`uv run --env-file .env scripts/pipeline_dados.py` executa todas as etapas. As que não dependem umas das outras rodam em paralelo, em três trilhas que se juntam no resumo do mapa:

```
distritos ──> ibge-populacao ─────────────────┐
geosampa-baixar ──> geosampa-carregar         ├──> resumo
ssp-baixar ──> ssp-carregar ──────────────────┘
```

- `--etapas` roda só algumas etapas; as dependências valem apenas entre as escolhidas.
- `--workers N` define quantos processos ou conexões cada etapa usa ao mesmo tempo. O padrão é o número de núcleos menos 1 (mínimo 2).
- Em terminal, há uma barra por tarefa em andamento. Com a saída redirecionada para arquivo, ou com `--sem-progresso`, o pipeline escreve linhas com horário no início e no fim de cada etapa e arquivo, e nos marcos de 25, 50 e 75%.
- Uma etapa que falha não interrompe as que não dependem dela. No fim aparece um resumo com o status de cada etapa, e o código de saída é 1 se alguma falhou.
- O que não mudou não é baixado nem recarregado de novo; `--refazer` força.

### Bases da SSP-SP

`scripts/baixar_ssp.py` baixa os XLSX de `https://www.ssp.sp.gov.br/assets/estatistica/transparencia/` e converte cada aba de dados em CSV (abas de metodologia e dicionário vão para `data/raw/ssp/dicionarios/`).

**Escopo padrão**, que é o que os indicadores usam (RF10 e RN08: taxas por natureza em janela de três anos completos):

- **Fontes:** `SPDadosCriminais` (furto, roubo, furto e roubo de veículo, crimes contra a vida), `CelularesSubtraidos` (o SPDados não separa roubo de celular) e `MDIP`.
- **Anos:** os três últimos anos completos. Em 2026, isso é 2023 a 2025; o ano corrente incompleto não entra.
- **Território:** só ocorrências no município de São Paulo, filtradas pelo código IBGE do local do fato já na conversão. As bases cobrem o estado inteiro, e a capital é cerca de 40% das linhas.

Para ampliar: `--fontes` (incluindo `veiculos`, `objetos`, `produtividade` ou `todas`), `--desde`/`--ate`, `--com-ano-corrente` e `--todo-estado`. Ao reduzir o escopo de novo, os CSVs e os registros do banco que saíram dele são removidos, para não contaminar as contagens.

| `--fontes` | Padrão do arquivo | Conteúdo | `categoria_dado` |
|---|---|---|---|
| `criminais` (padrão) | `spDados/SPDadosCriminais_{ano}.xlsx` | ocorrências criminais (abas semestrais) | `criminal` |
| `celulares` (padrão) | `baseDados/celularesSub/CelularesSubtraidos_{ano}.xlsx` | celulares subtraídos | `celulares_subtraidos` |
| `mdip` (padrão) | `spDados/MDIP_{ano}.xlsx` | mortes decorrentes de intervenção policial, 2013 até hoje em um só arquivo (o nome leva o ano corrente; não é recortado por ano) | `mdip` |
| `veiculos` | `baseDados/veiculosSub/VeiculosSubtraidos_{ano}.xlsx` | veículos subtraídos (detalhe do veículo; os crimes já estão no SPDados) | `veiculos` |
| `objetos` | `baseDados/objetosSub/ObjetosSubtraidos_{ano}.xlsx` | objetos subtraídos (cerca de 500 MB por ano) | `objetos` |
| `produtividade` | `spDados/DadosProdutividade_{ano}.xlsx` | produtividade policial: presos, veículos recuperados, armas, entorpecentes, flagrantes, ECA, prisões. Publicado a partir de 2024. | `presos_apreendidos`, `veiculos_recuperados`, `armas_apreendidas`, `entorpecentes_gramas`, `apreensao_entorpecente`, `flagrantes`, `apreensao_eca`, `prisoes` |

Cada XLSX é apagado assim que é convertido em CSV, o que reduz o pico de disco (o CSV ocupa cerca do dobro do XLSX). O `manifesto.json` guarda `Last-Modified` e tamanho de cada fonte; uma nova execução só baixa e reconverte o que a SSP atualizou (normalmente o ano corrente). Downloads rodam dois por vez (o servidor da SSP corta conexões longas e o download é retomado de onde parou) e as conversões rodam em processos paralelos. Na carga, cada arquivo vai numa transação própria, e um arquivo cujo conteúdo (hash SHA-1) já consta em `carga_etl` é pulado, mesmo que tenha sido reconvertido. Para atualizar periodicamente, agende o pipeline, por exemplo semanalmente: `0 3 * * 1 cd /caminho/do/projeto && uv run --env-file .env scripts/pipeline_dados.py --etapas ssp-baixar ssp-carregar resumo >> pipeline.log 2>&1`.

Cuidados com os dados:

- A SSP escreve `NULL` nos campos vazios e grava latitude/longitude `0,0` quando não há coordenada; o importador trata ambos como ausentes.
- Em crimes sensíveis o logradouro vem como "VEDAÇÃO DA DIVULGAÇÃO DOS DADOS RELATIVOS" e é descartado.
- O município gravado é o do local do fato (código IBGE ou município da circunscrição), não o da delegacia onde o BO foi registrado; `S.PAULO` vira `São Paulo`. O CEP vem como número sem o zero à esquerda e é completado para 8 dígitos.
- Placa, data de nascimento e profissão não são guardados no JSONB.
- Cada boletim pode gerar várias linhas (veículos, objetos, pessoas), como a própria SSP avisa na aba de metodologia. As contagens são de linhas, não de boletins.
- Se você já importou CSVs antigos (por exemplo `OBJETOS_01_TRIM_2025.csv`) que cobrem o mesmo período dos arquivos novos, apague os antigos do banco para não contar duas vezes: `DELETE FROM registro_ocorrencia WHERE arquivo_origem = '...'`.

### Outras fontes

A população por distrito vem do arquivo `Agregados_por_distritos_basico_BR` do Censo 2022 (variável `v0001`, população residente), baixado de `ftp.ibge.gov.br` para `data/raw/ibge/` e associado aos distritos do GeoSampa pelo nome, sem acento. Os 96 distritos casam e o total de São Paulo é 11.451.999. As camadas do GeoSampa que o servidor deles recusa (hoje `GEOSAMPA_cadparcs_parque_unidade_conservacao` e a de praças) são puladas com aviso. A camada de iluminação pública tem cerca de 663 mil pontos e leva alguns minutos. O fluxo do pipeline está em `database/pipeline_dados.mmd`. O modelo de dados está em `database/modelo_er.mmd`, com a comparação com o relatório em `database/modelo_er.md`.
