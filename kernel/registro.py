"""Registro de tudo.

Cada coisa que o K.E.R.N.E.L percebe, decide ou faz vira uma linha JSON num
arquivo do dia (``dados/registro/AAAA-MM-DD.jsonl``). O arquivo só cresce:
nada é reescrito, então dá para auditar depois com qualquer editor de texto.
O diário da mente é escrito a partir daqui.
"""
from __future__ import annotations

import json
import threading
from collections import deque
from datetime import date, datetime
from pathlib import Path


class Registro:
    def __init__(self, pasta: Path, relogio=datetime.now):
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self._relogio = relogio
        self._trava = threading.Lock()  # os ouvidos anotam de outra thread
        self._cauda: deque[dict] = deque(maxlen=300)

    def _arquivo(self, dia: date) -> Path:
        return self.pasta / f"{dia:%Y-%m-%d}.jsonl"

    def anotar(self, tipo: str, **dados) -> dict:
        agora = self._relogio()
        entrada = {"ts": agora.isoformat(timespec="seconds"), "tipo": tipo, **dados}
        linha = json.dumps(entrada, ensure_ascii=False, default=str)
        with self._trava:
            with open(self._arquivo(agora.date()), "a", encoding="utf-8") as f:
                f.write(linha + "\n")
            self._cauda.append(entrada)
        return entrada

    def do_dia(self, dia: date) -> list[dict]:
        arquivo = self._arquivo(dia)
        if not arquivo.exists():
            return []
        with self._trava, open(arquivo, encoding="utf-8") as f:
            return [json.loads(linha) for linha in f if linha.strip()]

    def ultimos(self, n: int = 50) -> list[dict]:
        with self._trava:
            return list(self._cauda)[-n:]

    def dias(self) -> list[date]:
        dias = []
        for arquivo in sorted(self.pasta.glob("*.jsonl")):
            try:
                dias.append(date.fromisoformat(arquivo.stem))
            except ValueError:
                pass
        return dias
