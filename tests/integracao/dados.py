"""Dados fictícios do banco de teste: três distritos quadrados e equipamentos a distâncias conhecidas.

Tudo é posicionado em metros a partir de ``ORIGEM`` (no distrito T1), para que
os testes possam afirmar distâncias exatas sem depender dos dados reais.

    T3 (norte)
    T1 (centro, contém a origem)   T2 (leste)
"""

from __future__ import annotations

import json
import math
from datetime import date

ORIGEM = (-23.55, -46.65)  # (latitude, longitude)
METROS_POR_GRAU_LAT = 111_320
METADE_DISTRITO_M = 1_500  # cada distrito é um quadrado de 3 km de lado


def deslocado(leste_m: float = 0, norte_m: float = 0, origem=ORIGEM) -> tuple[float, float]:
    """(latitude, longitude) do ponto a ``leste_m`` e ``norte_m`` metros da origem."""
    lat, lon = origem
    return (lat + norte_m / METROS_POR_GRAU_LAT,
            lon + leste_m / (METROS_POR_GRAU_LAT * math.cos(math.radians(lat))))


def quadrado_wkt(oeste_m: float, sul_m: float, leste_m: float, norte_m: float, multi: bool = True) -> str:
    cantos = [deslocado(oeste_m, sul_m), deslocado(leste_m, sul_m), deslocado(leste_m, norte_m),
              deslocado(oeste_m, norte_m), deslocado(oeste_m, sul_m)]
    anel = ", ".join(f"{lon} {lat}" for lat, lon in cantos)
    return f"MULTIPOLYGON((({anel})))" if multi else f"POLYGON(({anel}))"


def ponto_wkt(leste_m: float = 0, norte_m: float = 0) -> str:
    lat, lon = deslocado(leste_m, norte_m)
    return f"POINT({lon} {lat})"


M = METADE_DISTRITO_M
# código -> (nome, região, população, (oeste, sul, leste, norte) em metros)
DISTRITOS = {
    "T1": ("TESTE CENTRO", "Centro", 100_000, (-M, -M, M, M)),
    "T2": ("TESTE LESTE", "Leste", 200_000, (M, -M, 3 * M, M)),
    "T3": ("TESTE NORTE", "Norte", 50_000, (-M, M, M, 3 * M)),
}

# (tipo, categoria, nome, wkt): distâncias a partir da origem nos comentários.
EQUIPAMENTOS = [
    ("unidade_basica_saude", "servicos_essenciais", "UBS Perto", ponto_wkt(leste_m=250)),     # 250 m
    ("unidade_basica_saude", "servicos_essenciais", "UBS Longe", ponto_wkt(norte_m=600)),     # 600 m
    ("ponto_onibus", "mobilidade", "Ponto 300", ponto_wkt(norte_m=300)),                      # 300 m
    ("ponto_onibus", "mobilidade", "Ponto 800", ponto_wkt(norte_m=-800)),                     # 800 m
    ("ponto_onibus", "mobilidade", "Ponto 1500", ponto_wkt(leste_m=-1_450)),                  # 1,45 km
    # Parque de 200 m x 200 m com o centro a 500 m ao sul: o contorno fica a 400 m.
    ("parque_area_verde", "lazer_convivencia", "Parque Teste", quadrado_wkt(-100, -600, 100, -400, multi=False)),
    ("escola_publica", "servicos_essenciais", "Escola Leste", ponto_wkt(leste_m=2_000)),     # em T2
]
# Pontos de iluminação: 5 a até 300 m da origem e 3 a 500 m.
ILUMINACAO = [ponto_wkt(leste_m=d) for d in (50, 100, 150, 200, 250)] + \
             [ponto_wkt(norte_m=-500), ponto_wkt(leste_m=-500), ponto_wkt(norte_m=500)]

# Percentil de cada categoria por distrito (indicador_distrito).
PERCENTIS = {"T1": 80.0, "T2": 20.0, "T3": 50.0}

