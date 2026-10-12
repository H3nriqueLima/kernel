"""Dos fonemas à onda sonora: um sintetizador de formantes escrito à mão.

A fala humana tem duas partes, e o sintetizador imita as duas:

- **A fonte.** As cordas vocais vibram numa frequência (o tom, uns 110 Hz numa
  voz grave) e produzem essa nota mais todos os seus múltiplos (harmônicos).
  Aqui a fonte é uma soma de senos. Para os chiados (s, f, ch) a fonte é ruído.
- **O filtro.** A boca reforça algumas faixas de frequência, os *formantes*.
  Cada vogal é um desenho diferente dos três primeiros formantes: "i" tem o
  primeiro baixo e o segundo alto; "a" tem o primeiro alto. Mudar de um som
  para outro é deslizar os formantes, e esse deslizar é metade da fala.

O texto vira uma tabela com um valor de cada parâmetro a cada 5 ms (formantes,
força da voz, força e cor do chiado, tom). Depois é só "tocar" a tabela:
cada harmônico entra com a força que a boca daria àquela frequência.
"""
from __future__ import annotations

import io
import wave
from dataclasses import dataclass, replace

import numpy as np

from .fonemas import texto_para_fonemas

TAXA = 24_000            # amostras por segundo
QUADRO = 120             # amostras por quadro de parâmetros (5 ms)
MS = TAXA / QUADRO / 1000  # quadros por milissegundo
JANELA = 4 * QUADRO      # janela do ruído (20 ms)
VOZ_ATE = 5200.0         # acima disso as cordas vocais quase não têm energia
F4, B4, F5, B5 = 3500.0, 220.0, 4500.0, 300.0
NARIZ, BANDA_NASAL = 0.5, 130.0   # quanto o nariz colore um som nasal


@dataclass(frozen=True)
class Som:
    f1: float
    f2: float
    f3: float
    ms: float              # duração
    voz: float = 0.0       # força das cordas vocais
    ruido: float = 0.0     # força do chiado feito na boca (s, f, ch, estouro do p/t/k)
    centro: float = 0.0    # onde o chiado é mais forte (Hz)
    largura: float = 1.0   # largura da faixa do chiado (Hz)
    sopro: float = 0.0     # ar passando pela boca aberta (o "rr", um h)
    nasal: float = 0.0     # quanto do som sai pelo nariz


VOGAIS = {
    "a": Som(760, 1300, 2550, 80, voz=1.0),
    "A": Som(600, 1350, 2500, 70, voz=0.9),
    "E": Som(560, 1800, 2550, 80, voz=1.0),
    "e": Som(400, 2000, 2600, 78, voz=1.0),
    "i": Som(290, 2250, 3000, 72, voz=0.95),
    "O": Som(580, 950, 2500, 80, voz=1.0),
    "o": Som(420, 850, 2450, 78, voz=1.0),
    "u": Som(320, 800, 2350, 72, voz=0.95),
    "an": Som(520, 1300, 2500, 85, voz=0.95, nasal=1.0),
    "en": Som(420, 1900, 2600, 85, voz=0.95, nasal=1.0),
    "in": Som(300, 2200, 2950, 80, voz=0.9, nasal=1.0),
    "on": Som(430, 850, 2450, 85, voz=0.95, nasal=1.0),
    "un": Som(320, 800, 2350, 80, voz=0.9, nasal=1.0),
}
SONS = {
    **VOGAIS,
    "j": Som(280, 2200, 2950, 55, voz=0.75),
    "w": Som(320, 750, 2300, 55, voz=0.75),
    "jn": Som(280, 2200, 2950, 55, voz=0.7, nasal=1.0),
    "wn": Som(320, 750, 2300, 55, voz=0.7, nasal=1.0),
    "m": Som(250, 1000, 2300, 65, voz=0.45, nasal=1.0),
    "n": Som(250, 1500, 2500, 60, voz=0.45, nasal=1.0),
    "N": Som(250, 2100, 2800, 75, voz=0.45, nasal=1.0),
    "mc": Som(250, 1000, 2300, 38, voz=0.4, nasal=1.0),
    "nc": Som(250, 1500, 2500, 38, voz=0.4, nasal=1.0),
    "l": Som(360, 1250, 2700, 60, voz=0.65),
    "L": Som(300, 1950, 2750, 75, voz=0.6),
    "r": Som(450, 1450, 2500, 28, voz=0.28),
    "R": Som(550, 1300, 2500, 85, sopro=0.55),
    "f": Som(300, 1100, 2400, 95, ruido=0.25, centro=5500, largura=6000),
    "v": Som(280, 1100, 2400, 65, voz=0.4, ruido=0.14, centro=5000, largura=6000),
    "s": Som(300, 1700, 2600, 105, ruido=0.85, centro=6800, largura=3500),
    "z": Som(280, 1700, 2600, 75, voz=0.4, ruido=0.4, centro=6800, largura=3500),
    "S": Som(300, 2000, 2700, 110, ruido=0.9, centro=3400, largura=2600),
    "Z": Som(280, 2000, 2700, 80, voz=0.4, ruido=0.42, centro=3400, largura=2600),
}
# Oclusivas: (fechamento, estouro). No fechamento a boca está tapada; o estouro é um chiado curtíssimo.
OCLUSIVAS = {
    "p": (Som(250, 900, 2300, 75), Som(250, 900, 2300, 10, ruido=0.45, centro=1200, largura=2500)),
    "t": (Som(250, 1700, 2600, 70), Som(250, 1700, 2600, 12, ruido=0.7, centro=4800, largura=3500)),
    "k": (Som(250, 1500, 2400, 70), Som(250, 1500, 2400, 16, ruido=0.7, centro=2000, largura=1400)),
    "b": (Som(220, 900, 2300, 65, voz=0.16), Som(250, 900, 2300, 8, voz=0.2, ruido=0.22, centro=1200, largura=2500)),
    "d": (Som(220, 1700, 2600, 60, voz=0.16), Som(250, 1700, 2600, 8, voz=0.2, ruido=0.35, centro=4800, largura=3500)),
    "g": (Som(220, 1500, 2400, 60, voz=0.16), Som(250, 1500, 2400, 10, voz=0.2, ruido=0.35, centro=2000, largura=1400)),
}
PAUSAS = {",": 170, ".": 330, "?": 330}
_DA_FRENTE = {"e", "E", "i", "in", "en", "j", "jn"}


