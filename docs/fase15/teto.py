"""Fase 1.5: a corrida até o teto do mini.

Parte do fim do melhor braço das comparações (o checkpoint carrega a posição da passada)
e treina com tudo o que ajudou, até a validação parar de melhorar de forma mensurável
(``--parar-se-estagnar``) ou o tempo combinado acabar. Roda numa pasta própria
(``dados/fase15/teto/cerebro``), com o ``treino.bin`` ligado por hard link.

    python docs/fase15/teto.py --braco A3 --horas 4.8
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from ablacao import CEREBRO, PYTHON, preparar  # noqa: E402


def main() -> int:
    analisador = argparse.ArgumentParser()
    analisador.add_argument("--braco", required=True)
    analisador.add_argument("--horas", type=float, required=True)
    analisador.add_argument("--opcoes", default="--ao-continuar retomar --amostragem passada --corte 3.0 "
                                                "--parar-se-estagnar 6 --melhora-minima 0.002")
    args = analisador.parse_args()
    origem = RAIZ / "dados" / "fase15" / "bracos" / args.braco / "cerebro"
    pasta = RAIZ / "dados" / "fase15" / "teto" / "cerebro"
    preparar(pasta, origem / "checkpoint.pt")
    for nome in ("modelo.npz", "modelo.npz.sha256", "checkpoint.pt.sha256"):
        if (origem / nome).exists():
            shutil.copy2(origem / nome, pasta / nome)
    comando = [str(PYTHON), "-m", "kernel", "cerebro", "treinar", "--horas", str(args.horas), *args.opcoes.split()]
    print(" ".join(comando[3:]), flush=True)
    return subprocess.run(comando, cwd=RAIZ, env={**os.environ, "KERNEL_DADOS": str(pasta.parent),
                                                  "PYTHONIOENCODING": "utf-8"}).returncode


if __name__ == "__main__":
    sys.exit(main())
