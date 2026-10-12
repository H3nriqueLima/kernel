"""De HTML para texto: o que numa página é leitura, e o que é enfeite.

Uma página da web é mais menu, anúncio e código do que texto. O leitor daqui
percorre as etiquetas uma vez e separa:

- o **título**;
- os **blocos de texto** (parágrafos, itens de lista, títulos de seção), jogando
  fora o que está dentro de ``<script>``, ``<style>``, ``<nav>``, ``<footer>``,
  ``<form>`` e parecidos;
- os **links**, já com o endereço completo.

Depois escolhe os blocos que parecem leitura: os que estão dentro de
``<article>`` ou ``<main>`` (se houver bastante texto ali), com um tamanho
mínimo, e em que a maior parte das letras não é link (um bloco quase todo feito
de links é menu).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

_SEM_LEITURA = {"script", "style", "noscript", "template", "svg", "canvas", "iframe", "select", "button",
                "form", "nav", "footer", "aside", "figure", "menu", "dialog"}
_BLOCOS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th", "section", "article", "main",
           "blockquote", "pre", "dd", "dt", "ul", "ol", "table", "header", "br", "hr"}
_TITULOS = {"h1", "h2", "h3", "h4"}
_MIOLO = {"article", "main"}
_SEM_FECHO = {"br", "hr", "img", "input", "meta", "link", "source", "wbr", "area", "base", "col", "embed", "track"}
_ESPACOS = re.compile(r"\s+")


@dataclass
class Pagina:
    titulo: str
    texto: str                                                   # os blocos de leitura, um por linha
    links: list[tuple[str, str]] = field(default_factory=list)   # (endereço completo, texto do link)


class _Leitor(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.titulo = ""
        self.blocos: list[tuple[str, str, bool, int]] = []   # (etiqueta, texto, dentro do miolo?, letras em links)
        self.links: list[tuple[str, str]] = []
        self._calado = 0            # dentro de quantas etiquetas sem leitura
        self._no_miolo = 0
        self._no_titulo = False
        self._etiqueta = "div"
        self._texto: list[str] = []
        self._em_links = 0
        self._link: list | None = None   # [endereço, pedaços de texto]

    def _fechar_bloco(self) -> None:
        texto = _ESPACOS.sub(" ", "".join(self._texto)).strip()
        if texto:
            self.blocos.append((self._etiqueta, texto, self._no_miolo > 0, self._em_links))
        self._texto, self._em_links = [], 0

    def handle_starttag(self, etiqueta, atributos):
        if etiqueta in _SEM_LEITURA:
            self._fechar_bloco()
            self._calado += 1
        elif etiqueta == "title":
            self._no_titulo = True
        elif etiqueta in _BLOCOS:
            self._fechar_bloco()
            if etiqueta not in _SEM_FECHO:
                self._etiqueta = etiqueta
            self._no_miolo += etiqueta in _MIOLO
        elif etiqueta == "a" and not self._calado:
            endereco = dict(atributos).get("href") or ""
            self._link = [endereco, []]

    def handle_endtag(self, etiqueta):
        if etiqueta in _SEM_LEITURA:
            self._calado = max(self._calado - 1, 0)
        elif etiqueta == "title":
            self._no_titulo = False
        elif etiqueta in _BLOCOS:
            self._fechar_bloco()
            self._etiqueta = "div"
            if etiqueta in _MIOLO:
                self._no_miolo = max(self._no_miolo - 1, 0)
        elif etiqueta == "a" and self._link is not None:
            endereco, pedacos = self._link
            self._link = None
            texto = _ESPACOS.sub(" ", "".join(pedacos)).strip()
            completo = urljoin(self.base, endereco.strip())
            if texto and urlsplit(completo).scheme in ("http", "https"):
                self.links.append((completo.split("#")[0], texto))

    def handle_data(self, dados):
        if self._no_titulo:
            self.titulo += dados
        elif not self._calado:
            self._texto.append(dados)
            if self._link is not None:
                self._link[1].append(dados)
                self._em_links += len(dados.strip())


def ler_html(html: str, base: str = "") -> Pagina:
    """O título, o texto de leitura e os links de uma página."""
    leitor = _Leitor(base)
    try:
        leitor.feed(html)
        leitor.close()
    except Exception:  # noqa: BLE001  HTML muito torto: fica o que deu para ler até ali
        pass
    leitor._fechar_bloco()

    def de_leitura(bloco) -> bool:
        etiqueta, texto, _, em_links = bloco
        if em_links > 0.6 * len(texto):
            return False                       # quase tudo link: é menu
        return len(texto) >= (3 if etiqueta in _TITULOS else 60)

    bons = [b for b in leitor.blocos if de_leitura(b)]
    do_miolo = [b for b in bons if b[2]]
    if sum(len(b[1]) for b in do_miolo) >= 400:   # a página marcou onde está o texto principal
        bons = do_miolo
    linhas, anterior_era_titulo = [], False
    for etiqueta, texto, _, _ in bons:
        eh_titulo = etiqueta in _TITULOS
        if eh_titulo and anterior_era_titulo:
            linhas.pop()                          # título de seção vazia: não fica dois títulos seguidos
        linhas.append(texto)
        anterior_era_titulo = eh_titulo
    if linhas and anterior_era_titulo:
        linhas.pop()
    titulo = _ESPACOS.sub(" ", leitor.titulo).strip()
    if not titulo:
        titulo = next((texto for etiqueta, texto, _, _ in leitor.blocos if etiqueta == "h1"), "")
    vistos, links = set(), []
    for endereco, texto in leitor.links:
        if endereco not in vistos:
            vistos.add(endereco)
            links.append((endereco, texto))
    return Pagina(titulo[:200], "\n".join(linhas), links)
