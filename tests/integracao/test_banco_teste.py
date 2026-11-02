"""O banco de teste é criado à parte, com o esquema e os dados fictícios, e nunca é o de DATABASE_URL."""

import os

import pytest
from psycopg.conninfo import conninfo_to_dict

from tests.integracao.conftest import PREFIXO
from tests.integracao.dados import DISTRITOS, EQUIPAMENTOS, ILUMINACAO, OCORRENCIAS

pytestmark = pytest.mark.integracao


def test_banco_de_teste_nao_e_o_da_aplicacao(url_teste):
    nome = conninfo_to_dict(url_teste)["dbname"]
    assert nome.startswith(PREFIXO)
    assert nome != conninfo_to_dict(os.environ["DATABASE_URL"]).get("dbname")


def test_esquema_e_dados_ficticios_carregados(connect):
    with connect() as conn:
        contagem = conn.execute("""SELECT (SELECT count(*) FROM public.distrito_municipal_sp) AS distritos,
                                          (SELECT count(*) FROM public.equipamento_publico) AS equipamentos,
                                          (SELECT count(*) FROM public.registro_ocorrencia) AS ocorrencias""").fetchone()
    assert contagem == {"distritos": len(DISTRITOS), "equipamentos": len(EQUIPAMENTOS) + len(ILUMINACAO),
                        "ocorrencias": len(OCORRENCIAS)}
