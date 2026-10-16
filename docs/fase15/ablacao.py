"""Fase 1.5: mede cada mudança do treino, uma de cada vez, a partir do mesmo checkpoint.

Cada braço é uma sessão de treino de verdade (``python -m kernel cerebro treinar``), numa
pasta própria (``dados/fase15/bracos/NOME/cerebro``) com uma cópia do checkpoint de
partida e o ``treino.bin`` ligado por hard link (não ocupa espaço). No fim, os pesos do
último passo são medidos pelo protocolo no conjunto de teste fixo.

    python docs/fase15/ablacao.py --checkpoint dados/fase1/checkpoint-49039.pt --passos 1100 \\
        "A0=--ao-continuar reaquecer" "A1=--ao-continuar retomar" "R=--ao-continuar retomar --semente 1338"
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

PYTHON = RAIZ / ".venv" / "Scripts" / "python.exe"
CEREBRO = RAIZ / "dados" / "cerebro"


def preparar(pasta: Path, checkpoint: Path) -> None:
    """A pasta de um braço: o checkpoint de partida e os dados (ligados, não copiados)."""
    if pasta.exists():
        shutil.rmtree(pasta)
    (pasta / "avaliacao").mkdir(parents=True)
    for nome in ("treino.bin", "val.bin"):
        os.link(CEREBRO / nome, pasta / nome)
    for arquivo in (CEREBRO / "avaliacao").iterdir():
        if arquivo.suffix in (".bin", ".json") and not arquivo.name.startswith("ngramas"):
            os.link(arquivo, pasta / "avaliacao" / arquivo.name)
    shutil.copy2(CEREBRO / "tokenizador.json", pasta / "tokenizador.json")
    shutil.copy2(checkpoint, pasta / "checkpoint.pt")


def medir(pasta: Path, saida: Path, avisar) -> dict:
    """Os pesos do último passo do braço, medidos pelo protocolo."""
    import torch

    from kernel.cerebro import inferencia, protocolo
    from kernel.cerebro.dispositivo import escolher
    from kernel.cerebro.gpt import GPT, ConfigGPT

    salvo = torch.load(pasta / "checkpoint.pt", map_location="cpu", weights_only=True)
    modelo = GPT(ConfigGPT(**salvo["config"]))
    modelo.load_state_dict(salvo["modelo"])
    final = pasta / "final.npz"
    inferencia.exportar(modelo, final)
    dispositivo, descricao = escolher("auto")
    relatorio = protocolo.avaliar(final, CEREBRO, dispositivo, avisar=avisar)
    relatorio["modelo"]["arquivo"] = f"{pasta.parent.name}-passo-{salvo['passo']}.npz"
    relatorio["desempenho"]["dispositivo"] = descricao
    protocolo.salvar(relatorio, saida)
    return relatorio


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--medir":
        medir(Path(sys.argv[2]), Path(sys.argv[3]), lambda _: None)
        return 0
    analisador = argparse.ArgumentParser()
    analisador.add_argument("--checkpoint", required=True)
    analisador.add_argument("--passos", type=int, default=1100)
    analisador.add_argument("--saida", default=str(RAIZ / "docs" / "fase15" / "bracos"))
    analisador.add_argument("bracos", nargs="+", help='"NOME=opções do cerebro treinar"')
    args = analisador.parse_args()
    raiz_dos_bracos = RAIZ / "dados" / "fase15" / "bracos"

    def avisar(texto: str) -> None:
        print(f"{time.strftime('%H:%M:%S')} {texto}", flush=True)

    for braco in args.bracos:
        nome, opcoes = braco.split("=", 1)
        pasta = raiz_dos_bracos / nome / "cerebro"
        preparar(pasta, Path(args.checkpoint))
        comando = [str(PYTHON), "-m", "kernel", "cerebro", "treinar", "--sessao-passos", str(args.passos), *opcoes.split()]
        avisar(f"{nome}: {' '.join(comando[3:])}")
        inicio = time.time()
        resultado = subprocess.run(comando, cwd=RAIZ, env={**os.environ, "KERNEL_DADOS": str(pasta.parent),
                                                             "PYTHONIOENCODING": "utf-8"},
                                   capture_output=True, text=True, encoding="utf-8", errors="replace")
        (pasta / "saida.txt").write_text(resultado.stdout + resultado.stderr, encoding="utf-8")
        if resultado.returncode != 0:
            avisar(f"{nome}: o treino falhou (código {resultado.returncode}); veja {pasta / 'saida.txt'}")
            continue
        avisar(f"{nome}: treino em {(time.time() - inicio) / 60:.1f} min; medindo...")
        # a medida roda noutro processo: o DirectML guarda a VRAM até o processo sair, e o treino do
        # braço seguinte ficaria sem memória de vídeo (aconteceu: 8 vezes mais lento)
        subprocess.run([str(PYTHON), __file__, "--medir", str(pasta), str(Path(args.saida) / nome)], cwd=RAIZ,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"}, check=True)
        relatorio = json.loads((Path(args.saida) / nome / "relatorio.json").read_text(encoding="utf-8"))
        perdas = {conjunto: p["perda"] for conjunto, p in relatorio["perdas"].items()}
        avisar(f"{nome}: {json.dumps(perdas)}")
    avisar("fim")
    return 0


if __name__ == "__main__":
    sys.exit(main())
