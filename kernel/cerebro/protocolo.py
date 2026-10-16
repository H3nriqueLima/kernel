"""O protocolo de avaliação do cérebro: as mesmas medidas, do mesmo jeito, para qualquer modelo.

Rodar duas vezes no mesmo modelo dá os mesmos números (menos os de velocidade e
memória). Dois modelos medidos pelo protocolo podem ser comparados. O que ele mede:

1. A perda em CADA token de cada conjunto fixo (``conjuntos.py``): teste,
   validação, uma amostra do que ele já leu e a validação antiga (o fim do dump).
   Janelas de 256 tokens, sem sobreposição. Em nats por token, em perplexidade e em
   bits por byte, que não depende do tokenizador (compara com um cérebro futuro de
   outro vocabulário).
2. A perda por posição dentro da janela: quanto o contexto anterior ajuda. Se a
   perda para de cair depois de poucas posições, o modelo só usa o que está perto.
3. As linhas de base de n-gramas (``ngramas.py``) nos mesmos conjuntos.
4. Textos gerados com começos e sementes fixos, de três jeitos: o mais provável
   sempre (guloso), sorteio cru, e o jeito do serviço. Com medidas automáticas de
   repetição, palavras que existem e permanência no assunto. Coerência de verdade
   só uma pessoa julga: os textos ficam no relatório para isso.
5. Velocidade (tokens por segundo) e memória (RAM de pico, e VRAM na placa).

    python -m kernel cerebro protocolo [--modelo dados/cerebro/modelo.npz]
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import re
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from . import conjuntos, inferencia
from .ngramas import Ngramas
from .pesos import gpt_de_npz, ler_npz
from .tokenizador import Tokenizador

VERSAO = 2   # v2: o modo do serviço com 2 sementes (48 textos por modelo para a avaliação às cegas); pela interface
COMECOS = ["O Brasil é", "A fotossíntese é o processo", "Albert Einstein foi um", "A cidade de São Paulo",
           "A Segunda Guerra Mundial", "O futebol é um esporte", "Em 1500, Pedro Álvares Cabral",
           "A água é uma substância", "O Sol é a estrela", "A língua portuguesa", "Machado de Assis escreveu",
           "Um computador é uma máquina"]
MODOS = {  # nome -> (temperatura, top_k, top_p, repetição, sementes)
    "guloso": (1.0, 1, 1.0, 1.0, (0,)),
    "sorteio": (0.8, 40, 1.0, 1.0, (1, 2, 3)),
    "servico": (0.8, 40, 0.92, 1.2, (1, 2)),
}
TOKENS_GERADOS = 60
FAIXAS = [(0, 1), (1, 4), (4, 16), (16, 64), (64, 128), (128, 256)]   # posições na janela
_PALAVRA = re.compile(r"[a-záàâãéêíóôõúüç]+")


# ------------------------------------------------------------------ perda
@torch.no_grad()
def perda_em(modelo, ids: np.ndarray, bytes_por_token: np.ndarray, dispositivo, lote: int = 32) -> dict:
    """Perda em cada token de ``ids``, em janelas do contexto do modelo, sem sobreposição."""
    T = modelo.cfg.contexto
    n = (len(ids) - 1) // T
    entradas = np.asarray(ids[:n * T], dtype=np.int64).reshape(n, T)
    alvos = np.asarray(ids[1:n * T + 1], dtype=np.int64).reshape(n, T)
    por_posicao = np.zeros(T)
    soma = 0.0
    inicio = time.time()
    for i in range(0, n, lote):
        x = torch.from_numpy(entradas[i:i + lote]).to(dispositivo)
        y = torch.from_numpy(alvos[i:i + lote]).to(dispositivo)
        logits, _ = modelo(x)
        perdas = F.cross_entropy(logits.reshape(-1, logits.size(-1)).float(), y.reshape(-1), reduction="none")
        perdas = perdas.reshape(y.shape).double().cpu().numpy()
        por_posicao += perdas.sum(0)
        soma += float(perdas.sum())
    segundos = time.time() - inicio
    tokens = n * T
    media = soma / tokens
    bytes_ = float(bytes_por_token[alvos].sum())
    return {"perda": round(media, 5), "perplexidade": round(math.exp(media), 3),
            "bits_por_byte": round(soma / math.log(2) / bytes_, 5), "tokens": tokens,
            "por_posicao": (por_posicao / n).round(5).tolist(), "_segundos": segundos}


# ------------------------------------------------------------------ geração
def _metricas(tok: Tokenizador, comeco: str, ids_gerados: list[int], vocabulario: set[str]) -> dict:
    from ..memoria.texto import termos

    texto = tok.decodificar(ids_gerados)
    palavras = _PALAVRA.findall(texto.lower())
    trios = list(zip(ids_gerados, ids_gerados[1:], ids_gerados[2:]))
    pares = list(zip(palavras, palavras[1:]))
    return {
        "tokens": len(ids_gerados),
        "repeticao_3": round(1 - len(set(trios)) / len(trios), 3) if trios else 0.0,   # trios de tokens repetidos
        "distintos_2": round(len(set(pares)) / len(pares), 3) if pares else 0.0,       # pares de palavras diferentes
        "palavras_que_existem": round(sum(p in vocabulario for p in palavras) / len(palavras), 3) if palavras else 0.0,
        "no_assunto": bool(set(termos(comeco)) & set(termos(texto))),                  # repete alguma palavra do começo
    }


def gerar_amostras(cerebro, tok: Tokenizador, vocabulario: set[str]) -> tuple[list[dict], float]:
    """Os textos de cada começo fixo, em cada modo e semente, pela interface do cérebro (geração do serviço)."""
    amostras, tokens, segundos = [], 0, 0.0
    for comeco in COMECOS:
        ids = tok.codificar(comeco)
        for modo, (temperatura, top_k, top_p, repeticao, sementes) in MODOS.items():
            for semente in sementes:
                inicio = time.time()
                saida = cerebro.gerar_ids(ids, TOKENS_GERADOS, temperatura, top_k, top_p, repeticao, semente=semente)
                segundos += time.time() - inicio
                gerados = saida[len(ids):]
                tokens += len(gerados)
                amostras.append({"comeco": comeco, "modo": modo, "semente": semente,
                                 "texto": tok.decodificar(gerados), **_metricas(tok, comeco, gerados, vocabulario)})
    return amostras, tokens / max(segundos, 1e-9)


def _resumo_da_geracao(amostras: list[dict]) -> dict:
    resumo = {}
    for modo in MODOS:
        do_modo = [a for a in amostras if a["modo"] == modo]
        resumo[modo] = {chave: round(float(np.mean([a[chave] for a in do_modo])), 3)
                        for chave in ("repeticao_3", "distintos_2", "palavras_que_existem", "no_assunto", "tokens")}
    return resumo


# ------------------------------------------------------------------ memória
def _ram_de_pico_mb() -> float | None:
    """O maior uso de RAM (conjunto de trabalho) deste processo até agora, pelo Windows."""
    try:
        from ctypes import wintypes

        class Contadores(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Contadores), wintypes.DWORD]
        contadores = Contadores()
        contadores.cb = ctypes.sizeof(Contadores)
        if not kernel32.K32GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(contadores), contadores.cb):
            return None
        return round(contadores.PeakWorkingSetSize / 2**20, 1)
    except (AttributeError, OSError):   # fora do Windows
        return None


class _PicoDeVram:
    """O maior uso de memória de vídeo dedicada deste processo, lido do contador do Windows (``typeperf``)
    a cada segundo enquanto o protocolo roda. Se o contador não existir, a medida fica vazia."""

    def __init__(self):
        self.pico = None
        self._processo = None
        try:
            contador = rf"\GPU Process Memory(pid_{os.getpid()}_*)\Dedicated Usage"
            self._processo = subprocess.Popen(["typeperf", contador, "-si", "1"], stdout=subprocess.PIPE,
                                              stderr=subprocess.DEVNULL, text=True,
                                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            threading.Thread(target=self._ler, daemon=True).start()
        except OSError:
            self._processo = None

    def _ler(self) -> None:
        for linha in self._processo.stdout:
            partes = [parte.strip().strip('"') for parte in linha.strip().split('","')]
            if len(partes) < 2 or "/" not in partes[0]:
                continue   # cabeçalho ou linha vazia
            try:
                total = sum(float(valor) for valor in partes[1:] if valor.strip()) / 2**20
            except ValueError:
                continue
            self.pico = max(self.pico or 0.0, total)

    def parar(self) -> float | None:
        if self._processo is not None:
            self._processo.terminate()
        return round(self.pico, 1) if self.pico else None


# ------------------------------------------------------------------ o protocolo
def _bytes_por_token(tok: Tokenizador) -> np.ndarray:
    return np.array([len(b) for b in tok.bytes_de] + [1], dtype=np.float64)   # o fim conta como 1 byte


def _ngramas(pasta: Path, sets: dict[str, np.ndarray], vocab: int, tokens_ngramas: int, avisar) -> dict:
    """As linhas de base, contadas uma vez numa amostra fixa do treino e guardadas."""
    cache = Path(pasta) / conjuntos.PASTA / f"ngramas-{tokens_ngramas}.json"
    chave = hashlib.sha256(b"".join(sets[n].tobytes() for n in sorted(sets))).hexdigest()
    if cache.exists():
        guardado = json.loads(cache.read_text(encoding="utf-8"))
        if guardado.get("chave") == chave:
            return guardado["perdas"]
    avisar(f"contando n-gramas em {tokens_ngramas / 1e6:.0f} mi de tokens do treino (uma vez só)...")
    treino = np.memmap(Path(pasta) / "treino.bin", dtype=np.uint16, mode="r")
    fatias = 20
    tamanho = tokens_ngramas // fatias
    passos = np.linspace(0, len(treino) - tamanho, fatias).astype(np.int64)
    amostra = np.concatenate([np.asarray(treino[p:p + tamanho]) for p in passos])
    del treino
    modelo = Ngramas(amostra, vocab)
    perdas = {nome: modelo.perdas(ids) for nome, ids in sets.items()}
    cache.write_text(json.dumps({"chave": chave, "tokens": tokens_ngramas, "perdas": perdas}, indent=1), encoding="utf-8")
    return perdas


def conjuntos_fixos(pasta: Path, tok: Tokenizador) -> dict[str, np.ndarray]:
    """Os conjuntos medidos: os fixos (se existirem) e a validação antiga sem o artigo cortado no começo."""
    pasta = Path(pasta)
    saida = conjuntos.carregar(pasta) if conjuntos.existe(pasta) else {}
    antiga = np.fromfile(pasta / "val.bin", dtype=np.uint16)
    saida["validacao_antiga"] = antiga[int(np.flatnonzero(antiga == tok.id_fim)[0]) + 1:]
    return saida


def perda_pelo_cerebro(cerebro, ids: np.ndarray, bytes_por_token: np.ndarray) -> dict:
    """O mesmo que ``perda_em``, pela interface do cérebro (``pontuar``)."""
    T = cerebro.cfg["contexto"]
    inicio = time.time()
    perdas = cerebro.pontuar(ids)
    segundos = time.time() - inicio
    n = len(perdas)
    alvos = np.asarray(ids[1:n * T + 1], dtype=np.int64).reshape(n, T)
    soma, tokens = float(perdas.sum()), n * T
    media = soma / tokens
    return {"perda": round(media, 5), "perplexidade": round(math.exp(media), 3),
            "bits_por_byte": round(soma / math.log(2) / float(bytes_por_token[alvos].sum()), 5), "tokens": tokens,
            "por_posicao": perdas.mean(0).round(5).tolist(), "_segundos": segundos}


def avaliar(arquivo_modelo: Path, pasta: Path, dispositivo="cpu", tokens_ngramas: int = 100_000_000,
            avisar=print) -> dict:
    from .interface import Especificacao, carregar

    pasta, arquivo_modelo = Path(pasta), Path(arquivo_modelo)
    tok = Tokenizador.carregar(pasta / inferencia.TOKENIZADOR)
    sets = conjuntos_fixos(pasta, tok)
    cerebro = carregar(Especificacao(arquivo_modelo, pasta / inferencia.TOKENIZADOR, motor="torch",
                                     dispositivo=dispositivo))
    modelo = cerebro._torch
    vram = _PicoDeVram() if getattr(dispositivo, "type", str(dispositivo)) == "privateuseone" else None
    bytes_por_token = _bytes_por_token(tok)
    relatorio = {"protocolo": VERSAO, "data": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "modelo": {"arquivo": str(arquivo_modelo), "sha256": conjuntos._sha256(arquivo_modelo),
                            "config": modelo.configuracao(), "parametros": modelo.numero_de_parametros()},
                 "conjuntos": {nome: {"tokens": int(len(ids)), "sha256": hashlib.sha256(ids.tobytes()).hexdigest()}
                               for nome, ids in sets.items()},
                 "perdas": {}}
    tokens_avaliados, segundos = 0, 0.0
    for nome, ids in sets.items():
        resultado = perda_pelo_cerebro(cerebro, ids, bytes_por_token)
        segundos += resultado.pop("_segundos")
        tokens_avaliados += resultado["tokens"]
        relatorio["perdas"][nome] = resultado
        avisar(f"{nome:<17} perda {resultado['perda']:.4f} | perplexidade {resultado['perplexidade']:.2f} | "
               f"{resultado['bits_por_byte']:.4f} bits por byte | {resultado['tokens']:,} tokens".replace(",", "."))
    principal = "teste" if "teste" in relatorio["perdas"] else "validacao_antiga"
    curva = np.array(relatorio["perdas"][principal]["por_posicao"])
    relatorio["por_faixa_de_posicao"] = {f"{a + 1}-{min(b, len(curva))}": round(float(curva[a:b].mean()), 4)
                                         for a, b in FAIXAS if a < len(curva)}
    relatorio["ngramas"] = _ngramas(pasta, sets, tok.tamanho, tokens_ngramas, avisar)

    vocabulario_fonte = sets.get("amostra_treino", sets["validacao_antiga"])
    contagem = Counter(_PALAVRA.findall(tok.decodificar(vocabulario_fonte.tolist()).lower()))
    vocabulario = {palavra for palavra, n in contagem.items() if n >= 2}
    amostras, tokens_por_segundo_geracao = gerar_amostras(cerebro, tok, vocabulario)
    relatorio["geracao"] = _resumo_da_geracao(amostras)
    relatorio["amostras"] = amostras
    relatorio["desempenho"] = {"dispositivo": str(dispositivo),
                               "tokens_por_segundo_avaliacao": round(tokens_avaliados / max(segundos, 1e-9)),
                               "tokens_por_segundo_geracao": round(tokens_por_segundo_geracao, 1),
                               "ram_pico_mb": _ram_de_pico_mb(), "vram_pico_mb": vram.parar() if vram else None}
    return relatorio


def so_perdas(arquivo_modelo: Path, pasta: Path, dispositivo="cpu", conjuntos=("teste",)) -> dict:
    """Só a perda (sem n-gramas, textos nem desempenho), nos conjuntos pedidos: para os pontos de uma curva."""
    from .interface import Especificacao, carregar

    pasta, arquivo_modelo = Path(pasta), Path(arquivo_modelo)
    tok = Tokenizador.carregar(pasta / inferencia.TOKENIZADOR)
    sets = conjuntos_fixos(pasta, tok)
    cerebro = carregar(Especificacao(arquivo_modelo, pasta / inferencia.TOKENIZADOR, motor="torch",
                                     dispositivo=dispositivo))
    perdas = {}
    for nome in conjuntos:
        resultado = perda_pelo_cerebro(cerebro, sets[nome], _bytes_por_token(tok))
        resultado.pop("_segundos")
        perdas[nome] = resultado
    return {"protocolo": VERSAO, "modelo": {"arquivo": arquivo_modelo.name, "sha256": cerebro.sha256,
                                            "parametros": cerebro.parametros}, "perdas": perdas}


def comparavel(relatorio: dict) -> dict:
    """O relatório sem o que muda de uma rodada para outra (data, velocidade, memória)."""
    return {chave: valor for chave, valor in relatorio.items() if chave not in ("data", "desempenho")}


def markdown(relatorio: dict) -> str:
    """O relatório para gente ler."""
    m = relatorio["modelo"]
    linhas = [f"# Protocolo de avaliação v{relatorio['protocolo']}", "",
              f"- **Modelo:** `{Path(m['arquivo']).name}` (SHA-256 `{m['sha256'][:16]}…`), "
              f"{m['parametros'] / 1e6:.2f} mi de parâmetros, {m['config']['camadas']} camadas, dimensão "
              f"{m['config']['dim']}, contexto {m['config']['contexto']}",
              f"- **Data:** {relatorio['data']}", "", "## Perda", "",
              "| Conjunto | Tokens | Perda (nats) | Perplexidade | Bits por byte | Unigrama | Bigrama | Trigrama |",
              "|---|---|---|---|---|---|---|---|"]
    for nome, p in relatorio["perdas"].items():
        n = relatorio["ngramas"].get(nome, {})
        linhas.append(f"| {nome} | {p['tokens']} | {p['perda']:.4f} | {p['perplexidade']:.2f} | {p['bits_por_byte']:.4f} | "
                      f"{n.get('unigrama', float('nan')):.3f} | {n.get('bigrama', float('nan')):.3f} | "
                      f"{n.get('trigrama', float('nan')):.3f} |")
    linhas += ["", "## Perda por posição na janela", "", "| Posições | " + " | ".join(relatorio["por_faixa_de_posicao"]) + " |",
               "|---|" + "---|" * len(relatorio["por_faixa_de_posicao"]),
               "| Perda | " + " | ".join(f"{v:.3f}" for v in relatorio["por_faixa_de_posicao"].values()) + " |",
               "", "## Geração (médias)", "",
               "| Modo | Repetição de trios | Pares distintos | Palavras que existem | No assunto | Tokens |",
               "|---|---|---|---|---|---|"]
    for modo, g in relatorio["geracao"].items():
        linhas.append(f"| {modo} | {g['repeticao_3']:.1%} | {g['distintos_2']:.1%} | {g['palavras_que_existem']:.1%} | "
                      f"{g['no_assunto']:.0%} | {g['tokens']:.0f} |")
    linhas += ["", "## Textos", ""]
    for a in relatorio["amostras"]:
        if a["modo"] == "sorteio" and a["semente"] != 1:
            continue
        texto = re.sub(r"\s+", " ", a["texto"]).rstrip()   # junta as linhas, mas guarda o espaço do começo
        linhas.append(f"- **{a['modo']}** · *{a['comeco']}*{'' if texto[:1] in ',.;:' else ' '}{texto.lstrip()}")
    d = relatorio.get("desempenho", {})
    linhas += ["", "## Desempenho", "",
               f"- Dispositivo: {d.get('dispositivo')}; avaliação {d.get('tokens_por_segundo_avaliacao')} tokens/s; "
               f"geração (NumPy, um a um) {d.get('tokens_por_segundo_geracao')} tokens/s",
               f"- RAM de pico do processo: {d.get('ram_pico_mb')} MB; VRAM de pico (dedicada): "
               f"{d.get('vram_pico_mb', d.get('vram_mb'))} MB"]
    return "\n".join(linhas) + "\n"


def salvar(relatorio: dict, pasta_saida: Path) -> Path:
    pasta_saida = Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)
    (pasta_saida / "relatorio.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=1), encoding="utf-8")
    (pasta_saida / "relatorio.md").write_text(markdown(relatorio), encoding="utf-8")
    return pasta_saida
