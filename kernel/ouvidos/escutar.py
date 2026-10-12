"""Ficar ouvindo o microfone e avisar quando a palavra de ativação aparece.

O microfone entrega blocos de 0,1 s. Guardamos sempre o último segundo e, a
cada bloco, perguntamos à rede: "esse segundo é a palavra?". O ``Detector``
evita disparos bobos: exige duas respostas positivas seguidas e descansa uns
segundos depois de disparar. O som é analisado na RAM e descartado; nada é
gravado em disco.
"""
from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

import numpy as np

from .audio import AMOSTRAS, TAXA, caracteristicas, volume
from .modelo import RedeDeAtivacao
from .treinar import MODELO

BLOCO = TAXA // 10       # 0,1 s
PORTAO = 0.004           # abaixo desse volume nem consultamos a rede


class Detector:
    """A regra de disparo, separada do microfone para poder ser testada."""

    def __init__(self, limiar: float, seguidas: int = 2, descanso: float = 2.0):
        self.limiar, self.seguidas, self.descanso = limiar, seguidas, descanso
        self._contagem = 0
        self._ultimo_disparo = -1e9

    def avaliar(self, probabilidade: float, agora: float) -> bool:
        if agora - self._ultimo_disparo < self.descanso:
            return False
        self._contagem = self._contagem + 1 if probabilidade >= self.limiar else 0
        if self._contagem >= self.seguidas:
            self._contagem = 0
            self._ultimo_disparo = agora
            return True
        return False


class Ouvidos:
    def __init__(self, rede: RedeDeAtivacao, limiar: float, ao_ouvir, microfone: int | None = None):
        self.rede = rede
        self.detector = Detector(limiar)
        self.ao_ouvir = ao_ouvir
        self.microfone = microfone
        self._fila: queue.Queue = queue.Queue(maxsize=50)
        self._segundo = np.zeros(AMOSTRAS, dtype=np.float32)
        self._parar = threading.Event()
        self._fluxo = None
        self._thread = None

    def processar(self, bloco: np.ndarray, agora: float) -> bool:
        """Junta o bloco ao último segundo e decide se a palavra foi dita."""
        self._segundo = np.concatenate([self._segundo[len(bloco):], bloco])
        if volume(self._segundo) < PORTAO:
            return False
        probabilidade = float(self.rede.prever(caracteristicas(self._segundo))[0])
        if self.detector.avaliar(probabilidade, agora):
            self.ao_ouvir(probabilidade)
            return True
        return False

    def _trabalhar(self) -> None:
        while not self._parar.is_set():
            try:
                bloco = self._fila.get(timeout=0.5)
            except queue.Empty:
                continue
            self.processar(bloco, time.monotonic())

    def _chegou_som(self, entrada, _quadros, _tempo, _estado) -> None:
        try:
            self._fila.put_nowait(entrada[:, 0].copy())
        except queue.Full:
            pass  # CPU ocupada: melhor perder um bloco do que travar o áudio

    def iniciar(self) -> None:
        import sounddevice as sd

        self._fluxo = sd.InputStream(samplerate=TAXA, channels=1, dtype="float32", blocksize=BLOCO,
                                     device=self.microfone, callback=self._chegou_som)
        self._fluxo.start()
        self._thread = threading.Thread(target=self._trabalhar, name="ouvidos", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        if self._fluxo:
            self._fluxo.stop()
            self._fluxo.close()
            self._fluxo = None


def iniciar(cfg, ao_ouvir) -> tuple[Ouvidos | None, str]:
    """Liga os ouvidos se houver modelo treinado e microfone. Devolve (ouvidos, motivo se não ligou)."""
    if not cfg.ouvidos.ativo:
        return None, "desligados na configuração"
    arquivo = Path(cfg.pasta("ouvidos")) / MODELO
    if not arquivo.exists():
        return None, "sem modelo de ativação treinado"
    try:
        ouvidos = Ouvidos(RedeDeAtivacao.carregar(arquivo), cfg.ouvidos.limiar, ao_ouvir,
                          None if cfg.ouvidos.microfone < 0 else cfg.ouvidos.microfone)
        ouvidos.iniciar()
        return ouvidos, ""
    except Exception as erro:  # sem sounddevice, sem microfone, microfone ocupado...
        return None, f"não consegui abrir o microfone ({erro})"
