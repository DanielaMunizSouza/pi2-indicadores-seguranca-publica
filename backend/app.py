import os, re
from datetime import date
from pathlib import Path
import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from psycopg.rows import dict_row

ROOT=Path(__file__).resolve().parents[1]
# Read local configuration when present; environment variables still take precedence.
_env_file=ROOT/".env"
if _env_file.is_file():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _key, _sep, _value = _line.partition("=")
        if _sep and _key.strip() and not _key.lstrip().startswith("#"):
            os.environ.setdefault(_key.strip(), _value.strip().strip("\"'").strip())
DB_URL=os.getenv("DATABASE_URL","postgresql://postgres@localhost:5432/ProjetoIntergrador_2")
CATEGORIES={"objetos":"Objetos","celulares_subtraidos":"Celulares subtraídos","apreensao_entorpecente":"Apreensão de entorpecentes","entorpecentes_gramas":"Entorpecentes (gramas)","outros":"Outros"}
app=FastAPI(title="Indicadores de Segurança Pública — São Paulo",version="1.0.0",description="Resumos agregados por período, categoria e localização.")

def connect():
    try: return psycopg.connect(DB_URL,connect_timeout=5,row_factory=dict_row)
    except psycopg.Error as exc: raise HTTPException(503,"Não foi possível conectar ao PostgreSQL. Confira DATABASE_URL e se o servidor está ativo.") from exc

def make_where(start,end,cep,category):
    if start>end: raise HTTPException(400,"A data inicial deve ser anterior ou igual à data final.")
    if category and category not in CATEGORIES: raise HTTPException(400,"Categoria inválida.")
    clauses=["municipio = %s","data_ocorrencia >= %s","data_ocorrencia <= %s"]
    values:list[object]=["São Paulo",start,end]
    if cep:
        digits=re.sub(r"\D","",cep)
        if len(digits)!=8: raise HTTPException(400,"Digite um CEP com 8 dígitos.")
        clauses.append("cep = %s"); values.append(digits)
    if category: clauses.append("categoria_dado = %s"); values.append(category)
    return " AND ".join(clauses),values

@app.get("/",include_in_schema=False)
def home(): return FileResponse(ROOT/"frontend"/"index.html")

@app.get("/api/status")
def status():
    with connect() as conn:
        row=conn.execute("SELECT PostGIS_Full_Version() AS postgis, EXISTS(SELECT 1 FROM public.registro_ocorrencia LIMIT 1) AS tem_registros").fetchone()
    return {"banco":"conectado",**row}

@app.get("/api/categories")
def categories(): return [{"value":k,"label":v} for k,v in CATEGORIES.items()]

@app.get("/api/summary")
def summary(start:date=Query(date(2025,1,1)),end:date=Query(date(2026,12,31)),cep:str|None=None,category:str|None=None):
    where,params=make_where(start,end,cep,category)
    try:
        with connect() as conn:
            rows=conn.execute(f"""SELECT GROUPING(categoria_dado) AS sem_categoria,
                GROUPING(date_trunc('month',data_ocorrencia)) AS sem_mes,
                categoria_dado,date_trunc('month',data_ocorrencia)::date AS mes,
                count(*) AS total,
                count(*) FILTER(WHERE cep IS NOT NULL) AS com_cep,
                count(*) FILTER(WHERE localizacao IS NOT NULL) AS com_coordenada,
                avg(latitude) FILTER(WHERE localizacao IS NOT NULL) AS latitude,
                avg(longitude) FILTER(WHERE localizacao IS NOT NULL) AS longitude
                FROM public.registro_ocorrencia WHERE {where}
                GROUP BY GROUPING SETS ((),(date_trunc('month',data_ocorrencia)),(categoria_dado))
                ORDER BY sem_categoria DESC,sem_mes DESC,mes,categoria_dado""",params).fetchall()
            total=next(r for r in rows if r["sem_categoria"] and r["sem_mes"])
            monthly=[{"mes":r["mes"].strftime("%Y-%m"),"registros":r["total"]} for r in rows if r["sem_categoria"] and not r["sem_mes"]]
            grouped=[r for r in rows if not r["sem_categoria"] and r["sem_mes"]]
    except psycopg.Error as exc:
        raise HTTPException(503,"Falha ao consultar os dados. Confira se o esquema foi criado.") from exc
    return {"total":total["total"],"com_cep":total["com_cep"],"com_coordenada":total["com_coordenada"],
      "centro":{"latitude":total["latitude"],"longitude":total["longitude"]},"mensal":monthly,
      "categorias":[{"value":r["categoria_dado"],"label":CATEGORIES.get(r["categoria_dado"],r["categoria_dado"]),"registros":r["registros"]} for r in grouped],
      "periodo":{"inicio":start.isoformat(),"fim":end.isoformat()}}

@app.get("/api/map")
def map_cells(west:float,south:float,east:float,north:float,start:date=Query(date(2025,1,1)),
              end:date=Query(date(2026,12,31)),cep:str|None=None,category:str|None=None):
    if not(-180<=west<east<=180 and -90<=south<north<=90): raise HTTPException(400,"Área do mapa inválida.")
    where,params=make_where(start,end,cep,category)
    where+=" AND localizacao && ST_MakeEnvelope(%s,%s,%s,%s,4326)"; params += [west,south,east,north]
    sql=f"""SELECT ST_X(celula) AS longitude,ST_Y(celula) AS latitude,registros FROM (
      SELECT ST_SnapToGrid(localizacao,0.005) AS celula,count(*) AS registros
      FROM public.registro_ocorrencia WHERE {where} AND localizacao IS NOT NULL GROUP BY 1
    ) AS grade ORDER BY registros DESC LIMIT 1500"""
    try:
        with connect() as conn: rows=conn.execute(sql,params).fetchall()
    except psycopg.Error as exc: raise HTTPException(503,"Falha ao consultar a camada do mapa.") from exc
    return {"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Point","coordinates":[r["longitude"],r["latitude"]]},"properties":{"registros":r["registros"]}} for r in rows]}
