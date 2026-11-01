# Modelo de dados: relatório × esquema implementado

O diagrama do relatório (`relatorio/img/source/mer.mmd`) tem 8 entidades. O esquema real (`schema.sql`, diagrama em `modelo_er.mmd`) é mais enxuto em alguns pontos e mais detalhado em outros.

| Relatório | Esquema atual | Situação |
|---|---|---|
| `DISTRITO` (id, nome, subprefeitura, população, área, polígono) | `distrito_municipal_sp` (código GeoSampa como PK, nome, região, geometria, `populacao_2022`) | Equivalem. Faltam `area_km2` (calculável com `ST_Area(geometria::geography)`) e subprefeitura (a camada traz só "região"). |
| `OCORRENCIA` (distrito_id, carga_id, natureza, data, localização) | `registro_ocorrencia`, tabela única com `categoria_dado`, mais `ocorrencia_distrito` | **Diverge.** O distrito fica numa tabela estreita à parte (`ocorrencia_distrito`), preenchida uma vez por linha pelo ponto-em-polígono: gravá-lo na tabela grande regravaria cada linha e todos os índices. A tabela guarda os campos comuns e o restante em JSONB. |
| `CARGA_ETL` | `carga_etl` (nova) | Equivalem. A ligação com as ocorrências é pelo nome do arquivo (`arquivo_origem`), não por FK, porque cada arquivo é recarregado inteiro (idempotente). |
| `EQUIPAMENTO` (tipo_id, distrito_id, carga_id) | `equipamento_publico` (nova), com `categoria`/`tipo` em texto | Parcial. Sem FK de distrito (espacial) nem de carga. |
| `CATEGORIA` e `TIPO_EQUIPAMENTO` (limiares) | não existem como tabelas | **Faltam.** Categorias e limiares estão em `geohabita/domain/thresholds.py`. O relatório fala em "parâmetros de configuração"; o código já cumpre isso, então a tabela só se justifica se os pesos/limiares precisarem ser editados sem deploy. |
| `INDICADOR_DISTRITO` | `indicador_distrito` | Equivalem, em formato longo: percentis do IVEP e ocorrências por natureza e ano, recalculados pela etapa `indicadores`. O IVEP e as taxas finais são calculados na consulta, porque dependem dos pesos do usuário. |
| `CEP_CACHE` | não existe | **Falta.** O cache de CEP (`cep_lookup.py`) é um dicionário em memória, perdido ao reiniciar. |
| (ausente) | `resumo_distrito_diario`, `resumo_ocorrencia_diario`, views `vw_resumo_*` | Existem só no código: agregações para o mapa ficar rápido. Faltam no MER do relatório. |

## Recomendação

1. **Atualizar o MER do relatório** para o que existe (usar `modelo_er.mmd` como base): substituir `OCORRENCIA` por `REGISTRO_OCORRENCIA`, incluir as duas tabelas de resumo e marcar como espaciais (tracejadas) as relações com distrito.
2. **Criar `categoria_equipamento`/`tipo_equipamento` e `cep_cache` quando a sprint de IPL e CEP chegar**, e não antes. Hoje nada no código as consome.
3. Manter `registro_ocorrencia` como tabela única. As bases da SSP têm colunas diferentes, mas o conjunto comum (data, local, natureza, coordenada) é o que os indicadores usam.
