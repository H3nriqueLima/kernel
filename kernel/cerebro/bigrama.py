"""Modelo de bigramas: o modelo de linguagem mais simples que existe.

Ele só sabe uma coisa: dada a letra atual, qual a chance de cada letra vir
depois. "Treinar" é contar pares de letras num monte de palavras. Mesmo assim
ele já inventa nomes que parecem português, e tem a mesma interface de um GPT:
uma perda para medir e uma função para gerar.

    python -m kernel cerebro bigrama
"""
from __future__ import annotations

import math
import random
from collections import Counter
from pathlib import Path

NOMES = Path(__file__).with_name("nomes.txt")
BORDA = "."  # marca o começo e o fim de cada palavra


class Bigrama:
    def __init__(self, palavras: list[str], suavizacao: float = 0.1):
        self.letras = sorted({c for p in palavras for c in p} | {BORDA})
        pares = Counter()
        for palavra in palavras:
            marcada = BORDA + palavra + BORDA
            pares.update(zip(marcada, marcada[1:]))
        # probabilidades[a][b] = P(b vem depois de a); a suavização evita probabilidade zero
        self.probabilidades = {}
        for a in self.letras:
            total = sum(pares[(a, b)] + suavizacao for b in self.letras)
            self.probabilidades[a] = {b: (pares[(a, b)] + suavizacao) / total for b in self.letras}

    def perda(self, palavras: list[str]) -> float:
        """Média de -log(probabilidade) por letra: quanto menor, menos surpreso o modelo fica."""
        soma, n = 0.0, 0
        for palavra in palavras:
            marcada = BORDA + palavra + BORDA
            for a, b in zip(marcada, marcada[1:]):
                if a in self.probabilidades and b in self.probabilidades[a]:
                    soma -= math.log(self.probabilidades[a][b])
                    n += 1
        return soma / max(n, 1)

    def gerar(self, sorteio: random.Random | None = None, maximo: int = 20) -> str:
        sorteio = sorteio or random
        letra, saida = BORDA, []
        while len(saida) < maximo:
            opcoes = self.probabilidades[letra]
            letra = sorteio.choices(list(opcoes), weights=list(opcoes.values()))[0]
            if letra == BORDA:
                break
            saida.append(letra)
        return "".join(saida)


def carregar_palavras(arquivo: Path = NOMES) -> list[str]:
    linhas = arquivo.read_text(encoding="utf-8").splitlines()
    return [l.strip().lower() for l in linhas if l.strip() and not l.startswith("#")]


def demonstrar(quantos: int = 15, semente: int = 7) -> float:
    palavras = carregar_palavras()
    sorteio = random.Random(semente)
    sorteio.shuffle(palavras)
    corte = int(len(palavras) * 0.9)
    treino, teste = palavras[:corte], palavras[corte:]
    modelo = Bigrama(treino)
    acaso = math.log(len(modelo.letras))
    print(f"{len(treino)} nomes de treino, {len(modelo.letras)} símbolos")
    print(f"perda no treino {modelo.perda(treino):.3f} | no teste {modelo.perda(teste):.3f} "
          f"| chutando ao acaso seria {acaso:.3f}")
    print("nomes inventados:", ", ".join(modelo.gerar(sorteio).capitalize() for _ in range(quantos)))
    return modelo.perda(teste)
