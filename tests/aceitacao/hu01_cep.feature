Feature: Consulta por CEP (HU01)
  Como munícipe, quero digitar um CEP e ver o endereço reconhecido,
  para iniciar a consulta sem preencher formulários longos.

  Scenario: CEP válido reconhece o endereço
    Given o ViaCEP responde o endereço da Avenida Paulista para o CEP 01310100
    When o munícipe consulta o CEP "01310100"
    Then o sistema exibe logradouro "Avenida Paulista", bairro "Bela Vista" e município "São Paulo"

  Scenario: Formato inválido não consulta nenhum serviço
    Given o serviço de CEP não pode ser chamado
    When o munícipe informa "1234"
    Then o sistema exibe "O CEP deve ter 8 dígitos" e nenhuma API externa é chamada

  Scenario: CEP inexistente
    Given o ViaCEP e a BrasilAPI não reconhecem o CEP 99999999
    When o munícipe consulta o CEP "99999-999"
    Then o sistema exibe "CEP não encontrado"

  Scenario: Serviço principal indisponível
    Given o ViaCEP demora mais que 3 segundos
    When o munícipe consulta o CEP "01310100"
    Then o endereço vem do serviço de contingência
