"""Quais trechos do treino o cérebro já leu.

Os lotes do treino são sorteados (``dados.Lotes``), mas com semente conhecida: cada
sessão começa com ``semente = 1337 + passo inicial``. Então dá para refazer o
sorteio, chamada por chamada, sem ler um byte dos dados, e saber exatamente onde
começou cada janela que o cérebro viu.

Para que serve:

- medir quanto do corpus foi de fato lido (tokens distintos), e não só quantos
  tokens passaram pelo treino ("22%" contava repetições);
- separar documentos que o cérebro nunca viu, para um conjunto de teste limpo.

O sorteio refeito aqui tem de consumir o gerador exatamente como ``Lotes`` consome;
o teste ``test_cobertura_refaz_o_sorteio_de_verdade`` confere isso contra a classe real.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Sessao:
    """Uma sessão de treino: do passo ``inicio`` ao ``fim`` (os passos que ficaram nos pesos)."""
    inicio: int
    fim: int
    semente_base: int = 1337
    lote: int = 16
    acumular: int = 2
    contexto: int = 256
    pedaco: int = 8_000_000

    @property
    def semente(self) -> int:
        return self.semente_base + self.inicio

    @property
    def chamadas(self) -> int:
        return (self.fim - self.inicio) * self.acumular   # cada passo pega ``acumular`` lotes


def inicios_da_sessao(n_tokens: int, sessao: Sessao) -> np.ndarray:
    """Onde começou cada janela que a sessão sorteou (posições no arquivo de treino)."""
    return sortear(n_tokens, sessao)[0]


def sortear(n_tokens: int, sessao: Sessao) -> tuple[np.ndarray, list[int]]:
    """(inícios de cada janela, inícios de cada pedaço carregado na RAM) da sessão."""
    sorteio = np.random.default_rng(sessao.semente)
    contexto, lote, pedaco = sessao.contexto, sessao.lote, sessao.pedaco
    trocar_a_cada = max(1, pedaco // (lote * contexto))
    grande = n_tokens > pedaco

    def novo_pedaco() -> tuple[int, int]:
        if not grande:
            return 0, n_tokens
        return int(sorteio.integers(0, n_tokens - pedaco)), pedaco

    deslocamento, tamanho = novo_pedaco()            # o __init__ de Lotes já carrega um pedaço
    pedacos = [deslocamento]
    saida = np.empty(sessao.chamadas * lote, dtype=np.int64)
    for chamada in range(1, sessao.chamadas + 1):
        if chamada % trocar_a_cada == 0 and grande:
            deslocamento, tamanho = novo_pedaco()
            pedacos.append(deslocamento)
        inicios = sorteio.integers(0, tamanho - contexto - 1, size=lote)
        saida[(chamada - 1) * lote:chamada * lote] = deslocamento + inicios
    return saida, pedacos


def todas_as_janelas(n_tokens: int, sessoes: list[Sessao]) -> np.ndarray:
    """Os inícios de todas as janelas de todas as sessões, em ordem crescente."""
    return np.sort(np.concatenate([inicios_da_sessao(n_tokens, s) for s in sessoes]))


def todos_os_pedacos(n_tokens: int, sessoes: list[Sessao]) -> np.ndarray:
    """Os inícios de todos os pedaços que alguma sessão carregou, em ordem crescente."""
    return np.sort(np.concatenate([np.array(sortear(n_tokens, s)[1], dtype=np.int64) for s in sessoes]))


def tokens_distintos(inicios_ordenados: np.ndarray, largura: int) -> int:
    """Quantas posições diferentes as janelas cobrem (a união dos intervalos [início, início + largura))."""
    if len(inicios_ordenados) == 0:
        return 0
    fins = inicios_ordenados + largura
    # um intervalo só soma o que passa do maior fim visto antes dele
    maior_fim_antes = np.maximum.accumulate(np.concatenate([[inicios_ordenados[0]], fins[:-1]]))
    return int(np.sum(np.clip(fins - np.maximum(inicios_ordenados, maior_fim_antes), 0, None)))


def janelas_por_documento(inicios_ordenados: np.ndarray, largura: int, comecos: np.ndarray,
                          fins: np.ndarray) -> np.ndarray:
    """Quantas janelas tocaram cada documento [comeco, fim). Zero = o cérebro nunca viu nada dele."""
    # uma janela [s, s + largura) toca [a, b) se s < b e s + largura > a
    return (np.searchsorted(inicios_ordenados, fins, side="left")
            - np.searchsorted(inicios_ordenados, comecos - largura, side="right"))
