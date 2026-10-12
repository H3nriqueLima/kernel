"""Dados de treino: do texto para arquivos binários de tokens.

Com 12 GB de RAM e HD mecânico, o corpus não pode morar na memória nem ser lido
aos pulos. Então:

- ``preparar`` tokeniza o corpus uma vez e grava os ids em sequência
  (``treino.bin`` e ``val.bin``, 2 bytes por token).
- ``Lotes`` abre o arquivo com memmap, puxa um pedaço contínuo para a RAM (uma
  leitura sequencial, que o HD faz bem) e sorteia os lotes de dentro dele. De
  tempos em tempos troca de pedaço.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from .tokenizador import Tokenizador


def preparar(corpus: Path, tokenizador: Tokenizador, pasta: Path, ao_progredir=None) -> dict:
    """Tokeniza ``corpus`` e grava treino.bin e val.bin (o fim do corpus vira validação)."""
    if tokenizador.tamanho > 65536:
        raise ValueError("vocabulário grande demais para 2 bytes por token")
    treino, val = Path(pasta) / "treino.bin", Path(pasta) / "val.bin"
    total, lido, tamanho = 0, 0, os.path.getsize(corpus)
    with open(corpus, encoding="utf-8") as entrada, open(treino, "wb") as saida:
        while True:
            linhas = entrada.readlines(1 << 20)  # ~1 MB de texto por vez, sempre em fim de linha
            if not linhas:
                break
            bloco = "".join(linhas)
            ids = np.array(tokenizador.codificar(bloco), dtype=np.uint16)
            saida.write(ids.tobytes())
            total += len(ids)
            lido += len(bloco.encode("utf-8"))
            if ao_progredir:
                ao_progredir(lido, tamanho, total)
    # o último 1% (no máximo 2 milhões de tokens) sai do treino e vira validação
    n_val = min(max(total // 100, 1), 2_000_000)
    corte = (total - n_val) * 2
    with open(treino, "rb") as f:
        f.seek(corte)
        Path(val).write_bytes(f.read())
    os.truncate(treino, corte)
    return {"treino": total - n_val, "val": n_val}


class Lotes:
    def __init__(self, arquivo: Path, contexto: int, lote: int, pedaco: int = 8_000_000, semente=None):
        self.dados = np.memmap(arquivo, dtype=np.uint16, mode="r")
        if len(self.dados) < contexto + 2:
            raise ValueError(f"{arquivo} tem poucos tokens ({len(self.dados)}) para contexto {contexto}")
        self.contexto, self.lote, self.pedaco = contexto, lote, pedaco
        self.sorteio = np.random.default_rng(semente)
        self.trocar_a_cada = max(1, pedaco // (lote * contexto))  # ~uma passada pelo pedaço
        self._usados = 0
        self._ram = self._carregar()

    def __len__(self) -> int:
        return len(self.dados)

    def _carregar(self) -> np.ndarray:
        if len(self.dados) <= self.pedaco:
            return np.asarray(self.dados)
        inicio = int(self.sorteio.integers(0, len(self.dados) - self.pedaco))
        return np.array(self.dados[inicio:inicio + self.pedaco])

    def pegar(self, dispositivo):
        """Um lote (x, y): y é x deslocado de um token, ou seja, "qual é o próximo?"."""
        import torch

        self._usados += 1
        if self._usados % self.trocar_a_cada == 0 and len(self.dados) > self.pedaco:
            self._ram = self._carregar()
        inicios = self.sorteio.integers(0, len(self._ram) - self.contexto - 1, size=self.lote)
        x = np.stack([self._ram[i:i + self.contexto] for i in inicios]).astype(np.int64)
        y = np.stack([self._ram[i + 1:i + 1 + self.contexto] for i in inicios]).astype(np.int64)
        return torch.from_numpy(x).to(dispositivo), torch.from_numpy(y).to(dispositivo)
