"""Do som aos MFCC, passo a passo e à mão.

O microfone entrega 16 000 números por segundo. Uma rede pequena não aprende
direto disso, então resumimos:

1. Cortar o som em quadros de 25 ms, um a cada 10 ms.
2. Em cada quadro, a transformada de Fourier diz quanta energia há em cada frequência.
3. Juntar as frequências em 26 faixas na escala mel (finas nos graves, largas nos
   agudos, como o ouvido humano) e tirar o logaritmo.
4. Uma transformada do cosseno (DCT) compacta as 26 faixas em 13 coeficientes.

Um segundo de som vira uma tabela de 98 quadros x 13 números.
"""
from __future__ import annotations

import functools
import wave
from pathlib import Path

import numpy as np

TAXA = 16_000        # amostras por segundo
JANELA = 400         # 25 ms
SALTO = 160          # 10 ms
N_FFT = 512
N_MEL = 26
N_MFCC = 13
AMOSTRAS = TAXA      # o modelo sempre olha para 1 segundo
ENTRADAS = (1 + (AMOSTRAS - JANELA) // SALTO) * N_MFCC


def _hz_para_mel(hz):
    return 2595 * np.log10(1 + hz / 700)


def _mel_para_hz(mel):
    return 700 * (10 ** (mel / 2595) - 1)


@functools.lru_cache(maxsize=None)
def banco_mel() -> np.ndarray:
    """26 filtros triangulares: cada linha soma as frequências de uma faixa mel."""
    pontos = _mel_para_hz(np.linspace(_hz_para_mel(60), _hz_para_mel(TAXA / 2), N_MEL + 2))
    caixas = np.floor((N_FFT + 1) * pontos / TAXA).astype(int)
    banco = np.zeros((N_MEL, N_FFT // 2 + 1), dtype=np.float32)
    for m in range(N_MEL):
        esquerda, centro, direita = caixas[m], caixas[m + 1], caixas[m + 2]
        for k in range(esquerda, centro):
            banco[m, k] = (k - esquerda) / max(centro - esquerda, 1)
        for k in range(centro, direita):
            banco[m, k] = (direita - k) / max(direita - centro, 1)
    return banco


@functools.lru_cache(maxsize=None)
def matriz_dct() -> np.ndarray:
    n = np.arange(N_MEL)
    k = np.arange(N_MFCC)[:, None]
    return (np.cos(np.pi * k * (2 * n + 1) / (2 * N_MEL)) * np.sqrt(2 / N_MEL)).astype(np.float32)


def mfcc(sinal: np.ndarray) -> np.ndarray:
    """Sinal (float, -1 a 1) -> matriz (quadros, 13)."""
    sinal = sinal.astype(np.float32)
    sinal = np.append(sinal[:1], sinal[1:] - 0.97 * sinal[:-1])  # pré-ênfase: realça os agudos da fala
    quadros = 1 + (len(sinal) - JANELA) // SALTO
    indices = np.arange(JANELA)[None, :] + SALTO * np.arange(quadros)[:, None]
    janelas = sinal[indices] * np.hanning(JANELA).astype(np.float32)
    potencia = np.abs(np.fft.rfft(janelas, N_FFT)) ** 2 / N_FFT
    energia = np.log(potencia @ banco_mel().T + 1e-8)
    coeficientes = energia @ matriz_dct().T
    return coeficientes - coeficientes.mean(axis=0)  # tira a média: volume e microfone pesam menos


def caracteristicas(sinal: np.ndarray) -> np.ndarray:
    """1 segundo de som -> o vetor que entra na rede."""
    return mfcc(ajustar(sinal)).reshape(-1)


def ajustar(sinal: np.ndarray, amostras: int = AMOSTRAS) -> np.ndarray:
    """Corta ou completa com silêncio para ter exatamente ``amostras``."""
    if len(sinal) >= amostras:
        return sinal[:amostras]
    return np.concatenate([sinal, np.zeros(amostras - len(sinal), dtype=sinal.dtype)])


def recortar(sinal: np.ndarray, amostras: int = AMOSTRAS) -> np.ndarray:
    """O trecho de 1 s centrado na parte mais alta da gravação (onde está a palavra)."""
    if len(sinal) <= amostras:
        return ajustar(sinal, amostras)
    largura = int(0.4 * TAXA)
    energia = np.convolve(sinal.astype(np.float64) ** 2, np.ones(largura), mode="same")
    centro = int(np.argmax(energia))
    inicio = min(max(centro - amostras // 2, 0), len(sinal) - amostras)
    return sinal[inicio:inicio + amostras]


def volume(sinal: np.ndarray) -> float:
    """Raiz da média dos quadrados (RMS): quão alto está o som."""
    return float(np.sqrt(np.mean(sinal.astype(np.float64) ** 2))) if len(sinal) else 0.0


def ler_wav(arquivo: Path) -> np.ndarray:
    with wave.open(str(arquivo), "rb") as w:
        if w.getframerate() != TAXA or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{arquivo}: esperado WAV mono, 16 bits, {TAXA} Hz")
        bruto = w.readframes(w.getnframes())
    return np.frombuffer(bruto, dtype=np.int16).astype(np.float32) / 32768.0


def gravar_wav(arquivo: Path, sinal: np.ndarray) -> None:
    inteiro = (np.clip(sinal, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(arquivo), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes(inteiro.tobytes())
