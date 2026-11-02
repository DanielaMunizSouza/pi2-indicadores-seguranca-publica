# GeoHabita — Diagnóstico socioespacial de São Paulo

Aplicação web que transforma um endereço de São Paulo (CEP, ou rua e número) em um diagnóstico com três blocos lado a lado, nunca somados numa nota única de "segurança": a proximidade do endereço aos equipamentos públicos (Índice de Proximidade Local, IPL, incluindo a densidade de iluminação pública), a vitalidade do espaço público do distrito (IVEP) e as taxas oficiais de ocorrências da SSP-SP por 100 mil habitantes. Um explorador complementar mostra os registros SSP-SP por distrito, período e categoria, em taxa por habitante e escala de cor neutra.

Pilha: Python (FastAPI) em camadas, PostgreSQL/PostGIS, interface em HTML e JavaScript (módulos ES em `frontend/js`, Leaflet), Docker e Cloudflare Tunnel, testes com pytest, Playwright e axe-core.

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

O banco precisa existir e ter o esquema aplicado antes do pipeline (seção seguinte). A primeira execução baixa cerca de 1,5 GB (GeoSampa e SSP) e leva por volta de meia hora a uma hora, conforme a conexão; as seguintes só baixam o que mudou.

`uv sync` instala o Python 3.12, se necessário, cria `.venv` e instala exatamente as versões de `uv.lock`, incluindo as ferramentas de teste. Não é preciso ativar o ambiente: `uv run` usa `.venv` automaticamente. Para adicionar uma biblioteca, use `uv add nome` (ou `uv add --dev nome` para uso exclusivo em testes) e versione `pyproject.toml` e `uv.lock` juntos.

Abra http://127.0.0.1:8000 para o diagnóstico do endereço:

- **Consulta:** CEP, com o número do imóvel opcional; sem o CEP, o nome da rua com o número. A busca por rua lista os CEPs do logradouro (busca reversa no ViaCEP) e, com o número, escolhe o CEP do trecho certo ("de 612 a 1510 - lado par", CEPs exclusivos de prédios); quando o ViaCEP não traz o trecho, o CEP vem do OpenStreetMap. Com o número, a posição usada é a do próprio imóvel, e não o ponto genérico do CEP, que em avenidas longas cobre um trecho inteiro. Depois da primeira consulta, clicar no mapa diagnostica outro ponto.
- **Abas:** proximidade (mapa do entorno, IPL e equipamento mais próximo de cada tipo), vitalidade do distrito, ocorrências oficiais, comparação de até três endereços e "Ver como tabela", com todo o conteúdo do mapa para leitores de tela. Os pesos das categorias são recalculados na hora, inclusive na comparação.
- **Exportação:** o diagnóstico pode ser baixado em CSV, gerado no próprio navegador. O link da página guarda o CEP e o número.
- **Acessibilidade:** alto contraste e tamanho de fonte (preferências guardadas no navegador), atalhos Alt+1 a Alt+4, links para pular ao conteúdo, abas navegáveis pelas setas e anúncios das consultas e dos erros em região viva (WCAG 2.1 AA, WAI-ARIA, e-MAG).

A iluminação pública não é medida pela distância até o poste mais próximo, que quase sempre fica a poucos metros: o que conta é a densidade de pontos num raio de 300 m (nota 0 até 150 pontos/km² e 100 a partir de 1.500/km²). As praças não entram porque a camada do GeoSampa (`GEOSAMPA_v_praca_largo`) é recusada pelo servidor da Prefeitura com erro de certificado. Por isso, a categoria lazer e convivência usa os parques municipais.

Os limiares de distância e de densidade podem ser alterados sem mudar o código (RN13): copie `config/limiares.exemplo.toml` para `config/limiares.toml` (ou aponte `GEOHABITA_LIMIARES` para outro arquivo), reinicie a API e rode a etapa `indicadores` do pipeline. O explorador de ocorrências por distrito fica em http://127.0.0.1:8000/explorar. A API interativa está em http://127.0.0.1:8000/docs. Não envie senhas ao GitHub.

