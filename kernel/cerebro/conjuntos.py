"""Os conjuntos fixos para medir o cérebro: validação, teste e uma amostra do treino.

Até a v0.5.1, a "validação" era o último 1% do corpus: o fim do dump da Wikipédia,
artigos novos, em blocos de um assunto só (batalhas, álgebra, economia) e mais
longos que a média. Não representava o resto, e não havia conjunto de teste.

Aqui os conjuntos são tirados do próprio ``treino.bin``, de documentos que o cérebro
NUNCA leu (``cobertura.py`` refaz o sorteio de cada sessão de treino), e depois
saem do treino para continuarem nunca lidos:

- só entram documentos de regiões que nenhuma sessão chegou a carregar (pedaços de
  8 mi de tokens). Lá todo documento ficou de fora, curto ou longo; sortear entre os
  "não tocados" de qualquer lugar puxaria para os curtos, que escapam mais;
- documentos com cópia exata em outro lugar do treino não entram;
- o sorteio é reprodutível (semente fixa);
- ``teste`` (2 mi de tokens) é para o relatório final; ``validacao`` (1 mi) é a que
  o treino usa para escolher o melhor modelo; ``amostra_treino`` (1 mi) vem de
  documentos que o cérebro JÁ leu, para medir o quanto ele decorou;
- o ``manifesto.json`` guarda a regra, as sessões consideradas, de onde veio cada
  documento e a impressão digital (SHA-256) de cada arquivo.

    python -m kernel cerebro conjuntos --ate-o-passo N
"""
from __future__ import annotations

import gc
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from . import cobertura

PASTA = "avaliacao"
MANIFESTO = "manifesto.json"
ARQUIVOS = {"teste": "teste.bin", "validacao": "validacao.bin", "amostra_treino": "amostra_treino.bin"}
LARGURA = 257          # uma janela de treino toca 256 entradas e o alvo do último
NGRAMA = 13            # tamanho do trecho igual que conta como sobreposição
VERSAO = 1


