"""O cérebro no dia a dia: o mesmo GPT de ``gpt.py``, refeito só com NumPy.

O serviço não precisa carregar o PyTorch (centenas de MB de RAM) para conversar:
os pesos treinados são exportados para ``modelo.npz`` e as contas da rede são
repetidas aqui com matrizes do NumPy. É a "inferência própria" do plano.

Duas coisas fazem a geração ser rápida e legível:

- **memória de chaves e valores**: para escrever o próximo pedaço de palavra, só
  o pedaço novo passa pela rede; o que a atenção precisa dos anteriores (as
  chaves e os valores de cada camada) fica guardado. Sem isso, cada pedaço novo
  refaria a conta do texto inteiro;
- **sorteio com critério**: além da temperatura e do ``top_k``, ele pode cortar a
  cauda de opções improváveis (``top_p``), desanimar pedaços que acabou de usar
  (``repeticao``) e proibir que um trio de pedaços se repita. É o que impede o
  "grupos de grupos de grupos de grupos".
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np

from .tokenizador import Tokenizador

MODELO = "modelo.npz"
TOKENIZADOR = "tokenizador.json"


def exportar(modelo, arquivo: Path) -> None:
    """Grava os pesos de um GPT do PyTorch num .npz que este módulo sabe ler."""
    pesos = {nome: p.detach().cpu().numpy().astype(np.float32) for nome, p in modelo.state_dict().items()}
    temporario = Path(arquivo).with_suffix(".tmp.npz")
    np.savez(temporario, _config=np.array(json.dumps(modelo.configuracao())), **pesos)
    temporario.replace(arquivo)


def _norma(x, ganho, vies):
    media = x.mean(-1, keepdims=True)
    variancia = ((x - media) ** 2).mean(-1, keepdims=True)
    return ganho * (x - media) / np.sqrt(variancia + 1e-5) + vies


def _gelu(x):
    return 0.5 * x * (1.0 + np.tanh(0.7978845608 * (x + 0.044715 * x * x * x)))


def _softmax(x):
    e = np.exp(x - x.max(-1, keepdims=True))
    return e / e.sum(-1, keepdims=True)


class CerebroNumpy:
    def __init__(self, pesos: dict[str, np.ndarray], cfg: dict, tokenizador: Tokenizador):
        self.p = pesos
        self.cfg = cfg
        self.tokenizador = tokenizador
        self.parametros = int(sum(v.size for v in pesos.values()))
        self.descricao = (f"mini GPT de {self.parametros / 1e6:.1f} milhões de parâmetros "
                          f"({cfg['camadas']} camadas, contexto {cfg['contexto']})")
        self._sorteio = np.random.default_rng()

    # ------------------------------------------------------- a rede, inteira
    def logits(self, ids: list[int]) -> np.ndarray:
        """Notas para o próximo token em cada posição: matriz (len(ids), vocab). Refaz a conta toda."""
        p, T, C, H = self.p, len(ids), self.cfg["dim"], self.cfg["cabecas"]
        x = p["emb_token"][ids] + p["emb_posicao"][:T]
        mascara = np.triu(np.full((T, T), -1e9, dtype=np.float32), k=1)
        for i in range(self.cfg["camadas"]):
            b = f"blocos.{i}."
            h = _norma(x, p[b + "norma1.ganho"], p[b + "norma1.vies"])
            qkv = h @ p[b + "atencao.qkv.peso"].T + p[b + "atencao.qkv.vies"]
            # (T, C) -> (cabeças, T, C / cabeças)
            q, k, v = (parte.reshape(T, H, C // H).transpose(1, 0, 2) for parte in np.split(qkv, 3, axis=-1))
            pesos = _softmax(q @ k.transpose(0, 2, 1) / math.sqrt(C // H) + mascara)
            y = (pesos @ v).transpose(1, 0, 2).reshape(T, C)
            x = x + y @ p[b + "atencao.saida.peso"].T + p[b + "atencao.saida.vies"]
            h = _norma(x, p[b + "norma2.ganho"], p[b + "norma2.vies"])
            h = _gelu(h @ p[b + "sobe.peso"].T + p[b + "sobe.vies"])
            x = x + h @ p[b + "desce.peso"].T + p[b + "desce.vies"]
        x = _norma(x, p["norma_final.ganho"], p["norma_final.vies"])
        return x @ p["emb_token"].T

    # ------------------------------------------- a rede, um pedaço por vez
    def _memoria_nova(self) -> list[tuple[np.ndarray, np.ndarray]]:
        """Um lugar por camada para guardar as chaves e os valores de cada pedaço já lido."""
        H, d, T = self.cfg["cabecas"], self.cfg["dim"] // self.cfg["cabecas"], self.cfg["contexto"]
        return [(np.zeros((H, T, d), dtype=np.float32), np.zeros((H, T, d), dtype=np.float32))
                for _ in range(self.cfg["camadas"])]

    def _avancar(self, token: int, posicao: int, memoria: list[tuple[np.ndarray, np.ndarray]]) -> np.ndarray:
        """Passa UM pedaço pela rede, aproveitando o que já foi calculado para os anteriores.
        Devolve as notas para o pedaço seguinte (o mesmo que a última linha de ``logits``)."""
        p, C, H = self.p, self.cfg["dim"], self.cfg["cabecas"]
        d = C // H
        x = p["emb_token"][token] + p["emb_posicao"][posicao]
        for i in range(self.cfg["camadas"]):
            b = f"blocos.{i}."
            h = _norma(x, p[b + "norma1.ganho"], p[b + "norma1.vies"])
            qkv = h @ p[b + "atencao.qkv.peso"].T + p[b + "atencao.qkv.vies"]
            q, k, v = (parte.reshape(H, d) for parte in np.split(qkv, 3))
            chaves, valores = memoria[i]
            chaves[:, posicao], valores[:, posicao] = k, v
            # a atenção do pedaço novo sobre todos os anteriores e ele mesmo: (cabeças, posicao + 1)
            pesos = _softmax(np.einsum("htd,hd->ht", chaves[:, :posicao + 1], q) / math.sqrt(d))
            y = np.einsum("ht,htd->hd", pesos, valores[:, :posicao + 1]).reshape(C)
            x = x + y @ p[b + "atencao.saida.peso"].T + p[b + "atencao.saida.vies"]
            h = _norma(x, p[b + "norma2.ganho"], p[b + "norma2.vies"])
            h = _gelu(h @ p[b + "sobe.peso"].T + p[b + "sobe.vies"])
            x = x + h @ p[b + "desce.peso"].T + p[b + "desce.vies"]
        x = _norma(x, p["norma_final.ganho"], p["norma_final.vies"])
        return x @ p["emb_token"].T

    def _escolher(self, notas: np.ndarray, ids: list[int], temperatura: float, top_k: int, top_p: float,
                  repeticao: float) -> int:
        """Sorteia o próximo pedaço a partir das notas."""
        notas = notas.astype(np.float64)
        if repeticao > 1.0:   # o que ele acabou de escrever fica menos provável de sair de novo
            recentes = list(set(ids[-64:]))
            notas[recentes] = np.where(notas[recentes] > 0, notas[recentes] / repeticao, notas[recentes] * repeticao)
            if len(ids) >= 3:  # e um trio de pedaços que já saiu não sai igual outra vez
                a, b = ids[-2], ids[-1]
                for i in range(len(ids) - 2):
                    if ids[i] == a and ids[i + 1] == b:
                        notas[ids[i + 2]] = -np.inf
        notas = notas / max(temperatura, 1e-6)
        if top_k and top_k < notas.size:
            corte = np.partition(notas, -top_k)[-top_k]
            notas[notas < corte] = -np.inf
        chances = _softmax(notas)
        if 0.0 < top_p < 1.0:  # fica o menor grupo de opções que soma top_p; a cauda improvável sai
            ordem = np.argsort(-chances)
            acumulado = np.cumsum(chances[ordem])
            fora = ordem[int(np.searchsorted(acumulado, top_p)) + 1:]
            chances[fora] = 0.0
            chances /= chances.sum()
        return int(self._sorteio.choice(chances.size, p=chances))

    def gerar(self, ids: list[int], quantos: int, temperatura: float = 0.8, top_k: int = 40, top_p: float = 1.0,
              repeticao: float = 1.0) -> list[int]:
        ids = list(ids)
        contexto = self.cfg["contexto"]
        memoria, posicao, notas = self._memoria_nova(), 0, None
        for token in ids[-(contexto - 1):]:           # lê o começo que você deu
            notas = self._avancar(token, posicao, memoria)
            posicao += 1
        for _ in range(quantos):
            proximo = self._escolher(notas, ids, temperatura, top_k, top_p, repeticao)
            if proximo == self.tokenizador.id_fim:
                break
            ids.append(proximo)
            if posicao >= contexto:                   # a janela encheu: recomeça com a metade mais recente
                memoria, posicao = self._memoria_nova(), 0
                for token in ids[-(contexto // 2):-1]:
                    self._avancar(token, posicao, memoria)
                    posicao += 1
            notas = self._avancar(proximo, posicao, memoria)
            posicao += 1
        return ids

    def continuar(self, texto: str, quantos: int = 60, temperatura: float = 0.8, top_k: int = 40, top_p: float = 1.0,
                  repeticao: float = 1.0) -> str:
        """Devolve só o que o cérebro escreveu depois de ``texto``."""
        entrada = self.tokenizador.codificar(texto) or [self.tokenizador.id_fim]
        saida = self.gerar(entrada, quantos, temperatura, top_k, top_p, repeticao)
        return self.tokenizador.decodificar(saida[len(entrada):])

    def responder(self, texto: str, quantos: int = 60, temperatura: float = 0.8, top_k: int = 40) -> str:
        """Continuação para mostrar a você: sem repetição em laço e aparada na última frase completa."""
        bruto = self.continuar(texto, quantos, temperatura, top_k, top_p=0.92, repeticao=1.2)
        bruto = " ".join(bruto.split())               # o texto de treino tem quebras de linha de artigo
        fim = max(bruto.rfind("."), bruto.rfind("!"), bruto.rfind("?"))
        return bruto[:fim + 1] if fim > 20 else bruto

    def perda(self, ids: list[int]) -> float:
        """Entropia cruzada média ao prever cada pedaço de ``ids`` a partir dos anteriores."""
        notas = self.logits(ids[:-1]).astype(np.float64)
        notas -= notas.max(-1, keepdims=True)
        log_chances = notas - np.log(np.exp(notas).sum(-1, keepdims=True))
        return float(-log_chances[np.arange(len(ids) - 1), ids[1:]].mean())


def carregar_de(pasta: Path) -> CerebroNumpy | None:
    modelo, tokenizador = Path(pasta) / MODELO, Path(pasta) / TOKENIZADOR
    if not (modelo.exists() and tokenizador.exists()):
        return None
    with np.load(modelo) as dados:
        cfg = json.loads(str(dados["_config"]))
        pesos = {nome: dados[nome] for nome in dados.files if nome != "_config"}
    return CerebroNumpy(pesos, cfg, Tokenizador.carregar(tokenizador))


def carregar(cfg) -> CerebroNumpy | None:
    """O cérebro treinado em ``dados/cerebro``, ou None se ainda não existe."""
    return carregar_de(cfg.pasta("cerebro"))


def historico(pasta: Path) -> dict | None:
    """O que o diário de treino (``treino.csv``) conta: passos, horas, a perda de agora e a melhor."""
    arquivo = Path(pasta) / "treino.csv"
    if not arquivo.exists():
        return None
    with open(arquivo, newline="", encoding="utf-8") as f:
        linhas = [linha for linha in csv.DictReader(f) if linha.get("passo")]
    if not linhas:
        return None
    try:
        ultima = linhas[-1]
        segundos = float(ultima["segundos"])
        # pedaços lidos: a velocidade de cada trecho vezes a duração dele
        tokens, antes = 0.0, 0.0
        for linha in linhas:
            agora = float(linha["segundos"])
            tokens += float(linha["tokens_por_segundo"]) * max(agora - antes, 0.0)
            antes = agora
        return {"passos": int(ultima["passo"]), "horas": segundos / 3600, "perda": float(ultima["perda_val"]),
                "melhor": min(float(linha["perda_val"]) for linha in linhas), "tokens": tokens,
                "primeira": float(linhas[0]["perda_val"]), "pontos": len(linhas)}
    except (KeyError, ValueError):
        return None


def avaliar(cerebro: CerebroNumpy, pasta: Path, janelas: int = 24, semente: int = 0) -> dict | None:
    """Mede o cérebro em texto que ele nunca viu (``val.bin``): perda média e perplexidade."""
    arquivo = Path(pasta) / "val.bin"
    if not arquivo.exists():
        return None
    dados = np.memmap(arquivo, dtype=np.uint16, mode="r")
    tamanho = cerebro.cfg["contexto"] + 1
    if len(dados) <= tamanho:
        return None
    sorteio = np.random.default_rng(semente)
    perdas = [cerebro.perda(dados[i:i + tamanho].astype(np.int64).tolist())
              for i in sorteio.integers(0, len(dados) - tamanho, janelas)]
    media = float(np.mean(perdas))
    return {"perda": media, "perplexidade": math.exp(media), "janelas": janelas, "tokens": janelas * (tamanho - 1)}
