"""Fase 2: o que as notas às cegas dizem além dos critérios (depois de abrir a chave).

- a concordância entre os dois avaliadores, por critério (exata e "nota 1 ou 2"), com o kappa de Cohen;
- a fração de textos com nota 1 ou 2 por modo de gerar (o do serviço e o sorteio cru);
- a comparação pareada: o mesmo começo, modo e semente, candidato contra o teto do mini (teste do sinal);
- a consistência do Claude: os 24 textos do teto que já estavam na rodada da Fase 1.5, notas de lá e de agora.

    python docs/fase2/analise_cegas.py > docs/fase2/cegas/analise.txt
"""
import json, re
from math import comb
from collections import defaultdict

P = "docs/fase2/cegas/"
chave = json.load(open(P + "chave.json", encoding="utf-8"))
notas = {a: json.load(open(P + f"notas-{a}.json", encoding="utf-8")) for a in ("henrique", "claude")}
CRIT = ("portugues", "assunto", "coerencia")

def kappa(x, y):
    n = len(x); po = sum(a == b for a, b in zip(x, y)) / n
    cats = set(x) | set(y); pe = sum((x.count(c) / n) * (y.count(c) / n) for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else float("nan"), po

print("== concordância entre avaliadores (96 textos)")
for i, c in enumerate(CRIT):
    h = [notas["henrique"][k][i] for k in sorted(chave)]; cl = [notas["claude"][k][i] for k in sorted(chave)]
    k3, p3 = kappa(h, cl); k2, p2 = kappa([v >= 1 for v in h], [v >= 1 for v in cl])
    print(f"{c:10s} exata {p3:.0%} kappa {k3:.2f} | binária (>=1) {p2:.0%} kappa {k2:.2f} | médias H {sum(h)/96:.2f} C {sum(cl)/96:.2f}")

print("== por modo (fração com nota >=1)")
for a in notas:
    for modelo in ("candidato", "mini"):
        for modo in ("servico", "sorteio"):
            ks = [k for k, v in chave.items() if v["modelo"] == modelo and v["modo"] == modo]
            print(a, modelo, modo, len(ks), [f"{c[:4]} {sum(notas[a][k][i] >= 1 for k in ks) / len(ks):.0%}" for i, c in enumerate(CRIT)])

print("== pareado: o mesmo começo, modo e semente, candidato contra mini, critério por critério")
pares = defaultdict(dict)
for k, v in chave.items():
    pares[(v["comeco"], v["modo"], v["semente"])][v["modelo"]] = k
for a in notas:
    for i, c in enumerate(CRIT):
        melhor = pior = 0
        for p in pares.values():
            d = notas[a][p["candidato"]][i] - notas[a][p["mini"]][i]
            melhor += d > 0; pior += d < 0
        n = melhor + pior
        pval = sum(comb(n, j) for j in range(max(melhor, pior), n + 1)) / 2 ** n * 2 if n else 1.0
        print(f"{a:8s} {c:10s} candidato melhor em {melhor}, pior em {pior}, empate {48 - n} | sinal bilateral p={min(1, pval):.3f}")

print("== o texto com coerência >=1 do Henrique")
for k, v in notas["henrique"].items():
    if v[2] >= 1: print(k, v, chave[k]["modelo"], chave[k]["modo"], "| Claude:", notas["claude"][k])

print("== Claude: as mesmas 24 notas do teto na Fase 1.5 e agora")
def textos(p):
    t = open(p, encoding="utf-8").read()
    return {m[0]: re.sub(r"\s+", " ", m[1]).strip() for m in re.findall(r"\*\*(T\d+)\*\* · \*[^*]+\*(.*)", t)}
t15, t2 = textos("docs/fase15/cegas/cegas.md"), textos(P + "cegas.md")
n15 = json.load(open("docs/fase15/cegas/notas.json", encoding="utf-8"))
inv15 = {v: k for k, v in t15.items()}
iguais = [(inv15[v], k) for k, v in t2.items() if v in inv15]
print("pares:", len(iguais), "| todos do teto agora:", all(chave[k]["modelo"] == "mini" for _, k in iguais))
for i, c in enumerate(CRIT):
    antes = [n15[a][i] if isinstance(n15[a], list) else n15[a][c] for a, _ in iguais]
    agora = [notas["claude"][k][i] for _, k in iguais]
    k3, p3 = kappa(antes, agora)
    print(f"{c:10s} exata {p3:.0%} kappa {k3:.2f} | >=1 antes {sum(v >= 1 for v in antes)}/24 agora {sum(v >= 1 for v in agora)}/24 | média antes {sum(antes)/24:.2f} agora {sum(agora)/24:.2f}")
