"""Wikipédia em português: baixar o dump e transformar em texto limpo.

O dump oficial vem em partes compactadas (.bz2), cada uma um XML enorme com o
texto dos artigos em "wikitexto" (cheio de {{predefinições}}, [[ligações]] e
tabelas). ``limpar`` é o seu pipeline de limpeza: tira a marcação e deixa só a
prosa. O resultado vai para ``dados/cerebro/corpus.txt``, um artigo depois do
outro, separados por ``<|fim|>``.

    python -m kernel cerebro wikipedia --partes 1
"""
from __future__ import annotations

import bz2
import html
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

from .tokenizador import FIM

INDICE = "https://dumps.wikimedia.org/ptwiki/latest/"
_AGENTE = {"User-Agent": "KERNEL-estudo/0.1 (projeto pessoal de aprendizado)"}
_PARTE = re.compile(r'href="(ptwiki-latest-pages-articles(\d+)\.xml-p(\d+)p\d+\.bz2)"[^\n]*?\s(\d+)\s*$', re.M)
_SECOES_FINAIS = ("ver também", "referências", "ligações externas", "bibliografia", "notas", "notas e referências")


def listar_partes() -> list[tuple[str, int]]:
    """As partes do dump mais recente: [(nome do arquivo, tamanho em bytes)], em ordem."""
    pedido = urllib.request.Request(INDICE, headers=_AGENTE)
    with urllib.request.urlopen(pedido, timeout=60) as resposta:
        pagina = resposta.read().decode("utf-8", errors="replace")
    return interpretar_indice(pagina)


def interpretar_indice(pagina: str) -> list[tuple[str, int]]:
    # Um mesmo número de parte pode vir em mais de um arquivo (articles4...p1629225 e
    # articles4...p2880805), então a ordem é pelo número e pela primeira página do arquivo.
    # Enquanto um dump novo é gerado, o mesmo trecho pode aparecer duas vezes (fins diferentes):
    # fica o arquivo maior de cada começo.
    partes: dict[tuple[int, int], tuple[str, int]] = {}
    for nome, numero, primeira, tamanho in _PARTE.findall(pagina):
        chave = (int(numero), int(primeira))
        if chave not in partes or int(tamanho) > partes[chave][1]:
            partes[chave] = (nome, int(tamanho))
    return [partes[chave] for chave in sorted(partes)]


def baixar(nome: str, pasta: Path, max_mb: float | None = None, ao_progredir=None) -> Path:
    """Baixa (ou continua baixando) uma parte. ``max_mb`` para cedo, para pegar só uma amostra."""
    destino = Path(pasta) / nome
    ja_tem = destino.stat().st_size if destino.exists() else 0
    limite = int(max_mb * 1024 * 1024) if max_mb else None
    if limite and ja_tem >= limite:
        return destino
    pedido = urllib.request.Request(INDICE + nome, headers={**_AGENTE, "Range": f"bytes={ja_tem}-"})
    try:
        resposta = urllib.request.urlopen(pedido, timeout=60)
    except urllib.error.HTTPError as erro:
        if erro.code == 416:  # já estava completo
            return destino
        raise
    with resposta, open(destino, "ab" if resposta.status == 206 else "wb") as saida:
        if resposta.status != 206:
            ja_tem = 0
        total = ja_tem + int(resposta.headers.get("Content-Length", 0))
        while True:
            bloco = resposta.read(1 << 20)
            if not bloco:
                break
            saida.write(bloco)
            ja_tem += len(bloco)
            if ao_progredir:
                ao_progredir(ja_tem, min(total, limite) if limite else total)
            if limite and ja_tem >= limite:
                break
    return destino


def artigos(arquivo: Path) -> Iterator[tuple[str, str]]:
    """Lê uma parte do dump e devolve (título, wikitexto) de cada artigo de verdade."""
    titulo, espaco, redireciona, raiz = "", "", False, None
    with bz2.open(arquivo, "rb") as f:
        try:
            for evento, no in ET.iterparse(f, events=("start", "end")):
                if evento == "start":
                    raiz = no if raiz is None else raiz
                    continue
                etiqueta = no.tag.rsplit("}", 1)[-1]
                if etiqueta == "title":
                    titulo = no.text or ""
                elif etiqueta == "ns":
                    espaco = no.text or ""
                elif etiqueta == "redirect":
                    redireciona = True
                elif etiqueta == "text":
                    if espaco == "0" and not redireciona and no.text:
                        yield titulo, no.text
                elif etiqueta == "page":
                    redireciona = False
                    raiz.clear()  # sem isto a árvore inteira ficaria na RAM
        except (EOFError, ET.ParseError):
            return  # arquivo baixado pela metade (amostra): usamos o que deu para ler


