"""Dados de treino: do texto para arquivos binários de tokens.

Com 12 GB de RAM e HD mecânico, o corpus não pode morar na memória nem ser lido
aos pulos. Então:

- ``preparar`` tokeniza o corpus uma vez e grava os ids em sequência
  (``treino.bin`` e ``val.bin``, 2 bytes por token).
- ``Lotes`` abre o arquivo com memmap, puxa um pedaço contínuo para a RAM (uma
  leitura sequencial, que o HD faz bem) e sorteia os lotes de dentro dele. De
  tempos em tempos troca de pedaço. Repete parte do que lê e deixa outra parte
  sem ler (ver ``cobertura.py``).
- ``Passada`` lê o treino inteiro, sem repetir, em ordem embaralhada por documento.
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


class Passada:
    """Uma passada embaralhada pelos documentos do treino, sem repetição.

    ``Lotes`` sorteia janelas com reposição dentro de pedaços de 8 mi de tokens: uma parte
    do que ele lê é repetida (38% a 45% até a Fase 1) e outra parte do corpus nunca é lida.
    Aqui, os documentos são embaralhados (com semente) e emendados num fluxo só; o fluxo é
    cortado em ``lote`` faixas, e cada linha do lote lê a sua faixa em ordem, uma janela
    depois da outra. Numa época, cada token é lido uma vez, e as linhas de um mesmo lote vêm
    de lugares distantes do fluxo (documentos diferentes). Acabou a época, embaralha de novo.

    O estado (época e posição) vai no checkpoint: a sessão seguinte continua de onde a
    anterior parou, sem reler. O arquivo inteiro vai para a RAM (1,5 GB): ler documentos
    espalhados direto do HD mecânico seria lento.
    """

    def __init__(self, arquivo: Path, contexto: int, lote: int, id_fim: int, semente: int = 1337,
                 epoca: int = 0, posicao: int = 0):
        self.dados = np.fromfile(arquivo, dtype=np.uint16)
        fins = [np.flatnonzero(self.dados[i:i + 50_000_000] == id_fim) + i
                for i in range(0, len(self.dados), 50_000_000)]
        fins = np.concatenate(fins) if fins else np.empty(0, dtype=np.int64)
        if len(fins) == 0 or fins[-1] != len(self.dados) - 1:   # o último documento sem o token de fim
            fins = np.append(fins, len(self.dados) - 1)
        self.comecos = np.concatenate([[0], fins[:-1] + 1]).astype(np.int64)
        self.fins = fins.astype(np.int64)          # posição do último token de cada documento (o de fim)
        self.contexto, self.lote, self.semente = contexto, lote, semente
        self.epoca, self.posicao = epoca, posicao
        self._embaralhar()

    def __len__(self) -> int:
        return len(self.dados)

    def _embaralhar(self) -> None:
        sorteio = np.random.default_rng([self.semente, self.epoca])
        self._ordem = sorteio.permutation(len(self.comecos))
        tamanhos = (self.fins - self.comecos + 1)[self._ordem]
        self._acumulado = np.concatenate([[0], np.cumsum(tamanhos)])
        total = int(self._acumulado[-1])
        self.janelas_por_faixa = max(1, (total - 1) // (self.contexto * self.lote))
        self._faixa = self.janelas_por_faixa * self.contexto

    def _trecho(self, inicio: int, n: int) -> np.ndarray:
        """``n`` tokens do fluxo embaralhado, a partir de ``inicio`` (atravessando documentos)."""
        saida = np.empty(n, dtype=np.uint16)
        k = int(np.searchsorted(self._acumulado, inicio, side="right")) - 1
        dentro, cheio = inicio - int(self._acumulado[k]), 0
        while cheio < n:
            documento = self._ordem[k % len(self._ordem)]
            a, b = int(self.comecos[documento]), int(self.fins[documento]) + 1
            pegar = min(b - a - dentro, n - cheio)
            saida[cheio:cheio + pegar] = self.dados[a + dentro:a + dentro + pegar]
            cheio += pegar
            k += 1
            dentro = 0
        return saida

    def pegar(self, dispositivo):
        """Um lote (x, y): a próxima janela de cada faixa; y é x deslocado de um token."""
        import torch

        if self.posicao >= self.janelas_por_faixa:   # a época acabou: tudo foi lido uma vez
            self.epoca, self.posicao = self.epoca + 1, 0
            self._embaralhar()
        linhas = np.stack([self._trecho(r * self._faixa + self.posicao * self.contexto, self.contexto + 1)
                           for r in range(self.lote)]).astype(np.int64)
        self.posicao += 1
        return (torch.from_numpy(linhas[:, :-1].copy()).to(dispositivo),
                torch.from_numpy(linhas[:, 1:].copy()).to(dispositivo))

    def estado(self) -> dict:
        return {"amostragem": "passada", "semente": self.semente, "epoca": self.epoca, "posicao": self.posicao,
                "tokens": len(self.dados)}

    def lido(self) -> float:
        """Quanto da época atual já foi lido (0 a 1)."""
        return self.posicao / self.janelas_por_faixa
