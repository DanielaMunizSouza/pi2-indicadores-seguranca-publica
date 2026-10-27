"""Atualiza a agregação diária georreferenciada usada pelo mapa distrital."""
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app import DB_URL, MUNICIPIOS_SP


def main() -> None:
    with psycopg.connect(DB_URL) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS public.ocorrencia_distrito (
            id bigint PRIMARY KEY REFERENCES public.registro_ocorrencia(id) ON DELETE CASCADE,
            codigo_distrito text NOT NULL REFERENCES public.distrito_municipal_sp(codigo_distrito))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS public.resumo_distrito_diario (
            codigo_distrito text NOT NULL REFERENCES public.distrito_municipal_sp(codigo_distrito),
            data_ocorrencia date NOT NULL,
            categoria_dado text NOT NULL,
            cep varchar(8) NOT NULL DEFAULT '',
            registros bigint NOT NULL,
            PRIMARY KEY(codigo_distrito,data_ocorrencia,categoria_dado,cep)
        )""")
        conn.execute("""CREATE INDEX IF NOT EXISTS ix_resumo_distrito_periodo
            ON public.resumo_distrito_diario(data_ocorrencia,codigo_distrito)
            INCLUDE(categoria_dado,cep,registros)""")
        conn.execute("""CREATE INDEX IF NOT EXISTS ix_resumo_distrito_cep
            ON public.resumo_distrito_diario(cep) INCLUDE(codigo_distrito,registros)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS public.resumo_ocorrencia_diario (
            data_ocorrencia date NOT NULL,categoria_dado text NOT NULL,
            cep varchar(8) NOT NULL DEFAULT '',registros bigint NOT NULL,
            com_cep bigint NOT NULL,com_coordenada bigint NOT NULL,
            soma_latitude double precision NOT NULL DEFAULT 0,
            soma_longitude double precision NOT NULL DEFAULT 0,
            coordenadas_centro bigint NOT NULL DEFAULT 0,
            PRIMARY KEY(data_ocorrencia,categoria_dado,cep)
        )""")
        conn.execute("""CREATE INDEX IF NOT EXISTS ix_resumo_ocorrencia_periodo
            ON public.resumo_ocorrencia_diario(data_ocorrencia)
            INCLUDE(categoria_dado,cep,registros,com_cep,com_coordenada,
                    soma_latitude,soma_longitude,coordenadas_centro)""")
        # TRUNCATE and rebuild happen in one transaction: readers see the old or
        # the complete new summary, never a partially populated table.
        conn.execute("TRUNCATE public.resumo_distrito_diario,public.resumo_ocorrencia_diario")
        conn.execute("""INSERT INTO public.resumo_ocorrencia_diario
            (data_ocorrencia,categoria_dado,cep,registros,com_cep,com_coordenada,
             soma_latitude,soma_longitude,coordenadas_centro)
            SELECT data_ocorrencia,categoria_dado,COALESCE(cep,''),count(*),
                count(*) FILTER(WHERE cep IS NOT NULL),
                count(*) FILTER(WHERE localizacao IS NOT NULL),
                COALESCE(sum(latitude) FILTER(WHERE latitude IS NOT NULL AND longitude IS NOT NULL),0),
                COALESCE(sum(longitude) FILTER(WHERE latitude IS NOT NULL AND longitude IS NOT NULL),0),
                count(*) FILTER(WHERE latitude IS NOT NULL AND longitude IS NOT NULL)
            FROM public.registro_ocorrencia
            WHERE municipio=ANY(%s) AND data_ocorrencia IS NOT NULL
            GROUP BY data_ocorrencia,categoria_dado,COALESCE(cep,'')""",(MUNICIPIOS_SP,))
        conn.execute("ANALYZE public.resumo_ocorrencia_diario")
        # O distrito de cada ocorrência é calculado uma vez; nas execuções seguintes
        # só as linhas novas (recém-importadas) passam pelo ponto-em-polígono.
        # Polígonos subdivididos (no máximo 128 vértices) tornam o ST_Contains muito mais barato.
        conn.execute("""CREATE TEMP TABLE distrito_parte ON COMMIT DROP AS
            SELECT codigo_distrito, ST_Subdivide(geometria, 128) AS geom FROM public.distrito_municipal_sp""")
        conn.execute("CREATE INDEX ON distrito_parte USING gist(geom)")
        conn.execute("ANALYZE distrito_parte")
        # MATERIALIZED força a ordem: primeiro separa as linhas ainda sem distrito, depois
        # aplica a geometria só nelas (senão o planejador cruza a tabela inteira com os polígonos).
        atribuidas=conn.execute("""WITH novas AS MATERIALIZED (
                SELECT r.id, r.localizacao FROM public.registro_ocorrencia r
                WHERE r.localizacao IS NOT NULL AND r.municipio=ANY(%s)
                  AND NOT EXISTS (SELECT 1 FROM public.ocorrencia_distrito o WHERE o.id = r.id))
            INSERT INTO public.ocorrencia_distrito (id, codigo_distrito)
            SELECT DISTINCT ON (n.id) n.id, p.codigo_distrito
            FROM novas n JOIN distrito_parte p ON p.geom && n.localizacao AND ST_Contains(p.geom, n.localizacao)
            ORDER BY n.id, p.codigo_distrito""", (MUNICIPIOS_SP,)).rowcount
        print(f"Distrito atribuído a {atribuidas:,} ocorrências novas.")
        conn.execute("ANALYZE public.ocorrencia_distrito")
        conn.execute("""INSERT INTO public.resumo_distrito_diario
              (codigo_distrito,data_ocorrencia,categoria_dado,cep,registros)
            SELECT o.codigo_distrito,r.data_ocorrencia,r.categoria_dado,COALESCE(r.cep,''),count(*)
            FROM public.registro_ocorrencia r JOIN public.ocorrencia_distrito o USING (id)
            WHERE r.municipio=ANY(%s) AND r.data_ocorrencia IS NOT NULL
            GROUP BY o.codigo_distrito,r.data_ocorrencia,r.categoria_dado,COALESCE(r.cep,'')""",
                     (MUNICIPIOS_SP,))
        conn.execute("ANALYZE public.resumo_distrito_diario")
        row=conn.execute("SELECT count(*) AS grupos,COALESCE(sum(registros),0) AS registros "
                         "FROM public.resumo_distrito_diario").fetchone()
        print(f"Resumo diário atualizado: {row[0]} combinações; {row[1]} ocorrências georreferenciadas.")


if __name__ == "__main__":
    main()
