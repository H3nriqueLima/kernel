"""Classificador de intenções: regressão softmax escrita à mão em NumPy.

O caminho de uma frase:

1. ``tracos``: a frase vira pedaços — palavras, pares de palavras e trechos de
   3 e 4 letras ("abre" e "abrir" compartilham "^ab" e "abr", por isso ele
   entende conjugações que nunca viu). As primeiras palavras pesam mais.
2. ``vetor``: cada pedaço cai numa de 4096 posições (hashing) e a frase vira um
   vetor de contagens com comprimento 1.
3. ``W`` e ``b``: uma única camada linear dá uma nota para cada intenção, e a
   softmax transforma as notas em probabilidades.

O treino é gradiente descendente puro. A derivada da perda (entropia cruzada)
em relação às notas é simplesmente ``P - Y``: o quanto cada probabilidade
passou do alvo. Todo o resto é regra da cadeia sobre ``Z = X @ W + b``.
"""
from __future__ import annotations

import re
import zlib
from pathlib import Path

import numpy as np

from ..memoria.texto import normalizar

INTENCOES = ("conversa", "abrir_programa", "listar_pasta", "anotar_lembrete", "consultar_memoria", "sobre_si",
             "pergunta", "procurar_arquivo", "sistema", "descobertas")
DIMENSAO = 4096
CONFIANCA_MINIMA = 0.5  # abaixo disso a frase é tratada como conversa
PALAVRAS_DO_COMECO = 5
PESO_DO_RESTO = 0.3
EXEMPLOS = Path(__file__).with_name("exemplos.txt")

_PALAVRA = re.compile(r"[a-z0-9]+")
_CAMINHO = re.compile(r'[A-Za-z]:[\\/][^"<>|?*\n]*')


def tracos(texto: str) -> list[tuple[str, float]]:
    """Os pedaços da frase, cada um com um peso."""
    # Um caminho como C:\Users\fulano\Downloads vira uma palavra só: importa que há um
    # caminho na frase, não os nomes das pastas (que só encheriam o vetor de ruído).
    texto = _CAMINHO.sub(" umcaminho ", texto)
    palavras = _PALAVRA.findall(normalizar(texto))
    saida = []
    for i, palavra in enumerate(palavras):
        # O começo da frase diz que tipo de pedido é ("me lembra de...", "abre o...");
        # o resto costuma ser o assunto, e o assunto não pode decidir a intenção.
        peso = 1.0 if i < PALAVRAS_DO_COMECO else PESO_DO_RESTO
        saida.append(("p:" + palavra, peso))
        if i == 0:
            saida.append(("ini:" + palavra, 1.0))
        marcada = f"^{palavra}$"
        for n in (3, 4):
            saida += [("c:" + marcada[j:j + n], peso) for j in range(len(marcada) - n + 1)]
        if i:
            saida.append((f"b:{palavras[i - 1]}_{palavra}", peso))
    return saida


def vetor(texto: str) -> np.ndarray:
    x = np.zeros(DIMENSAO, dtype=np.float32)
    for traco, peso in tracos(texto):
        x[zlib.crc32(traco.encode("utf-8")) % DIMENSAO] += peso
    norma = np.linalg.norm(x)
    return x / norma if norma else x


def softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=-1, keepdims=True)  # evita estouro no exp
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)


class Classificador:
    def __init__(self, pesos: np.ndarray, vies: np.ndarray, intencoes=INTENCOES):
        self.pesos = pesos
        self.vies = vies
        self.intencoes = tuple(intencoes)

    def probabilidades(self, texto: str) -> dict[str, float]:
        p = softmax(vetor(texto) @ self.pesos + self.vies)
        return {nome: float(v) for nome, v in zip(self.intencoes, p)}

    def classificar(self, texto: str) -> tuple[str, float]:
        """Devolve (intenção, confiança). Na dúvida, é conversa."""
        probs = self.probabilidades(texto)
        intencao = max(probs, key=probs.get)
        if probs[intencao] < CONFIANCA_MINIMA:
            return "conversa", probs[intencao]
        return intencao, probs[intencao]

    def salvar(self, arquivo: Path) -> None:
        np.savez(arquivo, pesos=self.pesos, vies=self.vies, intencoes=np.array(self.intencoes))

    @classmethod
    def carregar(cls, arquivo: Path) -> "Classificador":
        with np.load(arquivo) as dados:
            return cls(dados["pesos"], dados["vies"], [str(i) for i in dados["intencoes"]])


def treinar(exemplos: list[tuple[str, str]], epocas: int = 1500, taxa: float = 4.0,
            decaimento: float = 1e-4, ao_progredir=None) -> Classificador:
    X = np.stack([vetor(texto) for texto, _ in exemplos])
    y = np.array([INTENCOES.index(intencao) for _, intencao in exemplos])
    n, classes = len(exemplos), len(INTENCOES)
    Y = np.zeros((n, classes), dtype=np.float32)
    Y[np.arange(n), y] = 1.0
    W = np.zeros((DIMENSAO, classes), dtype=np.float32)
    b = np.zeros(classes, dtype=np.float32)
    for epoca in range(1, epocas + 1):
        P = softmax(X @ W + b)                         # ida
        dZ = (P - Y) / n                               # volta: derivada da perda nas notas
        W -= taxa * (X.T @ dZ + decaimento * W)        # regra da cadeia + decaimento de peso
        b -= taxa * dZ.sum(axis=0)
        if ao_progredir and (epoca % 250 == 0 or epoca == 1):
            perda = float(-np.log(P[np.arange(n), y] + 1e-9).mean())
            ao_progredir(epoca, perda, float((P.argmax(axis=1) == y).mean()))
    return Classificador(W, b)


def carregar_exemplos(*arquivos: Path) -> list[tuple[str, str]]:
    exemplos, intencao = [], None
    for arquivo in arquivos:
        if not arquivo.exists():
            continue
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            if linha.startswith("[") and linha.endswith("]"):
                intencao = linha[1:-1]
                if intencao not in INTENCOES:
                    raise ValueError(f"{arquivo.name}: intenção desconhecida [{intencao}]")
            elif intencao is None:
                raise ValueError(f"{arquivo.name}: frase antes de qualquer [intenção]: {linha}")
            else:
                exemplos.append((linha, intencao))
    return exemplos


def arquivos_de_exemplos(cfg) -> tuple[Path, Path]:
    """Os exemplos do projeto e os que você ensinou depois (ficam em dados/)."""
    return EXEMPLOS, cfg.pasta("comandos") / "exemplos_extras.txt"


def garantir(cfg) -> Classificador:
    """Carrega o classificador salvo; treina de novo se os exemplos mudaram."""
    modelo = cfg.pasta("comandos") / "modelo.npz"
    fontes = [a for a in arquivos_de_exemplos(cfg) if a.exists()]
    if modelo.exists() and all(modelo.stat().st_mtime >= a.stat().st_mtime for a in fontes):
        salvo = Classificador.carregar(modelo)
        if salvo.intencoes == INTENCOES:
            return salvo
    classificador = treinar(carregar_exemplos(*fontes))
    classificador.salvar(modelo)
    return classificador
