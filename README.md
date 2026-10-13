# Indicadores de Segurança Pública — São Paulo

Aplicação web para explorar registros públicos SSP-SP por CEP, categoria e período. O mapa apresenta concentração de registros agregados, não probabilidade de vitimização nem risco individual.

## Aplicação web

1. Crie um arquivo .env a partir de .env.example e ajuste senha, porta, usuário e banco indicados no pgAdmin.
2. No PowerShell na raiz do projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt -r requirements-web.txt
$env:DATABASE_URL = "postgresql://postgres:SUA_SENHA@localhost:5432/ProjetoIntergrador_2"
py -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Abra http://127.0.0.1:8000. A API interativa está em http://127.0.0.1:8000/docs. Não envie senhas ao GitHub.

## Banco para os demais integrantes

GitHub não hospeda uma conexão PostgreSQL ao vivo. O repositório contém o esquema e um Compose opcional que inicia uma cópia local com PostGIS na porta 5433 (após instalar Docker Desktop): copie .env.example para .env, altere a senha e rode:

```powershell
docker compose --env-file .env -f database/docker-compose.yml up -d
```

Cada pessoa terá banco local. No arquivo .env, aponte DATABASE_URL para esse banco (usuário e senha definidos ali; porta 5433). Para preenchê-lo, é necessário obter os CSVs SSP-SP e seguir data/README.md.

## Dados

Os CSVs disponíveis somam cerca de 959 MB, alguns excedem o limite de 100 MB por arquivo do GitHub. O banco local ocupa vários GB. Por isso, os arquivos e dumps não são versionados: o repositório inclui rotinas reproduzíveis para criação, importação e padronização. Execute database/schema.sql uma vez no banco vazio, configure DATABASE_URL e use:

```powershell
py scripts/carregar_ssp.py --diretorio "data/raw/Dados Segurança Publica/SSP.SP/CSV"
```

O importador reprocessa cada arquivo em transação, sem alterar os originais, e mantém colunas heterogêneas em JSONB. Para criar cópias com as colunas da referência OBJETOS_01_TRIM_2025.csv, use scripts/padronizar_csvs_ssp.py com --origem e --destino. Saídas em data/processed não são versionadas.

## Interpretação

As contagens são linhas de planilhas policiais; um boletim pode ter mais de uma linha. Nem todos os registros têm CEP ou coordenadas. A base não possui limites oficiais de CEP: o mapa agrega pontos em células espaciais.
