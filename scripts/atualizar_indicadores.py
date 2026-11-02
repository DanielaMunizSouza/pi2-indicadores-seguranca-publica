"""Pré-calcula os indicadores por distrito usados no diagnóstico.

Grava em public.indicador_distrito:
  - equipamentos / densidade_km2 / densidade_10k_hab / percentil, por TIPO de
    equipamento (base do IVEP; RN06). O percentil do tipo é a média das posições
    percentis das duas densidades entre os 96 distritos; o da categoria é a média
    dos percentis dos seus tipos, para que um tipo muito denso (iluminação) não
    afogue os demais. Tipos medidos só por área (iluminação) usam a densidade por
    km².
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
from geohabita.config import DATABASE_URL as DB_URL  # noqa: E402
from geohabita.domain.equipment import EQUIPMENT_CATEGORY  # noqa: E402
from geohabita.domain.rates import occurrence_group  # noqa: E402
from geohabita.domain.thresholds import CATEGORIES, LIGHTING_TYPE, load_thresholds  # noqa: E402
from geohabita.domain.vitality import category_percentile, percentile_ranks, type_percentile  # noqa: E402

# Tipos medidos apenas pela densidade por área: a oferta por habitante não faz
# sentido para a malha de iluminação pública.
SO_AREA = {LIGHTING_TYPE}


def equipment_rows(conn):
    distritos = {codigo: (populacao, area) for codigo, populacao, area in conn.execute(
        """SELECT codigo_distrito, populacao_2022, ST_Area(geometria::geography) / 1e6
           FROM public.distrito_municipal_sp""")}
    sem_populacao = [c for c, (pop, _) in distritos.items() if not pop]
    if sem_populacao:
        raise SystemExit(f"Distritos sem população (rode a etapa ibge-populacao): {sem_populacao}")
    tipos = sorted(EQUIPMENT_CATEGORY)
    contagem = defaultdict(int)  # (distrito, tipo) -> equipamentos
    # Parques e ciclovias que cruzam a divisa contam nos dois distritos.
    for codigo, tipo, n in conn.execute(
            """SELECT d.codigo_distrito, e.tipo, count(*)
               FROM public.equipamento_publico e
               JOIN public.distrito_municipal_sp d ON ST_Intersects(d.geometria, e.geometria)
               WHERE e.tipo = ANY(%s)
               GROUP BY 1, 2""", (tipos,)):
        contagem[codigo, tipo] = n
    linhas = []
    posicoes_por_tipo = {}
    for tipo in tipos:
        por_area, por_habitante = {}, {}
        for codigo, (populacao, area) in distritos.items():
            n = contagem[codigo, tipo]
            dens_area = n / area
            por_area[codigo] = dens_area
            por_habitante[codigo] = n / populacao * 10_000
            linhas += [(codigo, "equipamentos", tipo, 0, n), (codigo, "densidade_km2", tipo, 0, dens_area)]
            if tipo not in SO_AREA:
                linhas.append((codigo, "densidade_10k_hab", tipo, 0, por_habitante[codigo]))
        p_area = percentile_ranks(por_area)
        if tipo in SO_AREA:
            posicoes_por_tipo[tipo] = p_area
        else:
            p_hab = percentile_ranks(por_habitante)
            posicoes_por_tipo[tipo] = {c: type_percentile(p_area[c], p_hab[c]) for c in distritos}
    for codigo in distritos:
        linhas += [(codigo, "percentil", tipo, 0, posicoes_por_tipo[tipo][codigo]) for tipo in tipos]
    for categoria in CATEGORIES:
        da_categoria = [t for t in tipos if EQUIPMENT_CATEGORY[t] == categoria]
        so_densidade = [t for t in da_categoria if t not in SO_AREA]
        for codigo in distritos:
            populacao, area = distritos[codigo]
            # Agregados da categoria para a tabela do distrito: a iluminação é
            # contada, mas sua densidade fica fora da soma (são outra grandeza).
            linhas.append((codigo, "percentil", categoria, 0,
                           category_percentile([posicoes_por_tipo[t][codigo] for t in da_categoria])))
            linhas.append((codigo, "equipamentos", categoria, 0,
                           sum(contagem[codigo, t] for t in da_categoria)))
            linhas.append((codigo, "densidade_km2", categoria, 0,
                           sum(contagem[codigo, t] for t in so_densidade) / area))
            linhas.append((codigo, "densidade_10k_hab", categoria, 0,
                           sum(contagem[codigo, t] for t in so_densidade) / populacao * 10_000))
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
    arquivo = load_thresholds()
    if arquivo:
        print(f"Limiares aplicados de {arquivo}.")
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
