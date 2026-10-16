"""Fase 2: o limite real da RX 570 para cada tamanho, com testes curtos.

Para cada tamanho, um treino curto de verdade (os dados reais, a passada sem repetição,
o AdamW e o corte do treino) com o maior lote que couber. Se faltar memória de vídeo, o
lote cai pela metade e o acúmulo dobra, mantendo os mesmos 8.192 tokens por passo (a
mesma régua para todos). Mede:

- tokens por segundo no treino (depois dos primeiros passos, que pagam a preparação);
- VRAM de pico (contador do Windows) e RAM de pico do processo;
- estabilidade: a perda é finita e cai nos passos medidos;
- a velocidade de geração na CPU (NumPy, um token por vez, como o serviço gera), com
  os pesos depois do teste. O portão da Fase 2 pede pelo menos 20 tokens por segundo.

Cada medida roda num processo separado: o DirectML guarda a memória de vídeo até o
processo sair, e uma medida seguraria a da seguinte.

    python docs/fase2/medir_placa.py --tamanhos mini medio pequeno grande
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
PYTHON = RAIZ / ".venv" / "Scripts" / "python.exe"
CEREBRO = RAIZ / "dados" / "cerebro"
SAIDA = RAIZ / "dados" / "fase2" / "placa"
TOKENS_POR_PASSO = 8192


def medir_um(tamanho: str, lote: int, passos: int) -> dict:
    """Roda dentro do processo filho: um treino curto e as medidas."""
    import numpy as np
    import torch

    from kernel.cerebro import inferencia
    from kernel.cerebro.dados import Passada
    from kernel.cerebro.dispositivo import escolher
    from kernel.cerebro.gpt import criar
    from kernel.cerebro.interface import Especificacao, carregar
    from kernel.cerebro.otimizador import AdamW
    from kernel.cerebro.protocolo import _PicoDeVram, _ram_de_pico_mb
    from kernel.cerebro.tokenizador import Tokenizador

    tok = Tokenizador.carregar(CEREBRO / "tokenizador.json")
    dispositivo, descricao = escolher("auto")
    torch.manual_seed(0)
    modelo = criar(tamanho, tok.tamanho).to(dispositivo)
    contexto = modelo.cfg.contexto
    acumular = TOKENS_POR_PASSO // (lote * contexto)
    otimizador = AdamW(modelo.parameters(), decaimento=0.1)
    dados = Passada(CEREBRO / "treino.bin", contexto, lote, tok.id_fim, semente=7)
    vram = _PicoDeVram()
    perdas, normas, inicio = [], [], None
    for passo in range(passos):
        if passo == 3:
            inicio = time.time()
        for _ in range(acumular):
            x, y = dados.pegar(dispositivo)
            _, perda = modelo(x, y)
            (perda / acumular).backward()
        normas.append(otimizador.cortar_gradiente(3.0))
        otimizador.passo(6e-4 * min(1.0, (passo + 1) / 20))
        otimizador.zerar()
        perdas.append(float(perda))
    segundos = time.time() - inicio
    vram_pico = vram.parar()
    with __import__("tempfile").TemporaryDirectory() as pasta:
        arquivo = Path(pasta) / inferencia.MODELO
        inferencia.exportar(modelo.cpu(), arquivo)
        cerebro = carregar(Especificacao(arquivo, CEREBRO / "tokenizador.json"))
        geracao = cerebro.velocidade_de_geracao(tokens=250)   # até a janela quase cheia
    return {"tamanho": tamanho, "parametros": modelo.numero_de_parametros(), "lote": lote, "acumular": acumular,
            "dispositivo": descricao, "tokens_por_segundo": round((passos - 3) * TOKENS_POR_PASSO / segundos),
            "segundos_por_passo": round(segundos / (passos - 3), 3), "vram_pico_mb": vram_pico,
            "ram_pico_mb": _ram_de_pico_mb(), "perda_inicio": round(float(np.mean(perdas[:5])), 3),
            "perda_fim": round(float(np.mean(perdas[-5:])), 3), "perda_finita": all(math.isfinite(p) for p in perdas),
            "norma_maxima": round(max(normas), 3), "geracao_cpu_tokens_por_segundo": round(geracao, 1)}


def main() -> int:
    analisador = argparse.ArgumentParser()
    analisador.add_argument("--tamanhos", nargs="+", default=["mini", "medio", "pequeno", "grande"])
    analisador.add_argument("--passos", type=int, default=40)
    analisador.add_argument("--um", nargs=2, metavar=("TAMANHO", "LOTE"))
    args = analisador.parse_args()
    if args.um:   # o processo filho
        resultado = medir_um(args.um[0], int(args.um[1]), args.passos)
        print("RESULTADO " + json.dumps(resultado), flush=True)
        return 0
    SAIDA.mkdir(parents=True, exist_ok=True)
    for tamanho in args.tamanhos:
        for lote in (16, 8, 4, 2, 1):
            inicio = time.time()
            processo = subprocess.run([str(PYTHON), __file__, "--um", tamanho, str(lote), "--passos", str(args.passos)],
                                      cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                      env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            linha = next((l for l in processo.stdout.splitlines() if l.startswith("RESULTADO ")), None)
            if linha:
                resultado = json.loads(linha[len("RESULTADO "):])
                (SAIDA / f"{tamanho}-lote{lote}.json").write_text(json.dumps(resultado, indent=1), encoding="utf-8")
                print(f"{time.strftime('%H:%M:%S')} {tamanho} lote {lote}: {json.dumps(resultado)}", flush=True)
                break
            erro = (processo.stdout + processo.stderr)[-400:].replace("\n", " ")
            memoria = "memory" in erro.lower() or "memória" in erro.lower()
            print(f"{time.strftime('%H:%M:%S')} {tamanho} lote {lote}: {'não cabe' if memoria else 'falhou'} "
                  f"({time.time() - inicio:.0f} s): {erro[-200:]}", flush=True)
            if not memoria:
                break
    print("fim", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
