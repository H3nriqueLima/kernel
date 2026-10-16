"""Linhas de base de n-gramas: o que dá para prever só contando vizinhos.

Uma perda de 3,0 é boa ou ruim? Depende de com o que se compara. Aqui ficam três
modelos que não entendem nada, só contam:

- unigrama: a frequência de cada token, sem olhar o contexto;
- bigrama: a chance do token dado o anterior;
- trigrama: dado os dois anteriores.

Os dois últimos usam a suavização de Kneser-Ney interpolada (desconto D = 0,75),
o jeito clássico de não dar probabilidade zero ao que nunca apareceu: parte da
probabilidade vem do contexto mais curto. Se o GPT ficar perto do trigrama, ele
aprendeu pouco além de "que palavra costuma vir depois desta".
"""
from __future__ import annotations

import math

import numpy as np

DESCONTO = 0.75


class Ngramas:
    def __init__(self, ids: np.ndarray, vocab: int):
        ids = np.asarray(ids, dtype=np.int64)
        V = self.V = vocab
        self.n_treino = len(ids)
        self.unigrama = (np.bincount(ids, minlength=V) + 1.0) / (len(ids) + V)   # com +1, nada tem chance zero

        # bigramas: chave v·V + w
        chaves2, c2 = np.unique(ids[:-1] * V + ids[1:], return_counts=True)
        self.chaves2, self.c2 = chaves2, c2.astype(np.float64)
        contexto2 = chaves2 // V
        self.c_v = np.bincount(contexto2, weights=self.c2, minlength=V)          # quantas vezes v foi contexto
        self.seguintes_v = np.bincount(contexto2, minlength=V).astype(np.float64)  # quantos w diferentes vieram depois de v
        anteriores_w = np.bincount(chaves2 % V, minlength=V).astype(np.float64)    # de quantos v diferentes w veio depois
        self.continuacao = (anteriores_w + 1.0) / (anteriores_w.sum() + V)         # a "unigrama" de Kneser-Ney

        # trigramas: chave (u·V + v)·V + w
        chaves3, c3 = np.unique((ids[:-2] * V + ids[1:-1]) * V + ids[2:], return_counts=True)
        self.chaves3, self.c3 = chaves3, c3.astype(np.float64)
        self.contextos3, inverso = np.unique(chaves3 // V, return_inverse=True)
        self.c_uv = np.bincount(inverso, weights=self.c3)
        self.seguintes_uv = np.bincount(inverso).astype(np.float64)

    @staticmethod
    def _procurar(ordenadas: np.ndarray, chaves: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(achou?, onde) de cada chave numa lista ordenada."""
        onde = np.clip(np.searchsorted(ordenadas, chaves), 0, len(ordenadas) - 1)
        return ordenadas[onde] == chaves, onde

    def _bigrama(self, v: np.ndarray, w: np.ndarray) -> np.ndarray:
        achou, onde = self._procurar(self.chaves2, v * self.V + w)
        c = np.where(achou, self.c2[onde], 0.0)
        cv = self.c_v[v]
        com_contexto = cv > 0
        cv_seguro = np.where(com_contexto, cv, 1.0)
        p = np.maximum(c - DESCONTO, 0) / cv_seguro + DESCONTO * self.seguintes_v[v] / cv_seguro * self.continuacao[w]
        return np.where(com_contexto, p, self.continuacao[w])

    def _trigrama(self, u: np.ndarray, v: np.ndarray, w: np.ndarray) -> np.ndarray:
        baixo = self._bigrama(v, w)
        achou_ctx, onde_ctx = self._procurar(self.contextos3, u * self.V + v)
        cuv = np.where(achou_ctx, self.c_uv[onde_ctx], 0.0)
        seguintes = np.where(achou_ctx, self.seguintes_uv[onde_ctx], 0.0)
        achou, onde = self._procurar(self.chaves3, (u * self.V + v) * self.V + w)
        c = np.where(achou, self.c3[onde], 0.0)
        cuv_seguro = np.where(cuv > 0, cuv, 1.0)
        p = np.maximum(c - DESCONTO, 0) / cuv_seguro + DESCONTO * seguintes / cuv_seguro * baixo
        return np.where(cuv > 0, p, baixo)

    def perdas(self, ids: np.ndarray) -> dict[str, float]:
        """Perda média (em nats por token) de cada modelo, prevendo cada token a partir do terceiro."""
        ids = np.asarray(ids, dtype=np.int64)
        u, v, w = ids[:-2], ids[1:-1], ids[2:]
        return {"unigrama": float(-np.log(self.unigrama[w]).mean()),
                "bigrama": float(-np.log(self._bigrama(v, w)).mean()),
                "trigrama": float(-np.log(self._trigrama(u, v, w)).mean())}


def perplexidade(perda: float) -> float:
    return math.exp(perda)
