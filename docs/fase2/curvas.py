"""Fase 2: as curvas de escala, a partir das medidas já gravadas (nada é treinado nem medido aqui).

Lê ``docs/fase2/escala/<nome>/marco-N.json`` (perda no teste fixo e na validação, medidas pelo
protocolo, cada uma num processo à parte) e ``marcos.jsonl`` (quando cada marco foi guardado, em
segundos de treino) e escreve:

- ``docs/fase2/escala/curvas.json``: todos os pontos e as comparações, cada número marcado como
  "medido" (saiu do protocolo) ou "estimado" (interpolado entre dois marcos medidos);
- ``docs/fase2/escala/perda-por-tokens.svg`` e ``perda-por-horas.svg``: as curvas, com o teto do
  mini, o critério e o trigrama como linhas de referência;
- ``docs/fase2/escala/continuacao.svg``, se a continuação do finalista já tiver rodado.

    python docs/fase2/curvas.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ESCALA = RAIZ / "docs" / "fase2" / "escala"
ORDEM = ["mini", "medio", "pequeno", "grande"]          # do menor para o maior
TOKENS_POR_PASSO = 8192

# cores fixas por tamanho (a cor segue o tamanho, nunca a posição no ranking); paleta validada para daltonismo
CORES = {"mini": "#2a78d6", "medio": "#eb6834", "pequeno": "#1baf7a", "grande": "#eda100"}
FUNDO, TINTA, TINTA_2, APAGADA, GRADE, EIXO = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
FONTE = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def br(valor: float, casas: int = 3) -> str:
    """Número com vírgula decimal (só o número: nunca trocar pontos de um texto inteiro)."""
    return f"{valor:.{casas}f}".replace(".", ",")


# --- os dados ---------------------------------------------------------------------------------------

def ler_serie(nome: str) -> dict | None:
    pasta = ESCALA / nome
    if not (pasta / "marcos.jsonl").exists():
        return None
    quando = {}
    for linha in (pasta / "marcos.jsonl").read_text(encoding="utf-8").splitlines():
        if linha.strip():
            marco = json.loads(linha)
            quando[marco["passo"]] = marco
    pontos, parametros = [], None
    for passo in sorted(quando):
        arquivo = pasta / f"marco-{passo}.json"
        if not arquivo.exists():
            continue
        medida = json.loads(arquivo.read_text(encoding="utf-8"))
        parametros = medida["modelo"]["parametros"]
        teste, validacao = medida["perdas"]["teste"], medida["perdas"]["validacao"]
        pontos.append({"passo": passo, "tokens": quando[passo]["tokens"], "horas": quando[passo]["segundos"] / 3600,
                       "teste": teste["perda"], "bits_por_byte": teste["bits_por_byte"],
                       "validacao": validacao["perda"], "origem": "medido"})
    if not pontos:
        return None
    tamanho, _, semente = nome.partition("-s")
    return {"nome": nome, "tamanho": tamanho, "semente": int(semente) if semente else 1337,
            "parametros": parametros, "pontos": pontos}


def referencias() -> dict:
    """O teto do mini (a régua), o critério (0,05 abaixo dele) e o trigrama contado, no teste fixo."""
    teto_arquivo = RAIZ / "docs" / "fase2" / "teto-mini" / "relatorio.json"
    if not teto_arquivo.exists():
        teto_arquivo = RAIZ / "docs" / "fase15" / "teto" / "relatorio.json"
    teto = json.loads(teto_arquivo.read_text(encoding="utf-8"))
    algum = next(ESCALA.glob("*/relatorio.json"), teto_arquivo)
    ngramas = json.loads(algum.read_text(encoding="utf-8"))["ngramas"]["teste"]
    perda_teto = teto["perdas"]["teste"]["perda"]
    fator = teto["perdas"]["teste"]["bits_por_byte"] / perda_teto   # bits por byte de cada nat por token, no teste
    return {"teto_mini": perda_teto, "criterio": round(perda_teto - 0.05, 4), "trigrama": ngramas["trigrama"],
            "bigrama": ngramas["bigrama"], "bits_por_byte_por_nat": fator, "teto_arquivo": teto_arquivo.name}


def interpolar(pontos: list[dict], x: str, alvo: float, y: str) -> tuple[float, str] | None:
    """O valor de ``y`` quando ``x`` vale ``alvo``: medido se cair num marco, estimado (reta) entre dois."""
    for ponto in pontos:
        if abs(ponto[x] - alvo) < 1e-9 * max(1.0, abs(alvo)):
            return ponto[y], "medido"
    for a, b in zip(pontos, pontos[1:]):
        if min(a[x], b[x]) <= alvo <= max(a[x], b[x]):
            fracao = (alvo - a[x]) / (b[x] - a[x])
            return a[y] + fracao * (b[y] - a[y]), "estimado"
    return None


def comparar(series: list[dict], refs: dict) -> dict:
    principais = [s for s in series if s["semente"] == 1337]
    mini = next((s for s in principais if s["tamanho"] == "mini"), None)
    fator = refs["bits_por_byte_por_nat"]

    # tokens iguais: o último marco que todos têm (60 mi de tokens quando a comparação está completa)
    tokens = min(s["pontos"][-1]["tokens"] for s in series)
    iguais_tokens = []
    for s in series:
        perda, origem = interpolar(s["pontos"], "tokens", tokens, "teste")
        linha = {"nome": s["nome"], "parametros": s["parametros"], "teste": round(perda, 5),
                 "bits_por_byte": round(perda * fator, 4), "origem": origem,
                 "contra_trigrama": round(perda - refs["trigrama"], 4), "contra_teto_mini": round(perda - refs["teto_mini"], 4)}
        if mini:
            linha["contra_mini_mesmos_tokens"] = round(perda - interpolar(mini["pontos"], "tokens", tokens, "teste")[0], 4)
        iguais_tokens.append(linha)

    # horas iguais: no tempo que o mini leva para os 60 mi; cada outro tamanho estimado entre os seus marcos
    iguais_horas, ate_a_perda_do_mini = [], []
    if mini:
        horas = mini["pontos"][-1]["horas"]
        perda_final_mini = mini["pontos"][-1]["teste"]
        for s in principais:
            achado = interpolar(s["pontos"], "horas", horas, "teste")
            iguais_horas.append({"nome": s["nome"], "horas": round(horas, 3),
                                 "teste": round(achado[0], 5) if achado else None,
                                 "origem": achado[1] if achado else "sem marco antes e depois"})
            # quanto tempo cada um leva para chegar na perda final do mini (a perda cai sempre: dá para inverter)
            invertidos = [{"perda": -p["teste"], "horas": p["horas"], "tokens": p["tokens"]} for p in s["pontos"]]
            em_horas = interpolar(invertidos, "perda", -perda_final_mini, "horas")
            em_tokens = interpolar(invertidos, "perda", -perda_final_mini, "tokens")
            ate_a_perda_do_mini.append({"nome": s["nome"], "perda": perda_final_mini,
                                        "horas": round(em_horas[0], 3) if em_horas else None,
                                        "tokens": round(em_tokens[0]) if em_tokens else None,
                                        "origem": em_horas[1] if em_horas else "não chegou nos marcos medidos"})

    # segunda semente: a mesma conta no mesmo número de tokens
    sementes = []
    for s in series:
        if s["semente"] != 1337:
            base = next((b for b in principais if b["tamanho"] == s["tamanho"]), None)
            if base:
                a, b = base["pontos"][-1], s["pontos"][-1]
                linha = {"tamanho": s["tamanho"], "tokens": b["tokens"], "semente_1337": a["teste"],
                         f"semente_{s['semente']}": b["teste"], "diferenca": round(abs(a["teste"] - b["teste"]), 5)}
                if mini:
                    linha["vantagem_sobre_o_mini"] = {str(base["semente"]): round(mini["pontos"][-1]["teste"] - a["teste"], 4),
                                                      str(s["semente"]): round(mini["pontos"][-1]["teste"] - b["teste"], 4)}
                sementes.append(linha)
    return {"tokens_iguais": {"tokens": tokens, "tamanhos": iguais_tokens},
            "horas_iguais": iguais_horas, "ate_a_perda_final_do_mini": ate_a_perda_do_mini, "segunda_semente": sementes}


def ler_continuacao() -> dict | None:
    """A curva inteira do candidato: o treino de comparação e depois a continuação (do treino.csv)."""
    arquivo = RAIZ / "dados" / "fase2" / "candidato" / "cerebro" / "treino.csv"
    finalista = RAIZ / "docs" / "fase2" / "finalista.json"
    if not (arquivo.exists() and finalista.exists()):
        return None
    with open(arquivo, encoding="utf-8") as f:
        linhas = [l for l in csv.DictReader(f) if l["perda_val"]]
    pontos = [{"passo": int(l["passo"]), "tokens": int(l["passo"]) * TOKENS_POR_PASSO,
               "horas": float(l["segundos"]) / 3600, "validacao_80_janelas": float(l["perda_val"])} for l in linhas]
    if not pontos or pontos[-1]["passo"] <= 7325:
        return None
    return {"tamanho": json.loads(finalista.read_text(encoding="utf-8"))["finalista"], "pontos": pontos}


# --- os gráficos (SVG à mão: o projeto não depende de biblioteca de gráficos) -----------------------

def _passo_bom(intervalo: float, alvo: int = 6) -> float:
    bruto = intervalo / alvo
    for passo in (0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10, 20, 25, 50, 100, 200):
        if bruto <= passo:
            return passo
    return bruto


def grafico(series: list[dict], refs: list[tuple[float, str]], titulo: str, rotulo_x: str, rotulo_y: str,
            formato_x, arquivo: Path, largura: int = 760, altura: int = 440) -> None:
    """Linhas com marcadores, legenda, rótulo direto no fim de cada linha e linhas de referência."""
    x0, x1, y0, y1 = 70, largura - 170, 74, altura - 56
    xs = [p[0] for s in series for p in s["pontos"]]
    ys = [p[1] for s in series for p in s["pontos"]] + [v for v, _ in refs]
    passo_y = _passo_bom(max(ys) - min(ys), 10)
    y_min = passo_y * int(min(ys) / passo_y - 0.25)
    y_max = passo_y * (int(max(ys) / passo_y) + 1)
    passo_x = _passo_bom(max(xs), 6)
    x_max = passo_x * -(-(max(xs) - 0.01 * passo_x) // passo_x)   # 60,006 mi de tokens cabe no 60

    def px(x: float) -> float:
        return x0 + (x1 - x0) * x / x_max

    def py(y: float) -> float:
        return y1 - (y1 - y0) * (y - y_min) / (y_max - y_min)

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura} {altura}" width="{largura}" height="{altura}" '
         f'font-family=\'{FONTE}\' role="img" aria-label="{titulo}">',
         f'<rect width="{largura}" height="{altura}" fill="{FUNDO}"/>',
         f'<text x="{x0 - 52}" y="24" font-size="15" font-weight="600" fill="{TINTA}">{titulo}</text>']
    # legenda numa linha, acima do gráfico
    lx = x0 - 52
    for s in series:
        tracejado = ' stroke-dasharray="6 4"' if s.get("tracejado") else ""
        o.append(f'<line x1="{lx}" y1="46" x2="{lx + 22}" y2="46" stroke="{s["cor"]}" stroke-width="2.5"{tracejado}/>')
        o.append(f'<text x="{lx + 28}" y="50" font-size="12" fill="{TINTA_2}">{s["nome"]}</text>')
        lx += 40 + 7 * len(s["nome"])
    # grade e eixos
    y = y_min
    while y <= y_max + 1e-9:
        o.append(f'<line x1="{x0}" y1="{py(y):.1f}" x2="{x1}" y2="{py(y):.1f}" stroke="{GRADE}" stroke-width="1"/>')
        o.append(f'<text x="{x0 - 8}" y="{py(y) + 4:.1f}" font-size="11" fill="{APAGADA}" text-anchor="end" '
                 f'style="font-variant-numeric: tabular-nums">{br(y, 2)}</text>')
        y += passo_y
    x = 0.0
    while x <= x_max + 1e-9:
        o.append(f'<text x="{px(x):.1f}" y="{y1 + 18}" font-size="11" fill="{APAGADA}" text-anchor="middle" '
                 f'style="font-variant-numeric: tabular-nums">{formato_x(x)}</text>')
        x += passo_x
    o.append(f'<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" stroke="{EIXO}" stroke-width="1"/>')
    o.append(f'<text x="{(x0 + x1) / 2}" y="{altura - 14}" font-size="12" fill="{TINTA_2}" text-anchor="middle">{rotulo_x}</text>')
    o.append(f'<text transform="translate(16 {(y0 + y1) / 2}) rotate(-90)" font-size="12" fill="{TINTA_2}" '
             f'text-anchor="middle">{rotulo_y}</text>')
    # referências: tracejadas e apagadas, com o nome no começo da linha
    for i, (valor, nome) in enumerate(sorted(refs, reverse=True)):
        o.append(f'<line x1="{x0}" y1="{py(valor):.1f}" x2="{x1}" y2="{py(valor):.1f}" stroke="{APAGADA}" '
                 f'stroke-width="1" stroke-dasharray="3 3"/>')
        # a mais baixa leva o nome embaixo da linha: o teto e o critério ficam a 0,05 um do outro
        y_nome = py(valor) + 14 if i == len(refs) - 1 and len(refs) > 1 else py(valor) - 5
        o.append(f'<text x="{x0 + 6}" y="{y_nome:.1f}" font-size="11" fill="{TINTA_2}">{nome} {br(valor)}</text>')
    # as linhas, com um marcador por medida (a dica mostra o número ao passar o mouse)
    finais = []
    for s in series:
        caminho = " ".join(f"{'M' if i == 0 else 'L'}{px(a):.1f},{py(b):.1f}" for i, (a, b, _) in enumerate(s["pontos"]))
        tracejado = ' stroke-dasharray="6 4"' if s.get("tracejado") else ""
        o.append(f'<path d="{caminho}" fill="none" stroke="{s["cor"]}" stroke-width="2" stroke-linejoin="round"{tracejado}/>')
        for a, b, dica in s["pontos"]:
            raio = 4 if s.get("marcadores", True) else 0
            if raio:
                o.append(f'<circle cx="{px(a):.1f}" cy="{py(b):.1f}" r="{raio}" fill="{s["cor"]}" stroke="{FUNDO}" '
                         f'stroke-width="2"><title>{dica}</title></circle>')
        a, b, _ = s["pontos"][-1]
        finais.append([py(b), px(a), f'{s["nome"]} {br(b)}'])
    # rótulos diretos no fim de cada linha, afastados para não se encostarem
    finais.sort()
    for i in range(1, len(finais)):
        finais[i][0] = max(finais[i][0], finais[i - 1][0] + 15)
    for y_rotulo, x_fim, texto in finais:
        o.append(f'<text x="{max(x_fim, x1) + 10:.1f}" y="{y_rotulo + 4:.1f}" font-size="12" fill="{TINTA}">{texto}</text>')
    o.append("</svg>")
    arquivo.write_text("\n".join(o) + "\n", encoding="utf-8")


def _nome_legivel(serie: dict) -> str:
    return serie["tamanho"] if serie["semente"] == 1337 else f'{serie["tamanho"]} (semente {serie["semente"]})'


def desenhar(series: list[dict], refs: dict, continuacao: dict | None) -> list[Path]:
    linhas_de_referencia = [(refs["trigrama"], "trigrama contado"), (refs["teto_mini"], "teto do mini"),
                            (refs["criterio"], "critério")]
    feitos = []
    for eixo, titulo, rotulo_x, formato, arquivo in (
            ("tokens", "Perda no teste fixo por tokens de treino", "milhões de tokens de treino",
             lambda v: f"{v:.0f}", "perda-por-tokens.svg"),
            ("horas", "Perda no teste fixo por horas de placa", "horas de treino na RX 570 (sem as medidas)",
             lambda v: br(v, 0 if v == int(v) else 1), "perda-por-horas.svg")):
        desenho = []
        for s in series:
            pontos = []
            for p in s["pontos"]:
                x = p["tokens"] / 1e6 if eixo == "tokens" else p["horas"]
                dica = (f'{_nome_legivel(s)}: {p["tokens"] / 1e6:.0f} mi de tokens, {br(p["horas"], 2)} h, '
                        f'teste {br(p["teste"])} ({br(p["bits_por_byte"], 3)} bits por byte), medido')
                pontos.append((x, p["teste"], dica))
            desenho.append({"nome": _nome_legivel(s), "cor": CORES.get(s["tamanho"], TINTA_2),
                            "tracejado": s["semente"] != 1337, "pontos": pontos})
        grafico(desenho, linhas_de_referencia, titulo, rotulo_x, "nats por token (menor é melhor)", formato,
                ESCALA / arquivo)
        feitos.append(ESCALA / arquivo)
    if continuacao:
        pontos = [(p["tokens"] / 1e6, p["validacao_80_janelas"],
                   f'passo {p["passo"]}: {p["tokens"] / 1e6:.0f} mi de tokens, validação {br(p["validacao_80_janelas"])}')
                  for p in continuacao["pontos"]]
        corte = next(i for i, p in enumerate(continuacao["pontos"]) if p["passo"] > 7325)
        desenho = [{"nome": "comparação (cosseno)", "cor": CORES.get(continuacao["tamanho"], TINTA_2),
                    "pontos": pontos[:corte], "marcadores": False},
                   {"nome": "continuação (taxa constante)", "cor": CORES.get(continuacao["tamanho"], TINTA_2),
                    "tracejado": True, "pontos": pontos[corte - 1:], "marcadores": False}]
        grafico(desenho, [(refs["teto_mini"], "teto do mini (no teste)"), (refs["criterio"], "critério (no teste)")],
                f'O finalista ({continuacao["tamanho"]}) do começo ao fim', "milhões de tokens de treino",
                "validação do treino (80 janelas)", lambda v: f"{v:.0f}", ESCALA / "continuacao.svg")
        feitos.append(ESCALA / "continuacao.svg")
    return feitos


def main() -> int:
    nomes = ORDEM + sorted(p.name for p in ESCALA.iterdir() if p.is_dir() and "-s" in p.name)
    series = [s for s in (ler_serie(n) for n in nomes) if s]
    if not series:
        print("nenhuma medida em docs/fase2/escala ainda")
        return 1
    refs = referencias()
    continuacao = ler_continuacao()
    resultado = {
        "observacao": ("'medido' saiu do protocolo (teste fixo, 2 mi de tokens); 'estimado' é uma reta entre dois "
                       "marcos medidos. Os marcos do meio são do meio do cosseno, com a taxa ainda alta: só o de 60 mi "
                       "terminou de descer a taxa. Por isso a comparação em horas iguais favorece o mini, que é o "
                       "único a chegar no fim do cosseno nesse tempo."),
        "referencias": refs,
        "series": series,
        "comparacoes": comparar(series, refs),
        "continuacao": continuacao,
    }
    (ESCALA / "curvas.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    feitos = desenhar(series, refs, continuacao)
    print(f"{len(series)} curvas; escrito curvas.json e " + ", ".join(f.name for f in feitos))
    return 0


if __name__ == "__main__":
    sys.exit(main())
