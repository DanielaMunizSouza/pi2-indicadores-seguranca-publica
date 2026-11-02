# Testes do GeoHabita

Guia detalhado da suíte de testes. A visão resumida (com a tabela de comandos)
está no [`README.md`](../README.md#testes).

A suíte segue desenvolvimento guiado por testes (TDD) e a pirâmide de testes:
muitos testes de unidade sobre as regras de negócio, testes de integração sobre
os adaptadores de dados e o banco geoespacial, e um conjunto menor de testes
ponta a ponta sobre os fluxos da interface. Nos testes automatizados, os
serviços externos são substituídos por dublês, para que os resultados sejam
reprodutíveis.

## Pré-requisitos

1. **Dependências do Python** (instala também o pytest, o Playwright, o
   pytest-cov e o pytest-bdd):

   ```bash
   uv sync
   ```

2. **Banco PostGIS** — necessário apenas para os testes de `integracao`. Aponte
   `.env` para um servidor (o usuário precisa da permissão de criar bancos;
   o `POSTGRES_USER` do Compose já a tem):

   ```env
   DATABASE_URL=postgresql://pi2:SENHA@10.42.42.50:5433/pi2_seguranca_publica
   ```

   Sem `DATABASE_URL`, os testes de integração são pulados.

3. **Navegadores** — necessários apenas para os testes de `e2e`:

   ```bash
   uv run playwright install --with-deps chromium firefox
   ```

   O `--with-deps` instala as bibliotecas do sistema de que os navegadores
   precisam (exige sudo). Veja [Solução de problemas](#solução-de-problemas)
   se os navegadores não iniciarem.

## As camadas de teste

| Camada | Pasta | Marcador | Ambiente necessário |
|---|---|---|---|
| Unidade (regras e casos de uso) | `tests/domain/`, `tests/application/` | — | só Python |
| API (rotas HTTP) | `tests/application/test_api_*.py` | — | só Python |
| Aceitação (cenários Gherkin das histórias Must) | `tests/aceitacao/` | — | só Python |
| Integração (PostGIS real) | `tests/integracao/` | `integracao` | `DATABASE_URL` |
| Ponta a ponta (interface) | `tests/e2e/` | `e2e` | Playwright + axe-core |

Os módulos de negócio em `geohabita/domain/` são testados em isolamento
(`cep.py`, `thresholds.py`, `proximity.py`, `vitality.py`, `rates.py`,
`territory.py`, `freshness.py`, `data_quality.py`, `equipment.py`,
`diagnosis.py`, `lighting.py` e `address.py`). Os casos de uso em
`geohabita/application/` são testados com dublês no lugar do banco e dos
serviços externos (`cep_lookup.py`, `address_search.py`, `geocoding.py`,
`diagnosis.py` e `rate_limit.py`). Os adaptadores em `geohabita/infrastructure/`
são testados com `urlopen` trocado (rede simulada) e, nos testes de integração,
contra o banco PostGIS real.

## Banco de teste descartável

Os testes de `integracao` criam, no servidor apontado por `DATABASE_URL`, um
banco chamado `geohabita_teste_<aleatório>`:

1. `CREATE DATABASE geohabita_teste_<aleatório>`;
2. aplica `database/schema.sql`;
3. insere dados fictícios (`tests/integracao/dados.py`): três distritos
   quadrados, equipamentos a distâncias conhecidas da origem, um parque cujo
   contorno fica a 400 m, pontos de iluminação e ocorrências;
4. roda os testes;
5. `DROP DATABASE ... WITH (FORCE)` ao fim, mesmo se os testes falharem.

O banco de `DATABASE_URL` nunca é lido nem alterado — ele só indica o servidor
e as credenciais. A fixture recusa qualquer nome que não comece com
`geohabita_teste_`.

## Comandos

Todos rodam na raiz do projeto. Troque `uv run` por `py -m` se preferir pip
(`py -m pip install -r requirements-dev.txt` antes).

```bash
# Tudo: unidade + integração + interface (uma execução)
uv run pytest

# Só unidade (rápido; sem banco nem navegador)
uv run pytest -m "not integracao and not e2e"

# Só integração (cria/apaga o banco geohabita_teste_*)
uv run pytest -m integracao

# Só interface, nos dois navegadores
uv run pytest -m e2e --browser chromium --browser firefox

# Só os cenários Gherkin das histórias Must
uv run pytest tests/aceitacao

# Um único arquivo de teste
uv run pytest tests/domain/test_proximity.py

# Um único teste (pelo nome)
uv run pytest tests/domain/test_proximity.py -k "tempo"
```

### Marcadores disponíveis

Os marcadores são declarados em `pytest.ini`. `integracao` e `e2e` pedem mais
que o Python; os demais testes não têm marcador e rodam no grupo "unidade".
O CI roda cada grupo num job separado (`.github/workflows/ci.yml`).

## Cobertura

A meta do RNF11 é **70% de cobertura nas regras de negócio**, e é isso que a
integração contínua exige:

```bash
# Porta do RNF11 (falha abaixo de 70% em geohabita)
uv run pytest -m "not integracao and not e2e" --cov=geohabita --cov-fail-under=70

# Cobertura completa: domínio + aplicação + API + scripts do pipeline
uv run pytest -m "not e2e" --cov=geohabita --cov=backend --cov=scripts
```

Formatos de relatório (podem ser combinados):

| Opção | Resultado |
|---|---|
| `--cov-report=term` | tabela no terminal (padrão) |
| `--cov-report=term-missing` | tabela com as linhas não cobertas |
| `--cov-report=html` | relatório navegável em `htmlcov/index.html` |
| `--cov-report=xml` | `coverage.xml`, para CI/editores/Codecov |

Exemplo com todos:

```bash
uv run pytest -m "not e2e" --cov=geohabita --cov=backend --cov=scripts \
  --cov-report=term-missing --cov-report=html --cov-report=xml
```

Os testes de interface **não geram cobertura**: eles sobem a aplicação num
processo `uvicorn` separado e exercitam o JavaScript no navegador, fora do
processo que o `coverage.py` instrumenta. A cobertura do `backend` vem dos
testes de API, que chamam as rotas pelo `TestClient` no mesmo processo.

## Relatório de resultados

Para um relatório dos testes em formato JUnit (aberto por GitLab, Jenkins,
Azure ou qualquer visualizador de JUnit):

```bash
uv run pytest --browser chromium --browser firefox \
  --junitxml=relatorios-teste/junit.xml
```

A pasta `relatorios-teste/` e `htmlcov/` são ignoradas pelo Git.

## Passo a passo recomendado

```bash
# 1. Ambiente
uv sync
# edite .env com DATABASE_URL (só para integração)

# 2. Navegadores (só para e2e; exige sudo)
uv run playwright install --with-deps chromium firefox

# 3. Unidade primeiro — deve terminar em segundos
uv run pytest -m "not integracao and not e2e"

# 4. Integração — cria e apaga o banco de teste sozinho
uv run pytest -m integracao

# 5. Interface — nos dois navegadores
uv run pytest -m e2e --browser chromium --browser firefox

# 6. Cobertura e relatório
uv run pytest -m "not e2e" --cov=geohabita --cov=backend --cov=scripts \
  --cov-report=html --cov-report=xml
uv run pytest --browser chromium --browser firefox \
  --junitxml=relatorios-teste/junit.xml
```

## Regravar as respostas simuladas do e2e

Os testes de interface não usam banco: as rotas `/api/*` são respondidas pelos
JSONs de `tests/e2e/respostas/`, gravados a partir de um banco real. Quando o
contrato da API mudar, regrave com a aplicação rodando:

```bash
uv run --env-file .env uvicorn backend.app:app --port 8000      # terminal 1
uv run --env-file .env scripts/capturar_respostas.py \
  --cep 01310-200 --numero 1578                                  # terminal 2
```

## Solução de problemas

**"DATABASE_URL não definido: ..." (integração pulada).** Aponte `.env` para o
servidor e confira que o usuário consegue criar bancos.

**O navegador não inicia** (`libasound.so.2`, por exemplo). As bibliotecas do
sistema estão faltando. Rode `uv run playwright install --with-deps chromium
firefox` (com sudo), ou instale o pacote à mão:

```bash
sudo apt-get update && sudo apt-get install -y libasound2t64
```

Se não houver sudo, dá para extrair só a biblioteca em `/tmp` e apontar o
carregador para ela:

```bash
apt-get download libasound2t64 -o Dir=/tmp/libasound-pkg
cd /tmp/libasound-pkg && dpkg -x libasound2t64_*.deb root
export LD_LIBRARY_PATH=/tmp/libasound-pkg/root/usr/lib/x86_64-linux-gnu
```

**"rode scripts/preparar_axe.py" (e2e pulado).** O axe-core em `tests/vendor`
está faltando; rode `uv run scripts/preparar_axe.py` (ou `uv run playwright
install`) para baixá-lo.
