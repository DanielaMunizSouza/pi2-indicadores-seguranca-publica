Feature: Diagnóstico de endereço (HU02, HU05, HU10)
  Distrito, taxas oficiais e distância aos equipamentos do dia a dia.

  Scenario: O distrito do endereço é informado (HU02)
    Given o diagnóstico localiza o CEP 01310100 no distrito "SÉ"
    When o munícipe consulta o diagnóstico do CEP "01310100"
    Then o sistema informa o distrito "SÉ"

  Scenario: As taxas trazem média municipal, tendência e nota de subnotificação (HU05)
    Given o distrito tem taxas oficiais por cem mil habitantes
    When o munícipe consulta o diagnóstico do CEP "01310100"
    Then cada natureza mostra a taxa, a média municipal e a tendência
    And o diagnóstico traz a nota de subnotificação

  Scenario: A distância aos equipamentos do dia a dia é mostrada (HU10)
    Given o endereço tem a UBS a 250 metros, a escola a 300 metros e o ponto de ônibus a 150 metros
    When o munícipe consulta o diagnóstico do CEP "01310100"
    Then o diagnóstico mostra a distância e o tempo a pé até o equipamento mais próximo de cada tipo
