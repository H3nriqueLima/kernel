"""Fase 2.5: a linha de base da rubrica calibrada (ver rubrica.md).

Os 96 textos da Fase 2 (48 do candidato grande e 48 do teto do mini) voltam embaralhados de novo, com códigos
novos (L001...), para ninguém lembrar o código antigo de cada um. Cada texto recebe quatro notas de 0 a 2:
[português, assunto, coerência interna, factualidade].

    python docs/fase25/cegas.py --montar
        -> docs/fase25/linha-de-base/cegas.md (os textos, sem dizer de que modelo vieram),
           notas-claude.json e notas-henrique.json (para preencher) e chave.json (fechada até as duas notas)
    python docs/fase25/cegas.py --revelar
        -> resultado.json: por avaliador e por modelo, a fração de textos com nota 1 ou 2 em cada critério, e a
           concordância entre os dois avaliadores (kappa de Cohen)

A concordância que vale para o critério (kappa >= 0,6 em coerência interna) foi fixada antes de qualquer nota:
a divisão "nota 1 ou 2" contra "nota 0", sem os textos usados como exemplo na rubrica, que já têm nota combinada.
O kappa nas três notas e o kappa com todos os textos vêm ao lado, só para informar.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
FASE2 = AQUI.parent / "fase2" / "cegas"
PASTA = AQUI / "linha-de-base"
AVALIADORES = ("henrique", "claude")
CRITERIOS = ("portugues", "assunto", "coerencia_interna", "factualidade")
SEMENTE = 25   # outra ordem, que não a da Fase 2


def textos_da_fase2() -> dict[str, tuple[str, str]]:
    texto = (FASE2 / "cegas.md").read_text(encoding="utf-8")
    return {c: (comeco.strip(), re.sub(r"\s+", " ", resto).strip())
            for c, comeco, resto in re.findall(r"\*\*(T\d+)\*\* · \*([^*]+)\*(.*)", texto)}


def exemplos_da_rubrica() -> set[str]:
    """Os textos da Fase 2 citados como exemplo na rubrica: a nota deles foi combinada antes."""
    return set(re.findall(r"\bT\d{3}\b", (AQUI / "rubrica.md").read_text(encoding="utf-8")))   # em negrito ou não


def montar() -> None:
    textos, chave_antiga = textos_da_fase2(), json.loads((FASE2 / "chave.json").read_text(encoding="utf-8"))
    assert len(textos) == 96 and set(textos) == set(chave_antiga)
    antigos = sorted(textos)
    ordem = np.random.default_rng(SEMENTE).permutation(len(antigos))
    PASTA.mkdir(parents=True, exist_ok=True)
    linhas = ["# Linha de base da rubrica calibrada (Fase 2.5)", "",
              "Os 96 textos da Fase 2, embaralhados de novo, com códigos novos. Dê quatro notas de 0 a 2 a cada um, "
              "na ordem [português, assunto, coerência interna, factualidade], pela rubrica (`../rubrica.md`), "
              "no seu arquivo de notas (`notas-SEU-NOME.json`). Não abra `chave.json` nem as notas do outro avaliador.", ""]
    chave, vazio = {}, {}
    for posicao, indice in enumerate(ordem, 1):
        codigo, antigo = f"L{posicao:03d}", antigos[indice]
        comeco, resto = textos[antigo]
        junta = "" if resto[:1] in ",.;:" else " "
        chave[codigo] = {**chave_antiga[antigo], "codigo_fase2": antigo}
        vazio[codigo] = [None, None, None, None]
        linhas += [f"**{codigo}** · *{comeco}*{junta}{resto}", ""]
    (PASTA / "cegas.md").write_text("\n".join(linhas), encoding="utf-8")
    (PASTA / "chave.json").write_text(json.dumps(chave, ensure_ascii=False, indent=1), encoding="utf-8")
    for avaliador in AVALIADORES:
        arquivo = PASTA / f"notas-{avaliador}.json"
        if not arquivo.exists():
            arquivo.write_text(json.dumps(vazio, indent=0), encoding="utf-8")
    print(f"{len(chave)} textos em {PASTA / 'cegas.md'}")


def kappa(a: list, b: list) -> float | None:
    """Kappa de Cohen: a concordância que passa do que o acaso daria. None quando o acaso já explica tudo."""
    n = len(a)
    observada = sum(x == y for x, y in zip(a, b)) / n
    acaso = sum((a.count(c) / n) * (b.count(c) / n) for c in set(a) | set(b))
    return None if acaso >= 1 else round((observada - acaso) / (1 - acaso), 3)


def revelar() -> dict:
    chave = json.loads((PASTA / "chave.json").read_text(encoding="utf-8"))
    notas = {}
    for avaliador in AVALIADORES:
        notas[avaliador] = json.loads((PASTA / f"notas-{avaliador}.json").read_text(encoding="utf-8"))
        faltam = [c for c, n in notas[avaliador].items() if None in n or len(n) != 4]
        if faltam:
            raise SystemExit(f"{avaliador}: faltam notas em {len(faltam)} textos ({faltam[:5]}...)")
    exemplos = exemplos_da_rubrica()
    sem_exemplos = sorted(c for c in chave if chave[c]["codigo_fase2"] not in exemplos)
    resultado: dict = {"textos": len(chave), "exemplos_da_rubrica": len(chave) - len(sem_exemplos)}
    for avaliador in AVALIADORES:
        resultado[avaliador] = {}
        for modelo in sorted({v["modelo"] for v in chave.values()}):
            codigos = [c for c in chave if chave[c]["modelo"] == modelo]
            matriz = np.array([notas[avaliador][c] for c in codigos])
            resultado[avaliador][modelo] = {
                "textos": len(codigos),
                **{criterio: round(100 * float(np.mean(matriz[:, i] >= 1)), 1) for i, criterio in enumerate(CRITERIOS)},
                **{f"{criterio}_media": round(float(np.mean(matriz[:, i])), 3) for i, criterio in enumerate(CRITERIOS)}}
    concordancia = {}
    for i, criterio in enumerate(CRITERIOS):
        def lista(avaliador, codigos, binaria):
            return [int(notas[avaliador][c][i] >= 1) if binaria else notas[avaliador][c][i] for c in codigos]
        todos = sorted(chave)
        concordancia[criterio] = {
            "kappa_1ou2_sem_exemplos": kappa(lista("henrique", sem_exemplos, True), lista("claude", sem_exemplos, True)),
            "kappa_1ou2_todos": kappa(lista("henrique", todos, True), lista("claude", todos, True)),
            "kappa_tres_notas_sem_exemplos": kappa(lista("henrique", sem_exemplos, False), lista("claude", sem_exemplos, False)),
            "acordo_1ou2_sem_exemplos": round(100 * float(np.mean([x == y for x, y in zip(
                lista("henrique", sem_exemplos, True), lista("claude", sem_exemplos, True))])), 1)}
    resultado["concordancia"] = concordancia
    k = concordancia["coerencia_interna"]["kappa_1ou2_sem_exemplos"]
    resultado["criterio_kappa_06"] = k is not None and k >= 0.6
    (PASTA / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False, indent=1))
    return resultado


def main() -> int:
    analisador = argparse.ArgumentParser()
    analisador.add_argument("--montar", action="store_true")
    analisador.add_argument("--revelar", action="store_true")
    args = analisador.parse_args()
    if args.montar:
        montar()
    if args.revelar:
        revelar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
