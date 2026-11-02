"""API HTTP do GeoHabita: camada de apresentação (RNF10).

Este módulo só traduz HTTP: valida parâmetros, chama os serviços de aplicação
e os repositórios da infraestrutura e converte erros em códigos de status.
Consultas SQL e chamadas externas ficam em ``geohabita.infrastructure``.
"""

import logging
from dataclasses import asdict
from datetime import date

import psycopg
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from geohabita.application.address_search import AddressSearch
from geohabita.application.cep_lookup import Address, CepLookup, CepNotFoundError, ProviderError
from geohabita.application.diagnosis import DiagnosisService, LocationNotFoundError
from geohabita.application.geocoding import CachedGeocoder, decode_point, encode_point
from geohabita.application.rate_limit import RateLimiter
from geohabita.config import DATABASE_URL as DB_URL, ROOT, TRUSTED_PROXIES, is_trusted
from geohabita.domain.address import InvalidAddressError
from geohabita.domain.cep import InvalidCepError, require_valid_cep
from geohabita.domain.ssp import DATASET_LABELS as CATEGORIES, rate_per_100k
from geohabita.domain.territory import APPROXIMATE_LOCATION_NOTICE, OUT_OF_CITY_MESSAGE, is_sao_paulo
from geohabita.infrastructure.cache import PersistentCache
from geohabita.infrastructure.cep_providers import brasilapi, brasilapi_coordinates, viacep, viacep_street
from geohabita.infrastructure.database import DatabaseUnavailable, connector
from geohabita.infrastructure.nominatim import NominatimClient, NominatimGeocoder, free_search
from geohabita.infrastructure.ocorrencias import OccurrenceFilter, PostgisOccurrenceRepository
from geohabita.infrastructure.postgis import PostgisDiagnosisRepository

app = FastAPI(title="GeoHabita — Diagnóstico socioespacial de São Paulo", version="1.0.0",
              description="Diagnóstico de endereço (proximidade, vitalidade e ocorrências oficiais) e "
                          "resumos agregados das ocorrências da SSP-SP por período, categoria e distrito.")

rate_limiter = RateLimiter()


# Só do cloudflared (local ou na rede do Docker) o CF-Connecting-IP é confiável.
def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else None
    forwarded = request.headers.get("cf-connecting-ip", "").strip()
    if is_trusted(peer, TRUSTED_PROXIES) and forwarded:
        return forwarded
    return peer or "desconhecido"


class AccessLogWithoutQuery(logging.Filter):
    """RNF15 (LGPD): o log de acesso não guarda o CEP consultado junto do IP de quem consultou."""

    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) >= 3 and isinstance(record.args[2], str):
            path = record.args[2].split("?", 1)[0]
            if path.startswith("/api/cep/"):
                path = "/api/cep/<cep>"
            record.args = record.args[:2] + (path,) + record.args[3:]
        return True


logging.getLogger("uvicorn.access").addFilter(AccessLogWithoutQuery())


@app.middleware("http")
async def limit_api_requests(request: Request, call_next):
    # RNF08: 60 requisições por minuto por IP nas rotas públicas da API.
    if request.url.path.startswith("/api/") and not rate_limiter.allow(client_ip(request)):
        return JSONResponse({"detail": "Muitas requisições. Aguarde um minuto e tente novamente."},
                            status_code=429, headers={"Retry-After": "60"})
    return await call_next(request)


@app.exception_handler(DatabaseUnavailable)
async def database_unavailable(request: Request, exc: DatabaseUnavailable):
    return JSONResponse({"detail": "Não foi possível conectar ao PostgreSQL. Confira DATABASE_URL "
                                   "e se o servidor está ativo."}, status_code=503)


@app.exception_handler(psycopg.Error)
async def database_error(request: Request, exc: psycopg.Error):
    return JSONResponse({"detail": "Falha ao consultar o banco de dados. Confira se o esquema foi "
                                   "criado e o pipeline executado."}, status_code=503)


connect = connector(DB_URL)
occurrence_repository = PostgisOccurrenceRepository(lambda: connect())


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(ROOT / "frontend" / "diagnostico.html")


@app.get("/explorar", include_in_schema=False)
def explorar():
    return FileResponse(ROOT / "frontend" / "explorar.html")


@app.get("/api/status")
def status():
    return {"banco": "conectado", **occurrence_repository.status()}


# ViaCEP é o serviço principal; a BrasilAPI responde quando ele falha ou demora (RN03).
# Endereços e coordenadas ficam 30 dias no banco (RN04).
cep_service = CepLookup(viacep, brasilapi, cache=PersistentCache(
    connect, "cep", encode=asdict, decode=lambda d: Address(**d)))


