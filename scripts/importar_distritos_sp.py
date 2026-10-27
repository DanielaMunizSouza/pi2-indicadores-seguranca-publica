"""Importa limites oficiais dos distritos do GeoSampa para o PostGIS local."""
import json
import sys
from datetime import date
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app import DB_URL

ARQUIVO = ROOT / "data" / "reference" / "distritos_sp.geojson"


def main() -> None:
    dados = json.loads(ARQUIVO.read_text(encoding="utf-8-sig"))
    distritos = []
    for feature in dados.get("features", []):
        props = feature.get("properties", {})
        codigo = str(props.get("cd_distrito_municipal", "")).strip()
        nome = str(props.get("nm_distrito_municipal", "")).strip()
        if not codigo or not nome or not feature.get("geometry"):
            continue
        atualizado = str(props.get("dt_atualizacao", ""))[:10]
        try:
            atualizado_em = date.fromisoformat(atualizado) if atualizado else None
        except ValueError:
            atualizado_em = None
        distritos.append((codigo, nome, props.get("nm_regiao_05"), atualizado_em,
                          json.dumps(feature["geometry"], ensure_ascii=False)))

    if len(distritos) != 96:
        raise SystemExit(f"Esperados 96 distritos oficiais; encontrados {len(distritos)}.")

    with psycopg.connect(DB_URL) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS public.distrito_municipal_sp (
            codigo_distrito text PRIMARY KEY,
            nome_distrito text NOT NULL,
            regiao text,
            atualizado_em date,
            geometria geometry(MultiPolygon,4326) NOT NULL
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_distrito_municipal_sp_geometria "
                     "ON public.distrito_municipal_sp USING gist(geometria)")
        impressao = """SELECT md5(COALESCE(string_agg(codigo_distrito || ST_AsEWKB(geometria)::text, ''
                            ORDER BY codigo_distrito), '')) FROM public.distrito_municipal_sp"""
        antes = conn.execute(impressao).fetchone()[0]
        with conn.cursor() as cur:
            cur.executemany("""INSERT INTO public.distrito_municipal_sp
                (codigo_distrito,nome_distrito,regiao,atualizado_em,geometria)
                VALUES (%s,%s,%s,%s,ST_Multi(ST_CollectionExtract(
                  ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)),3)))
                ON CONFLICT (codigo_distrito) DO UPDATE SET
                  nome_distrito=EXCLUDED.nome_distrito,regiao=EXCLUDED.regiao,
                  atualizado_em=EXCLUDED.atualizado_em,geometria=EXCLUDED.geometria""",
                              distritos)
        if conn.execute(impressao).fetchone()[0] != antes:
            # Limites mudaram: o distrito gravado nas ocorrências precisa ser recalculado.
            existe = conn.execute("SELECT to_regclass('public.ocorrencia_distrito')").fetchone()[0]
            if existe:
                conn.execute("TRUNCATE public.ocorrencia_distrito")
                print("Limites alterados: o distrito das ocorrências será recalculado no resumo.")
        conn.commit()
    print(f"Limites oficiais importados: {len(distritos)} distritos.")


if __name__ == "__main__":
    main()
