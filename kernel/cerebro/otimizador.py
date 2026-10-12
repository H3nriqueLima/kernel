"""AdamW escrito à mão.

O gradiente descendente puro dá o mesmo tamanho de passo para todo peso. O Adam
guarda, para cada peso, duas médias móveis:

- ``m``: a média dos gradientes (para onde ele vem apontando);
- ``v``: a média dos gradientes ao quadrado (o quanto ele costuma variar).

O passo é ``m / sqrt(v)``: pesos com gradiente estável andam mais, pesos com
gradiente barulhento andam menos. O "W" é o decaimento de peso aplicado direto
no peso, fora dessas médias.

Só operações básicas (multiplicar, somar, raiz), que funcionam no DirectML.
"""
from __future__ import annotations

import torch


class AdamW:
    def __init__(self, parametros, betas=(0.9, 0.95), eps: float = 1e-8, decaimento: float = 0.1):
        self.parametros = [p for p in parametros if p.requires_grad]
        self.beta1, self.beta2 = betas
        self.eps = eps
        self.decaimento = decaimento
        self.m = [torch.zeros_like(p) for p in self.parametros]
        self.v = [torch.zeros_like(p) for p in self.parametros]
        self.passos = 0

    @torch.no_grad()
    def passo(self, taxa: float) -> None:
        self.passos += 1
        # No começo m e v estão puxados para zero; estas correções desfazem isso.
        correcao1 = 1 - self.beta1 ** self.passos
        correcao2 = 1 - self.beta2 ** self.passos
        for p, m, v in zip(self.parametros, self.m, self.v):
            if p.grad is None:
                continue
            g = p.grad
            m.mul_(self.beta1).add_(g * (1 - self.beta1))
            v.mul_(self.beta2).add_(g * g * (1 - self.beta2))
            if p.dim() >= 2:  # decaimento só nas matrizes, não em vieses e ganhos
                p.mul_(1 - taxa * self.decaimento)
            p.sub_(taxa * (m / correcao1) / ((v / correcao2).sqrt() + self.eps))

    def zerar(self) -> None:
        for p in self.parametros:
            p.grad = None

    @torch.no_grad()
    def cortar_gradiente(self, maximo: float) -> float:
        """Se a norma do gradiente passar de ``maximo``, encolhe todos na mesma proporção."""
        # soma no dispositivo e traz um número só para a CPU (cada ida e volta à GPU custa caro)
        total = float(sum((p.grad * p.grad).sum() for p in self.parametros if p.grad is not None)) ** 0.5
        if total > maximo:
            for p in self.parametros:
                if p.grad is not None:
                    p.grad.mul_(maximo / total)
        return total

    def estado(self) -> dict:
        return {"passos": self.passos, "m": [m.cpu() for m in self.m], "v": [v.cpu() for v in self.v]}

    def carregar_estado(self, estado: dict) -> None:
        self.passos = estado["passos"]
        for alvo, origem in zip(self.m, estado["m"]):
            alvo.copy_(origem.to(alvo.device))
        for alvo, origem in zip(self.v, estado["v"]):
            alvo.copy_(origem.to(alvo.device))
