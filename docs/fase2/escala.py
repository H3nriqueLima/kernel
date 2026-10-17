"""Fase 2: o treino de comparação de escala (ver plano.md).

Cada tamanho treina do zero numa pasta própria (``dados/fase2/escala/NOME/cerebro``), com o
``treino.bin`` ligado por hard link, pelo próprio ``python -m kernel cerebro treinar``. Os
pesos são guardados nos marcos (a cada 10 mi de tokens). Depois do treino, cada marco é
medido no teste fixo e o último passa pelo protocolo completo, sempre num processo à parte
(o DirectML segura a memória de vídeo até o processo sair).

    python docs/fase2/escala.py --tamanhos mini medio pequeno grande
    python docs/fase2/escala.py --tamanhos pequeno --semente 2026     (a segunda semente do finalista)
    python docs/fase2/escala.py --tamanhos grande --continuar         (continua um treino de comparação parado no
                                                                       meio, com a taxa que ele teria sem a parada)
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
PASSOS = 7325                                      # 60 mi de tokens a 8.192 por passo
MARCOS = (1221, 2442, 3663, 4883, 6104, 7325)      # a cada 10 mi de tokens


def preparar(pasta: Path) -> None:
    """Uma pasta para treinar do zero: os dados ligados (não copiados) e o tokenizador."""
    if pasta.exists():
        shutil.rmtree(pasta)
    (pasta / "avaliacao").mkdir(parents=True)
    for nome in ("treino.bin", "val.bin"):
        os.link(CEREBRO / nome, pasta / nome)
    for arquivo in (CEREBRO / "avaliacao").iterdir():
        if arquivo.suffix in (".bin", ".json") and not arquivo.name.startswith("ngramas"):
            os.link(arquivo, pasta / "avaliacao" / arquivo.name)
    shutil.copy2(CEREBRO / "tokenizador.json", pasta / "tokenizador.json")


def memoria_de_video_em_uso_mb() -> float | None:
    """O que a placa tem ocupado agora, por todos os programas (contador do Windows)."""
    saida = subprocess.run(["typeperf", r"\GPU Adapter Memory(*)\Dedicated Usage", "-sc", "1"], capture_output=True,
                           text=True, errors="replace").stdout.strip().splitlines()
    medidas = [linha for linha in saida if linha.startswith('"') and "/" in linha.split('","')[0]]   # "data","valor",...
    try:
        valores = [float(v.strip('"')) for v in medidas[-1].split('","')[1:] if v.strip('"')]
        return max(valores) / 2**20
    except (IndexError, ValueError):
        return None


def esperar_a_placa(avisar, limite_mb: float = 1500, maximo_s: int = 300) -> None:
    """O DirectML devolve a memória de vídeo um pouco depois de o processo sair: espera ela baixar."""
    time.sleep(30)
    inicio = time.time()
    while time.time() - inicio < maximo_s:
        uso = memoria_de_video_em_uso_mb()
        if uso is None or uso < limite_mb:
            return
        time.sleep(15)
    avisar(f"a placa continua com {memoria_de_video_em_uso_mb():.0f} MB ocupados; seguindo assim mesmo")


def rodar(comando: list[str], **ambiente) -> subprocess.CompletedProcess:
    return subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8", **ambiente})


def main() -> int:
    from kernel.cerebro.gpt import LOTES

    analisador = argparse.ArgumentParser()
    analisador.add_argument("--tamanhos", nargs="+", required=True)
    analisador.add_argument("--semente", type=int, default=1337)
    analisador.add_argument("--passos", type=int, default=PASSOS)
    analisador.add_argument("--continuar", action="store_true",
                            help="continua do checkpoint da pasta (a sessão começou no passo 0), sem apagar nada")
    args = analisador.parse_args()
    marcos = [m for m in MARCOS if m <= args.passos] or [args.passos]

    def avisar(texto: str) -> None:
        print(f"{time.strftime('%d/%m %H:%M:%S')} {texto}", flush=True)

    for tamanho in args.tamanhos:
        nome = tamanho if args.semente == 1337 else f"{tamanho}-s{args.semente}"
        pasta = RAIZ / "dados" / "fase2" / "escala" / nome / "cerebro"
        docs = RAIZ / "docs" / "fase2" / "escala" / nome
        if not args.continuar:
            preparar(pasta)
        elif not (pasta / "checkpoint.pt").exists():
            avisar(f"{nome}: não há checkpoint em {pasta} para continuar")
            continue
        lote, acumular = LOTES[tamanho]
        comando = [str(PYTHON), "-m", "kernel", "cerebro", "treinar", "--tamanho", tamanho, "--sessao-passos",
                   str(args.passos), "--lote", str(lote), "--acumular", str(acumular), "--semente", str(args.semente),
                   "--marcos", ",".join(map(str, marcos))] + (["--sessao-desde", "0"] if args.continuar else [])
        for tentativa in range(3):
            esperar_a_placa(avisar)
            avisar(f"{nome}: treinando ({' '.join(comando[3:])})")
            inicio = time.time()
            resultado = rodar(comando, KERNEL_DADOS=str(pasta.parent))
            (pasta / "saida.txt").write_text(resultado.stdout + resultado.stderr, encoding="utf-8")
            sem_memoria = "not enough GPU video memory" in resultado.stdout + resultado.stderr
            if resultado.returncode == 0 or not sem_memoria or time.time() - inicio > 600:
                break
            # faltou memória logo no começo: espera e tenta de novo; na terceira vez, com metade do lote
            # (o mesmo número de tokens por passo: a conta é a mesma, só cabe menos de uma vez)
            avisar(f"{nome}: faltou memória de vídeo no começo (tentativa {tentativa + 1}); tentando de novo")
            if not args.continuar:   # continuando, a pasta guarda o progresso: nada de apagar
                preparar(pasta)
            if tentativa == 1 and not args.continuar:   # a passada reparte os dados pelo lote: não muda no meio
                lote, acumular = max(1, lote // 2), acumular * 2
                comando[comando.index("--lote") + 1] = str(lote)
                comando[comando.index("--acumular") + 1] = str(acumular)
            time.sleep(120)
        if resultado.returncode != 0:
            avisar(f"{nome}: o treino falhou (código {resultado.returncode}); veja {pasta / 'saida.txt'}")
            continue
        avisar(f"{nome}: treino em {(time.time() - inicio) / 3600:.2f} h; medindo os marcos")
        docs.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pasta / "marcos" / "marcos.jsonl", docs / "marcos.jsonl")
        for marco in marcos:
            esperar_a_placa(avisar)
            arquivo = pasta / "marcos" / f"passo-{marco}.npz"
            medida = rodar([str(PYTHON), "-m", "kernel", "cerebro", "protocolo", "--modelo", str(arquivo),
                            "--so-perda", "teste,validacao", "--saida", str(docs / f"marco-{marco}.json")])
            avisar(f"{nome}: marco {marco}: {medida.stdout.strip().splitlines()[-1] if medida.stdout.strip() else medida.stderr[-200:]}")
        final = pasta / "marcos" / f"passo-{marcos[-1]}.npz"
        esperar_a_placa(avisar)
        completo = rodar([str(PYTHON), "-m", "kernel", "cerebro", "protocolo", "--modelo", str(final), "--saida", str(docs)])
        relatorio = docs / "relatorio.json"
        if relatorio.exists():
            dados = json.loads(relatorio.read_text(encoding="utf-8"))
            dados["modelo"]["arquivo"] = f"{nome}-passo-{marcos[-1]}.npz"   # sem caminho local no relatório
            relatorio.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
            avisar(f"{nome}: protocolo completo: " + json.dumps({k: v["perda"] for k, v in dados["perdas"].items()}))
        else:
            avisar(f"{nome}: o protocolo completo falhou: {completo.stderr[-300:]}")
    avisar("fim")
    return 0


if __name__ == "__main__":
    sys.exit(main())
