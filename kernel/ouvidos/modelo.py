"""A rede da palavra de ativação: um MLP pequeno em NumPy, com backpropagation à mão.

É o ``micrograd.py`` em versão de matrizes. A ida calcula a probabilidade de o
som ser a palavra; a volta aplica a regra da cadeia camada por camada, de trás
para frente, e o Adam ajusta os pesos.

Por ser só NumPy, fica ligada o tempo todo na CPU gastando quase nada.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


def sigmoide(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


class RedeDeAtivacao:
    def __init__(self, entradas: int, ocultas: tuple[int, ...] = (64, 32), semente: int = 0):
        sorteio = np.random.default_rng(semente)
        tamanhos = (entradas, *ocultas, 1)
        # inicialização de He: desvio sqrt(2 / entradas), boa para ReLU
        self.pesos = [sorteio.normal(0, np.sqrt(2 / a), (a, b)).astype(np.float32)
                      for a, b in zip(tamanhos, tamanhos[1:])]
        self.vieses = [np.zeros(b, dtype=np.float32) for b in tamanhos[1:]]
        self.media = np.zeros(entradas, dtype=np.float32)   # para padronizar a entrada
        self.desvio = np.ones(entradas, dtype=np.float32)
        self.limiar = 0.85

    # ------------------------------------------------------------------- ida
    def _ida(self, X: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
        ativacoes = [(X - self.media) / self.desvio]
        for W, b in zip(self.pesos[:-1], self.vieses[:-1]):
            ativacoes.append(np.maximum(0, ativacoes[-1] @ W + b))  # ReLU
        p = sigmoide(ativacoes[-1] @ self.pesos[-1] + self.vieses[-1])[:, 0]
        return p, ativacoes

    def prever(self, X: np.ndarray) -> np.ndarray:
        """Probabilidade de cada linha de X ser a palavra de ativação."""
        return self._ida(np.atleast_2d(X).astype(np.float32))[0]

    # ----------------------------------------------------------------- volta
    def _volta(self, p: np.ndarray, y: np.ndarray, ativacoes: list[np.ndarray]):
        """Gradientes da entropia cruzada binária em relação a cada peso e viés."""
        n = len(y)
        dZ = ((p - y) / n)[:, None]  # sigmoide + entropia cruzada: a derivada é só (p - y)
        grad_pesos, grad_vieses = [], []
        for camada in range(len(self.pesos) - 1, -1, -1):
            grad_pesos.append(ativacoes[camada].T @ dZ)
            grad_vieses.append(dZ.sum(axis=0))
            if camada:
                dA = dZ @ self.pesos[camada].T
                dZ = dA * (ativacoes[camada] > 0)  # a ReLU só deixa passar onde estava ligada
        return grad_pesos[::-1], grad_vieses[::-1]

    # ---------------------------------------------------------------- treino
    def treinar(self, X: np.ndarray, y: np.ndarray, epocas: int = 40, lote: int = 64,
                taxa: float = 1e-3, decaimento: float = 1e-4, semente: int = 0, ao_progredir=None) -> float:
        X, y = X.astype(np.float32), y.astype(np.float32)
        self.media = X.mean(axis=0)
        self.desvio = X.std(axis=0) + 1e-6
        sorteio = np.random.default_rng(semente)
        parametros = self.pesos + self.vieses
        m = [np.zeros_like(p) for p in parametros]
        v = [np.zeros_like(p) for p in parametros]
        beta1, beta2, passo, perda = 0.9, 0.999, 0, 0.0
        for epoca in range(1, epocas + 1):
            ordem = sorteio.permutation(len(X))
            perdas = []
            for inicio in range(0, len(X), lote):
                idx = ordem[inicio:inicio + lote]
                p, ativacoes = self._ida(X[idx])
                perdas.append(-np.mean(y[idx] * np.log(p + 1e-7) + (1 - y[idx]) * np.log(1 - p + 1e-7)))
                grad_pesos, grad_vieses = self._volta(p, y[idx], ativacoes)
                gradientes = [g + decaimento * W for g, W in zip(grad_pesos, self.pesos)] + grad_vieses
                passo += 1
                for i, g in enumerate(gradientes):  # Adam, o mesmo de cerebro/otimizador.py
                    m[i] = beta1 * m[i] + (1 - beta1) * g
                    v[i] = beta2 * v[i] + (1 - beta2) * g * g
                    parametros[i] -= taxa * (m[i] / (1 - beta1 ** passo)) / (np.sqrt(v[i] / (1 - beta2 ** passo)) + 1e-8)
            perda = float(np.mean(perdas))
            if ao_progredir:
                ao_progredir(epoca, perda)
        return perda

    # --------------------------------------------------------------- arquivo
    def salvar(self, arquivo: Path) -> None:
        dados = {f"W{i}": W for i, W in enumerate(self.pesos)}
        dados.update({f"b{i}": b for i, b in enumerate(self.vieses)})
        np.savez(arquivo, media=self.media, desvio=self.desvio, limiar=self.limiar, **dados)

    @classmethod
    def carregar(cls, arquivo: Path) -> "RedeDeAtivacao":
        with np.load(arquivo) as dados:
            camadas = len([nome for nome in dados.files if nome.startswith("W")])
            rede = cls.__new__(cls)
            rede.pesos = [dados[f"W{i}"] for i in range(camadas)]
            rede.vieses = [dados[f"b{i}"] for i in range(camadas)]
            rede.media, rede.desvio = dados["media"], dados["desvio"]
            rede.limiar = float(dados["limiar"])
        return rede
