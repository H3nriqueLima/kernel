"""Tom e marcas de período: o que o PSOLA precisa saber sobre uma gravação.

O PSOLA corta a voz em "grãos" de dois períodos, um para cada vibração das cordas
vocais, e depois os reespaça. Para isso é preciso saber, amostra a amostra, onde
cada vibração acontece. São dois passos:

1. ``tom``: a cada 5 ms, medir a frequência da voz pela autocorrelação (um som
   periódico se parece consigo mesmo deslocado de um período).
2. ``marcas``: dentro de cada trecho com voz, pôr uma marca no pico de cada
   período, andando de pico em pico. Onde não há voz (s, f, silêncio), as marcas
   vão de 5 em 5 ms, só para o som poder ser picado do mesmo jeito.
"""
from __future__ import annotations

import numpy as np

SALTO = 0.005            # segundos entre duas medidas do tom
JANELA = 0.040           # janela da autocorrelação
TOM_MINIMO, TOM_MAXIMO = 110.0, 420.0   # faixa de uma voz feminina (em Hz)
CLAREZA = 0.45           # autocorrelação mínima para dizer que há voz


def tom(som: np.ndarray, taxa: int, minimo: float = TOM_MINIMO, maximo: float = TOM_MAXIMO) -> np.ndarray:
    """A frequência da voz a cada 5 ms (0 onde não há voz)."""
    salto, janela = int(taxa * SALTO), int(taxa * JANELA)
    if len(som) < janela:
        return np.zeros(0)
    quadros = 1 + (len(som) - janela) // salto
    indices = np.arange(janela)[None, :] + salto * np.arange(quadros)[:, None]
    hann = np.hanning(janela)
    pedacos = som[indices].astype(np.float64)
    pedacos = (pedacos - pedacos.mean(axis=1, keepdims=True)) * hann
    n = 1 << (2 * janela - 1).bit_length()
    correlacao = np.fft.irfft(np.abs(np.fft.rfft(pedacos, n)) ** 2, n)[:, :janela]
    # a janela de Hann "encolhe" a correlação nos atrasos longos; dividir pela correlação da janela desfaz isso
    da_janela = np.fft.irfft(np.abs(np.fft.rfft(hann, n)) ** 2, n)[:janela]
    energia = correlacao[:, 0].copy()
    correlacao = correlacao / (energia[:, None] + 1e-12) / np.maximum(da_janela / da_janela[0], 0.05)
    perto, longe = int(taxa / maximo), min(int(taxa / minimo), janela - 1)
    faixa = correlacao[:, perto:longe]
    # entre picos parecidos fica o de período mais curto (evita cair uma oitava abaixo)
    atrasos = np.arange(perto, longe)
    melhor = np.argmax(faixa - 0.06 * np.log2(atrasos / perto)[None, :], axis=1)
    clareza = faixa[np.arange(quadros), melhor]
    # refina o pico com uma parábola pelos vizinhos
    a = faixa[np.arange(quadros), np.clip(melhor - 1, 0, faixa.shape[1] - 1)]
    c = faixa[np.arange(quadros), np.clip(melhor + 1, 0, faixa.shape[1] - 1)]
    curvatura = a - 2 * clareza + c
    desvio = np.where(np.abs(curvatura) > 1e-9, 0.5 * (a - c) / np.where(np.abs(curvatura) > 1e-9, curvatura, 1.0), 0.0)
    frequencia = taxa / (perto + melhor + np.clip(desvio, -0.5, 0.5))
    forte = energia > 0.003 * np.percentile(energia, 95)
    frequencia[~((clareza > CLAREZA) & forte)] = 0.0
    return _limpar(frequencia)


def _limpar(f0: np.ndarray) -> np.ndarray:
    """Tira saltos de oitava isolados e ilhas de 1 ou 2 quadros."""
    f0 = f0.copy()
    com_voz = f0 > 0
    if com_voz.sum() < 5:
        return np.zeros_like(f0)
    for i in range(1, len(f0) - 1):  # mediana de 3 só onde há voz dos dois lados
        if f0[i - 1] > 0 and f0[i] > 0 and f0[i + 1] > 0:
            mediana = sorted((f0[i - 1], f0[i], f0[i + 1]))[1]
            if abs(np.log2(f0[i] / mediana)) > 0.35:
                f0[i] = mediana
    # ilhas curtas de voz no meio do silêncio (e buracos curtos no meio da voz)
    inicio = 0
    while inicio < len(f0):
        fim = inicio
        while fim < len(f0) and (f0[fim] > 0) == (f0[inicio] > 0):
            fim += 1
        if fim - inicio <= 2 and 0 < inicio and fim < len(f0):
            f0[inicio:fim] = 0.5 * (f0[inicio - 1] + f0[fim]) if f0[inicio] == 0 and f0[inicio - 1] > 0 and f0[fim] > 0 else 0.0
        inicio = fim
    return f0


def marcas(som: np.ndarray, taxa: int, f0: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Devolve (posições das marcas em amostras, verdadeiro onde a marca é de voz)."""
    if f0 is None:
        f0 = tom(som, taxa)
    salto = int(taxa * SALTO)
    meio_da_janela = int(taxa * JANELA) // 2
    sem_voz = int(taxa * SALTO)
    # suaviza para ficar só a ondulação do período (some o detalhe dos formantes)
    largura = max(3, int(taxa / 900))
    liso = np.convolve(som.astype(np.float64), np.hanning(largura) / np.hanning(largura).sum(), mode="same")
    if -liso.min() > liso.max():
        liso = -liso  # usa o lado em que os picos são mais fortes

    def periodo_em(amostra: int) -> float:
        quadro = int(np.clip((amostra - meio_da_janela) / salto, 0, len(f0) - 1))
        return taxa / f0[quadro] if f0[quadro] > 0 else 0.0

    posicoes: list[int] = []
    de_voz: list[bool] = []
    quadro = 0
    while quadro < len(f0):
        fim = quadro
        while fim < len(f0) and (f0[fim] > 0) == (f0[quadro] > 0):
            fim += 1
        a = quadro * salto + (meio_da_janela if quadro else 0)
        b = min(len(som), fim * salto + meio_da_janela) if fim < len(f0) else len(som)
        if f0[quadro] > 0 and b - a > 2 * taxa / TOM_MAXIMO:
            # começa no pico mais alto do trecho e anda de período em período para os dois lados
            semente = a + int(np.argmax(liso[a:b]))
            trecho = [semente]
            for sentido in (1, -1):
                atual = semente
                while True:
                    periodo = periodo_em(atual) or taxa / 200.0
                    alvo = atual + sentido * periodo
                    perto, longe = int(alvo - 0.25 * periodo), int(alvo + 0.25 * periodo) + 1
                    if perto < a or longe > b:
                        break
                    atual = perto + int(np.argmax(liso[perto:longe]))
                    trecho.append(atual)
            trecho.sort()
            posicoes += trecho
            de_voz += [True] * len(trecho)
        else:
            inicio = posicoes[-1] + sem_voz if posicoes else a + sem_voz // 2
            passos = list(range(inicio, b, sem_voz))
            posicoes += passos
            de_voz += [False] * len(passos)
        quadro = fim
    ordem = np.argsort(posicoes, kind="stable")
    posicoes_ = np.asarray(posicoes, dtype=np.int64)[ordem]
    de_voz_ = np.asarray(de_voz, dtype=bool)[ordem]
    manter = np.concatenate([[True], np.diff(posicoes_) > taxa / (2 * TOM_MAXIMO)])  # marcas coladas: fica a primeira
    return posicoes_[manter], de_voz_[manter]
