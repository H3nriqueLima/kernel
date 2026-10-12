"""O cérebro no dia a dia: o mesmo GPT de ``gpt.py``, refeito só com NumPy.

O serviço não precisa carregar o PyTorch (centenas de MB de RAM) para conversar:
os pesos treinados são exportados para ``modelo.npz`` e as contas da rede são
repetidas aqui com matrizes do NumPy. É a "inferência própria" do plano.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from .tokenizador import Tokenizador

MODELO = "modelo.npz"
TOKENIZADOR = "tokenizador.json"


def exportar(modelo, arquivo: Path) -> None:
    """Grava os pesos de um GPT do PyTorch num .npz que este módulo sabe ler."""
    pesos = {nome: p.detach().cpu().numpy().astype(np.float32) for nome, p in modelo.state_dict().items()}
    temporario = Path(arquivo).with_suffix(".tmp.npz")
    np.savez(temporario, _config=np.array(json.dumps(modelo.configuracao())), **pesos)
    temporario.replace(arquivo)


def _norma(x, ganho, vies):
    media = x.mean(-1, keepdims=True)
    variancia = ((x - media) ** 2).mean(-1, keepdims=True)
    return ganho * (x - media) / np.sqrt(variancia + 1e-5) + vies


def _gelu(x):
    return 0.5 * x * (1.0 + np.tanh(0.7978845608 * (x + 0.044715 * x * x * x)))


def _softmax(x):
    e = np.exp(x - x.max(-1, keepdims=True))
    return e / e.sum(-1, keepdims=True)


class CerebroNumpy:
    def __init__(self, pesos: dict[str, np.ndarray], cfg: dict, tokenizador: Tokenizador):
        self.p = pesos
        self.cfg = cfg
        self.tokenizador = tokenizador
        self.parametros = int(sum(v.size for v in pesos.values()))
        self.descricao = (f"mini GPT de {self.parametros / 1e6:.1f} milhões de parâmetros "
                          f"({cfg['camadas']} camadas, contexto {cfg['contexto']})")
        self._sorteio = np.random.default_rng()

    def logits(self, ids: list[int]) -> np.ndarray:
        """Notas para o próximo token em cada posição: matriz (len(ids), vocab)."""
        p, T, C, H = self.p, len(ids), self.cfg["dim"], self.cfg["cabecas"]
        x = p["emb_token"][ids] + p["emb_posicao"][:T]
        mascara = np.triu(np.full((T, T), -1e9, dtype=np.float32), k=1)
        for i in range(self.cfg["camadas"]):
            b = f"blocos.{i}."
            h = _norma(x, p[b + "norma1.ganho"], p[b + "norma1.vies"])
            qkv = h @ p[b + "atencao.qkv.peso"].T + p[b + "atencao.qkv.vies"]
            # (T, C) -> (cabeças, T, C / cabeças)
            q, k, v = (parte.reshape(T, H, C // H).transpose(1, 0, 2) for parte in np.split(qkv, 3, axis=-1))
            pesos = _softmax(q @ k.transpose(0, 2, 1) / math.sqrt(C // H) + mascara)
            y = (pesos @ v).transpose(1, 0, 2).reshape(T, C)
            x = x + y @ p[b + "atencao.saida.peso"].T + p[b + "atencao.saida.vies"]
            h = _norma(x, p[b + "norma2.ganho"], p[b + "norma2.vies"])
            h = _gelu(h @ p[b + "sobe.peso"].T + p[b + "sobe.vies"])
            x = x + h @ p[b + "desce.peso"].T + p[b + "desce.vies"]
        x = _norma(x, p["norma_final.ganho"], p["norma_final.vies"])
        return x @ p["emb_token"].T

    def gerar(self, ids: list[int], quantos: int, temperatura: float = 0.8, top_k: int = 40) -> list[int]:
        ids = list(ids)
        for _ in range(quantos):
            notas = self.logits(ids[-self.cfg["contexto"]:])[-1].astype(np.float64) / max(temperatura, 1e-6)
            if top_k and top_k < notas.size:
                corte = np.partition(notas, -top_k)[-top_k]
                notas[notas < corte] = -np.inf
            proximo = int(self._sorteio.choice(notas.size, p=_softmax(notas)))
            if proximo == self.tokenizador.id_fim:
                break
            ids.append(proximo)
        return ids

    def continuar(self, texto: str, quantos: int = 60, temperatura: float = 0.8, top_k: int = 40) -> str:
        """Devolve só o que o cérebro escreveu depois de ``texto``."""
        entrada = self.tokenizador.codificar(texto) or [self.tokenizador.id_fim]
        saida = self.gerar(entrada, quantos, temperatura, top_k)
        return self.tokenizador.decodificar(saida[len(entrada):])

    def responder(self, texto: str, quantos: int = 60, temperatura: float = 0.8, top_k: int = 40) -> str:
        """Continuação aparada na última frase completa (o cérebro da v0.1 completa texto, não dialoga)."""
        bruto = self.continuar(texto, quantos, temperatura, top_k).strip()
        fim = max(bruto.rfind("."), bruto.rfind("!"), bruto.rfind("?"))
        return bruto[:fim + 1] if fim > 20 else bruto


def carregar_de(pasta: Path) -> CerebroNumpy | None:
    modelo, tokenizador = Path(pasta) / MODELO, Path(pasta) / TOKENIZADOR
    if not (modelo.exists() and tokenizador.exists()):
        return None
    with np.load(modelo) as dados:
        cfg = json.loads(str(dados["_config"]))
        pesos = {nome: dados[nome] for nome in dados.files if nome != "_config"}
    return CerebroNumpy(pesos, cfg, Tokenizador.carregar(tokenizador))


def carregar(cfg) -> CerebroNumpy | None:
    """O cérebro treinado em ``dados/cerebro``, ou None se ainda não existe."""
    return carregar_de(cfg.pasta("cerebro"))
