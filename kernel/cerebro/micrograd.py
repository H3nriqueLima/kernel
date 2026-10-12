"""Micrograd: backpropagation com números soltos.

Baseado no micrograd do Andrej Karpathy (série "Neural Networks: Zero to Hero").
Cada ``Valor`` guarda um número, o gradiente dele e como ele nasceu. Fazer
contas com ``Valor`` monta um grafo; ``retropropagar`` anda nesse grafo de trás
para frente aplicando a regra da cadeia.

O portão da Fase 0 é você conseguir explicar cada linha de ``_volta`` abaixo.

    python -m kernel cerebro micrograd
"""
from __future__ import annotations

import math
import random


class Valor:
    def __init__(self, dado: float, _filhos=(), _op: str = ""):
        self.dado = dado
        self.grad = 0.0            # d(saída final)/d(este valor)
        self._volta = lambda: None  # como repassar o gradiente para os filhos
        self._filhos = set(_filhos)
        self._op = _op

    def __repr__(self) -> str:
        return f"Valor(dado={self.dado:.4f}, grad={self.grad:.4f})"

    def __add__(self, outro):
        outro = outro if isinstance(outro, Valor) else Valor(outro)
        saida = Valor(self.dado + outro.dado, (self, outro), "+")

        def _volta():
            # a soma só distribui: d(a+b)/da = 1 e d(a+b)/db = 1
            self.grad += saida.grad
            outro.grad += saida.grad
        saida._volta = _volta
        return saida

    def __mul__(self, outro):
        outro = outro if isinstance(outro, Valor) else Valor(outro)
        saida = Valor(self.dado * outro.dado, (self, outro), "*")

        def _volta():
            # d(a*b)/da = b e d(a*b)/db = a
            self.grad += outro.dado * saida.grad
            outro.grad += self.dado * saida.grad
        saida._volta = _volta
        return saida

    def __pow__(self, expoente: float):
        saida = Valor(self.dado ** expoente, (self,), f"**{expoente}")

        def _volta():
            self.grad += expoente * self.dado ** (expoente - 1) * saida.grad
        saida._volta = _volta
        return saida

    def tanh(self):
        t = math.tanh(self.dado)
        saida = Valor(t, (self,), "tanh")

        def _volta():
            self.grad += (1 - t * t) * saida.grad
        saida._volta = _volta
        return saida

    def relu(self):
        saida = Valor(max(0.0, self.dado), (self,), "relu")

        def _volta():
            self.grad += (saida.dado > 0) * saida.grad
        saida._volta = _volta
        return saida

    def exp(self):
        e = math.exp(self.dado)
        saida = Valor(e, (self,), "exp")

        def _volta():
            self.grad += e * saida.grad
        saida._volta = _volta
        return saida

    def log(self):
        saida = Valor(math.log(self.dado), (self,), "log")

        def _volta():
            self.grad += saida.grad / self.dado
        saida._volta = _volta
        return saida

    def retropropagar(self) -> None:
        """Calcula o gradiente de todo o grafo em relação a este valor."""
        ordem, vistos = [], set()

        def visitar(v):  # ordenação topológica: um nó só entra depois dos seus filhos
            if v not in vistos:
                vistos.add(v)
                for filho in v._filhos:
                    visitar(filho)
                ordem.append(v)
        visitar(self)
        self.grad = 1.0
        for v in reversed(ordem):
            v._volta()

    def __neg__(self): return self * -1
    def __radd__(self, outro): return self + outro
    def __sub__(self, outro): return self + (-outro)
    def __rsub__(self, outro): return outro + (-self)
    def __rmul__(self, outro): return self * outro
    def __truediv__(self, outro): return self * outro ** -1
    def __rtruediv__(self, outro): return outro * self ** -1


class Neuronio:
    def __init__(self, entradas: int, linear: bool = False):
        self.pesos = [Valor(random.uniform(-1, 1)) for _ in range(entradas)]
        self.vies = Valor(0.0)
        self.linear = linear

    def __call__(self, x):
        soma = sum((p * xi for p, xi in zip(self.pesos, x)), self.vies)
        return soma if self.linear else soma.tanh()

    def parametros(self):
        return self.pesos + [self.vies]


class Camada:
    def __init__(self, entradas: int, saidas: int, linear: bool = False):
        self.neuronios = [Neuronio(entradas, linear) for _ in range(saidas)]

    def __call__(self, x):
        saidas = [n(x) for n in self.neuronios]
        return saidas[0] if len(saidas) == 1 else saidas

    def parametros(self):
        return [p for n in self.neuronios for p in n.parametros()]


class MLP:
    """Perceptron de várias camadas: ``MLP(2, [8, 8, 1])``."""

    def __init__(self, entradas: int, tamanhos: list[int]):
        dims = [entradas] + tamanhos
        self.camadas = [Camada(dims[i], dims[i + 1], linear=(i == len(tamanhos) - 1))
                        for i in range(len(tamanhos))]

    def __call__(self, x):
        for camada in self.camadas:
            x = camada(x)
        return x

    def parametros(self):
        return [p for c in self.camadas for p in c.parametros()]


def demonstrar(passos: int = 200, taxa: float = 0.1, semente: int = 7) -> float:
    """Treina um MLP para aprender o XOR, o problema que um neurônio sozinho não resolve."""
    random.seed(semente)
    entradas = [[0.0, 0.0], [0.0, 1.0], [1.0, 0.0], [1.0, 1.0]]
    alvos = [-1.0, 1.0, 1.0, -1.0]
    rede = MLP(2, [4, 4, 1])
    print(f"rede com {len(rede.parametros())} parâmetros")
    perda = None
    for passo in range(1, passos + 1):
        previsoes = [rede(x).tanh() for x in entradas]
        perda = sum(((p - a) ** 2 for p, a in zip(previsoes, alvos)), Valor(0.0))
        for p in rede.parametros():
            p.grad = 0.0
        perda.retropropagar()
        for p in rede.parametros():
            p.dado -= taxa * p.grad  # gradiente descendente: um passo contra o gradiente
        if passo == 1 or passo % 25 == 0:
            print(f"passo {passo:3d}  perda {perda.dado:.4f}")
    for x, a in zip(entradas, alvos):
        print(f"  {x} -> {rede(x).tanh().dado:+.3f}  (alvo {a:+.0f})")
    return perda.dado
