# Indicadores de Segurança Pública — São Paulo

Aplicação web para explorar registros públicos SSP-SP por CEP, categoria, período e distrito municipal. O mapa colore os 96 distritos oficiais com a contagem de ocorrências georreferenciadas que caem em cada limite. O número de registros não é uma taxa por habitante nem uma probabilidade de vitimização.

## Aplicação web

1. Na raiz do projeto, crie `.env` a partir de `.env.example` e ajuste a conexão para a senha, porta, usuário e banco indicados no pgAdmin. A senha fica somente em `.env`, que é ignorado pelo Git. Se ela contiver caracteres reservados de URL, codifique-os (por exemplo, `@` como `%40`).
2. Instale o [uv](https://docs.astral.sh/uv/), que gerencia o Python, o ambiente virtual e as dependências do projeto (declaradas em `pyproject.toml` e fixadas em `uv.lock`):

   - Windows (PowerShell): `winget install --id=astral-sh.uv -e`
   - Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`, ou o pacote `uv` da distribuição

3. Na raiz do projeto, em qualquer sistema:

```bash
uv sync
uv run --env-file .env scripts/pipeline_dados.py   # popula o banco (veja a seção Dados)
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

O banco precisa existir e ter o esquema aplicado antes do pipeline (seção seguinte). A primeira execução baixa vários GB e leva um bom tempo.

`uv sync` instala o Python 3.12, se necessário, cria `.venv` e instala exatamente as versões de `uv.lock`, incluindo as ferramentas de teste. Não é preciso ativar o ambiente: `uv run` usa `.venv` automaticamente. Para adicionar uma biblioteca, use `uv add nome` (ou `uv add --dev nome` para uso exclusivo em testes) e versione `pyproject.toml` e `uv.lock` juntos.

Abra http://127.0.0.1:8000. A API interativa está em http://127.0.0.1:8000/docs. Não envie senhas ao GitHub.

A aplicação lê `.env` automaticamente. O pipeline e o importador `scripts/carregar_ssp.py` leem apenas variáveis de ambiente; por isso, execute-os com `uv run --env-file .env`, como na seção [Dados](#dados).

## Banco para os demais integrantes

GitHub não hospeda uma conexão PostgreSQL ao vivo. O repositório contém o esquema e um Compose opcional que inicia uma cópia local com PostGIS na porta 5433 (após instalar Docker Desktop): copie .env.example para .env, altere a senha e rode:

```powershell
docker compose --env-file .env -f database/docker-compose.yml up -d
```

No Linux, o mesmo comando funciona com Docker Engine e o plugin Compose (pacote `docker-compose-plugin` ou equivalente da distribuição), sem Docker Desktop. Se o usuário não pertencer ao grupo `docker`, prefixe o comando com `sudo`. Na primeira inicialização, o contêiner executa `database/schema.sql` automaticamente. Para um PostgreSQL instalado no sistema, com a extensão PostGIS, aplique o esquema com `psql "postgresql://usuario:senha@localhost:5432/banco" -f database/schema.sql`.

Cada pessoa terá banco local. No `.env`, aponte DATABASE_URL para esse banco (usuário e senha definidos ali; porta 5433). Depois de aplicar `database/schema.sql`, rode `uv run --env-file .env scripts/pipeline_dados.py`, que baixa e importa as fontes públicas e gera a agregação diária usada pela interface (detalhes na seção Dados). Quem já tem um banco criado antes pode reaplicar `database/schema.sql` com segurança: o arquivo é idempotente e só acrescenta as tabelas e colunas novas. O modelo de dados está em `database/modelo_er.mmd`.

## Testes

A suíte segue desenvolvimento guiado por testes (TDD): os testes descrevem o comportamento esperado pela especificação de requisitos (`relatorio_parcial/requisitos_geohabita.tex`) antes da implementação.

Instale as dependências de desenvolvimento:

```powershell
py -m pip install -r requirements-dev.txt
```

Execute os testes na raiz do projeto:

```powershell
py -m pytest
```

Para medir a cobertura das regras de negócio (meta de 70% do RNF11):

```powershell
py -m pytest --cov=geohabita
```

A especificação, os testes e o código são organizados por regra:

- `geohabita/domain/` reúne as regras de negócio puras, sem acesso a banco de dados, rede ou interface.
- `geohabita/application/` reúne os casos de uso que coordenam o domínio e os serviços externos, recebidos como dependências para que possam ser substituídos por dublês nos testes.
- `tests/domain/` e `tests/application/` reúnem os testes correspondentes, com referência à regra (RN), ao requisito (RF/RNF) ou ao caso de teste (CT) da especificação.

Cada módulo de domínio cobre um bloco do modelo de indicadores: `cep.py` (validação e normalização de CEP), `thresholds.py` (limiares de distância por tipo de equipamento), `proximity.py` (nota por tipo, tempo de caminhada e IPL), `vitality.py` (IVEP), `rates.py` (taxas oficiais de ocorrências e janela de anos completos), `territory.py` (endereço fora do município), `freshness.py` (validade do cache e dado desatualizado), `data_quality.py` (descarte de coordenadas na carga), `equipment.py` (equipamentos do entorno) e `diagnosis.py` (blocos separados do diagnóstico). Na camada de aplicação, `cep_lookup.py` cobre a consulta de CEP com contingência e cache, e `rate_limit.py`, o limite de requisições por IP. No momento, as funções de cálculo ainda são contratos que levantam `NotImplementedError`, de modo que a suíte permanece em estado vermelho até a implementação. O alvo de cobertura de 70% das regras de negócio vem do RNF11.

## Dados

As bases da SSP-SP somam vários GB (alguns XLSX passam de 400 MB) e o banco local ocupa vários GB, então nada disso é versionado: o repositório traz o pipeline que baixa, converte e importa tudo. Com o esquema aplicado e `DATABASE_URL` no `.env`:

```bash
uv run --env-file .env scripts/pipeline_dados.py
```

Sem argumentos, ele executa tudo, nesta ordem: importação dos distritos (a partir de `data/reference/`), download e carga dos equipamentos públicos do GeoSampa, população por distrito (Censo 2022, IBGE), download, conversão e importação das bases da SSP-SP e resumos do mapa. Só passar `--etapas` restringe a ingestão (por exemplo `--etapas ssp-baixar ssp-carregar resumo` para atualizar só a SSP). O que já está em dia não é baixado de novo. As fontes, os padrões de URL, as categorias e os cuidados com os dados estão em [`data/README.md`](data/README.md).

O importador `scripts/carregar_ssp.py` reprocessa cada arquivo em transação, sem alterar os originais, e mantém colunas heterogêneas em JSONB. Para usar CSVs que você já baixou manualmente, execute `uv run --env-file .env scripts/carregar_ssp.py --diretorio <pasta>`. Para criar cópias com as colunas da referência OBJETOS_01_TRIM_2025.csv, use `uv run scripts/padronizar_csvs_ssp.py` com `--origem` e `--destino`. Saídas em `data/raw` e `data/processed` não são versionadas.

## Interpretação

As contagens são linhas de planilhas policiais; um boletim pode ter mais de uma linha. Nem todos os registros têm CEP ou coordenadas. O mapa atribui pontos georreferenciados aos distritos pelo PostGIS; os registros sem coordenada permanecem nos indicadores gerais, mas não podem ser contados por área. As cores são faixas relativas entre distritos para os filtros escolhidos, não taxas populacionais. Ao filtrar por CEP, os registros georreferenciados são reunidos em um único distrito: o de maior concentração histórica de coordenadas daquele CEP, para evitar que coordenadas divergentes destaquem várias áreas. O resumo mantém o total de registros do CEP. Os distritos são limites administrativos oficiais, não polígonos de CEP ou bairros. A geometria de referência está em `data/reference/distritos_sp.geojson` e sua origem/licença estão documentadas em `data/reference/README.md`.

## Licença

Este repositório usa duas licenças, conforme o tipo de conteúdo:

| Conteúdo | Licença |
|---|---|
| Código-fonte e software (tudo fora dos diretórios do relatório) | [GNU AGPL-3.0](LICENSE) |
| Relatório acadêmico: diretórios `relatorio/` e `relatorio_parcial/` (fontes LaTeX, bibliografia, figuras, fontes dos diagramas e PDFs gerados) | [CC BY-ND 4.0](https://creativecommons.org/licenses/by-nd/4.0/deed.pt-br) |

**Código (AGPL-3.0):** o software é livre para uso, estudo, modificação e redistribuição nos termos do arquivo `LICENSE`. Quem disponibilizar uma versão modificada para uso por rede deve oferecer o código-fonte correspondente aos usuários.

**Relatório (CC BY-ND 4.0):** o relatório pode ser copiado e redistribuído livremente, em qualquer meio ou formato, inclusive para fins comerciais, desde que integralmente, sem alterações e com a atribuição aos autores. Não é permitido distribuir versões modificadas ou obras derivadas do texto. O conteúdo é definido exclusivamente pelos autores, que são as pessoas identificadas como autoras no arquivo `.tex` principal e no PDF final do relatório, incluindo quem vier a ser acrescentado nessas listas. Citações com a devida referência continuam permitidas nos termos do art. 46 da Lei nº 9.610/1998. Detalhes em `relatorio/LICENSE.md`.

**Exceções:** materiais de terceiros mantêm as licenças originais, por exemplo a classe abnTeX2 (`abntex2_ref.cls`, LPPL 1.3c), o texto da AGPL (`AGPL.tex`, © Free Software Foundation) e os dados de `data/reference/` (ver `data/reference/README.md`).