@app.get("/api/cep/{cep}")
def cep_address(cep: str):
    try:
        address = cep_service.lookup(cep)
    except InvalidCepError as exc:
        raise HTTPException(400, str(exc)) from exc
    except CepNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(503, "Os serviços de CEP estão indisponíveis. Tente novamente em instantes.") from exc
    inside = is_sao_paulo(address.ibge_code)
    return {"cep": address.cep, "logradouro": address.street, "bairro": address.neighbourhood,
            "municipio": address.city, "dentro_sao_paulo": inside,
            "aviso": None if inside else OUT_OF_CITY_MESSAGE,
            "latitude": address.latitude, "longitude": address.longitude,
            "nota_localizacao": APPROXIMATE_LOCATION_NOTICE}


# Diagnóstico socioespacial (UC02): proximidade e IPL, vitalidade e IVEP, ocorrências.
# O ViaCEP não traz coordenadas: elas vêm dos geocodificadores abaixo, em ordem.
diagnosis_repository = PostgisDiagnosisRepository(lambda: connect())
# Ordem: coordenada específica da BrasilAPI; mediana das ocorrências com o mesmo CEP;
# logradouro no Nominatim (OpenStreetMap).
def point_cache(namespace: str) -> PersistentCache:
    return PersistentCache(connect, namespace, encode=encode_point, decode=decode_point)


# Um só cliente do Nominatim, para que todos os usos respeitem 1 requisição por segundo.
nominatim = NominatimClient()
diagnosis_service = DiagnosisService(diagnosis_repository, cep_service, geocoders=[
    # Com o número do imóvel, a posição do próprio número vem antes de todas as outras.
    ("openstreetmap_numero", NominatimGeocoder(client=nominatim, house_number=True,
                                               cache=point_cache("nominatim_numero"))),
    ("brasilapi", CachedGeocoder(lambda endereco: brasilapi_coordinates(endereco.cep, raise_errors=True),
                                 point_cache("brasilapi"), key=lambda endereco: endereco.cep)),
    ("registros_ssp", lambda endereco: diagnosis_repository.cep_centroid(endereco.cep, endereco.street)),
    ("openstreetmap", NominatimGeocoder(client=nominatim, cache=point_cache("nominatim")))])

# Busca por endereço e busca reversa do CEP (RF03): ViaCEP, com o Nominatim de reserva.
address_search = AddressSearch(viacep_street, lambda texto: free_search(nominatim, texto),
                               cache=PersistentCache(connect, "viacep_logradouro"))


@app.get("/api/enderecos")
def enderecos(logradouro: str = Query(..., description="Nome da rua, avenida etc. (ao menos 3 letras)."),
              numero: str | None = Query(None, description="Número do imóvel, para escolher o CEP do trecho.")):
    """Endereços de São Paulo para o logradouro, com o CEP de cada trecho de numeração."""
    try:
        return address_search.search(logradouro, numero)
    except InvalidAddressError as exc:
        raise HTTPException(400, str(exc)) from exc


def peso():  # um Query novo por parâmetro: o mesmo objeto em vários parâmetros os confunde
    return Query(1, ge=0, le=5, description="Peso da categoria, inteiro de 0 a 5 (RN06).")


@app.get("/api/diagnostico")
def diagnostico(cep: str | None = Query(None, description="CEP do endereço (8 dígitos)."),
                numero: str | None = Query(None, description="Número do imóvel (opcional, só com CEP)."),
                lat: float | None = Query(None, ge=-90, le=90), lon: float | None = Query(None, ge=-180, le=180),
                peso_lazer_convivencia: int = peso(), peso_cultura_esporte: int = peso(),
                peso_mobilidade: int = peso(), peso_comercio_rua: int = peso(),
                peso_servicos_essenciais: int = peso(), peso_conectividade: int = peso()):
    """Diagnóstico de um CEP ou de uma coordenada, em três blocos independentes (RN07)."""
    pesos = {"lazer_convivencia": peso_lazer_convivencia, "cultura_esporte": peso_cultura_esporte,
             "mobilidade": peso_mobilidade, "comercio_rua": peso_comercio_rua,
             "servicos_essenciais": peso_servicos_essenciais, "conectividade": peso_conectividade}
    if (cep is None) == (lat is None or lon is None):
        raise HTTPException(400, "Informe o CEP ou a latitude e a longitude.")
    try:
        if cep is not None:
            return diagnosis_service.diagnose_cep(cep, pesos, numero)
        return diagnosis_service.diagnose_point(lat, lon, pesos)
    except InvalidCepError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except CepNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except LocationNotFoundError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(503, "Os serviços de CEP estão indisponíveis. Tente novamente em instantes.") from exc