def _sha256(arquivo: Path) -> str:
    resumo = hashlib.sha256()
    with open(arquivo, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def documentos(dados: np.ndarray, id_fim: int, passo: int = 50_000_000) -> tuple[np.ndarray, np.ndarray]:
    """(começo, fim) de cada documento; ``fim`` é a posição do token de fim (que fica fora)."""
    fins = []
    for i in range(0, len(dados), passo):
        fins.append(np.flatnonzero(np.asarray(dados[i:i + passo]) == id_fim) + i)
    fins = np.concatenate(fins)
    return np.concatenate([[0], fins[:-1] + 1]).astype(np.int64), fins.astype(np.int64)


def _digitais(dados: np.ndarray, comecos: np.ndarray, fins: np.ndarray) -> np.ndarray:
    """Uma impressão curta (8 bytes) do conteúdo de cada documento, para achar cópias exatas."""
    saida = np.empty(len(comecos), dtype=np.uint64)
    for i, (a, b) in enumerate(zip(comecos, fins)):
        saida[i] = int.from_bytes(hashlib.blake2b(np.asarray(dados[a:b]).tobytes(), digest_size=8).digest(), "little")
    return saida


def _hashes_de_ngramas(ids: np.ndarray, n: int = NGRAMA) -> np.ndarray:
    """Um número (64 bits) para cada trecho de ``n`` tokens seguidos."""
    ids = np.asarray(ids, dtype=np.uint64)
    if len(ids) < n:
        return np.empty(0, dtype=np.uint64)
    base = np.uint64(1_000_003)
    h = np.zeros(len(ids) - n + 1, dtype=np.uint64)
    with np.errstate(over="ignore"):
        for j in range(n):
            h = h * base + ids[j:len(ids) - n + 1 + j]
    return h


def sobreposicao(conjunto: np.ndarray, treino: np.ndarray, passo: int = 40_000_000) -> np.ndarray:
    """Para cada trecho de 13 tokens do conjunto: ele aparece igual em algum lugar do treino?"""
    alvo = _hashes_de_ngramas(conjunto)
    ordenados = np.unique(alvo)
    achados = np.zeros(len(ordenados), dtype=bool)
    for i in range(0, len(treino), passo):
        pedaco = np.asarray(treino[i:i + passo + NGRAMA - 1])
        h = np.sort(_hashes_de_ngramas(pedaco))   # ordenar e procurar é ~10x mais rápido que np.isin aqui
        onde = np.clip(np.searchsorted(h, ordenados), 0, len(h) - 1)
        achados |= h[onde] == ordenados
    return achados[np.searchsorted(ordenados, alvo)]


def _escrever(arquivo: Path, dados: np.ndarray, escolhidos: np.ndarray, comecos, fins, id_fim: int) -> int:
    with open(arquivo, "wb") as f:
        total = 0
        for i in escolhidos:
            pedaco = np.asarray(dados[comecos[i]:fins[i] + 1])   # o documento e o token de fim
            f.write(pedaco.astype(np.uint16).tobytes())
            total += len(pedaco)
    return total


def _escolher(candidatos: np.ndarray, tamanhos: np.ndarray, tokens: int, sorteio) -> np.ndarray:
    ordem = sorteio.permutation(candidatos)
    acumulado = np.cumsum(tamanhos[ordem] + 1)
    return np.sort(ordem[:int(np.searchsorted(acumulado, tokens)) + 1])


def montar(pasta: Path, sessoes: list[cobertura.Sessao], id_fim: int, tokens_teste: int = 2_000_000,
           tokens_validacao: int = 1_000_000, tokens_amostra: int = 1_000_000, semente: int = 2026,
           avisar=print) -> dict:
    """Monta os conjuntos, tira teste e validação do treino e grava o manifesto.

    O ``treino.bin`` antigo fica como ``treino-original.bin`` (com ele e o manifesto dá para refazer tudo).
    """
    pasta = Path(pasta)
    if (pasta / "treino-original.bin").exists():
        raise RuntimeError("os conjuntos já foram montados (existe treino-original.bin); montar de novo apagaria o "
                           "treino original. Para refazer, devolva treino-original.bin para treino.bin antes.")
    saida = pasta / PASTA
    saida.mkdir(exist_ok=True)
    original = pasta / "treino.bin"
    dados = np.memmap(original, dtype=np.uint16, mode="r")
    N = len(dados)
    t0 = time.time()
    comecos, fins = documentos(dados, id_fim)
    tamanhos = fins - comecos
    avisar(f"{len(comecos):,} documentos no treino ({time.time() - t0:.0f} s)".replace(",", "."))

    janelas = cobertura.todas_as_janelas(N, sessoes)
    tocados = cobertura.janelas_por_documento(janelas, LARGURA, comecos, fins + 1)
    pedacos = cobertura.todos_os_pedacos(N, sessoes)
    # um documento está "fora de qualquer pedaço" se nenhum pedaço [p, p + 8 mi) o alcança
    alcance = sessoes[0].pedaco
    fora_dos_pedacos = (np.searchsorted(pedacos, fins + 1, side="left")
                        - np.searchsorted(pedacos, comecos - alcance, side="right")) == 0
    digitais = _digitais(dados, comecos, fins)
    _, inverso, repeticoes = np.unique(digitais, return_inverse=True, return_counts=True)
    unico = repeticoes[inverso] == 1
    avisar(f"sorteio refeito: {len(janelas):,} janelas, {len(pedacos)} pedaços | documentos nunca tocados: "
           f"{int((tocados == 0).sum()):,} | fora de qualquer pedaço: {int(fora_dos_pedacos.sum()):,} | "
           f"com cópia exata no treino: {int((~unico).sum()):,} ({time.time() - t0:.0f} s)".replace(",", "."))

    sorteio = np.random.default_rng(semente)
    candidatos = np.flatnonzero(fora_dos_pedacos & (tocados == 0) & unico & (tamanhos >= 32) & (tamanhos <= 16384))
    teste = _escolher(candidatos, tamanhos, tokens_teste, sorteio)
    resto = np.setdiff1d(candidatos, teste)
    validacao = _escolher(resto, tamanhos, tokens_validacao, sorteio)
    vistos = np.flatnonzero((tocados > 0) & unico & (tamanhos >= 32) & (tamanhos <= 16384))
    amostra = _escolher(vistos, tamanhos, tokens_amostra, sorteio)

    escolhas = {"teste": teste, "validacao": validacao, "amostra_treino": amostra}
    manifesto = {"versao": VERSAO, "criado": time.strftime("%Y-%m-%dT%H:%M:%S"), "semente": semente,
                 "regra": "documentos nunca lidos, de regiões que nenhuma sessão carregou, sem cópia exata, "
                          "32 a 16384 tokens; teste e validação saem do treino",
                 "sessoes": [{"inicio": s.inicio, "fim": s.fim, "semente": s.semente} for s in sessoes],
                 "treino_original": {"arquivo": "treino-original.bin", "tokens": int(N), "documentos": len(comecos),
                                     "sha256": _sha256(original)},
                 "cobertura": {"tokens_processados": int(len(janelas) * 256),
                               "tokens_distintos": cobertura.tokens_distintos(janelas, LARGURA),
                               "documentos_tocados": int((tocados > 0).sum()),
                               "documentos_fora_dos_pedacos": int(fora_dos_pedacos.sum()),
                               "documentos_com_copia": int((~unico).sum())},
                 "conjuntos": {}}
    for nome, escolhidos in escolhas.items():
        arquivo = saida / ARQUIVOS[nome]
        total = _escrever(arquivo, dados, escolhidos, comecos, fins, id_fim)
        manifesto["conjuntos"][nome] = {
            "arquivo": f"{PASTA}/{ARQUIVOS[nome]}", "tokens": total, "documentos": len(escolhidos),
            "tamanho_mediano": int(np.median(tamanhos[escolhidos])), "sha256": _sha256(arquivo),
            "origem": [[int(comecos[i]), int(fins[i])] for i in escolhidos]}
        avisar(f"{nome}: {len(escolhidos)} documentos, {total:,} tokens".replace(",", "."))

    # o treino novo: o original sem os documentos de teste e de validação (cada um com o seu token de fim)
    fora = np.sort(np.concatenate([teste, validacao]))
    novo = pasta / "treino.novo.bin"
    with open(novo, "wb") as f:
        anterior = 0
        for i in fora:
            f.write(np.asarray(dados[anterior:comecos[i]]).tobytes())
            anterior = fins[i] + 1
        f.write(np.asarray(dados[anterior:]).tobytes())
    del dados
    gc.collect()   # o Windows não renomeia um arquivo que ainda está mapeado na memória
    original.replace(pasta / "treino-original.bin")
    novo.replace(original)
    treino_novo = np.memmap(original, dtype=np.uint16, mode="r")
    manifesto["treino"] = {"arquivo": "treino.bin", "tokens": int(len(treino_novo)), "sha256": _sha256(original)}
    avisar(f"treino.bin novo: {len(treino_novo):,} tokens (saíram {N - len(treino_novo):,})".replace(",", "."))

    # quanto do teste e da validação aparece igual (13 tokens seguidos) no treino que sobrou
    for nome in ("teste", "validacao"):
        conjunto = np.fromfile(saida / ARQUIVOS[nome], dtype=np.uint16)
        achados = sobreposicao(conjunto, treino_novo)
        manifesto["conjuntos"][nome]["trechos_de_13_no_treino"] = float(achados.mean())
        avisar(f"{nome}: {achados.mean():.1%} dos trechos de 13 tokens aparecem iguais no treino ({time.time() - t0:.0f} s)")
    del treino_novo
    (saida / MANIFESTO).write_text(json.dumps(manifesto, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifesto


def carregar(pasta: Path) -> dict[str, np.ndarray]:
    """Os conjuntos, conferidos contra o manifesto (um arquivo trocado ou estragado é recusado)."""
    pasta = Path(pasta)
    manifesto = json.loads((pasta / PASTA / MANIFESTO).read_text(encoding="utf-8"))
    conjuntos = {}
    for nome, info in manifesto["conjuntos"].items():
        arquivo = pasta / info["arquivo"]
        if _sha256(arquivo) != info["sha256"]:
            raise ValueError(f"{arquivo.name} não confere com o manifesto: os conjuntos fixos mudaram")
        conjuntos[nome] = np.fromfile(arquivo, dtype=np.uint16)
    return conjuntos


def existe(pasta: Path) -> bool:
    return (Path(pasta) / PASTA / MANIFESTO).exists()
