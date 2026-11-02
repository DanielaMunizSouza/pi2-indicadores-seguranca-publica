"""Detalhes de funcionamento extraídos das camadas do GeoSampa (dia da feira, horário do mercado)."""

from scripts.pipeline_dados import detalhes_da_feicao


def test_feira_guarda_o_dia_com_acento():
    assert detalhes_da_feicao("equipamento_feira_livre", {"tx_dia_funcionamento": "SABADO"}) == {"dia": "sábado"}
    assert detalhes_da_feicao("equipamento_feira_livre", {"tx_dia_funcionamento": "TERCA-FEIRA"}) == \
        {"dia": "terça-feira"}


def test_feira_sem_dia_nao_tem_detalhes():
    assert detalhes_da_feicao("equipamento_feira_livre", {"tx_dia_funcionamento": None}) is None


def test_mercado_guarda_horario_e_telefone_limpos():
    detalhes = detalhes_da_feicao("equipamento_mercados_municipais", {
        "tx_horario_funcionamento": "TERÇA Á SÁBADO 8:30-18H, DOMINGO 8H-13H.\xa0\xa0",
        "tx_numero_telefone": "11 2061-7616.\xa0\xa0"})
    assert detalhes == {"horario": "Terça á sábado 8:30-18h, domingo 8h-13h", "telefone": "11 2061-7616"}


def test_telefone_nao_informado_e_omitido():
    detalhes = detalhes_da_feicao("equipamento_mercados_municipais", {
        "tx_horario_funcionamento": "SEGUNDA A SABADO 8H-19H", "tx_numero_telefone": "Não informado"})
    assert detalhes == {"horario": "Segunda a sabado 8h-19h"}


def test_outras_camadas_nao_tem_detalhes():
    assert detalhes_da_feicao("ponto_onibus", {"tx_dia_funcionamento": "SABADO"}) is None
