-- Esquema compartilhável PostgreSQL/PostGIS.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS public.registro_ocorrencia (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 arquivo_origem text NOT NULL, linha_origem bigint NOT NULL, categoria_dado text NOT NULL,
 municipio text, ano_bo smallint, data_ocorrencia date, hora_ocorrencia time, cep varchar(8),
 bairro text, logradouro text, numero_logradouro text, latitude double precision, longitude double precision,
 localizacao geometry(Point,4326) GENERATED ALWAYS AS (CASE WHEN latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180
 THEN ST_SetSRID(ST_MakePoint(longitude,latitude),4326) ELSE NULL END) STORED,
 natureza text, rubrica text, tipo_objeto text, subtipo_objeto text, marca_objeto text,
 tipo_local text, modo_objeto text, tipo_entorpecente text, quantidade numeric, unidade_quantidade text,
 dados_originais jsonb NOT NULL, importado_em timestamptz NOT NULL DEFAULT now(),
 CONSTRAINT uq_registro_origem UNIQUE(arquivo_origem,linha_origem),
 CONSTRAINT ck_cep_formato CHECK(cep IS NULL OR cep ~ '^[0-9]{8}$')
);
CREATE INDEX IF NOT EXISTS ix_registro_cep ON public.registro_ocorrencia(cep,data_ocorrencia);
CREATE INDEX IF NOT EXISTS ix_registro_municipio_data ON public.registro_ocorrencia(municipio,data_ocorrencia);
CREATE INDEX IF NOT EXISTS ix_registro_categoria_data ON public.registro_ocorrencia(categoria_dado,data_ocorrencia);
CREATE INDEX IF NOT EXISTS ix_registro_localizacao ON public.registro_ocorrencia USING gist(localizacao);
CREATE TABLE IF NOT EXISTS public.distrito_municipal_sp (
 codigo_distrito text PRIMARY KEY,
 nome_distrito text NOT NULL,
 regiao text,
 atualizado_em date,
 geometria geometry(MultiPolygon,4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_distrito_municipal_sp_geometria
 ON public.distrito_municipal_sp USING gist(geometria);
CREATE TABLE IF NOT EXISTS public.resumo_distrito_diario (
 codigo_distrito text NOT NULL REFERENCES public.distrito_municipal_sp(codigo_distrito),
 data_ocorrencia date NOT NULL,
 categoria_dado text NOT NULL,
 cep varchar(8) NOT NULL DEFAULT '',
 registros bigint NOT NULL,
 PRIMARY KEY(codigo_distrito,data_ocorrencia,categoria_dado,cep)
);
CREATE INDEX IF NOT EXISTS ix_resumo_distrito_periodo
 ON public.resumo_distrito_diario(data_ocorrencia,codigo_distrito)
 INCLUDE(categoria_dado,cep,registros);
CREATE INDEX IF NOT EXISTS ix_resumo_distrito_cep ON public.resumo_distrito_diario(cep) INCLUDE(codigo_distrito,registros);
CREATE OR REPLACE VIEW public.vw_resumo_mensal AS
 SELECT date_trunc('month',data_ocorrencia)::date AS mes,municipio,categoria_dado,count(*) AS registros,
 count(*) FILTER(WHERE cep IS NOT NULL) AS registros_com_cep,count(*) FILTER(WHERE localizacao IS NOT NULL) AS registros_com_coordenada
 FROM public.registro_ocorrencia GROUP BY 1,2,3;
CREATE OR REPLACE VIEW public.vw_resumo_cep AS
 SELECT municipio,cep,categoria_dado,count(*) AS registros,min(data_ocorrencia) AS primeira_data,max(data_ocorrencia) AS ultima_data,
 avg(latitude) FILTER(WHERE localizacao IS NOT NULL) AS latitude_media,avg(longitude) FILTER(WHERE localizacao IS NOT NULL) AS longitude_media
 FROM public.registro_ocorrencia WHERE cep IS NOT NULL GROUP BY 1,2,3;
