"""Fase 2: a avaliação às cegas com dois avaliadores (ver docs/fase15/rubrica.md e plano.md).

    python docs/fase2/cegas.py --montar mini=docs/fase15/teto/relatorio.json candidato=docs/fase2/.../relatorio.json
        -> docs/fase2/cegas/cegas.md (os textos com códigos, sem dizer de que modelo vieram),
           notas-henrique.json e notas-claude.json (para preencher) e chave.json (fechada até as notas)
    python docs/fase2/cegas.py --revelar
        -> resultado.json: por modelo e por avaliador, a fração de textos com nota 1 ou 2 em cada critério,
           e os critérios da fase (coerência >= 25%, assunto >= 50%, português no máximo 10 pontos abaixo do mini).
           Traz também a medida da Fase 1.5 (pontos sobre o máximo, ``*_pontos``), que é outra conta: os números
           de partida do ROADMAP ("o mini fica em torno de 10%", "assunto 35%") estão nela

48 textos por modelo: os 12 começos fixos, cada um do jeito do serviço (sementes 1 e 2) e em sorteio cru
(sementes 1 e 2). Os dois avaliadores dão as notas em arquivos separados, sem ver a chave nem as notas do outro.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

PASTA = Path(__file__).resolve().parent / "cegas"
MODOS = (("servico", 1), ("servico", 2), ("sorteio", 1), ("sorteio", 2))
AVALIADORES = ("henrique", "claude")
CRITERIOS = ("portugues", "assunto", "coerencia")


def montar(fontes: dict[str, Path], semente: int = 2) -> None:
    itens = []
    for nome, arquivo in fontes.items():
        relatorio = json.loads(Path(arquivo).read_text(encoding="utf-8"))
        if relatorio.get("protocolo", 1) < 2:
            raise SystemExit(f"{arquivo}: o relatório precisa ser do protocolo v2 (2 sementes do modo do serviço)")
        escolhidas = [a for a in relatorio["amostras"] if (a["modo"], a["semente"]) in MODOS]
        if len(escolhidas) != 48:
            raise SystemExit(f"{arquivo}: esperava 48 textos, achei {len(escolhidas)}")
        itens += [{"modelo": nome, "comeco": a["comeco"], "modo": a["modo"], "semente": a["semente"],
                   "texto": re.sub(r"\s+", " ", a["texto"]).strip()} for a in escolhidas]
    ordem = np.random.default_rng(semente).permutation(len(itens))
    PASTA.mkdir(parents=True, exist_ok=True)
    linhas = ["# Textos para avaliar às cegas (Fase 2)", "",
              f"{len(itens)} textos. Dê notas de 0 a 2 em português, assunto e coerência (ver `../../fase15/rubrica.md`) "
              "no seu arquivo de notas (`notas-SEU-NOME.json`), sem abrir `chave.json` e sem ver as notas do outro "
              "avaliador.", ""]
    chave, vazio = {}, {}
    for posicao, indice in enumerate(ordem, 1):
        codigo = f"T{posicao:03d}"
        item = itens[indice]
        chave[codigo] = {k: item[k] for k in ("modelo", "modo", "semente", "comeco")}
        vazio[codigo] = [None, None, None]
        linhas += [f"**{codigo}** · *{item['comeco']}* {item['texto']}", ""]
    (PASTA / "cegas.md").write_text("\n".join(linhas), encoding="utf-8")
    (PASTA / "chave.json").write_text(json.dumps(chave, ensure_ascii=False, indent=1), encoding="utf-8")
    for avaliador in AVALIADORES:
        arquivo = PASTA / f"notas-{avaliador}.json"
        if not arquivo.exists():
            arquivo.write_text(json.dumps(vazio, indent=0), encoding="utf-8")
    print(f"{len(itens)} textos em {PASTA / 'cegas.md'}")


def revelar() -> dict:
    chave = json.loads((PASTA / "chave.json").read_text(encoding="utf-8"))
    resultado = {}
    for avaliador in AVALIADORES:
        notas = json.loads((PASTA / f"notas-{avaliador}.json").read_text(encoding="utf-8"))
        faltam = [c for c, n in notas.items() if None in n]
        if faltam:
            raise SystemExit(f"{avaliador}: faltam notas em {len(faltam)} textos ({faltam[:5]}...)")
        por_modelo: dict[str, list] = {}
        for codigo, trio in notas.items():
            por_modelo.setdefault(chave[codigo]["modelo"], []).append(trio)
        resultado[avaliador] = {
            modelo: {"textos": len(lista),
                     **{criterio: round(100 * float(np.mean(np.array(lista)[:, i] >= 1)), 1)
                        for i, criterio in enumerate(CRITERIOS)},
                     **{f"{criterio}_media": round(float(np.mean(np.array(lista)[:, i])), 3)
                        for i, criterio in enumerate(CRITERIOS)},
                     # a medida da Fase 1.5 (pontos sobre o máximo), para comparar com os números de lá
                     **{f"{criterio}_pontos": round(100 * float(np.mean(np.array(lista)[:, i])) / 2, 1)
                        for i, criterio in enumerate(CRITERIOS)}}
            for modelo, lista in sorted(por_modelo.items())}
    criterios = {}
    for modelo in resultado[AVALIADORES[0]]:
        if modelo == "mini":
            continue
        criterios[modelo] = {
            "coerencia_25": all(resultado[a][modelo]["coerencia"] >= 25 for a in AVALIADORES),
            "assunto_50": all(resultado[a][modelo]["assunto"] >= 50 for a in AVALIADORES),
            "portugues_10": all(resultado[a]["mini"]["portugues"] - resultado[a][modelo]["portugues"] <= 10
                                for a in AVALIADORES if "mini" in resultado[a]),
        }
    resultado["criterios"] = criterios
    (PASTA / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False, indent=1))
    return resultado


def main() -> int:
    analisador = argparse.ArgumentParser()
    analisador.add_argument("--montar", nargs="+", help="nome=relatorio.json ... (o teto do mini com o nome 'mini')")
    analisador.add_argument("--revelar", action="store_true")
    args = analisador.parse_args()
    if args.montar:
        montar({par.split("=", 1)[0]: Path(par.split("=", 1)[1]) for par in args.montar})
    if args.revelar:
        revelar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