@dataclass
class Trecho:
    som: Som
    quadros: int
    tonico: bool = False
    vogal: bool = False
    pausa: str = ""
    fonema: int = -1       # posição, na lista de fonemas, do som que gerou este trecho


def _trechos(fonemas: list[str], velocidade: float) -> list[Trecho]:
    """Cada fonema vira um ou dois trechos com duração em quadros."""
    limpos = [f.lstrip("'") for f in fonemas]

    def proxima_vogal(i: int) -> Som | None:
        for nome in limpos[i + 1:i + 4]:
            if nome in VOGAIS or nome in ("j", "w"):
                return SONS[nome]
            if nome in PAUSAS:
                break
        return None

    saida: list[Trecho] = []
    for i, (bruto, nome) in enumerate(zip(fonemas, limpos)):
        tonico = bruto.startswith("'")
        if nome in PAUSAS:
            anterior = saida[-1].som if saida else SONS["A"]
            saida.append(Trecho(replace(anterior, voz=0, ruido=0, sopro=0, ms=PAUSAS[nome]),
                                round(PAUSAS[nome] * MS), pausa=nome, fonema=i))
            continue
        partes: list[Som]
        if nome in ("tS", "dZ"):
            fecha, _ = OCLUSIVAS["t" if nome == "tS" else "d"]
            chiado = SONS["S" if nome == "tS" else "Z"]
            partes = [replace(fecha, f2=2000, ms=fecha.ms * 0.8), replace(chiado, ms=chiado.ms * 0.6)]
        elif nome in OCLUSIVAS:
            partes = list(OCLUSIVAS[nome])
            if nome in "kg":  # o "k" se encosta onde a vogal seguinte vai estar
                seguinte = limpos[i + 1] if i + 1 < len(limpos) else ""
                f2 = 2300 if seguinte in _DA_FRENTE else 1200
                partes = [replace(p, f2=f2, centro=p.centro and (2600 if seguinte in _DA_FRENTE else 1500))
                          for p in partes]
        elif nome == "R":  # o sopro toma a forma da vogal que vem depois
            vogal = proxima_vogal(i)
            base = SONS["R"]
            partes = [replace(base, f1=vogal.f1, f2=vogal.f2, f3=vogal.f3) if vogal else base]
        elif nome in SONS:
            partes = [SONS[nome]]
        else:
            continue
        for parte in partes:
            ms = parte.ms * (1.45 if tonico and nome in VOGAIS else 1.0) / velocidade
            saida.append(Trecho(parte, max(1, round(ms * MS)), tonico, nome in VOGAIS, fonema=i))
    # a última vogal antes de cada pausa se alonga, como na fala
    for i, trecho in enumerate(saida):
        if trecho.pausa:
            for anterior in reversed(saida[max(0, i - 4):i]):
                if anterior.vogal:
                    anterior.quadros = round(anterior.quadros * 1.3)
                    break
    return saida


