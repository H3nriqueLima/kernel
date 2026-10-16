"""A interface estável do cérebro: carregar por configuração, gerar e pontuar.

O resto do sistema (o serviço, o protocolo, a linha de comando) fala com o cérebro só
por aqui e não precisa saber o tamanho dele, o motor que faz as contas nem onde ficam
os arquivos. Um cérebro é descrito por uma ``Especificacao`` (pesos, tokenizador, motor
e dispositivo) e oferece:

- ``gerar(texto, ...)``: continua um texto e devolve só o que ele escreveu;
- ``pontuar(ids)``: a perda (em nats) de cada token, dado o que veio antes, em janelas
  do contexto do modelo, sem sobreposição;
- ``info``: parâmetros, configuração e a impressão SHA-256 dos pesos.

Dois motores, com as mesmas contas (conferido em ``verificar``):

- ``"numpy"``: o do serviço, sem PyTorch, gerando um token por vez com a memória de
  chaves e valores;
- ``"torch"``: para pontuar muito texto de uma vez (o protocolo, na placa de vídeo).
  Gerar continua pelo NumPy, que é o que o serviço usa.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import inferencia
from .tokenizador import Tokenizador


@dataclass(frozen=True)
class Especificacao:
    pesos: Path
    tokenizador: Path
    motor: str = "numpy"       # "numpy" (o do serviço) ou "torch"
    dispositivo: str = "cpu"   # só no motor torch: "cpu", "directml" ou "auto"

    @classmethod
    def da_pasta(cls, pasta: Path, **opcoes) -> "Especificacao":
        pasta = Path(pasta)
        return cls(pasta / inferencia.MODELO, pasta / inferencia.TOKENIZADOR, **opcoes)

    @classmethod
    def da_configuracao(cls, cfg, **opcoes) -> "Especificacao":
        """O cérebro que a configuração indica: ``[cerebro] pesos`` (vazio = ``dados/cerebro/modelo.npz``)."""
        pasta = Path(cfg.pasta("cerebro"))
        pesos = getattr(getattr(cfg, "cerebro", None), "pesos", "") or ""
        return cls(Path(pesos) if pesos else pasta / inferencia.MODELO, pasta / inferencia.TOKENIZADOR, **opcoes)

    def existe(self) -> bool:
        return Path(self.pesos).exists() and Path(self.tokenizador).exists()


class Cerebro:
    def __init__(self, especificacao: Especificacao):
        self.especificacao = especificacao
        pesos = Path(especificacao.pesos)
        guardada = Path(str(pesos) + ".sha256")   # pesos de antes da v0.5.1 não têm impressão: valem como estão
        self.sha256 = inferencia._impressao(pesos)
        if guardada.exists() and guardada.read_text(encoding="ascii").strip() != self.sha256:
            raise inferencia.ModeloEstragado(f"{pesos.name} não confere com a impressão digital gravada no treino")
        with np.load(pesos) as dados:
            self.cfg = json.loads(str(dados["_config"]))
            matrizes = {nome: dados[nome] for nome in dados.files if nome != "_config"}
        self.tokenizador = Tokenizador.carregar(especificacao.tokenizador)
        self._numpy = inferencia.CerebroNumpy(matrizes, self.cfg, self.tokenizador)
        self._torch = None
        self._dispositivo = None
        if especificacao.motor == "torch":
            from .dispositivo import escolher
            from .pesos import gpt_de_npz
            if isinstance(especificacao.dispositivo, str):
                self._dispositivo, self.descricao_do_dispositivo = escolher(especificacao.dispositivo)
            else:   # um dispositivo do PyTorch já escolhido por quem chamou
                self._dispositivo, self.descricao_do_dispositivo = especificacao.dispositivo, str(especificacao.dispositivo)
            self._torch = gpt_de_npz(pesos, self._dispositivo)
        elif especificacao.motor != "numpy":
            raise ValueError(f"motor desconhecido: {especificacao.motor!r} (use numpy ou torch)")

    # ------------------------------------------------------------ o que ele é
    @property
    def parametros(self) -> int:
        return self._numpy.parametros

    @property
    def descricao(self) -> str:
        return self._numpy.descricao

    @property
    def info(self) -> dict:
        return {"parametros": self.parametros, "config": dict(self.cfg), "sha256": self.sha256,
                "motor": self.especificacao.motor, "pesos": Path(self.especificacao.pesos).name}

    # ------------------------------------------------------------ gerar
    def gerar_ids(self, ids: list[int], tokens: int = 60, temperatura: float = 0.8, top_k: int = 40,
                  top_p: float = 1.0, repeticao: float = 1.0, semente: int | None = None) -> list[int]:
        """Os ids de entrada mais os que ele escreveu (para no token de fim)."""
        if semente is not None:
            self._numpy._sorteio = np.random.default_rng(semente)
        return self._numpy.gerar(list(ids), tokens, temperatura, top_k, top_p, repeticao)

    def gerar(self, texto: str, tokens: int = 60, temperatura: float = 0.8, top_k: int = 40, top_p: float = 1.0,
              repeticao: float = 1.0, semente: int | None = None) -> str:
        """Só o que ele escreveu depois de ``texto``."""
        entrada = self.tokenizador.codificar(texto) or [self.tokenizador.id_fim]
        saida = self.gerar_ids(entrada, tokens, temperatura, top_k, top_p, repeticao, semente)
        return self.tokenizador.decodificar(saida[len(entrada):])

    def responder(self, texto: str, quantos: int = 60, temperatura: float = 0.8, top_k: int = 40) -> str:
        """A continuação que o serviço mostra (sem laço de repetição, aparada na última frase completa)."""
        return self._numpy.responder(texto, quantos, temperatura, top_k)

    def continuar(self, texto: str, quantos: int = 60, temperatura: float = 0.8, top_k: int = 40,
                  top_p: float = 1.0, repeticao: float = 1.0) -> str:
        return self._numpy.continuar(texto, quantos, temperatura, top_k, top_p, repeticao)

    def velocidade_de_geracao(self, tokens: int = 200, semente: int = 0) -> float:
        """Tokens por segundo gerando um por vez na CPU, do jeito que o serviço gera."""
        inicio = time.time()
        saida = self.gerar_ids(self.tokenizador.codificar("O Brasil é"), tokens, top_k=40, semente=semente)
        return (len(saida) - 3) / max(time.time() - inicio, 1e-9)

    # ------------------------------------------------------------ pontuar
    def pontuar(self, ids: np.ndarray, lote: int = 32) -> np.ndarray:
        """A perda de cada token, em janelas do contexto do modelo sem sobreposição: matriz (janelas, contexto).

        O token ``i`` de cada janela é previsto a partir dos ``i`` anteriores da mesma janela.
        """
        T = self.cfg["contexto"]
        n = (len(ids) - 1) // T
        entradas = np.asarray(ids[:n * T], dtype=np.int64).reshape(n, T)
        alvos = np.asarray(ids[1:n * T + 1], dtype=np.int64).reshape(n, T)
        if self._torch is None:   # motor numpy: uma janela por vez
            saida = np.empty((n, T))
            for i in range(n):
                notas = self._numpy.logits(entradas[i].tolist()).astype(np.float64)
                notas -= notas.max(-1, keepdims=True)
                log_chances = notas - np.log(np.exp(notas).sum(-1, keepdims=True))
                saida[i] = -log_chances[np.arange(T), alvos[i]]
            return saida
        import torch
        import torch.nn.functional as F

        partes = []
        with torch.no_grad():
            for i in range(0, n, lote):
                x = torch.from_numpy(entradas[i:i + lote]).to(self._dispositivo)
                y = torch.from_numpy(alvos[i:i + lote]).to(self._dispositivo)
                logits, _ = self._torch(x)
                perdas = F.cross_entropy(logits.reshape(-1, logits.size(-1)).float(), y.reshape(-1), reduction="none")
                partes.append(perdas.reshape(y.shape).double().cpu().numpy())
        return np.concatenate(partes) if partes else np.empty((0, T))

    def perda(self, ids: list[int]) -> float:
        """Perda média de uma sequência curta (até o contexto), pelo NumPy."""
        return self._numpy.perda(ids)


def carregar(especificacao: Especificacao) -> Cerebro:
    return Cerebro(especificacao)