A aplicação lê `.env` automaticamente. O pipeline e o importador `scripts/carregar_ssp.py` leem apenas variáveis de ambiente; por isso, execute-os com `uv run --env-file .env`, como na seção [Dados](#dados).

## Banco para os demais integrantes

GitHub não hospeda uma conexão PostgreSQL ao vivo. O repositório contém o esquema e um Compose opcional que inicia uma cópia local com PostGIS na porta 5433 (após instalar Docker Desktop): copie .env.example para .env, altere a senha e rode:

```powershell
docker compose --env-file .env -f database/docker-compose.yml up -d
```

No Linux, o mesmo comando funciona com Docker Engine e o plugin Compose (pacote `docker-compose-plugin` ou equivalente da distribuição), sem Docker Desktop. Se o usuário não pertencer ao grupo `docker`, prefixe o comando com `sudo`. Na primeira inicialização, o contêiner executa `database/schema.sql` automaticamente. Para um PostgreSQL instalado no sistema, com a extensão PostGIS, aplique o esquema com `psql "postgresql://usuario:senha@localhost:5432/banco" -f database/schema.sql`.

Cada pessoa terá banco local. No `.env`, aponte DATABASE_URL para esse banco (usuário e senha definidos ali; porta 5433). Depois de aplicar `database/schema.sql`, rode `uv run --env-file .env scripts/pipeline_dados.py`, que baixa e importa as fontes públicas e gera a agregação diária usada pela interface (detalhes na seção Dados). Quem já tem um banco criado antes pode reaplicar `database/schema.sql` com segurança: o arquivo é idempotente e só acrescenta as tabelas e colunas novas. O modelo de dados está em `database/modelo_er.mmd`.

## Implantação (nuvem híbrida)

A aplicação publicada usa nuvem híbrida: a origem (aplicação e banco) roda em contêineres Docker no servidor da equipe e chega à internet pela borda de nuvem da Cloudflare, por meio de um Cloudflare Tunnel. Nenhum plano gratuito de nuvem comporta um PostGIS de vários GB (2,1 milhões de ocorrências e cerca de 663 mil pontos de iluminação) nem a aplicação desse porte; o túnel, por outro lado, é gratuito e dispensa IP público, abertura de portas no roteador e certificado próprio.

```
navegador ──HTTPS──> borda Cloudflare ──túnel──> cloudflared ──HTTP──> app (FastAPI) ──> db (PostGIS)
                     (TLS, CDN, DDoS)           └──────────── contêineres no servidor da equipe ────────────┘
```

O `cloudflared` abre a conexão de saída até a Cloudflare, então nada no servidor fica exposto à internet. `compose.yml` publica a aplicação só em `127.0.0.1` (`APP_PORT`). O banco também fica em `127.0.0.1` (`DB_PORT`), a menos que `DB_BIND` aponte outra interface: com `DB_BIND=0.0.0.0`, ou o IP da rede local, outros computadores da rede acessam o banco, sempre com usuário e senha (`scram-sha-256`). Nunca encaminhe essa porta para a internet.

Os dados ficam no volume `geohabita_postgis_data`, que tem nome fixo. Ele é reaproveitado em todo `docker compose up` e sobrevive a `docker compose down`; só `docker compose down -v` o apaga. Para levar um banco existente para o volume, gere um dump e restaure:

```bash
docker exec <contêiner-antigo> pg_dump -U pi2 -d pi2_seguranca_publica -Fc > geohabita.dump
docker compose up -d db
docker cp geohabita.dump geohabita-db-1:/tmp/ && docker exec geohabita-db-1 \
  pg_restore -U pi2 -d pi2_seguranca_publica --clean --if-exists --no-owner -j 4 /tmp/geohabita.dump
```

O único erro esperado no restore é "cannot drop extension postgis", porque a imagem cria `postgis_topology` junto. Ele não afeta os dados.

O túnel pode rodar de duas formas. As duas usam o mesmo `compose.yml`:

- **Túnel no próprio servidor**: é o caso do GeoHabita hoje. O túnel é criado pela linha de comando (`cloudflared tunnel create`), com as rotas em `~/.cloudflared/config.yml`, e o `cloudflared` roda como serviço do sistema. Basta apontar o hostname para `http://127.0.0.1:8000` e subir o Compose sem o perfil `tunel`. Nenhum token é necessário.
- **Túnel em contêiner**: o túnel é criado no painel Zero Trust e o `cloudflared` sobe junto com o Compose no perfil `tunel`, autenticado por `CLOUDFLARE_TUNNEL_TOKEN`.

Passo a passo, com Docker e o plugin Compose instalados:

1. Crie `.env` a partir de `.env.example` e defina `POSTGRES_PASSWORD`, sem `@ : / ? #`, porque a senha também compõe a URL de conexão.
2. Configure o túnel:
   - **No servidor**: no `config.yml` do `cloudflared`, a regra de `ingress` do hostname público aponta para `service: http://127.0.0.1:8000` (ou para a porta definida em `APP_PORT`). Mantenha o `cloudflared` rodando como serviço (`cloudflared service install`, ou uma unidade do systemd).
   - **Em contêiner**: no painel Zero Trust, em Networks > Tunnels, crie um túnel do tipo Cloudflared. Copie o token do comando de instalação (o trecho que começa com `eyJ`) para `CLOUDFLARE_TUNNEL_TOKEN` no `.env`. Depois adicione um hostname público com o serviço `http://app:8000`.
3. Suba os serviços com um comando:

   ```bash
   docker compose up -d --build                    # túnel no servidor
   docker compose --profile tunel up -d --build    # túnel em contêiner
   ```

4. Popule o banco (a primeira vez leva de meia hora a uma hora; os arquivos baixados ficam em `data/raw` do servidor):

   ```bash
   docker compose --profile pipeline run --rm pipeline
   ```

5. Agende a atualização periódica, por exemplo semanal, no cron do servidor: `0 3 * * 1 cd /caminho/do/projeto && docker compose --profile pipeline run --rm -T pipeline python scripts/pipeline_dados.py --etapas ssp-baixar ssp-carregar resumo indicadores >> pipeline.log 2>&1`. Argumentos depois do nome do serviço substituem o comando inteiro, por isso o comando é repetido antes das opções.

Sem o perfil `tunel`, `docker compose up -d --build` sobe só banco e aplicação, acessível em http://127.0.0.1:8000. O banco de `compose.yml` usa a mesma porta 5433 do Compose de `database/`, que continua funcionando para quem só precisa do banco; pare um antes de subir o outro. Os volumes são diferentes, então o novo banco começa vazio.

O que cada lado cobre:

- Borda da Cloudflare: HTTPS e TLS com certificado gerenciado (RNF08), CDN dos arquivos estáticos e proteção contra DDoS, no plano gratuito (RNF14).
- Servidor da equipe: contêineres reprodutíveis e implantação em um comando (RNF12), sem custo de hospedagem (RNF14).

Limites assumidos: a disponibilidade depende do servidor da equipe (energia, rede e manutenção); não há réplica nem failover, e a meta de disponibilidade do RNF07 fica como trabalho futuro.

O IP do visitante chega no cabeçalho `CF-Connecting-IP`, usado pelo limite de requisições. Como qualquer cliente pode enviar esse cabeçalho, ele só é aceito de conexões vindas de proxies confiáveis, listados em `GEOHABITA_PROXIES_CONFIAVEIS` (IPs ou CIDRs separados por vírgula; padrão `127.0.0.1,::1`, para o `cloudflared` instalado na mesma máquina). No Compose, a aplicação já confia em duas origens da rede `geohabita`, as duas com IP fixo:
- `172.28.0.10`, o contêiner `cloudflared` do perfil `tunel`;
- `172.28.0.1`, o gateway da rede. É dele que vêm as conexões feitas pela porta publicada em `127.0.0.1`, como as de um `cloudflared` instalado no servidor. Só processos da própria máquina alcançam essa porta.

## Integração contínua

O workflow `.github/workflows/ci.yml` roda a cada push e pull request, com Python 3.12 e uv:

- `testes`: suíte sem os marcadores `integracao` e `e2e`, com cobertura mínima de 70% em `geohabita` (RNF11).
- `integracao`: testes marcados com `integracao`, contra um serviço PostGIS 16 com `database/schema.sql` aplicado.
- `e2e-acessibilidade`: testes marcados com `e2e` (Playwright e axe-core) no Chromium e no Firefox (RNF12); os relatórios em `relatorios-teste/` ficam como artefato.
- `auditoria`: `pip-audit` sobre as dependências fixadas em `uv.lock` (RNF09).
- `docker`: build da imagem do `Dockerfile`, sem publicação.

## Testes

A suíte segue desenvolvimento guiado por testes (TDD): os testes descrevem o
comportamento esperado pela especificação (`relatorio/requisitos_geohabita.tex`)
antes da implementação. Rode na raiz do projeto, com `uv` instalado (`uv sync` já
instala as ferramentas de teste):

```bash
uv run pytest
```

| Comando | O que roda |
|---|---|
| `uv run pytest` | tudo: unidade, integração e interface |
| `uv run pytest -m "not integracao and not e2e"` | só unidade — rápido, sem banco nem navegador |
| `uv run pytest -m integracao` | integração com PostGIS (banco `geohabita_teste_*` descartável) |
| `uv run pytest -m e2e --browser chromium --browser firefox` | interface em navegador real (Playwright + axe-core) |
| `uv run pytest -m "not integracao and not e2e" --cov=geohabita --cov-fail-under=70` | cobertura das regras de negócio (porta do RNF11) |
| `uv run pytest -m "not e2e" --cov=geohabita --cov=backend --cov=scripts --cov-report=html` | cobertura completa, HTML em `htmlcov/` |

Os marcadores `integracao` e `e2e` exigem ambiente além do Python: o primeiro
cria e apaga um banco descartável no servidor de `DATABASE_URL` (nunca toca o
banco real); o segundo roda num navegador e não precisa de banco. Sem esses
ambientes, cada grupo é pulado.

Pré-requisitos, o passo a passo recomendado, relatórios de cobertura e de
resultados e a solução de problemas estão em
[`tests/README.md`](tests/README.md).

## Dados

As bases baixadas e o banco local ocupam alguns GB, então nada disso é versionado: o repositório traz o pipeline que baixa, converte e importa tudo. Com o esquema aplicado e `DATABASE_URL` no `.env`:

```bash
uv run --env-file .env scripts/pipeline_dados.py
```

Sem argumentos, ele executa tudo: distritos (a partir de `data/reference/`), equipamentos públicos do GeoSampa, população por distrito (Censo 2022, IBGE), bases da SSP-SP e resumos do mapa. As etapas independentes rodam em paralelo, com barra de progresso no terminal ou linhas de log com horário quando a saída vai para arquivo. Da SSP, o padrão é o que os indicadores usam: dados criminais, celulares subtraídos e mortes por intervenção policial, nos três últimos anos completos, só do município de São Paulo. `--etapas` restringe as etapas, `--fontes`/`--desde`/`--todo-estado` ampliam o escopo da SSP e `--workers` ajusta o paralelismo. O que já está em dia não é baixado nem recarregado. As fontes, as opções e os cuidados com os dados estão em [`data/README.md`](data/README.md).

Cada etapa que grava no banco registra uma linha em `carga_etl` (RF19), com fonte, arquivo, registros importados, registros sem coordenada e registros com coordenada fora dos 96 distritos (RN10).

O importador `scripts/carregar_ssp.py` reprocessa cada arquivo em transação, sem alterar os originais, e mantém colunas heterogêneas em JSONB. Para usar CSVs que você já baixou manualmente, execute `uv run --env-file .env scripts/carregar_ssp.py --diretorio <pasta>`. Para criar cópias com as colunas da referência OBJETOS_01_TRIM_2025.csv, use `uv run scripts/padronizar_csvs_ssp.py` com `--origem` e `--destino`. Saídas em `data/raw` e `data/processed` não são versionadas.

## Interpretação

As contagens são linhas de planilhas policiais; um boletim pode ter mais de uma linha. Nem todos os registros têm CEP ou coordenadas. O mapa atribui pontos georreferenciados aos distritos pelo PostGIS; os registros sem coordenada permanecem nos indicadores gerais, mas não podem ser contados por área. No explorador, o mapa usa por padrão a taxa de registros por 100 mil moradores (Censo 2022), e a contagem bruta fica disponível num seletor. As cores são quintis numa escala de um só matiz, sem vermelho, e a tabela de distritos é ordenada pelo nome, não pelo volume: o objetivo é informar, não ranquear territórios (RNF18). Ao filtrar por CEP, os registros georreferenciados são reunidos em um único distrito: o de maior concentração histórica de coordenadas daquele CEP, para evitar que coordenadas divergentes destaquem várias áreas. O resumo mantém o total de registros do CEP. Os distritos são limites administrativos oficiais, não polígonos de CEP ou bairros. A geometria de referência está em `data/reference/distritos_sp.geojson` e sua origem/licença estão documentadas em `data/reference/README.md`.

## Licença

Este repositório usa duas licenças, conforme o tipo de conteúdo:

| Conteúdo | Licença |
|---|---|
| Código-fonte e software (tudo fora dos diretórios do relatório) | [GNU AGPL-3.0](LICENSE) |
| Relatório acadêmico: diretórios `relatorio/` e `relatorio_parcial/` (fontes LaTeX, bibliografia, figuras, fontes dos diagramas e PDFs gerados) | [CC BY-ND 4.0](https://creativecommons.org/licenses/by-nd/4.0/deed.pt-br) |

**Código (AGPL-3.0):** o software é livre para uso, estudo, modificação e redistribuição nos termos do arquivo `LICENSE`. Quem disponibilizar uma versão modificada para uso por rede deve oferecer o código-fonte correspondente aos usuários.

**Relatório (CC BY-ND 4.0):** o relatório pode ser copiado e redistribuído livremente, em qualquer meio ou formato, inclusive para fins comerciais, desde que integralmente, sem alterações e com a atribuição aos autores. Não é permitido distribuir versões modificadas ou obras derivadas do texto. O conteúdo é definido exclusivamente pelos autores, que são as pessoas identificadas como autoras no arquivo `.tex` principal e no PDF final do relatório, incluindo quem vier a ser acrescentado nessas listas. Citações com a devida referência continuam permitidas nos termos do art. 46 da Lei nº 9.610/1998. Detalhes em `relatorio/LICENSE.md`.

**Exceções:** materiais de terceiros mantêm as licenças originais, por exemplo a classe abnTeX2 (`abntex2_ref.cls`, LPPL 1.3c), o texto da AGPL (`AGPL.tex`, © Free Software Foundation) e os dados de `data/reference/` (ver `data/reference/README.md`).
