"""Fase 2.5: o que a linha de base diz além do resultado.json (depois de abrir a chave).

- a fração de textos com nota 2 (o corte mais exigente) por avaliador e modelo, e a concordância nesse corte;
- coerência interna por jeito de gerar (o do serviço e o sorteio cru);
- a comparação pareada candidato contra mini (o mesmo começo, modo e semente), critério por critério;
- onde os avaliadores discordam no assunto e na coerência interna.

    python docs/fase25/analise_linha_de_base.py > docs/fase25/linha-de-base/analise.txt
"""
import json
import sys
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cegas  # noqa: E402

chave = json.loads((cegas.PASTA / "chave.json").read_text(encoding="utf-8"))
notas = {a: json.loads((cegas.PASTA / f"notas-{a}.json").read_text(encoding="utf-8")) for a in cegas.AVALIADORES}
exemplos = cegas.exemplos_da_rubrica()
sem_exemplos = sorted(c for c in chave if chave[c]["codigo_fase2"] not in exemplos)

print("== fração de textos com nota 2 (o corte exigente)")
for a in cegas.AVALIADORES:
    for modelo in ("candidato", "mini"):
        ks = [k for k in chave if chave[k]["modelo"] == modelo]
        print(f"{a:8s} {modelo:9s}", " | ".join(
            f"{c} {100 * sum(notas[a][k][i] == 2 for k in ks) / len(ks):.1f}%" for i, c in enumerate(cegas.CRITERIOS)))

print("== concordância no corte 'nota 2' contra 'nota 0 ou 1', sem os exemplos")
for i, c in enumerate(cegas.CRITERIOS):
    h = [int(notas["henrique"][k][i] == 2) for k in sem_exemplos]
    cl = [int(notas["claude"][k][i] == 2) for k in sem_exemplos]
    print(f"{c:18s} kappa {cegas.kappa(h, cl)} | acordo {100 * sum(x == y for x, y in zip(h, cl)) / len(h):.1f}%")

print("== coerência interna por jeito de gerar (nota 1 ou 2 | nota 2)")
for a in cegas.AVALIADORES:
    for modelo in ("candidato", "mini"):
        for modo in ("servico", "sorteio"):
            ks = [k for k in chave if chave[k]["modelo"] == modelo and chave[k]["modo"] == modo]
            um = 100 * sum(notas[a][k][2] >= 1 for k in ks) / len(ks)
            dois = 100 * sum(notas[a][k][2] == 2 for k in ks) / len(ks)
            print(f"{a:8s} {modelo:9s} {modo:8s} {um:5.1f}% | {dois:5.1f}%")

print("== pareado: candidato contra mini no mesmo começo, modo e semente (teste do sinal, bilateral)")
pares = defaultdict(dict)
for k, v in chave.items():
    pares[(v["comeco"], v["modo"], v["semente"])][v["modelo"]] = k
for a in cegas.AVALIADORES:
    for i, c in enumerate(cegas.CRITERIOS):
        melhor = sum(notas[a][p["candidato"]][i] > notas[a][p["mini"]][i] for p in pares.values())
        pior = sum(notas[a][p["candidato"]][i] < notas[a][p["mini"]][i] for p in pares.values())
        n = melhor + pior
        p = min(1.0, 2 * sum(comb(n, j) for j in range(max(melhor, pior), n + 1)) / 2 ** n) if n else 1.0
        print(f"{a:8s} {c:18s} candidato melhor em {melhor:2d}, pior em {pior:2d}, empate {48 - n:2d} | p = {p:.3f}")

print("== discordâncias (Henrique, Claude) por critério, sem os exemplos")
for i, c in enumerate(cegas.CRITERIOS):
    pares_de_notas = Counter((notas["henrique"][k][i], notas["claude"][k][i]) for k in sem_exemplos
                             if notas["henrique"][k][i] != notas["claude"][k][i])
    print(f"{c:18s}", dict(sorted(pares_de_notas.items())))
print("== assunto: os textos com nota 0 do Henrique e nota 1 ou 2 do Claude")
for k in sorted(chave):
    if notas["henrique"][k][1] == 0 and notas["claude"][k][1] >= 1:
        print(k, chave[k]["codigo_fase2"], chave[k]["comeco"], "| H", notas["henrique"][k], "C", notas["claude"][k])