def _tirar_aninhado(texto: str, abre: str, fecha: str) -> str:
    """Remove trechos ``abre ... fecha``, mesmo com outros dentro (predefinições e tabelas)."""
    marcas = re.compile(re.escape(abre) + "|" + re.escape(fecha))
    saida, nivel, inicio = [], 0, 0
    for marca in marcas.finditer(texto):
        if marca.group() == abre:
            if nivel == 0:
                saida.append(texto[inicio:marca.start()])
            nivel += 1
        elif nivel:
            nivel -= 1
            if nivel == 0:
                inicio = marca.end()
    if nivel == 0:
        saida.append(texto[inicio:])
    return "".join(saida)


_BLOCOS = re.compile(r"<(math|gallery|timeline|code|pre|syntaxhighlight|source|imagemap|score|nowiki)\b[^>]*>.*?</\1>",
                     re.S | re.I)
_MIDIA = re.compile(r"\[\[(?:Ficheiro|Arquivo|Imagem|File|Image|Categoria|Category):"
                    r"(?:[^\[\]]|\[\[[^\[\]]*\]\])*\]\]", re.I)


def limpar(wikitexto: str) -> str:
    """Wikitexto -> prosa. Devolve parágrafos separados por linha em branco."""
    t = re.sub(r"<!--.*?-->", "", wikitexto, flags=re.S)
    t = re.sub(r"<ref[^>]*/>", "", t)
    t = re.sub(r"<ref\b.*?</ref>", "", t, flags=re.S | re.I)
    t = _BLOCOS.sub("", t)
    t = _tirar_aninhado(t, "{{", "}}")
    t = _tirar_aninhado(t, "{|", "|}")
    t = _MIDIA.sub("", t)
    t = re.sub(r"\[\[[a-z-]{2,12}:[^\]]*\]\]", "", t)             # ligações para outros idiomas
    t = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", t)       # [[alvo|texto]] -> texto
    t = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", t)          # [url texto] -> texto
    t = re.sub(r"\[https?://\S+\]", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"'{2,}", "", t)                                   # negrito e itálico
    t = html.unescape(t).replace("\xa0", " ")

    paragrafos = []
    for linha in t.split("\n"):
        linha = re.sub(r"[ \t]+", " ", linha).strip()
        titulo_de_secao = re.fullmatch(r"=+\s*(.*?)\s*=+", linha)
        if titulo_de_secao:
            if titulo_de_secao.group(1).lower() in _SECOES_FINAIS:
                break  # daqui para baixo só há listas de links
            continue
        if not linha or linha[0] in "*#:;|!{}" or len(linha) < 40:
            continue  # listas, restos de tabela e linhas soltas
        paragrafos.append(re.sub(r"\s+([,.;:])", r"\1", re.sub(r"\(\s*[,;]?\s*\)", "", linha)))
    return "\n\n".join(paragrafos)


def extrair(arquivos: list[Path], saida: Path, max_artigos: int | None = None,
            minimo: int = 500, ao_progredir=None) -> dict:
    """Limpa os artigos das partes baixadas e grava o corpus. Artigos repetidos são pulados."""
    vistos: set[int] = set()
    escritos = caracteres = 0
    with open(saida, "w", encoding="utf-8") as f:
        for arquivo in arquivos:
            for titulo, wikitexto in artigos(arquivo):
                texto = limpar(wikitexto)
                if len(texto) < minimo:
                    continue  # desambiguações, esboços e listas
                impressao = hash(texto[:300])
                if impressao in vistos:
                    continue
                vistos.add(impressao)
                f.write(f"{titulo}\n\n{texto}\n{FIM}\n")
                escritos += 1
                caracteres += len(texto)
                if ao_progredir and escritos % 1000 == 0:
                    ao_progredir(escritos, caracteres)
                if max_artigos and escritos >= max_artigos:
                    return {"artigos": escritos, "caracteres": caracteres}
    return {"artigos": escritos, "caracteres": caracteres}
