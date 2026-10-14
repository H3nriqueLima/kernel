"""Resumir sem cérebro: escolher, de um texto, as frases que mais dizem sobre o assunto.

É um resumo "por extração": nenhuma frase é inventada, todas saem do texto.
A nota de uma frase soma três coisas:

- as palavras dela que mais se repetem no texto inteiro (o que o texto repete é
  o que ele tem de central);
- as palavras do próprio assunto pedido;
- a posição: a primeira frase de um artigo costuma ser a definição.

Frases quase iguais a uma já escolhida ficam de fora, e o resumo sai na ordem
em que as frases aparecem no texto.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from ..memoria.texto import termos

_FRASE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÀ\"0-9])")


def frases(texto: str, minimo: int = 25, maximo: int = 400) -> list[str]:
    """O texto cortado em frases (as muito curtas e as gigantes ficam de fora)."""
    partes = (parte.strip() for linha in texto.split("\n") for parte in _FRASE.split(linha))
    return [f for f in partes if minimo <= len(f) <= maximo]


def resumir(textos: list[str] | str, assunto: str = "", quantas: int = 3, limite: int = 700) -> str:
    """As ``quantas`` frases que melhor resumem os textos, na ordem em que aparecem."""
    if isinstance(textos, str):
        textos = [textos]
    todas: list[tuple[int, str, set[str]]] = []      # (posição, frase, termos)
    vistas: set[str] = set()
    for texto in textos:
        for i, frase in enumerate(frases(texto)):
            chave = " ".join(termos(frase))
            if chave and chave not in vistas:
                vistas.add(chave)
                todas.append((len(todas) if i else -1, frase, set(chave.split())))   # -1 marca a primeira de um texto
    if not todas:
        return ""
    conta = Counter(termo for _, _, dos_termos in todas for termo in dos_termos)
    do_assunto = set(termos(assunto))

    def nota(item) -> float:
        posicao, _, dos_termos = item
        if not dos_termos:
            return 0.0
        base = sum(math.log1p(conta[t]) for t in dos_termos) / math.sqrt(len(dos_termos))
        if do_assunto:
            base *= 1.0 + 0.6 * len(do_assunto & dos_termos) / len(do_assunto)
        return base * (1.5 if posicao == -1 else 1.0)

    escolhidas: list[tuple[int, str, set[str]]] = []
    for item in sorted(todas, key=nota, reverse=True):
        _, _, dos_termos = item
        if any(len(dos_termos & outros) > 0.6 * min(len(dos_termos), len(outros)) for _, _, outros in escolhidas):
            continue   # diz quase o mesmo que uma frase já escolhida
        escolhidas.append(item)
        if len(escolhidas) == quantas:
            break
    ordem = {id(item): n for n, item in enumerate(todas)}
    saida = " ".join(frase for _, frase, _ in sorted(escolhidas, key=lambda item: ordem[id(item)]))
    return saida if len(saida) <= limite else saida[:limite].rsplit(" ", 1)[0] + "…"
