"""Comandos: o classificador pequeno que decide o que você pediu.

O cérebro da v0.1 é pequeno demais para confiar a ele um "abrir X" ou
"lembrar Y". Então os comandos críticos passam por este classificador, treinado
por você com os exemplos de ``exemplos.txt``; o cérebro fica com a conversa.
"""
from .classificador import INTENCOES, Classificador, carregar_exemplos, garantir, treinar

__all__ = ["INTENCOES", "Classificador", "carregar_exemplos", "garantir", "treinar"]
