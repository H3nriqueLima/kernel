"""Conhecimento: uma enciclopédia local montada a partir da Wikipédia que ele estudou.

Não é o cérebro respondendo: é busca. Ele acha o artigo certo e lê para você o
começo. Funciona sem internet, depois que o estudo termina.
"""
from .enciclopedia import Enciclopedia, assunto_da_pergunta

__all__ = ["Enciclopedia", "assunto_da_pergunta"]