def _suavizar(x: np.ndarray, quadros: int) -> np.ndarray:
    """Média móvel com janela de Hann: transforma degraus em deslizes."""
    if quadros < 3:
        return x
    janela = np.hanning(quadros + 2)[1:-1]
    cheio = np.concatenate([np.full(quadros, x[0]), x, np.full(quadros, x[-1])])
    return np.convolve(cheio, janela / janela.sum(), mode="same")[quadros:-quadros]


def _tabela(trechos: list[Trecho], tom: float, escala: float = 1.0) -> dict:
    """A tabela de parâmetros: um valor de cada coisa a cada 5 ms."""
    total = sum(t.quadros for t in trechos)
    t = {nome: np.zeros(total) for nome in ("f1", "f2", "f3", "voz", "ruido", "centro", "largura", "sopro",
                                             "nasal", "tom")}
    pos = 0
    inicio_da_frase = 0
    for i, trecho in enumerate(trechos):
        fim = pos + trecho.quadros
        s = trecho.som
        for nome in ("f1", "f2", "f3", "voz", "ruido", "sopro", "nasal"):
            t[nome][pos:fim] = getattr(s, nome)
        t["centro"][pos:fim] = s.centro or 3000.0
        t["largura"][pos:fim] = s.largura if s.ruido else 3000.0
        t["tom"][pos:fim] = 1.0 + (0.16 if trecho.tonico and trecho.vogal else 0.0)
        if trecho.pausa:
            # entoação da frase que acabou: desce do começo ao fim; a pergunta sobe no final
            n = pos - inicio_da_frase
            if n > 0:
                queda = np.linspace(1.08, 0.90, n)
                cauda = min(n, round(260 * MS))
                final = {"?": 1.38, ",": 1.03, ".": 0.80}[trecho.pausa]
                queda[-cauda:] *= np.linspace(1.0, final / 0.90, cauda)
                t["tom"][inicio_da_frase:pos] *= queda
                t["tom"][pos:fim] = t["tom"][pos - 1]  # o silêncio guarda o tom final (senão a suavização o desfaz)
            inicio_da_frase = fim
        pos = fim
    # os formantes deslizam devagar (a língua tem peso); as forças mudam mais rápido
    for nome in ("f1", "f2", "f3"):
        t[nome] = _suavizar(t[nome], 11) * escala
    t["escala"] = escala  # boca menor = formantes mais altos = voz mais "fina"
    for nome, quadros in (("voz", 5), ("sopro", 5), ("nasal", 7), ("ruido", 3), ("centro", 3), ("largura", 3)):
        t[nome] = _suavizar(t[nome], quadros)
    t["tom"] = _suavizar(t["tom"], 13) * tom
    return t


def _boca(freq: np.ndarray, f1, f2, f3, nasal, escala: float = 1.0) -> np.ndarray:
    """O ganho que a boca dá a cada frequência: o produto de cinco ressonâncias."""
    ganho = np.ones_like(freq, dtype=np.float64)
    f2q = freq * freq
    for centro, banda in ((f1, 70.0 + BANDA_NASAL * nasal), (f2, 100.0), (f3, 160.0), (F4 * escala, B4), (F5 * escala, B5)):
        c2 = centro * centro
        ganho *= c2 / np.sqrt((c2 - f2q) ** 2 + (banda * freq) ** 2)
    # som nasal: ganha um reforço grave (o nariz ressoa perto de 250 Hz)
    nariz = 250.0 ** 2 / np.sqrt((250.0 ** 2 - f2q) ** 2 + (120.0 * freq) ** 2)
    return ganho * (1.0 + NARIZ * nasal * (nariz - 1.0).clip(min=-0.9))


