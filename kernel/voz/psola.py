"""TD-PSOLA: mudar a duração e o tom de uma gravação sem mudar o timbre.

PSOLA quer dizer "sobrepor e somar em sincronia com o tom". A ideia:

1. A gravação é picada em **grãos**: cada grão é um pedacinho de dois períodos,
   centrado numa marca de período e amaciado por uma janela (zero nas pontas).
2. Para falar **mais agudo**, os mesmos grãos são recolocados mais perto um do
   outro; **mais grave**, mais longe. O desenho de cada grão (que carrega o
   timbre, os formantes) não muda: só muda de quanto em quanto tempo ele se repete.
3. Para falar **mais devagar**, alguns grãos são usados duas vezes; **mais
   rápido**, alguns são pulados.

Como tudo é feito grão a grão, colar pedaços de gravações diferentes (os
difones) é a mesma operação: na emenda, o último grão de um pedaço se sobrepõe
ao primeiro do seguinte, e a soma faz a transição em um período.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PESO_MINIMO = 0.35  # onde as janelas somam menos que isso, não se compensa (evita amplificar restos)


@dataclass
class Pedaco:
    """Um trecho de uma gravação, com a duração que ele deve ter na fala final."""
    som: np.ndarray        # a gravação inteira de onde o trecho sai
    marcas: np.ndarray     # todas as marcas de período dessa gravação (amostras)
    de_voz: np.ndarray     # para cada marca: é um período de voz?
    inicio: int
    fim: int
    duracao: float | None = None            # segundos na saída (None = a duração original)
    ganho: tuple[float, float] = (1.0, 1.0)  # volume no começo e no fim do trecho


def _janela(esquerda: int, direita: int) -> np.ndarray:
    """Janela de Hann assimétrica: sobe em ``esquerda`` amostras, vale 1 na marca, desce em ``direita``."""
    sobe = np.hanning(2 * esquerda + 1)[:esquerda]
    desce = np.hanning(2 * direita + 1)[direita:]
    return np.concatenate([sobe, desce])


def sintetizar(pedacos: list[Pedaco], taxa: int, tom_alvo: np.ndarray | None = None,
               passo_do_tom: float = 0.005) -> np.ndarray:
    """Cola os pedaços, cada um com a sua duração-alvo, impondo o tom ``tom_alvo``.

    ``tom_alvo`` é a frequência desejada (Hz) a cada ``passo_do_tom`` segundos da saída.
    Sem ele, cada grão mantém o espaçamento original (só a duração muda).
    """
    duracoes = [(p.fim - p.inicio) if p.duracao is None else p.duracao * taxa for p in pedacos]
    total = int(sum(duracoes)) + 1
    maior_periodo = int(taxa / 60)
    saida = np.zeros(total + 2 * maior_periodo)
    peso = np.zeros(total + 2 * maior_periodo)
    t = 0.0           # onde vai o próximo grão, em amostras da saída
    comeco = 0.0      # onde começa o pedaço atual na saída
    primeiro = True
    for pedaco, duracao in zip(pedacos, duracoes):
        fim_na_saida = comeco + duracao
        a, b = (int(x) for x in np.searchsorted(pedaco.marcas, np.array([pedaco.inicio, pedaco.fim], dtype=pedaco.marcas.dtype)))
        if b <= a or duracao < 1:  # trecho curto demais para ter uma marca: só anda o relógio
            comeco = fim_na_saida
            t = max(t, comeco)
            continue
        marcas = pedaco.marcas
        fonte_por_saida = (pedaco.fim - pedaco.inicio) / duracao
        if primeiro:  # o primeiro grão cai onde a primeira marca cairia, não no instante zero
            t = comeco + (marcas[a] - pedaco.inicio) / fonte_por_saida
            primeiro = False
        anterior, repeticoes = -1, 0
        while t < fim_na_saida:
            fonte = pedaco.inicio + (t - comeco) * fonte_por_saida
            # (a posição vai como inteiro: procurar um número quebrado numa lista de inteiros faria o NumPy
            # converter a lista toda a cada grão, e a fala ficaria dez vezes mais lenta)
            i = min(max(int(np.searchsorted(marcas, int(fonte))), a), b - 1)
            if i > a and abs(marcas[i - 1] - fonte) < abs(marcas[i] - fonte):
                i -= 1
            m = int(marcas[i])
            esquerda = int(min(m - marcas[i - 1], maior_periodo)) if i > 0 else maior_periodo // 2
            direita = int(min(marcas[i + 1] - m, maior_periodo)) if i + 1 < len(marcas) else maior_periodo // 2
            esquerda, direita = max(esquerda, 2), max(direita, 2)
            if m - esquerda >= 0 and m + direita + 1 <= len(pedaco.som):
                janela = _janela(esquerda, direita)
                grao = pedaco.som[m - esquerda:m + direita + 1] * janela
                repeticoes = repeticoes + 1 if i == anterior else 0
                if repeticoes % 2 == 1 and not pedaco.de_voz[i]:
                    grao = grao[::-1]  # chiado repetido igual vira zumbido: alterna o sentido
                avanco = (t - comeco) / duracao
                grao = grao * (pedaco.ganho[0] + (pedaco.ganho[1] - pedaco.ganho[0]) * avanco)
                onde = int(round(t)) + maior_periodo - esquerda
                saida[onde:onde + len(grao)] += grao
                peso[onde:onde + len(grao)] += janela
            anterior = i
            if pedaco.de_voz[i] and tom_alvo is not None and len(tom_alvo):
                alvo = tom_alvo[min(int(t / taxa / passo_do_tom), len(tom_alvo) - 1)]
                periodo = taxa / alvo if alvo > 0 else float(direita)
            else:
                periodo = float(direita)  # sem voz (ou sem tom-alvo): o passo original
            t += max(periodo, 8.0)
        comeco = fim_na_saida
    saida /= np.maximum(peso, PESO_MINIMO)
    return saida[maior_periodo:maior_periodo + total].astype(np.float32)


def modificar(som: np.ndarray, taxa: int, marcas: np.ndarray, de_voz: np.ndarray, duracao: float = 1.0,
              tom: float = 1.0, f0: np.ndarray | None = None) -> np.ndarray:
    """PSOLA numa gravação só: ``duracao`` e ``tom`` são fatores (1.5 = 50% mais longo ou mais agudo)."""
    alvo = None
    if tom != 1.0 and f0 is not None and len(f0):
        # o tom original, esticado para o tempo da saída e multiplicado pelo fator
        preenchido = f0.copy()
        com_voz = np.where(f0 > 0)[0]
        if len(com_voz):
            preenchido = np.interp(np.arange(len(f0)), com_voz, f0[com_voz])
        n = int(len(f0) * duracao)
        alvo = np.interp(np.arange(n) / duracao, np.arange(len(f0)), preenchido) * tom
    pedaco = Pedaco(som, marcas, de_voz, 0, len(som), duracao=len(som) / taxa * duracao)
    return sintetizar([pedaco], taxa, alvo)
