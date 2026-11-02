"""Registro das cargas executadas pelo pipeline (RF19, RN10).

Toda etapa que grava dados no banco deixa uma linha em `public.carga_etl`: fonte,
arquivo, quantidade importada, quantidade sem coordenada e quantidade cuja
coordenada cai fora do município. É o rastro que a tela de fontes e a auditoria
precisam para dizer quando cada base foi carregada.
"""
from __future__ import annotations

import hashlib
from typing import Any


def assinatura(*valores: Any) -> str:
    """Hash curto dos argumentos, para identificar uma execução repetida."""
    texto = "|".join("" if v is None else str(v) for v in valores)
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:16]


def registrar(conn, fonte: str, arquivo: str, categoria: str | None, importados: int,
              sem_coordenada: int = 0, fora_do_municipio: int = 0, situacao: str = "concluida",
              sig: str | None = None) -> None:
    """Grava (ou atualiza) a linha de carga do arquivo; idempotente por fonte+arquivo."""
    conn.execute(
        """INSERT INTO public.carga_etl (fonte, arquivo, categoria, registros_importados,
                registros_sem_coordenada, registros_fora_do_municipio, situacao, assinatura)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (fonte, arquivo) DO UPDATE SET categoria = EXCLUDED.categoria,
                registros_importados = EXCLUDED.registros_importados,
                registros_sem_coordenada = EXCLUDED.registros_sem_coordenada,
                registros_fora_do_municipio = EXCLUDED.registros_fora_do_municipio,
                situacao = EXCLUDED.situacao, assinatura = EXCLUDED.assinatura,
                executada_em = now()""",
        (fonte, arquivo, categoria, importados, sem_coordenada, fora_do_municipio, situacao,
         sig or assinatura(fonte, arquivo, importados)))
