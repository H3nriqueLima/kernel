"""Treino da palavra de ativação.

Duzentas gravações são pouco para uma rede, então cada uma vira várias
("aumento de dados"): a palavra um pouco mais cedo ou mais tarde, mais alta ou
mais baixa, com ruído do ambiente por cima. A avaliação é feita com gravações
que ficaram de fora do treino: é o único número que diz se ele vai acertar
no dia a dia.

    python -m kernel ouvidos treinar
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .audio import AMOSTRAS, ENTRADAS, TAXA, ajustar, caracteristicas, ler_wav, recortar
from .modelo import RedeDeAtivacao

TIPOS = ("positivo", "negativo", "ruido")
MODELO = "ativacao.npz"


def carregar_gravacoes(pasta: Path) -> dict[str, list[np.ndarray]]:
    return {tipo: [ler_wav(a) for a in sorted((Path(pasta) / tipo).glob("*.wav"))] for tipo in TIPOS}


def _fatias_de_ruido(ruidos: list[np.ndarray]) -> list[np.ndarray]:
    """Corta as gravações de ambiente em trechos de 1 s."""
    return [r[i:i + AMOSTRAS] for r in ruidos for i in range(0, len(r) - AMOSTRAS + 1, AMOSTRAS)]


def aumentar(sinal: np.ndarray, fundos: list[np.ndarray], sorteio: np.random.Generator) -> np.ndarray:
    """Uma variação de 1 s: deslocada, com outro volume e com ruído por cima."""
    sinal = ajustar(sinal)
    desloca = int(sorteio.integers(-int(0.15 * TAXA), int(0.15 * TAXA) + 1))
    variado = np.zeros_like(sinal)
    if desloca >= 0:
        variado[desloca:] = sinal[:AMOSTRAS - desloca]
    else:
        variado[:desloca] = sinal[-desloca:]
    variado = variado * sorteio.uniform(0.5, 1.5)
    if fundos and sorteio.random() < 0.7:
        variado = variado + fundos[int(sorteio.integers(len(fundos)))] * sorteio.uniform(0.2, 1.0)
    variado = variado + sorteio.normal(0, sorteio.uniform(0.0005, 0.004), AMOSTRAS)  # chiado do microfone
    return variado.astype(np.float32)


def montar(positivos, negativos, fundos, copias: int, sorteio) -> tuple[np.ndarray, np.ndarray]:
    X, y = [], []
    for sinal in positivos:
        centrado = recortar(sinal)
        X += [caracteristicas(aumentar(centrado, fundos, sorteio)) for _ in range(copias)]
        y += [1.0] * copias
    for sinal in negativos:
        centrado = recortar(sinal)
        X += [caracteristicas(aumentar(centrado, fundos, sorteio)) for _ in range(copias)]
        y += [0.0] * copias
    for fundo in fundos:  # o ambiente sozinho também é um "não"
        X.append(caracteristicas(aumentar(fundo, [], sorteio)))
        y.append(0.0)
    return np.array(X, dtype=np.float32).reshape(-1, ENTRADAS), np.array(y, dtype=np.float32)


def treinar(gravacoes: dict[str, list[np.ndarray]], copias: int = 20, epocas: int = 40,
            semente: int = 0, ao_progredir=None) -> tuple[RedeDeAtivacao, dict]:
    """Treina e avalia com 20% das gravações separadas. Devolve (rede, medidas)."""
    sorteio = np.random.default_rng(semente)
    positivos, negativos = list(gravacoes["positivo"]), list(gravacoes["negativo"])
    fundos = _fatias_de_ruido(gravacoes["ruido"])
    if len(positivos) < 10 or len(negativos) < 10:
        raise ValueError(f"poucas gravações: {len(positivos)} positivas e {len(negativos)} negativas "
                         "(grave pelo menos 10 de cada; o ideal é umas 100)")
    sorteio.shuffle(positivos)
    sorteio.shuffle(negativos)
    sorteio.shuffle(fundos)
    corte = lambda lista: max(1, len(lista) // 5)  # noqa: E731
    teste_pos, treino_pos = positivos[:corte(positivos)], positivos[corte(positivos):]
    teste_neg, treino_neg = negativos[:corte(negativos)], negativos[corte(negativos):]
    teste_fundo, treino_fundo = fundos[:len(fundos) // 5], fundos[len(fundos) // 5:]

    X, y = montar(treino_pos, treino_neg, treino_fundo, copias, sorteio)
    rede = RedeDeAtivacao(ENTRADAS, semente=semente)
    rede.treinar(X, y, epocas=epocas, semente=semente, ao_progredir=ao_progredir)

    X_teste, y_teste = montar(teste_pos, teste_neg, teste_fundo, 5, sorteio)
    p = rede.prever(X_teste)
    acima = p >= rede.limiar
    medidas = {
        "gravacoes": {"positivas": len(positivos), "negativas": len(negativos), "segundos_de_ruido": len(fundos)},
        "exemplos_de_treino": int(len(y)),
        "exemplos_de_teste": int(len(y_teste)),
        "acerto": float(np.mean(acima == (y_teste == 1))),
        "nao_ouviu": float(np.mean(~acima[y_teste == 1])),        # disse a palavra e ele não reagiu
        "alarme_falso": float(np.mean(acima[y_teste == 0])),      # reagiu sem você chamar
        "limiar": rede.limiar,
    }
    return rede, medidas