# Ocorrências: (distrito, deslocamento leste/norte, data, categoria_dado, natureza, cep).
OCORRENCIAS = (
    [("T1", (10 * i, 0), date(2024, 1 + i % 12, 5), "criminal", "FURTO (ART. 155)", "01310100") for i in range(12)]
    + [("T1", (0, 10 * i), date(2025, 3, 10), "criminal", "ROUBO (ART. 157)", "01310100") for i in range(3)]
    + [("T2", (M * 2, 10 * i), date(2024, 6, 1), "celulares_subtraidos", None, "01310100") for i in range(5)]
    + [("T3", (0, M * 2), date(2025, 7, 1), "criminal", "FURTO (ART. 155)", "02000000")]
)


def semear(conn) -> None:
    """Insere os dados fictícios num banco recém-criado com database/schema.sql."""
    for codigo, (nome, regiao, populacao, (o, s, l, n)) in DISTRITOS.items():
        conn.execute("""INSERT INTO public.distrito_municipal_sp
                        (codigo_distrito, nome_distrito, regiao, atualizado_em, geometria, populacao_2022)
                        VALUES (%s, %s, %s, '2025-01-01', ST_GeomFromText(%s, 4326), %s)""",
                     (codigo, nome, regiao, quadrado_wkt(o, s, l, n), populacao))
    for i, (tipo, categoria, nome, wkt) in enumerate(EQUIPAMENTOS):
        conn.execute("""INSERT INTO public.equipamento_publico
                        (categoria, tipo, camada, identificador, nome, geometria)
                        VALUES (%s, %s, 'teste', %s, %s, ST_GeomFromText(%s, 4326))""",
                     (categoria, tipo, f"eq{i}", nome, wkt))
    for i, wkt in enumerate(ILUMINACAO):
        conn.execute("""INSERT INTO public.equipamento_publico
                        (categoria, tipo, camada, identificador, geometria)
                        VALUES ('conectividade', 'iluminacao_publica', 'teste_luz', %s, ST_GeomFromText(%s, 4326))""",
                     (f"luz{i}", wkt))
    from geohabita.domain.thresholds import CATEGORIES
    for codigo, percentil in PERCENTIS.items():
        for categoria in CATEGORIES:
            conn.execute("""INSERT INTO public.indicador_distrito (codigo_distrito, indicador, subcategoria, ano, valor)
                            VALUES (%s, 'percentil', %s, 0, %s)""", (codigo, categoria, percentil))
    for linha, (codigo, (leste, norte), dia, categoria, natureza, cep) in enumerate(OCORRENCIAS):
        o, s, _, _ = DISTRITOS[codigo][3]
        lat, lon = deslocado(leste, norte)
        rubrica = "ROUBO" if categoria == "celulares_subtraidos" else None
        (ident,) = conn.execute(
            """INSERT INTO public.registro_ocorrencia
               (arquivo_origem, linha_origem, categoria_dado, municipio, data_ocorrencia, cep,
                latitude, longitude, natureza, rubrica, dados_originais)
               VALUES ('teste.csv', %s, %s, 'S.PAULO', %s, %s, %s, %s, %s, %s, %s::jsonb) RETURNING id""",
            (linha, categoria, dia, cep, lat, lon, natureza, rubrica, json.dumps({}))).fetchone()
        conn.execute("INSERT INTO public.ocorrencia_distrito (id, codigo_distrito) VALUES (%s, %s)", (ident, codigo))
    # Agregados diários usados pela página de exploração (o pipeline os calcula na etapa resumo).
    conn.execute("""INSERT INTO public.resumo_distrito_diario (codigo_distrito, data_ocorrencia, categoria_dado, cep, registros)
                    SELECT o.codigo_distrito, r.data_ocorrencia, r.categoria_dado, COALESCE(r.cep, ''), count(*)
                    FROM public.registro_ocorrencia r JOIN public.ocorrencia_distrito o USING (id)
                    GROUP BY 1, 2, 3, 4""")
    conn.execute("""INSERT INTO public.resumo_ocorrencia_diario
                    (data_ocorrencia, categoria_dado, cep, registros, com_cep, com_coordenada,
                     soma_latitude, soma_longitude, coordenadas_centro)
                    SELECT data_ocorrencia, categoria_dado, COALESCE(cep, ''), count(*), count(cep),
                           count(localizacao), sum(latitude), sum(longitude), count(localizacao)
                    FROM public.registro_ocorrencia GROUP BY 1, 2, 3""")
