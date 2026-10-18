"""Regras de negócio puras do GeoHabita.

Nenhum módulo deste pacote deve acessar banco de dados, rede ou interface.
Essas dependências pertencem às camadas de aplicação e infraestrutura, de
modo que as regras abaixo possam ser testadas de forma isolada (RNs, RFs e
o Quadro de limiares da especificação).
"""
