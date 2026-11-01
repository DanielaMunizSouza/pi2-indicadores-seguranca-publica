"""Consultas PostGIS da exploração de ocorrências (página /explorar) e do estado do banco."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from geohabita.domain.ssp import SAO_PAULO_NAMES


@dataclass(frozen=True)
class OccurrenceFilter:
    """Filtro já validado: período, CEP normalizado e categoria_dado opcionais."""

    start: date
    end: date
    cep: str | None = None
    category: str | None = None


def _where(f: OccurrenceFilter, include_city: bool = True) -> tuple[str, list[object]]:
    clauses, values = [], []
    if include_city:
        clauses.append("municipio = ANY(%s)")
        values.append(list(SAO_PAULO_NAMES))
    clauses += ["data_ocorrencia >= %s", "data_ocorrencia <= %s"]
    values += [f.start, f.end]
    if f.cep:
        clauses.append("cep = %s")
        values.append(f.cep)
    if f.category:
        clauses.append("categoria_dado = %s")
        values.append(f.category)
    return " AND ".join(clauses), values


class PostgisOccurrenceRepository:
    def __init__(self, connect: Callable[[], Any]) -> None:
        self.connect = connect

    def status(self) -> dict[str, Any]:
        with self.connect() as conn:
            return conn.execute("""SELECT PostGIS_Full_Version() AS postgis,
                EXISTS(SELECT 1 FROM public.registro_ocorrencia LIMIT 1) AS tem_registros""").fetchone()

    def district_boundary(self, code: str) -> dict[str, Any] | None:
        """Limite do distrito em GeoJSON, simplificado (~5 m) para o mapa do diagnóstico."""
        with self.connect() as conn:
            row = conn.execute("""SELECT nome_distrito, ST_AsGeoJSON(ST_SimplifyPreserveTopology(geometria,0.00005),6) AS g
                FROM public.distrito_municipal_sp WHERE codigo_distrito=%s""", (code,)).fetchone()
        if not row:
            return None
        return {"type": "Feature", "properties": {"codigo": code, "nome": row["nome_distrito"]},
                "geometry": json.loads(row["g"])}

    def summary(self, f: OccurrenceFilter) -> dict[str, Any]:
        where, params = _where(f, include_city=False)
        with self.connect() as conn:
            rows = conn.execute(f"""SELECT GROUPING(categoria_dado) AS sem_categoria,
                GROUPING(date_trunc('month',data_ocorrencia)) AS sem_mes,
                categoria_dado,date_trunc('month',data_ocorrencia)::date AS mes,
                sum(registros) AS total,sum(com_cep) AS com_cep,
                sum(com_coordenada) AS com_coordenada,
                sum(soma_latitude)/NULLIF(sum(coordenadas_centro),0) AS latitude,
                sum(soma_longitude)/NULLIF(sum(coordenadas_centro),0) AS longitude
                FROM public.resumo_ocorrencia_diario WHERE {where}
                GROUP BY GROUPING SETS ((),(date_trunc('month',data_ocorrencia)),(categoria_dado))
                ORDER BY sem_categoria DESC,sem_mes DESC,mes,categoria_dado""", params).fetchall()
        total = next(r for r in rows if r["sem_categoria"] and r["sem_mes"])
        return {"total": total,
                "mensal": [r for r in rows if r["sem_categoria"] and not r["sem_mes"]],
                "categorias": [r for r in rows if not r["sem_categoria"] and r["sem_mes"]]}

    def district_counts(self, f: OccurrenceFilter) -> list[dict[str, Any]]:
        """Registros georreferenciados por distrito, com a população do Censo 2022."""
        where, params = _where(f, include_city=False)
        with self.connect() as conn:
            return conn.execute(f"""SELECT d.codigo_distrito AS codigo,d.nome_distrito AS distrito,d.regiao,
                     d.populacao_2022 AS populacao,COALESCE(c.registros,0) AS registros
              FROM public.distrito_municipal_sp d
              LEFT JOIN (
                SELECT codigo_distrito,SUM(registros) AS registros
                FROM public.resumo_distrito_diario WHERE {where}
                GROUP BY codigo_distrito
              ) c ON c.codigo_distrito=d.codigo_distrito
              ORDER BY d.nome_distrito""", params).fetchall()

    def cep_main_district(self, cep: str) -> dict[str, Any] | None:
        """Distrito com mais coordenadas históricas do CEP."""
        with self.connect() as conn:
            return conn.execute("""SELECT d.codigo_distrito AS codigo,d.nome_distrito AS distrito
                FROM public.resumo_distrito_diario r
                JOIN public.distrito_municipal_sp d USING (codigo_distrito)
                WHERE r.cep=%s
                GROUP BY d.codigo_distrito,d.nome_distrito
                ORDER BY SUM(r.registros) DESC,d.nome_distrito
                LIMIT 1""", (cep,)).fetchone()

    def map_cells(self, f: OccurrenceFilter, west: float, south: float, east: float,
                  north: float) -> list[dict[str, Any]]:
        where, params = _where(f)
        where += " AND localizacao && ST_MakeEnvelope(%s,%s,%s,%s,4326)"
        params += [west, south, east, north]
        with self.connect() as conn:
            return conn.execute(f"""SELECT ST_X(celula) AS longitude,ST_Y(celula) AS latitude,registros FROM (
              SELECT ST_SnapToGrid(localizacao,0.005) AS celula,count(*) AS registros
              FROM public.registro_ocorrencia WHERE {where} AND localizacao IS NOT NULL GROUP BY 1
            ) AS grade ORDER BY registros DESC LIMIT 1500""", params).fetchall()
