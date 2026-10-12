"""BM25: a fórmula que dá nota a uma memória para uma busca.

Para cada termo da busca que aparece na memória, somamos

    idf(termo) * tf * (k1 + 1) / (tf + k1 * (1 - b + b * tamanho / tamanho_medio))

- ``tf`` é quantas vezes o termo aparece na memória. Mais vezes, mais pontos,
  mas com retorno decrescente (``k1`` controla a rapidez com que satura).
- ``idf`` vale muito para termos raros e quase nada para os comuns.
- ``b`` desconta memórias compridas, que acertam termos só por terem muito texto.
"""
from __future__ import annotations

import math

K1 = 1.5
B = 0.75


def idf(total_de_memorias: int, memorias_com_o_termo: int) -> float:
    n, df = total_de_memorias, memorias_com_o_termo
    return math.log(1 + (n - df + 0.5) / (df + 0.5))


def pontuacao(tf: int, tamanho: int, tamanho_medio: float, idf_do_termo: float,
              k1: float = K1, b: float = B) -> float:
    desconto = 1 - b + b * tamanho / (tamanho_medio or 1.0)
    return idf_do_termo * tf * (k1 + 1) / (tf + k1 * desconto)
