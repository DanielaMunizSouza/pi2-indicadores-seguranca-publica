# Indicadores de Segurança Pública — São Paulo

Aplicação web para explorar registros públicos SSP-SP por CEP, categoria, período e distrito municipal. O mapa colore os 96 distritos oficiais com a contagem de ocorrências georreferenciadas que caem em cada limite. O número de registros não é uma taxa por habitante nem uma probabilidade de vitimização.

## Aplicação web

1. Na raiz do projeto, crie `.env` a partir de `.env.example` e ajuste a conexão para a senha, porta, usuário e banco indicados no pgAdmin. A senha fica somente em `.env`, que é ignorado pelo Git. Se ela contiver caracteres reservados de URL, codifique-os (por exemplo, `@` como `%40`).
2. No PowerShell na raiz do projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt -r requirements-web.txt
py scripts/importar_distritos_sp.py
py scripts/atualizar_resumo_distritos.py
py -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Abra http://127.0.0.1:8000. A API interativa está em http://127.0.0.1:8000/docs. Não envie senhas ao GitHub.

## Banco para os demais integrantes

GitHub não hospeda uma conexão PostgreSQL ao vivo. O repositório contém o esquema e um Compose opcional que inicia uma cópia local com PostGIS na porta 5433 (após instalar Docker Desktop): copie .env.example para .env, altere a senha e rode:

```powershell
docker compose --env-file .env -f database/docker-compose.yml up -d
```

Cada pessoa terá banco local. No `.env`, aponte DATABASE_URL para esse banco (usuário e senha definidos ali; porta 5433). Após executar `database/schema.sql` e importar os CSVs conforme `data/README.md`, rode `py scripts/importar_distritos_sp.py` e `py scripts/atualizar_resumo_distritos.py`. A segunda rotina cria a agregação diária usada pela interface; execute-a novamente após novos CSVs.

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
- `tests/domain/` reúne os testes unitários correspondentes, com referência à regra (RN), ao requisito (RF/RNF) ou ao caso de teste (CT) da especificação.

Cada módulo de domínio cobre um bloco do modelo de indicadores: `cep.py` (validação e normalização de CEP), `thresholds.py` (limiares de distância por tipo de equipamento), `proximity.py` (nota por tipo, tempo de caminhada e IPL), `vitality.py` (IVEP) e `rates.py` (taxas oficiais de ocorrências). No momento, as funções de cálculo ainda são contratos que levantam `NotImplementedError`, de modo que a suíte permanece em estado vermelho até a implementação. O alvo de cobertura de 70% das regras de negócio vem do RNF11.

## Dados

Os CSVs disponíveis somam cerca de 959 MB, alguns excedem o limite de 100 MB por arquivo do GitHub. O banco local ocupa vários GB. Por isso, os arquivos e dumps não são versionados: o repositório inclui rotinas reproduzíveis para criação, importação e padronização. Execute `database/schema.sql` uma vez no banco vazio, configure DATABASE_URL e use:

```powershell
py scripts/carregar_ssp.py --diretorio "data/raw/Dados Segurança Publica/SSP.SP/CSV"
```

O importador reprocessa cada arquivo em transação, sem alterar os originais, e mantém colunas heterogêneas em JSONB. Para criar cópias com as colunas da referência OBJETOS_01_TRIM_2025.csv, use scripts/padronizar_csvs_ssp.py com --origem e --destino. Saídas em data/processed não são versionadas.

## Interpretação

As contagens são linhas de planilhas policiais; um boletim pode ter mais de uma linha. Nem todos os registros têm CEP ou coordenadas. O mapa atribui pontos georreferenciados aos distritos pelo PostGIS; os registros sem coordenada permanecem nos indicadores gerais, mas não podem ser contados por área. As cores são faixas relativas entre distritos para os filtros escolhidos, não taxas populacionais. Ao filtrar por CEP, os registros georreferenciados são reunidos em um único distrito: o de maior concentração histórica de coordenadas daquele CEP, para evitar que coordenadas divergentes destaquem várias áreas. O resumo mantém o total de registros do CEP. Os distritos são limites administrativos oficiais, não polígonos de CEP ou bairros. A geometria de referência está em `data/reference/distritos_sp.geojson` e sua origem/licença estão documentadas em `data/reference/README.md`.
