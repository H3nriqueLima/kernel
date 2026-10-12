"""Como um texto vira termos de busca.

"Reuniões com os clientes" -> ["reuniao", "cliente"]: minúsculas, sem acento,
sem palavras vazias ("com", "os") e com o plural reduzido ao singular.
A busca só enxerga o que sair daqui, então mexer nesta função muda o que a
memória consegue encontrar.
"""
from __future__ import annotations

import re
import unicodedata

# Palavras que aparecem em toda frase e não ajudam a achar nada (já sem acento).
PARADAS = frozenset(
    """a o as os um uma uns umas de do da dos das em no na nos nas por para pra pro
    com sem e ou que se me te lhe eu tu ele ela nos voce voces eles elas meu minha
    meus minhas seu sua seus suas este esta isto esse essa isso aquele aquela aquilo
    ao aos foi ser sao era ha tem ter mais mas como quando onde qual quais quem
    muito ja nao sim so tambem ate sobre entre depois antes la aqui ai""".split()
)

_PALAVRA = re.compile(r"[a-z0-9]+")


def sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def normalizar(texto: str) -> str:
    return sem_acento(texto.lower())


def radical(palavra: str) -> str:
    """Plural -> singular, do jeito mais simples que funciona na maioria dos casos."""
    if len(palavra) > 4 and palavra.endswith(("oes", "aes")):
        return palavra[:-3] + "ao"  # reunioes -> reuniao, paes -> pao
    if len(palavra) > 3 and palavra.endswith("s") and not palavra.endswith("ss"):
        return palavra[:-1]
    return palavra


def termos(texto: str) -> list[str]:
    return [
        radical(p)
        for p in _PALAVRA.findall(normalizar(texto))
        if p not in PARADAS and len(p) > 1
    ]