@app.get("/api/categories")
def categories():
    return [{"value": k, "label": v} for k, v in CATEGORIES.items()]


@app.get("/api/distritos/{codigo}/limite", include_in_schema=False)
def district_boundary(codigo: str):
    """Limite de um distrito em GeoJSON, simplificado (~5 m) para o mapa do diagnóstico."""
    feature = occurrence_repository.district_boundary(codigo)
    if feature is None:
        raise HTTPException(404, "Distrito não encontrado.")
    return JSONResponse(feature, media_type="application/geo+json")


@app.get("/api/areas/geometry", include_in_schema=False)
def area_geometry():
    path = ROOT / "data" / "reference" / "distritos_sp.geojson"
    if not path.is_file():
        raise HTTPException(503, "Limites dos distritos não encontrados.")
    return FileResponse(path, media_type="application/geo+json")


def occurrence_filter(start: date, end: date, cep: str | None, category: str | None) -> OccurrenceFilter:
    if start > end:
        raise HTTPException(400, "A data inicial deve ser anterior ou igual à data final.")
    if category and category not in CATEGORIES:
        raise HTTPException(400, "Categoria inválida.")
    digits = None
    if cep:
        try:
            digits = require_valid_cep(cep)
        except InvalidCepError as exc:
            raise HTTPException(400, str(exc)) from exc
    return OccurrenceFilter(start, end, digits, category or None)


@app.get("/api/summary")
def summary(start: date = Query(date(2025, 1, 1)), end: date = Query(date(2026, 12, 31)),
            cep: str | None = None, category: str | None = None):
    result = occurrence_repository.summary(occurrence_filter(start, end, cep, category))
    total = result["total"]
    return {"total": total["total"], "com_cep": total["com_cep"], "com_coordenada": total["com_coordenada"],
            "centro": {"latitude": total["latitude"], "longitude": total["longitude"]},
            "mensal": [{"mes": r["mes"].strftime("%Y-%m"), "registros": r["total"]} for r in result["mensal"]],
            "categorias": [{"value": r["categoria_dado"], "label": CATEGORIES.get(r["categoria_dado"], r["categoria_dado"]),
                            "registros": r["total"]} for r in result["categorias"]],
            "periodo": {"inicio": start.isoformat(), "fim": end.isoformat()}}


@app.get("/api/areas")
def area_stats(start: date = Query(date(2025, 1, 1)), end: date = Query(date(2026, 12, 31)),
               cep: str | None = None, category: str | None = None):
    """Registros georreferenciados por distrito e taxa por 100 mil habitantes no período (RNF18)."""
    f = occurrence_filter(start, end, cep, category)
    rows = occurrence_repository.district_counts(f)
    cep_distrito = None
    cep_area = occurrence_repository.cep_main_district(f.cep) if f.cep else None
    if cep_area:
        # Coordenadas históricas de um CEP podem cair em distritos diferentes.
        # Use o distrito mais frequente no histórico e reúna nele os registros
        # do filtro atual, evitando que um mesmo CEP pinte áreas concorrentes.
        total_cep = sum(r["registros"] for r in rows)
        cep_distrito = {"codigo": cep_area["codigo"], "distrito": cep_area["distrito"],
                        "criterio": "maior concentração histórica de coordenadas do CEP"}
        rows = [{**r, "registros": total_cep if r["codigo"] == cep_area["codigo"] else 0} for r in rows]
    return {"unidade": "distrito", "cep_distrito": cep_distrito,
            "areas": [{"codigo": r["codigo"], "distrito": r["distrito"], "regiao": r["regiao"],
                       "registros": r["registros"], "populacao": r["populacao"],
                       "taxa_100k": rate_per_100k(r["registros"], r["populacao"])} for r in rows]}


@app.get("/api/map")
def map_cells(west: float, south: float, east: float, north: float,
              start: date = Query(date(2025, 1, 1)), end: date = Query(date(2026, 12, 31)),
              cep: str | None = None, category: str | None = None):
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(400, "Área do mapa inválida.")
    rows = occurrence_repository.map_cells(occurrence_filter(start, end, cep, category), west, south, east, north)
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["longitude"], r["latitude"]]},
         "properties": {"registros": r["registros"]}} for r in rows]}
