"""Registro de tudo.

Cada coisa que o K.E.R.N.E.L percebe, decide ou faz vira uma linha JSON num
arquivo do dia (``dados/registro/AAAA-MM-DD.jsonl``). O arquivo só cresce:
nada é reescrito, então dá para auditar depois com qualquer editor de texto.
O diário da mente é escrito a partir daqui. Os dias com mais de 30 dias são
compactados (``AAAA-MM-DD.jsonl.gz``): o texto continua todo lá, num décimo do espaço.
"""
from __future__ import annotations

import gzip
import json
import shutil
import threading
from collections import deque
from datetime import date, datetime, timedelta
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
        compactado = arquivo.with_name(arquivo.name + ".gz")
        if arquivo.exists():
            abrir = lambda: open(arquivo, encoding="utf-8")   # noqa: E731
        elif compactado.exists():
            abrir = lambda: gzip.open(compactado, "rt", encoding="utf-8")   # noqa: E731
        else:
            return []
        with self._trava, abrir() as f:
            return [json.loads(linha) for linha in f if linha.strip()]

    def compactar_antigos(self, dias: int = 30) -> int:
        """Compacta (gzip) os arquivos dos dias com mais de ``dias`` dias. Devolve quantos."""
        limite = self._relogio().date() - timedelta(days=dias)
        feitos = 0
        for dia in self.dias():
            arquivo = self._arquivo(dia)
            if dia >= limite or not arquivo.exists():
                continue
            temporario = arquivo.with_name(arquivo.name + ".gz.tmp")
            with self._trava:
                with open(arquivo, "rb") as origem, gzip.open(temporario, "wb") as destino:
                    shutil.copyfileobj(origem, destino)
                temporario.replace(arquivo.with_name(arquivo.name + ".gz"))
                arquivo.unlink()
            feitos += 1
        return feitos

    def ultimos(self, n: int = 50) -> list[dict]:
        with self._trava:
            return list(self._cauda)[-n:]

    def dias(self) -> list[date]:
        dias = []
        for arquivo in self.pasta.glob("*.jsonl*"):
            if arquivo.name.endswith((".jsonl", ".jsonl.gz")):
                try:
                    dias.append(date.fromisoformat(arquivo.name.split(".")[0]))
                except ValueError:
                    pass
        return sorted(set(dias))
