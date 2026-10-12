"""Tokenizador BPE (Byte Pair Encoding) escrito à mão.

Como texto vira números:

1. O texto é cortado em pedaços: palavras (com o espaço da frente junto),
   números, pontuação e espaços.
2. Cada pedaço começa como uma sequência de bytes UTF-8 (256 símbolos).
3. Treinar é repetir: achar o par de símbolos vizinhos mais frequente e fundi-lo
   num símbolo novo. "d"+"e" vira "de", depois " "+"de" vira " de", e assim
   palavras comuns em português acabam virando um token só.
4. Codificar um texto novo é aplicar as mesmas fusões, na mesma ordem.

Treinado em português, ele gasta menos tokens por frase do que um tokenizador
feito para inglês, e isso rende mais contexto para o mesmo tamanho de cérebro.

    python -m kernel cerebro tokenizador
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path

# palavra | número (até 3 dígitos) | pontuação | espaços. Todo caractere cai em algum.
PEDACOS = re.compile(r" ?[^\W\d_]+| ?\d{1,3}| ?(?:[^\s\w]|_)+|\s+")
FIM = "<|fim|>"  # separa um documento do outro


def fundir(ids: list[int], par: tuple[int, int], novo: int) -> list[int]:
    saida, i = [], 0
    while i < len(ids):
        if i < len(ids) - 1 and ids[i] == par[0] and ids[i + 1] == par[1]:
            saida.append(novo)
            i += 2
        else:
            saida.append(ids[i])
            i += 1
    return saida


class Tokenizador:
    def __init__(self, fusoes: list[tuple[int, int]]):
        self.lista_de_fusoes = [tuple(par) for par in fusoes]
        # par -> símbolo novo. O número do símbolo também é a prioridade: menor = aprendido antes.
        self.fusoes = {par: 256 + i for i, par in enumerate(self.lista_de_fusoes)}
        self.bytes_de = [bytes([i]) for i in range(256)]
        for a, b in self.lista_de_fusoes:
            self.bytes_de.append(self.bytes_de[a] + self.bytes_de[b])
        self.id_fim = len(self.bytes_de)
        self._cache: dict[str, list[int]] = {}

    @property
    def tamanho(self) -> int:
        return self.id_fim + 1

    def _codificar_pedaco(self, pedaco: str) -> list[int]:
        ids = self._cache.get(pedaco)
        if ids is None:
            ids = list(pedaco.encode("utf-8"))
            while len(ids) > 1:
                par = min(zip(ids, ids[1:]), key=lambda p: self.fusoes.get(p, float("inf")))
                if par not in self.fusoes:
                    break
                ids = fundir(ids, par, self.fusoes[par])
            if len(self._cache) < 500_000:
                self._cache[pedaco] = ids
        return ids

    def codificar(self, texto: str) -> list[int]:
        saida: list[int] = []
        for i, trecho in enumerate(texto.split(FIM)):
            if i:
                saida.append(self.id_fim)
            for pedaco in PEDACOS.findall(trecho):
                saida.extend(self._codificar_pedaco(pedaco))
        return saida

    def decodificar(self, ids: Iterable[int]) -> str:
        partes = [FIM.encode() if i == self.id_fim else self.bytes_de[i] for i in ids]
        return b"".join(partes).decode("utf-8", errors="replace")

    def salvar(self, arquivo: Path) -> None:
        dados = {"versao": 1, "fusoes": self.lista_de_fusoes}
        Path(arquivo).write_text(json.dumps(dados), encoding="utf-8")

    @classmethod
    def carregar(cls, arquivo: Path) -> "Tokenizador":
        return cls(json.loads(Path(arquivo).read_text(encoding="utf-8"))["fusoes"])


def treinar(textos: Iterable[str], tamanho: int = 4096, ao_progredir=None) -> Tokenizador:
    """Aprende ``tamanho - 257`` fusões (256 bytes de base + o token de fim)."""
    frequencia: Counter[str] = Counter()
    for texto in textos:
        frequencia.update(PEDACOS.findall(texto.replace(FIM, "")))
    if len(frequencia) > 100_000:  # pedaços vistos uma única vez só deixam o treino lento
        frequencia = Counter({p: n for p, n in frequencia.items() if n > 1})

    palavras = [list(p.encode("utf-8")) for p in frequencia]
    vezes = list(frequencia.values())
    pares: Counter[tuple[int, int]] = Counter()
    onde: dict[tuple[int, int], set[int]] = defaultdict(set)  # par -> em quais palavras aparece
    for i, (ids, n) in enumerate(zip(palavras, vezes)):
        for par in zip(ids, ids[1:]):
            pares[par] += n
            onde[par].add(i)

    fusoes: list[tuple[int, int]] = []
    while 256 + len(fusoes) < tamanho - 1 and pares:
        maior = max(pares.values())
        if maior < 2:
            break
        par = max(p for p, n in pares.items() if n == maior)  # desempate fixo: resultado reprodutível
        novo = 256 + len(fusoes)
        fusoes.append(par)
        # Só as palavras que contêm o par mudam: tiramos os pares antigos delas e pomos os novos.
        for i in onde.pop(par):
            ids, n = palavras[i], vezes[i]
            for p in zip(ids, ids[1:]):
                pares[p] -= n
            ids = palavras[i] = fundir(ids, par, novo)
            for p in zip(ids, ids[1:]):
                pares[p] += n
                onde[p].add(i)
        pares.pop(par, None)
        if len(fusoes) % 200 == 0:
            pares = +pares  # joga fora os pares que zeraram
            if ao_progredir:
                ao_progredir(256 + len(fusoes), tamanho)
    return Tokenizador(fusoes)
