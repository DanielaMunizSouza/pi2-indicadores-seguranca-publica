"""Pré-calcula os indicadores por distrito usados no diagnóstico.

Grava em public.indicador_distrito:
  - equipamentos / densidade_km2 / densidade_10k_hab / percentil, por categoria de
    equipamento (base do IVEP; RN06). O percentil é a média das posições percentis
    das duas densidades entre os 96 distritos;
  - ocorrencias, por grupo de natureza (RF10) e ano do fato, contando só registros
    georreferenciados atribuídos ao distrito pela rotina de resumo.

Depende de: distritos (com população), equipamentos carregados e resumo
(que grava o distrito de cada ocorrência). O IVEP e as taxas são calculados na
consulta, com os pesos escolhidos pelo usuário.
"""
import sys
from collections import defaultdict
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app import DB_URL  # noqa: E402
from geohabita.domain.equipment import EQUIPMENT_CATEGORY  # noqa: E402
from geohabita.domain.rates import occurrence_group  # noqa: E402
from geohabita.domain.thresholds import CATEGORIES  # noqa: E402
from geohabita.domain.vitality import category_percentile, percentile_ranks  # noqa: E402


def equipment_rows(conn):
    distritos = {codigo: (populacao, area) for codigo, populacao, area in conn.execute(
        """SELECT codigo_distrito, populacao_2022, ST_Area(geometria::geography) / 1e6
           FROM public.distrito_municipal_sp""")}
    sem_populacao = [c for c, (pop, _) in distritos.items() if not pop]
    if sem_populacao:
        raise SystemExit(f"Distritos sem população (rode a etapa ibge-populacao): {sem_populacao}")
    contagem = defaultdict(int)  # (distrito, categoria) -> equipamentos
    # Parques e ciclovias que cruzam a divisa contam nos dois distritos.
    for codigo, tipo, n in conn.execute(
            """SELECT d.codigo_distrito, e.tipo, count(*)
               FROM public.equipamento_publico e
               JOIN public.distrito_municipal_sp d ON ST_Intersects(d.geometria, e.geometria)
               WHERE e.tipo = ANY(%s)
               GROUP BY 1, 2""", (list(EQUIPMENT_CATEGORY),)):
        contagem[codigo, EQUIPMENT_CATEGORY[tipo]] += n
    linhas = []
    for categoria in CATEGORIES:
        por_area, por_habitante = {}, {}
        for codigo, (populacao, area) in distritos.items():
            n = contagem[codigo, categoria]
            por_area[codigo] = n / area
            por_habitante[codigo] = n / populacao * 10_000
            linhas += [(codigo, "equipamentos", categoria, 0, n),
                       (codigo, "densidade_km2", categoria, 0, por_area[codigo]),
                       (codigo, "densidade_10k_hab", categoria, 0, por_habitante[codigo])]
        p_area, p_hab = percentile_ranks(por_area), percentile_ranks(por_habitante)
        linhas += [(codigo, "percentil", categoria, 0, category_percentile(p_area[codigo], p_hab[codigo]))
                   for codigo in distritos]
    return linhas


def occurrence_rows(conn):
    contagem = defaultdict(int)  # (distrito, grupo, ano) -> ocorrências
    for codigo, ano, dataset, natureza, rubrica, linhas, boletins in conn.execute(
            """SELECT o.codigo_distrito, extract(year FROM r.data_ocorrencia)::int, r.categoria_dado,
                      r.natureza, r.rubrica, count(*), count(DISTINCT (r.ano_bo, r.num_bo, r.id_delegacia))
               FROM public.registro_ocorrencia r JOIN public.ocorrencia_distrito o USING (id)
               WHERE r.data_ocorrencia IS NOT NULL
                 AND r.categoria_dado IN ('criminal', 'celulares_subtraidos')
               GROUP BY 1, 2, 3, 4, 5"""):
        grupo = occurrence_group(dataset, natureza, rubrica)
        if grupo:
            # Na base de celulares cada aparelho é uma linha: conta-se o boletim.
            contagem[codigo, grupo, ano] += boletins if dataset == "celulares_subtraidos" else linhas
    return [(codigo, "ocorrencias", grupo, ano, n) for (codigo, grupo, ano), n in contagem.items()]


def main() -> None:
    with psycopg.connect(DB_URL) as conn:
        linhas = equipment_rows(conn) + occurrence_rows(conn)
        with conn.transaction():
            conn.execute("TRUNCATE public.indicador_distrito")
            with conn.cursor().copy("COPY public.indicador_distrito "
                                    "(codigo_distrito, indicador, subcategoria, ano, valor) FROM STDIN") as copy:
                for linha in linhas:
                    copy.write_row(linha)
    print(f"Indicadores por distrito atualizados: {len(linhas):,} valores.")


if __name__ == "__main__":
    main()
