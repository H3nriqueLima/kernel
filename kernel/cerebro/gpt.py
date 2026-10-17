"""O mini GPT: um Transformer só de decodificador, camada por camada.

Nada de modelo pronto: cada camada abaixo é escrita com operações básicas
(multiplicar matrizes, somar, softmax). Do PyTorch usamos só os tensores e o
cálculo automático do gradiente, que você já escreveu à mão em ``micrograd.py``.

O caminho de um texto:

    ids -> embedding do token + embedding da posição
        -> N blocos [ atenção -> MLP ], cada um somando na "via residual"
        -> normalização final -> uma nota (logit) para cada token do vocabulário

``inferencia.py`` refaz exatamente estas contas em NumPy; um teste garante que
os dois dão o mesmo resultado.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class ConfigGPT:
    vocab: int = 4096
    contexto: int = 256   # quantos tokens ele enxerga para trás
    camadas: int = 6
    cabecas: int = 6
    dim: int = 192        # largura da via residual


# Tamanhos prontos. Parâmetros aproximados com vocabulário de 4096 (8192 no "pequeno"):
TAMANHOS = {
    "nano": dict(contexto=64, camadas=2, cabecas=2, dim=64),        # ~0,4 mi: testes de minutos
    "mini": dict(contexto=256, camadas=6, cabecas=6, dim=192),      # ~3,5 mi: primeira rodada (horas)
    "medio": dict(contexto=256, camadas=8, cabecas=8, dim=320),     # ~11 mi: o intermediário da Fase 2
    "pequeno": dict(contexto=256, camadas=8, cabecas=8, dim=384),   # ~16 mi (17 mi com vocabulário de 8192)
    "grande": dict(contexto=256, camadas=12, cabecas=8, dim=512),   # ~40 mi: o maior que a Fase 2 mede
}

# (lote, acumular) que cabem nos 4 GB da RX 570 com DirectML, medidos nesta máquina.
# O DirectML não reaproveita memória como o CUDA: o "mini" estoura com lote 24 e o
# "pequeno" com lote 8. Acumular gradiente compensa o lote pequeno.
# medidos em 16 e 17/10; o pequeno cabe com lote 8, mas no limite: com outros programas usando a placa faltou memória
LOTES = {"nano": (16, 2), "mini": (16, 2), "medio": (8, 4), "pequeno": (4, 8), "grande": (4, 8)}


def gelu(x):
    """GELU pela aproximação com tanh (a mesma do GPT-2)."""
    return 0.5 * x * (1.0 + torch.tanh(0.7978845608 * (x + 0.044715 * x * x * x)))


class Linear(nn.Module):
    def __init__(self, entrada: int, saida: int, desvio: float = 0.02):
        super().__init__()
        self.peso = nn.Parameter(torch.randn(saida, entrada) * desvio)
        self.vies = nn.Parameter(torch.zeros(saida))

    def forward(self, x):
        return x @ self.peso.t() + self.vies


class NormaDeCamada(nn.Module):
    """LayerNorm: deixa cada vetor com média 0 e variância 1, depois reescala."""

    def __init__(self, dim: int):
        super().__init__()
        self.ganho = nn.Parameter(torch.ones(dim))
        self.vies = nn.Parameter(torch.zeros(dim))

    def forward(self, x):
        media = x.mean(-1, keepdim=True)
        variancia = ((x - media) ** 2).mean(-1, keepdim=True)
        return self.ganho * (x - media) / torch.sqrt(variancia + 1e-5) + self.vies


class Atencao(nn.Module):
    """Autoatenção causal com várias cabeças: cada token olha para os anteriores."""

    def __init__(self, cfg: ConfigGPT):
        super().__init__()
        assert cfg.dim % cfg.cabecas == 0
        self.cabecas = cfg.cabecas
        self.qkv = Linear(cfg.dim, 3 * cfg.dim)  # consulta, chave e valor de uma vez
        self.saida = Linear(cfg.dim, cfg.dim, desvio=0.02 / math.sqrt(2 * cfg.camadas))
        # Máscara causal: -1e9 acima da diagonal impede olhar para o futuro.
        # (Somada, e não com masked_fill, porque o DirectML lida melhor com soma.)
        mascara = torch.triu(torch.full((cfg.contexto, cfg.contexto), -1e9), diagonal=1)
        self.register_buffer("mascara", mascara, persistent=False)

    def forward(self, x):
        B, T, C = x.shape
        q, k, v = self.qkv(x).split(C, dim=2)
        # (B, T, C) -> (B, cabeças, T, C / cabeças)
        q = q.view(B, T, self.cabecas, C // self.cabecas).transpose(1, 2)
        k = k.view(B, T, self.cabecas, C // self.cabecas).transpose(1, 2)
        v = v.view(B, T, self.cabecas, C // self.cabecas).transpose(1, 2)
        notas = q @ k.transpose(-2, -1) / math.sqrt(C // self.cabecas)
        pesos = torch.softmax(notas + self.mascara[:T, :T], dim=-1)
        y = (pesos @ v).transpose(1, 2).contiguous().view(B, T, C)
        return self.saida(y)


class Bloco(nn.Module):
    def __init__(self, cfg: ConfigGPT):
        super().__init__()
        self.norma1 = NormaDeCamada(cfg.dim)
        self.atencao = Atencao(cfg)
        self.norma2 = NormaDeCamada(cfg.dim)
        self.sobe = Linear(cfg.dim, 4 * cfg.dim)
        self.desce = Linear(4 * cfg.dim, cfg.dim, desvio=0.02 / math.sqrt(2 * cfg.camadas))

    def forward(self, x):
        x = x + self.atencao(self.norma1(x))                 # os tokens conversam entre si
        x = x + self.desce(gelu(self.sobe(self.norma2(x))))  # cada token pensa sozinho
        return x


class GPT(nn.Module):
    def __init__(self, cfg: ConfigGPT):
        super().__init__()
        self.cfg = cfg
        self.emb_token = nn.Parameter(torch.randn(cfg.vocab, cfg.dim) * 0.02)
        self.emb_posicao = nn.Parameter(torch.randn(cfg.contexto, cfg.dim) * 0.02)
        self.blocos = nn.ModuleList(Bloco(cfg) for _ in range(cfg.camadas))
        self.norma_final = NormaDeCamada(cfg.dim)

    def forward(self, ids, alvos=None):
        T = ids.shape[1]
        x = F.embedding(ids, self.emb_token) + self.emb_posicao[:T]
        for bloco in self.blocos:
            x = bloco(x)
        x = self.norma_final(x)
        logits = x @ self.emb_token.t()  # pesos amarrados: a saída reutiliza o embedding
        if alvos is None:
            return logits, None
        # Entropia cruzada: -log da probabilidade dada ao token certo. Usamos a função do
        # PyTorch porque a versão à mão (log_softmax + gather) não tem gradiente no DirectML.
        perda = F.cross_entropy(logits.reshape(-1, logits.size(-1)), alvos.reshape(-1))
        return logits, perda

    def numero_de_parametros(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def configuracao(self) -> dict:
        return asdict(self.cfg)

    @torch.no_grad()
    def gerar(self, ids: list[int], quantos: int, temperatura: float = 0.8, top_k: int = 40,
              parar_em: int | None = None) -> list[int]:
        """Continua a sequência um token por vez, sorteando entre os ``top_k`` mais prováveis."""
        dispositivo = self.emb_token.device
        ids = list(ids)
        for _ in range(quantos):
            janela = torch.tensor([ids[-self.cfg.contexto:]], dtype=torch.long).to(dispositivo)
            logits, _ = self(janela)
            ultimo = logits[0, -1].float().cpu() / max(temperatura, 1e-6)
            if top_k:
                corte = torch.topk(ultimo, min(top_k, ultimo.numel())).values[-1]
                ultimo[ultimo < corte] = -float("inf")
            proximo = int(torch.multinomial(torch.softmax(ultimo, dim=-1), 1))
            if proximo == parar_em:
                break
            ids.append(proximo)
        return ids


def criar(tamanho: str, vocab: int) -> GPT:
    return GPT(ConfigGPT(vocab=vocab, **TAMANHOS[tamanho]))
