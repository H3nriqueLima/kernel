"""Fase 1: os experimentos de diagnóstico do treino, para refazer.

A partir de um mesmo checkpoint, compara dois jeitos de continuar o treino e mede
a estabilidade:

- ``reaquecer``: o que cada sessão nova fazia até a v0.5.1 — a taxa sobe de novo
  até 3e-4 (metade da taxa inicial) e desce em cosseno até o fim;
- ``baixa``: continua com a taxa baixa e constante (3e-5, onde as sessões terminam);
- ``baixa_de_novo``: repete o começo de ``baixa`` com a mesma semente, para ver se
  o treino é reprodutível na placa (DirectML) e quanto as medidas oscilam.

Cada execução mede a validação fixa (as mesmas 320 janelas) de tempos em tempos e,
no fim, a validação inteira. Os resultados vão para ``--saida`` em JSON.

    python docs/fase1/experimentos.py --checkpoint dados/fase1/checkpoint-final.pt --saida dados/fase1/experimentos
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from kernel.cerebro import conjuntos  # noqa: E402
from kernel.cerebro.dados import Lotes  # noqa: E402
from kernel.cerebro.dispositivo import escolher  # noqa: E402
from kernel.cerebro.gpt import GPT, ConfigGPT  # noqa: E402
from kernel.cerebro.otimizador import AdamW  # noqa: E402
from kernel.cerebro.protocolo import _bytes_por_token, perda_em  # noqa: E402
from kernel.cerebro.tokenizador import Tokenizador  # noqa: E402
from kernel.cerebro.treinar import avaliar, janelas_fixas  # noqa: E402


def taxa_reaquecer(passo: int, total: int, pico: float = 3e-4, aquecimento: int = 200) -> float:
    if passo < aquecimento:
        return pico * (passo + 1) / aquecimento
    progresso = (passo - aquecimento) / max(1, total - aquecimento)
    return pico * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * progresso)))


def rodar(nome: str, checkpoint: Path, pasta: Path, taxa, passos: int, avaliar_cada: int, dispositivo,
          semente: int = 777, avisar=print) -> dict:
    salvo = torch.load(checkpoint, map_location="cpu", weights_only=True)
    modelo = GPT(ConfigGPT(**salvo["config"]))
    modelo.load_state_dict(salvo["modelo"])
    modelo.to(dispositivo).train()
    otimizador = AdamW(modelo.parameters(), decaimento=0.1)
    otimizador.carregar_estado(salvo["otimizador"])
    torch.manual_seed(semente)
    contexto = modelo.cfg.contexto
    lotes = Lotes(pasta / "treino.bin", contexto, 16, semente=semente)
    arquivo_val = pasta / conjuntos.PASTA / conjuntos.ARQUIVOS["validacao"]
    janelas = janelas_fixas(arquivo_val, contexto, 320)

    def medir() -> float:
        modelo.eval()
        perda = avaliar(modelo, janelas, dispositivo)
        modelo.train()
        return perda

    pontos = [{"passo": 0, "validacao": medir()}]
    perdas, normas = [], []
    inicio = time.time()
    for passo in range(passos):
        for _ in range(2):   # acumular 2 lotes, como o treino de verdade
            x, y = lotes.pegar(dispositivo)
            _, perda = modelo(x, y)
            (perda / 2).backward()
        normas.append(otimizador.cortar_gradiente(1.0))
        otimizador.passo(taxa(passo))
        otimizador.zerar()
        perdas.append(float(perda))
        if (passo + 1) % avaliar_cada == 0:
            ponto = {"passo": passo + 1, "validacao": medir(), "treino": float(np.mean(perdas[-avaliar_cada:])),
                     "taxa": taxa(passo), "gradiente_medio": float(np.mean(normas[-avaliar_cada:])),
                     "gradiente_maximo": float(np.max(normas[-avaliar_cada:])),
                     "cortados": float(np.mean(np.array(normas[-avaliar_cada:]) > 1.0))}
            pontos.append(ponto)
            avisar(f"{nome}: passo {passo + 1} | validação {ponto['validacao']:.4f} | treino {ponto['treino']:.4f} | "
                   f"taxa {ponto['taxa']:.1e} | gradiente {ponto['gradiente_medio']:.2f} | "
                   f"{(time.time() - inicio) / 60:.1f} min")
    tok = Tokenizador.carregar(pasta / "tokenizador.json")
    modelo.eval()
    inteira = perda_em(modelo, np.fromfile(arquivo_val, dtype=np.uint16), _bytes_por_token(tok), dispositivo)
    inteira.pop("por_posicao")
    inteira.pop("_segundos")
    return {"nome": nome, "passos": passos, "semente": semente, "pontos": pontos, "validacao_inteira": inteira,
            "perdas_por_passo": perdas, "normas_por_passo": normas, "minutos": (time.time() - inicio) / 60}


def main() -> int:
    analisador = argparse.ArgumentParser()
    analisador.add_argument("--checkpoint", required=True)
    analisador.add_argument("--saida", required=True)
    analisador.add_argument("--pasta", default=str(RAIZ / "dados" / "cerebro"))
    analisador.add_argument("--passos", type=int, default=1100)
    analisador.add_argument("--repetir", type=int, default=300)
    analisador.add_argument("--avaliar-cada", type=int, default=100)
    analisador.add_argument("--dispositivo", default="auto")
    analisador.add_argument("--so", default="", help="rodar só estes, separados por vírgula")
    args = analisador.parse_args()
    dispositivo, descricao = escolher(args.dispositivo)
    print("dispositivo:", descricao)
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    execucoes = {
        "baixa": (lambda p: 3e-5, args.passos),
        "baixa_de_novo": (lambda p: 3e-5, args.repetir),
        "reaquecer": (lambda p: taxa_reaquecer(p, args.passos), args.passos),
    }
    escolhidas = [n for n in execucoes if not args.so or n in args.so.split(",")]
    for nome in escolhidas:
        taxa, passos = execucoes[nome]
        resultado = rodar(nome, Path(args.checkpoint), Path(args.pasta), taxa, passos, args.avaliar_cada, dispositivo)
        (saida / f"{nome}.json").write_text(json.dumps(resultado, indent=1), encoding="utf-8")
        print(f"{nome}: validação inteira {resultado['validacao_inteira']['perda']:.4f} em {resultado['minutos']:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
