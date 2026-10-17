"""Fase 2: do resultado da comparação ao candidato, aplicando as regras do plano.md sem intervenção.

1. espera a comparação de escala acabar (``dados/fase2/escala.log`` termina com "fim");
2. escolhe o finalista pela regra registrada: a menor perda no teste em 60 mi de tokens; se dois
   ficarem a menos de 0,01 um do outro, o menor;
3. refaz o treino de comparação do finalista com a segunda semente (2026);
4. continua o finalista a partir do marco de 60 mi (padrão da Fase 1.5: retomar sem reaquecer, a
   passada de onde parou), até o orçamento de 48 h acabar ou a validação estabilizar;
5. mede o candidato (o de melhor validação) e o teto do mini pelo protocolo v2, e monta a avaliação às cegas.

    python docs/fase2/finalista.py --inicio "2026-10-16 19:30" --orcamento 48
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
PYTHON = RAIZ / ".venv" / "Scripts" / "python.exe"
ESCALA = RAIZ / "docs" / "fase2" / "escala"
ORDEM = ["mini", "medio", "pequeno", "grande"]          # do menor para o maior


def avisar(texto: str) -> None:
    print(f"{time.strftime('%d/%m %H:%M:%S')} {texto}", flush=True)


def rodar(comando: list[str], **ambiente) -> subprocess.CompletedProcess:
    return subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8", **ambiente})


def escolher_finalista() -> tuple[str, dict]:
    perdas = {}
    for tamanho in ORDEM:
        arquivo = ESCALA / tamanho / "marco-7325.json"
        if arquivo.exists():
            perdas[tamanho] = json.loads(arquivo.read_text(encoding="utf-8"))["perdas"]["teste"]["perda"]
    melhor = min(perdas.values())
    empatados = [t for t in ORDEM if t in perdas and perdas[t] - melhor < 0.01]
    return empatados[0], perdas   # o menor entre os que ficaram a menos de 0,01 do melhor


def main() -> int:
    analisador = argparse.ArgumentParser()
    analisador.add_argument("--inicio", required=True, help="quando a fase começou a usar a placa")
    analisador.add_argument("--orcamento", type=float, default=48.0)
    args = analisador.parse_args()
    inicio = datetime.strptime(args.inicio, "%Y-%m-%d %H:%M")
    log = RAIZ / "dados" / "fase2" / "escala.log"
    while not (log.exists() and log.read_text(encoding="utf-8", errors="replace").rstrip().endswith("fim")):
        time.sleep(60)
    finalista, perdas = escolher_finalista()
    if set(perdas) != set(ORDEM):
        # a regra compara os quatro: sem um deles não há finalista (foi o que deu errado em 17/10 às 04:30)
        avisar(f"comparação incompleta: só {sorted(perdas)} têm a medida de 60 mi; parando sem escolher")
        avisar("fim")
        return 1
    avisar(f"comparação pronta: {json.dumps(perdas)} | finalista pela regra do plano: {finalista}")
    (ESCALA.parent / "finalista.json").write_text(json.dumps({"finalista": finalista, "perdas_60mi": perdas},
                                                             indent=1), encoding="utf-8")

    avisar(f"segunda semente do {finalista}")
    semente = rodar([str(PYTHON), str(RAIZ / "docs" / "fase2" / "escala.py"), "--tamanhos", finalista, "--semente", "2026"])
    avisar("segunda semente: " + (semente.stdout.strip().splitlines()[-2] if semente.stdout.strip() else semente.stderr[-300:]))

    from escala import esperar_a_placa, preparar
    from kernel.cerebro.gpt import LOTES
    origem = RAIZ / "dados" / "fase2" / "escala" / finalista / "cerebro"
    pasta = RAIZ / "dados" / "fase2" / "candidato" / "cerebro"
    preparar(pasta)
    for nome in ("checkpoint.pt", "checkpoint.pt.sha256", "treino.log", "treino.csv"):
        shutil.copy2(origem / nome, pasta / nome)
    marco = origem / "marcos" / "passo-7325.npz"   # o modelo exportado de partida: o do último passo (60 mi)
    shutil.copy2(marco, pasta / "modelo.npz")
    shutil.copy2(Path(str(marco) + ".sha256"), pasta / "modelo.npz.sha256")
    horas = args.orcamento - (datetime.now() - inicio).total_seconds() / 3600 - 1.0   # 1 h para as medidas finais
    lote, acumular = LOTES[finalista]
    if horas > 0.25:
        comando = [str(PYTHON), "-m", "kernel", "cerebro", "treinar", "--tamanho", finalista, "--horas", f"{horas:.2f}",
                   "--lote", str(lote), "--acumular", str(acumular), "--parar-se-estagnar", "6",
                   "--melhora-minima", "0.002"]
        for tentativa in range(3):
            esperar_a_placa(avisar)   # o processo anterior acabou de sair da placa
            avisar(f"continuação do {finalista} por até {horas:.2f} h: {' '.join(comando[3:])}")
            comeco = time.time()
            continuacao = rodar(comando, KERNEL_DADOS=str(pasta.parent))
            (pasta / "saida.txt").write_text(continuacao.stdout + continuacao.stderr, encoding="utf-8")
            sem_memoria = "not enough GPU video memory" in continuacao.stdout + continuacao.stderr
            if continuacao.returncode == 0 or not sem_memoria or time.time() - comeco > 600:
                break
            avisar(f"faltou memória de vídeo no começo da continuação (tentativa {tentativa + 1}); tentando de novo")
            time.sleep(120)
            horas -= (time.time() - comeco) / 3600
            comando[comando.index("--horas") + 1] = f"{horas:.2f}"
        avisar(f"continuação acabou (código {continuacao.returncode}): "
               + (continuacao.stdout.strip().splitlines()[-2] if continuacao.stdout.strip() else continuacao.stderr[-300:]))
    else:
        avisar(f"sem horas para a continuação ({horas:.2f} h)")

    docs = RAIZ / "docs" / "fase2" / "candidato"
    for nome, arquivo, saida in (("candidato", pasta / "modelo.npz", docs),
                                 ("mini", RAIZ / "dados" / "cerebro" / "modelo.npz", RAIZ / "docs" / "fase2" / "teto-mini")):
        esperar_a_placa(avisar)
        medida = rodar([str(PYTHON), "-m", "kernel", "cerebro", "protocolo", "--modelo", str(arquivo), "--saida", str(saida)])
        relatorio = saida / "relatorio.json"
        if relatorio.exists():
            dados = json.loads(relatorio.read_text(encoding="utf-8"))
            dados["modelo"]["arquivo"] = f"{nome}-modelo.npz"
            relatorio.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
            avisar(f"protocolo do {nome}: " + json.dumps({k: v["perda"] for k, v in dados["perdas"].items()}))
        else:
            avisar(f"protocolo do {nome} falhou: {medida.stderr[-300:]}")
    cegas = rodar([str(PYTHON), str(RAIZ / "docs" / "fase2" / "cegas.py"), "--montar",
                   f"mini={RAIZ / 'docs' / 'fase2' / 'teto-mini' / 'relatorio.json'}", f"candidato={docs / 'relatorio.json'}"])
    avisar("avaliação às cegas: " + cegas.stdout.strip()[-200:])
    avisar("fim")
    return 0


if __name__ == "__main__":
    sys.exit(main())