def _voz(t: dict[str, np.ndarray], sorteio: np.random.Generator) -> np.ndarray:
    """As cordas vocais: soma de harmônicos, cada um com a força que a boca lhe dá."""
    quadros = len(t["tom"])
    n = quadros * QUADRO
    centros = (np.arange(quadros) + 0.5) * QUADRO
    amostras = np.arange(n)
    segundos = amostras / TAXA
    tom = np.interp(amostras, centros, t["tom"])
    tom *= 1.0 + 0.008 * np.sin(2 * np.pi * 5.3 * segundos) + 0.004 * np.sin(2 * np.pi * 11.1 * segundos + 1.0)
    fase = 2 * np.pi * np.cumsum(tom) / TAXA
    sinal = np.zeros(n)
    if not t["voz"].any():
        return sinal
    for k in range(1, int(VOZ_ATE / max(t["tom"].min(), 50.0)) + 1):
        freq = k * t["tom"]
        forca = _boca(freq, t["f1"], t["f2"], t["f3"], t["nasal"], t["escala"]) * t["voz"] / k ** 1.15
        forca[freq > VOZ_ATE] = 0.0
        if not forca.any():
            continue
        sinal += np.interp(amostras, centros, forca) * np.sin(k * fase)
    return sinal


def _chiado(t: dict[str, np.ndarray], sorteio: np.random.Generator) -> np.ndarray:
    """Os ruídos: a cada quadro, um espectro com a cor certa e fase sorteada."""
    quadros = len(t["tom"])
    freq = np.fft.rfftfreq(JANELA, 1 / TAXA)[None, :]
    centro, largura = t["centro"][:, None], t["largura"][:, None]
    faixa = np.exp(-0.5 * ((freq - centro) / (largura / 2.355)) ** 2)
    boca = _boca(np.broadcast_to(freq, (quadros, freq.shape[1])), t["f1"][:, None], t["f2"][:, None],
                 t["f3"][:, None], t["nasal"][:, None], t["escala"])
    sopro = (t["sopro"] + 0.05 * t["voz"])[:, None] * boca * freq / (freq + 900.0)  # um pouco de ar em toda vogal
    espectro = t["ruido"][:, None] * faixa * 1.35 + sopro
    fases = np.exp(2j * np.pi * sorteio.random(espectro.shape))
    pedacos = np.fft.irfft(espectro * fases, JANELA, axis=1) * np.hanning(JANELA) * 18.0
    sinal = np.zeros(quadros * QUADRO + JANELA)
    for q in range(quadros):  # sobrepõe e soma
        sinal[q * QUADRO:q * QUADRO + JANELA] += pedacos[q]
    return sinal[JANELA // 2 - QUADRO // 2:][:quadros * QUADRO]


def duracoes(fonemas: list[str], velocidade: float = 1.0) -> list[tuple[int, float, float]]:
    """Onde cada fonema começa e acaba (em segundos) na fala deste sintetizador: (posição, início, fim)."""
    saida: list[tuple[int, float, float]] = []
    agora = 0.0
    for trecho in _trechos(fonemas, velocidade):
        fim = agora + trecho.quadros * QUADRO / TAXA
        if saida and saida[-1][0] == trecho.fonema:   # fechamento + estouro de uma oclusiva: um fonema só
            saida[-1] = (trecho.fonema, saida[-1][1], fim)
        else:
            saida.append((trecho.fonema, agora, fim))
        agora = fim
    return saida


def sintetizar_fonemas(fonemas: list[str], tom: float = 112.0, velocidade: float = 1.0, semente: int = 0,
                       escala: float = 1.0) -> np.ndarray:
    """Fonemas -> onda. É o miolo de ``sintetizar``; o alinhador usa para saber onde cada som cai."""
    if not fonemas:
        return np.zeros(0, dtype=np.float32)
    tabela = _tabela(_trechos(fonemas, velocidade), tom, escala)
    sorteio = np.random.default_rng(semente)
    sinal = _voz(tabela, sorteio) + _chiado(tabela, sorteio)
    pico = np.abs(sinal).max()
    if pico > 0:
        sinal = sinal / pico * 0.85
    borda = min(len(sinal) // 2, TAXA // 100)
    sinal[:borda] *= np.linspace(0, 1, borda)
    sinal[-borda:] *= np.linspace(1, 0, borda)
    return sinal.astype(np.float32)


def sintetizar(texto: str, tom: float = 112.0, velocidade: float = 1.0, semente: int = 0,
               escala: float = 1.0) -> np.ndarray:
    """Texto -> onda (float entre -1 e 1, a ``TAXA`` amostras por segundo)."""
    return sintetizar_fonemas(texto_para_fonemas(texto), tom, velocidade, semente, escala)


def falar(texto: str, tom: float = 112.0, velocidade: float = 1.0) -> bytes:
    """Texto -> arquivo WAV em memória (16 bits, mono)."""
    sinal = sintetizar(texto, tom, velocidade)
    memoria = io.BytesIO()
    with wave.open(memoria, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes((sinal * 32767).astype(np.int16).tobytes())
    return memoria.getvalue()
