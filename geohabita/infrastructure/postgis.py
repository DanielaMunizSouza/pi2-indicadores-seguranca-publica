"""Repositório PostGIS do diagnóstico (implementa ``DiagnosisRepository``).

As distâncias são geodésicas, em metros, calculadas sobre ``geography`` (RN12);
para parques e ciclovias, a distância vai até o ponto mais próximo do contorno
ou da linha. Os dados por distrito mudam só quando o pipeline roda, por isso
ficam em memória por alguns minutos.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Any

from psycopg.rows import tuple_row

from geohabita.application.diagnosis import District
from geohabita.domain.equipment import NearbyEquipment

PONTO = "ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)"
# A iluminação pública (~663 mil pontos) não entra no diagnóstico; o índice parcial
# sem ela evita que a busca por vizinhos percorra postes antes de achar o tipo pedido.
SEM_ILUMINACAO = "tipo <> 'iluminacao_publica'"
GRAUS_POR_METRO = 1 / 80_000  # folga para o filtro por caixa (1 grau de longitude ≈ 102 km em SP)
CACHE_S = 300


class PostgisDiagnosisRepository:
    def __init__(self, connect: Callable[[], Any], cache_s: float = CACHE_S) -> None:
        self.connect = connect
        self.cache_s = cache_s
        self._cache: dict[str, tuple[float, Any]] = {}

    def _cached(self, key: str, load: Callable[[], Any]) -> Any:
        stamp, value = self._cache.get(key, (0.0, None))
        if time.monotonic() - stamp > self.cache_s:
            value = load()
            self._cache[key] = (time.monotonic(), value)
        return value

    def _rows(self, sql: str, params: Any = None) -> list[tuple]:
        with self.connect() as conn, conn.cursor(row_factory=tuple_row) as cur:
            return cur.execute(sql, params).fetchall()

    def district_at(self, latitude: float, longitude: float) -> District | None:
        rows = self._rows(f"""SELECT codigo_distrito, nome_distrito, regiao FROM public.distrito_municipal_sp
                              WHERE ST_Contains(geometria, {PONTO}) LIMIT 1""", {"lat": latitude, "lon": longitude})
        return District(*rows[0]) if rows else None

    def available_types(self) -> set[str]:
        return self._cached("tipos", lambda: {r[0] for r in self._rows(
            "SELECT DISTINCT tipo FROM public.equipamento_publico")})

    def nearest_by_type(self, latitude: float, longitude: float, types: Sequence[str]) -> list[NearbyEquipment]:
        # Os 10 candidatos mais próximos pelo índice (distância em graus) são reordenados
        # pela distância geodésica, que é a que vale (RN12).
        rows = self._rows(f"""
            SELECT t.tipo, n.nome, n.distancia
            FROM unnest(%(tipos)s::text[]) AS t(tipo)
            CROSS JOIN LATERAL (
                SELECT c.nome, ST_Distance(c.geometria::geography, {PONTO}::geography) AS distancia
                FROM (SELECT nome, geometria FROM public.equipamento_publico e
                      WHERE e.tipo = t.tipo AND e.{SEM_ILUMINACAO}
                      ORDER BY e.geometria <-> {PONTO} LIMIT 10) c
                ORDER BY distancia LIMIT 1) n""",
                          {"tipos": list(types), "lat": latitude, "lon": longitude})
        return [NearbyEquipment(tipo, nome or "sem nome", float(d)) for tipo, nome, d in rows]

    def equipment_within(self, latitude: float, longitude: float, radius_m: float,
                         types: Sequence[str]) -> list[NearbyEquipment]:
        rows = self._rows(f"""
            SELECT tipo, nome, ST_Distance(geometria::geography, {PONTO}::geography)
            FROM public.equipamento_publico
            WHERE tipo = ANY(%(tipos)s) AND {SEM_ILUMINACAO}
              AND geometria && ST_Expand({PONTO}, %(folga)s)
              AND ST_DWithin(geometria::geography, {PONTO}::geography, %(raio)s)""",
                          {"tipos": list(types), "lat": latitude, "lon": longitude, "raio": radius_m,
                           "folga": radius_m * GRAUS_POR_METRO * 1.5})
        return [NearbyEquipment(tipo, nome or "sem nome", float(d)) for tipo, nome, d in rows]

    def district_indicators(self) -> dict[str, dict[tuple[str, str, int], float]]:
        def load() -> dict[str, dict[tuple[str, str, int], float]]:
            dados: dict[str, dict[tuple[str, str, int], float]] = {}
            for codigo, indicador, sub, ano, valor in self._rows(
                    "SELECT codigo_distrito, indicador, subcategoria, ano, valor FROM public.indicador_distrito"):
                dados.setdefault(codigo, {})[(indicador, sub, ano)] = valor
            return dados
        return self._cached("indicadores", load)

    def populations(self) -> dict[str, int]:
        return self._cached("populacao", lambda: {c: p for c, p in self._rows(
            "SELECT codigo_distrito, populacao_2022 FROM public.distrito_municipal_sp "
            "WHERE populacao_2022 IS NOT NULL")})

    def cep_centroid(self, cep: str) -> tuple[float, float] | None:
        """Mediana das coordenadas das ocorrências registradas com o CEP (reserva de geocodificação)."""
        rows = self._rows("""
            SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY latitude),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY longitude), count(*)
            FROM public.registro_ocorrencia WHERE cep = %s AND localizacao IS NOT NULL""", (cep,))
        lat, lon, n = rows[0]
        return (float(lat), float(lon)) if n else None
