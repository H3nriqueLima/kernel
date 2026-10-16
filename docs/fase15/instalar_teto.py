"""Fase 1.5: instala o modelo do teto como o cérebro do serviço (com o serviço desligado).

1. faz uma cópia de segurança dos dados (``python -m kernel copia fazer``): o cérebro de
   antes fica nela, para dar para voltar;
2. copia o ``modelo.npz`` do teto (o de melhor validação) e o checkpoint final, com as
   impressões digitais, para ``dados/cerebro``;
3. confere que o serviço consegue carregar o modelo e que o treino consegue retomar o checkpoint.

    python docs/fase15/instalar_teto.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))


def main() -> int:
    from kernel.cerebro import inferencia
    from kernel.cerebro.treinar import carregar_checkpoint, confere

    teto = RAIZ / "dados" / "fase15" / "teto" / "cerebro"
    cerebro = RAIZ / "dados" / "cerebro"
    saude = subprocess.run([str(RAIZ / ".venv" / "Scripts" / "python.exe"), "-m", "kernel", "estado"], cwd=RAIZ,
                           capture_output=True, text=True, encoding="utf-8")
    if "rodando" in saude.stdout and "não está" not in saude.stdout:
        print("Desligue o serviço antes de instalar o cérebro novo.")
        return 1
    for nome in ("modelo.npz", "checkpoint.pt"):
        if confere(teto / nome) is not True:
            print(f"{nome} do teto não confere com a impressão digital: nada foi instalado")
            return 1
    copia = subprocess.run([str(RAIZ / ".venv" / "Scripts" / "python.exe"), "-m", "kernel", "copia", "fazer"], cwd=RAIZ,
                           capture_output=True, text=True, encoding="utf-8")
    print(copia.stdout.strip())
    if copia.returncode != 0:
        print("a cópia de segurança falhou: nada foi instalado")
        return 1
    for nome in ("modelo.npz", "modelo.npz.sha256", "checkpoint.pt", "checkpoint.pt.sha256"):
        shutil.copy2(teto / nome, cerebro / nome)
    cerebro_novo = inferencia.carregar_de(cerebro)
    salvo = carregar_checkpoint(cerebro, avisar=print)
    print(f"instalado: {cerebro_novo.descricao}; checkpoint no passo {salvo['passo']} "
          f"(passada: época {salvo['amostrador']['epoca']}, posição {salvo['amostrador']['posicao']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
