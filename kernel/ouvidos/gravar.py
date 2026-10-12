"""Gravar os exemplos da palavra de ativação com a sua voz.

    python -m kernel ouvidos gravar positivo --quantidade 100
    python -m kernel ouvidos gravar negativo --quantidade 100
    python -m kernel ouvidos gravar ruido --segundos 120

Positivo: você dizendo a palavra de ativação, de jeitos diferentes (perto,
longe, rápido, devagar). Negativo: qualquer outra coisa, principalmente palavras
parecidas. Ruído: o som normal do seu quarto, sem você falar com ele.
"""
from __future__ import annotations

import time
from pathlib import Path

from .audio import TAXA, gravar_wav, volume

DURACAO = 1.5          # segundos por gravação
SILENCIO = 0.004       # volume abaixo disso conta como "não ouvi nada"

# Coisas para dizer nas gravações negativas: parecidas com "kernel" primeiro, depois fala comum.
FRASES_NEGATIVAS = [
    "querer", "coronel", "carnaval", "caderno", "inverno", "terminal", "quermesse", "colher", "cabelo",
    "quero ver", "que mel", "túnel", "painel", "papel", "pincel", "hotel", "quartel", "cartel",
    "bom dia", "computador", "abrir", "obrigado", "tudo bem", "que horas são", "internet", "telefone",
    "amanhã", "trabalho", "música", "janela", "pode ser", "não sei", "vamos lá", "um, dois, três",
]


def _proximo_numero(pasta: Path) -> int:
    numeros = [int(a.stem) for a in pasta.glob("*.wav") if a.stem.isdigit()]
    return max(numeros, default=0) + 1


def microfones() -> list[str]:
    import sounddevice as sd

    return [f"{i}: {d['name']}" for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]


def gravar(pasta: Path, tipo: str, quantidade: int, palavra: str, microfone: int | None = None,
           avisar=print) -> int:
    """Grava ``quantidade`` exemplos curtos, um depois do outro. Devolve quantos ficaram."""
    import sounddevice as sd

    destino = Path(pasta) / tipo
    destino.mkdir(parents=True, exist_ok=True)
    numero, feitas, vazias = _proximo_numero(destino), 0, 0
    avisar("Vou gravar em seguida, sem você apertar nada. Ctrl+C para parar.")
    time.sleep(1.5)
    try:
        while feitas < quantidade and vazias < 5:
            if tipo == "positivo":
                avisar(f'[{feitas + 1}/{quantidade}] Diga: "{palavra}"')
            else:
                avisar(f'[{feitas + 1}/{quantidade}] Diga: "{FRASES_NEGATIVAS[feitas % len(FRASES_NEGATIVAS)]}"')
            sinal = sd.rec(int(DURACAO * TAXA), samplerate=TAXA, channels=1, dtype="float32", device=microfone)
            sd.wait()
            sinal = sinal[:, 0]
            if volume(sinal) < SILENCIO:
                vazias += 1
                avisar("    não ouvi nada; vou repetir esta.")
                continue
            vazias = 0
            gravar_wav(destino / f"{numero:04d}.wav", sinal)
            numero += 1
            feitas += 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        avisar("parei.")
    if vazias >= 5:
        avisar("Cinco gravações mudas seguidas. Confira o microfone (python -m kernel ouvidos microfones).")
    return feitas


def gravar_ruido(pasta: Path, segundos: int, microfone: int | None = None, avisar=print) -> Path:
    """Grava o som ambiente de uma vez só (o treino corta em trechos de 1 s)."""
    import sounddevice as sd

    destino = Path(pasta) / "ruido"
    destino.mkdir(parents=True, exist_ok=True)
    avisar(f"Gravando {segundos} s do ambiente. Pode digitar, mexer no mouse, deixar a TV: só não fale com ele.")
    sinal = sd.rec(int(segundos * TAXA), samplerate=TAXA, channels=1, dtype="float32", device=microfone)
    sd.wait()
    arquivo = destino / f"{_proximo_numero(destino):04d}.wav"
    gravar_wav(arquivo, sinal[:, 0])
    return arquivo
