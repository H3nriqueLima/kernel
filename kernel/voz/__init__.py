"""Voz: a fala do K.E.R.N.E.L.

São dois sintetizadores, e os dois são feitos aqui, sem motor de voz pronto:

- **Difones com PSOLA** (``difones.py``, ``psola.py``): cola pedacinhos de uma voz
  gravada (do meio de um fonema ao meio do seguinte) e ajusta duração e tom. Soa
  como gente, porque é gente. Precisa do banco de difones, que se monta com
  ``python -m kernel voz baixar`` e ``python -m kernel voz construir``.
- **Formantes** (``sintetizador.py``): gera a onda inteira por regra. Voz de
  máquina, mas não depende de gravação nenhuma. É o molde que o alinhador usa para
  cortar as gravações e a voz de reserva quando o banco falta ou não tem um som.

``fonemas.py`` (texto -> sons) serve aos dois.
"""
from __future__ import annotations

import io
import threading
import wave
from pathlib import Path

import numpy as np

from .sintetizador import TAXA, falar, sintetizar

__all__ = ["TAXA", "falar", "falar_com", "sintetizar", "onda_com"]

_falantes: dict[str, object] = {}
_trava = threading.Lock()   # duas falas pedidas juntas não carregam o banco duas vezes


def _wav(onda: np.ndarray, taxa: int) -> bytes:
    memoria = io.BytesIO()
    with wave.open(memoria, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes((np.clip(onda, -1, 1) * 32767).astype(np.int16).tobytes())
    return memoria.getvalue()


def falante_de(cfg):
    """O banco de difones carregado (uma vez só), ou None se ainda não foi construído."""
    pasta = Path(cfg.dados) / "voz" / "banco"
    chave = str(pasta)
    with _trava:
        if chave not in _falantes:
            if not (pasta / "meta.json").exists():
                return None
            from .difones import Falante

            _falantes[chave] = Falante(pasta)
        return _falantes[chave]


def onda_com(cfg, texto: str) -> tuple[np.ndarray, int, str]:
    """Fala o texto com o motor da configuração. Devolve (onda, taxa, motor que acabou sendo usado)."""
    voz = cfg.voz
    if voz.motor == "difones":
        falante = falante_de(cfg)
        if falante is not None:
            onda = falante.falar(texto, velocidade=voz.velocidade, altura=voz.altura, estilo=voz.estilo)
            if onda is not None:
                return onda, falante.taxa, "difones"
            # Faltou um som no banco. A reserva fala na altura da voz gravada (e com o trato vocal mais
            # curto), para a troca de motor não parecer que outra pessoa pegou o microfone.
            tom = falante.meta["tom"] * voz.altura
            return sintetizar(texto, tom, voz.velocidade, escala=1.15), TAXA, "formantes (reserva)"
    return sintetizar(texto, voz.tom, voz.velocidade), TAXA, "formantes"


def falar_com(cfg, texto: str, detalhes: dict | None = None) -> bytes:
    """Texto -> arquivo WAV em memória, pelo motor escolhido em ``[voz]`` (com a reserva de formantes).

    ``detalhes``, se vier, recebe o motor que acabou falando e os segundos de fala (vai para o registro).
    """
    onda, taxa, motor = onda_com(cfg, texto)
    if detalhes is not None:
        detalhes.update(motor=motor, segundos=round(len(onda) / taxa, 2))
    return _wav(onda, taxa)
