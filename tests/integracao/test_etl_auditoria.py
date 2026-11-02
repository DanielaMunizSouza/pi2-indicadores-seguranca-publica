"""A carga da SSP grava a auditoria em carga_etl (RF19, RF20, RN10; CT13)."""

import csv

import pytest
from psycopg.rows import dict_row


from scripts import carregar_ssp

pytestmark = pytest.mark.integracao


@pytest.fixture(autouse=True)
def limpa_carga(url_teste):
    """A carga apaga e recria as linhas do arquivo: remova-as ao fim de cada teste,
    para que os demais testes vejam só os dados fictícios de ``dados.py``."""
    import psycopg
    yield
    with psycopg.connect(url_teste) as conn:
        conn.execute("DELETE FROM public.carga_etl")
        conn.execute("DELETE FROM public.ocorrencia_distrito USING public.registro_ocorrencia r "
                     "WHERE ocorrencia_distrito.id = r.id AND r.arquivo_origem LIKE 'SPDadosCriminais_2024__TESTE%'")
        conn.execute("DELETE FROM public.registro_ocorrencia WHERE arquivo_origem LIKE 'SPDadosCriminais_2024__TESTE%'")

# Cabeçalho mínimo de um CSV do pipeline; os campos de SSP que fazem sentido ao teste.
CABECALHO = ["DATA_OCORRENCIA_BO", "ANO_BO", "HORA_OCORRENCIA", "CEP", "BAIRRO", "LOGRADOURO",
             "NUMERO_LOGRADOURO", "LATITUDE", "LONGITUDE", "NATUREZA_APURADA", "RUBRICA",
             "NOME_MUNICIPIO", "CD_IBGE", "NUM_BO", "ID_DELEGACIA"]

# Duas coordenadas válidas em SP, uma zerada e uma fora do município.
LINHAS = [
    {"DATA_OCORRENCIA_BO": "05/01/2024", "ANO_BO": "2024", "CEP": "01310100", "BAIRRO": "Bela Vista",
     "LOGRADOURO": "Avenida Paulista", "NUMERO_LOGRADOURO": "100",
     "LATITUDE": "-23.55", "LONGITUDE": "-46.65", "NATUREZA_APURADA": "FURTO (ART. 155)",
     "NOME_MUNICIPIO": "São Paulo", "CD_IBGE": "3550308", "NUM_BO": "1", "ID_DELEGACIA": "D1"},
    {"DATA_OCORRENCIA_BO": "06/01/2024", "ANO_BO": "2024", "CEP": "01310100",
     "LATITUDE": "-23.56", "LONGITUDE": "-46.64", "NATUREZA_APURADA": "ROUBO (ART. 157)",
     "NOME_MUNICIPIO": "São Paulo", "CD_IBGE": "3550308", "NUM_BO": "2", "ID_DELEGACIA": "D1"},
    {"DATA_OCORRENCIA_BO": "07/01/2024", "ANO_BO": "2024", "CEP": "01310100",
     "LATITUDE": "0", "LONGITUDE": "0", "NATUREZA_APURADA": "FURTO (ART. 155)",
     "NOME_MUNICIPIO": "São Paulo", "CD_IBGE": "3550308", "NUM_BO": "3", "ID_DELEGACIA": "D1"},
    {"DATA_OCORRENCIA_BO": "08/01/2024", "ANO_BO": "2024", "CEP": "01310100",
     "LATITUDE": "-1.0", "LONGITUDE": "-1.0", "NATUREZA_APURADA": "FURTO (ART. 155)",
     "NOME_MUNICIPIO": "São Paulo", "CD_IBGE": "3550308", "NUM_BO": "4", "ID_DELEGACIA": "D1"},
]


def _gravar_csv(tmp_path, nome):
    arquivo = tmp_path / nome
    with arquivo.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CABECALHO, delimiter=";")
        writer.writeheader()
        writer.writerows(LINHAS)
    return arquivo


def test_carga_registra_importados_sem_coordenada_e_fora_do_municipio(tmp_path, url_teste):
    arquivo = _gravar_csv(tmp_path, "SPDadosCriminais_2024__TESTE.csv")
    importados, pulado = carregar_ssp.carregar_arquivo(arquivo, url_teste, refazer=True)
    assert (importados, pulado) == (4, False)

    import psycopg
    with psycopg.connect(url_teste, row_factory=dict_row) as conn:
        auditoria = conn.execute("""SELECT registros_importados, registros_sem_coordenada,
                registros_fora_do_municipio FROM public.carga_etl WHERE arquivo = %s""",
                                 (arquivo.name,)).fetchone()
    assert auditoria == {"registros_importados": 4, "registros_sem_coordenada": 1, "registros_fora_do_municipio": 1}


def test_carga_repete_o_arquivo_sem_reimportar(tmp_path, url_teste):
    arquivo = _gravar_csv(tmp_path, "SPDadosCriminais_2024__TESTE2.csv")
    carregar_ssp.carregar_arquivo(arquivo, url_teste, refazer=True)
    importados, pulado = carregar_ssp.carregar_arquivo(arquivo, url_teste)
    assert pulado is True and importados == 4  # assinatura idêntica: nada foi recarregado


def test_atualizar_indicadores_exclui_tipos_sem_equipamento(url_teste):
    import psycopg
    from scripts.atualizar_indicadores import equipment_rows
    with psycopg.connect(url_teste) as conn:
        linhas = equipment_rows(conn)
    subcategorias = {s for _, _, s, _, _ in linhas}
    # A seed não carrega praças nem metrô: esses tipos não geram linhas nem percentil.
    assert "praca" not in subcategorias and "estacao_metro_trem" not in subcategorias
    assert {"parque_area_verde", "unidade_basica_saude", "ponto_onibus", "iluminacao_publica"} <= subcategorias
    # Percentil da categoria lazer = percentil do único tipo com dados (parque).
    lazer = {c: v for c, i, s, _, v in linhas if i == "percentil" and s == "lazer_convivencia"}
    parque = {c: v for c, i, s, _, v in linhas if i == "percentil" and s == "parque_area_verde"}
    assert lazer == parque
