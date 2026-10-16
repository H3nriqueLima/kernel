"""Avaliação às cegas dos textos gerados (ver rubrica.md).

    python docs/fase15/cegas.py --montar base=docs/fase1/linha-de-base/passo-46000/relatorio.json teto=docs/fase15/teto/relatorio.json
        -> docs/fase15/cegas/cegas.md (só os textos, com códigos) e chave.json (de que modelo veio cada código)
    (dar as notas em docs/fase15/cegas/notas.json: {"T01": [português, assunto, coerência], ...}, sem abrir a chave)
    python docs/fase15/cegas.py --revelar
        -> resultado.json e a média de cada modelo
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

PASTA = Path(__file__).resolve().parent / "cegas"
MODOS = (("servico", 1), ("sorteio", 1))


def montar(fontes: dict[str, Path], semente: int = 15) -> None:
    itens = []
    for nome, arquivo in fontes.items():
        relatorio = json.loads(Path(arquivo).read_text(encoding="utf-8"))
        for amostra in relatorio["amostras"]:
            if (amostra["modo"], amostra["semente"]) in MODOS:
                itens.append({"modelo": nome, "comeco": amostra["comeco"], "modo": amostra["modo"],
                              "texto": re.sub(r"\s+", " ", amostra["texto"]).strip()})
    ordem = np.random.default_rng(semente).permutation(len(itens))
    PASTA.mkdir(parents=True, exist_ok=True)
    linhas = ["# Textos para avaliar às cegas", "",
              "Notas de 0 a 2 em português, assunto e coerência (ver `../rubrica.md`). O modelo de cada texto está "
              "na chave, que só se abre depois das notas.", ""]
    chave = {}
    for posicao, indice in enumerate(ordem, 1):
        codigo = f"T{posicao:02d}"
        item = itens[indice]
        chave[codigo] = {"modelo": item["modelo"], "modo": item["modo"], "comeco": item["comeco"]}
        linhas.append(f"**{codigo}** · *{item['comeco']}* {item['texto']}")
        linhas.append("")
    (PASTA / "cegas.md").write_text("\n".join(linhas), encoding="utf-8")
    (PASTA / "chave.json").write_text(json.dumps(chave, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(itens)} textos em {PASTA / 'cegas.md'}")


def revelar() -> dict:
    notas = json.loads((PASTA / "notas.json").read_text(encoding="utf-8"))
    chave = json.loads((PASTA / "chave.json").read_text(encoding="utf-8"))
    por_modelo: dict[str, list] = {}
    for codigo, (portugues, assunto, coerencia) in notas.items():
        por_modelo.setdefault(chave[codigo]["modelo"], []).append((portugues, assunto, coerencia))
    resultado = {}
    for modelo, lista in sorted(por_modelo.items()):
        matriz = np.array(lista, dtype=float)
        resultado[modelo] = {"textos": len(lista),
                             **{criterio: {"pontos": int(matriz[:, i].sum()), "de": 2 * len(lista),
                                           "porcentagem": round(100 * matriz[:, i].mean() / 2, 1)}
                                for i, criterio in enumerate(("portugues", "assunto", "coerencia"))}}
    (PASTA / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False, indent=1))
    return resultado


def main() -> int:
    analisador = argparse.ArgumentParser()
    analisador.add_argument("--montar", nargs="+", help="nome=relatorio.json ...")
    analisador.add_argument("--revelar", action="store_true")
    args = analisador.parse_args()
    if args.montar:
        montar({par.split("=", 1)[0]: Path(par.split("=", 1)[1]) for par in args.montar})
    if args.revelar:
        revelar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
