"""CT22 (RN16): o IPL é calculado sobre o ponto do endereço; o IVEP é o do distrito.

Diagnóstico completo, com o repositório PostGIS real sobre os dados fictícios.
"""

from datetime import date

import pytest

from geohabita.application.diagnosis import DiagnosisService
from geohabita.infrastructure.postgis import PostgisDiagnosisRepository
from tests.integracao.dados import deslocado

pytestmark = pytest.mark.integracao


class SemConsultaDeCep:
    def lookup(self, cep):  # o teste diagnostica coordenadas, sem CEP
        raise AssertionError("não deveria consultar CEP")


def test_ct22_dois_pontos_no_mesmo_distrito_tem_ipl_diferente_e_mesmo_ivep(connect):
    servico = DiagnosisService(PostgisDiagnosisRepository(connect, cache_s=0), SemConsultaDeCep(),
                               today=lambda: date(2026, 6, 1))
    perto = servico.diagnose_point(*deslocado(0, 0))
    longe = servico.diagnose_point(*deslocado(leste_m=-1_000))
    assert perto["local"]["distrito"]["codigo"] == longe["local"]["distrito"]["codigo"] == "T1"
    ipl_perto = perto["diagnostico"]["proximidade"]["ipl"]
    ipl_longe = longe["diagnostico"]["proximidade"]["ipl"]
    assert ipl_perto > ipl_longe
    assert perto["diagnostico"]["vitalidade"]["ivep"] == longe["diagnostico"]["vitalidade"]["ivep"] == 80.0


def test_diagnostico_real_tem_ubs_mais_proxima_e_taxas_do_distrito(connect):
    servico = DiagnosisService(PostgisDiagnosisRepository(connect, cache_s=0), SemConsultaDeCep(),
                               today=lambda: date(2026, 6, 1))
    diagnostico = servico.diagnose_point(*deslocado(0, 0))["diagnostico"]
    ubs = diagnostico["proximidade"]["tipos"]["unidade_basica_saude"]
    assert ubs["nome"] == "UBS Perto" and ubs["tempo_caminhada_min"] == 4  # 250 m a 80 m/min
    assert diagnostico["ocorrencias"]["janela"] == [2023, 2025]
    assert diagnostico["ocorrencias"]["populacao"] == 100_000
