"""As fontes de pesquisa: onde ele procura um assunto.

- **Wikipédia e Wikcionário**, pela API que a Wikimedia oferece a programas.
  É a fonte principal: texto limpo, em português, com licença livre.
- **Um buscador** (DuckDuckGo, na versão leve em HTML puro), para achar páginas
  do resto da web sobre o assunto. O buscador só indica endereços; quem lê cada
  página é o navegador dele, com todas as suas regras.

Se o buscador responder com um desafio ("prove que não é um robô"), a busca é
dada como indisponível. Ele não tenta contornar: fica com a Wikipédia.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlsplit

from .rede import ErroDeRede, Navegador

WIKIPEDIA = "pt.wikipedia.org"
WIKCIONARIO = "pt.wiktionary.org"
BUSCADOR = "https://lite.duckduckgo.com/lite/?"
_ESPACOS = re.compile(r"\s+")
_DESAFIO = re.compile(r"anomaly|captcha|unusual traffic|are you a robot|bots use", re.I)


class BuscadorIndisponivel(ErroDeRede):
    """O buscador não respondeu com resultados (fora do ar, ou pediu prova de que não é robô)."""


@dataclass
class Achado:
    titulo: str
    url: str
    texto: str      # o começo do artigo, ou o trecho que o buscador mostra
    fonte: str      # "Wikipédia", "Wikcionário" ou "busca"


def _api(navegador: Navegador, site: str, por_conta_propria: bool, **parametros) -> dict:
    consulta = urlencode({"action": "query", "format": "json", "formatversion": 2, "utf8": 1, **parametros})
    resposta = navegador.abrir(f"https://{site}/w/api.php?{consulta}", por_conta_propria)
    try:
        return json.loads(resposta.texto).get("query", {})
    except ValueError as erro:
        raise ErroDeRede("a resposta da API não é JSON") from erro


def wikipedia(navegador: Navegador, termo: str, por_conta_propria: bool = True, k: int = 3,
              site: str = WIKIPEDIA) -> list[Achado]:
    """Os ``k`` artigos que a busca da Wikipédia acha para o termo, cada um com a sua introdução."""
    dados = _api(navegador, site, por_conta_propria, generator="search", gsrsearch=termo, gsrlimit=k,
                 prop="extracts|info", exintro=1, explaintext=1, exlimit=k, inprop="url")
    paginas = sorted(dados.get("pages", []), key=lambda p: p.get("index", 0))
    return [Achado(p["title"], p.get("fullurl", f"https://{site}/wiki/{p['title'].replace(' ', '_')}"),
                   (p.get("extract") or "").strip(), "Wikipédia") for p in paginas if p.get("title")]


def artigo(navegador: Navegador, titulo: str, por_conta_propria: bool = True, site: str = WIKIPEDIA,
           fonte: str = "Wikipédia") -> Achado | None:
    """O texto inteiro de um artigo (sem formatação), pelo título exato."""
    dados = _api(navegador, site, por_conta_propria, titles=titulo, prop="extracts|info", explaintext=1,
                 exsectionformat="plain", exlimit=1, inprop="url", redirects=1)
    for p in dados.get("pages", []):
        texto = (p.get("extract") or "").strip()
        if texto and not p.get("missing"):
            return Achado(p["title"], p.get("fullurl", f"https://{site}/wiki/{p['title'].replace(' ', '_')}"), texto, fonte)
    return None


def wikcionario(navegador: Navegador, palavra: str, por_conta_propria: bool = True) -> Achado | None:
    """O verbete de uma palavra no dicionário livre."""
    return artigo(navegador, palavra.lower(), por_conta_propria, WIKCIONARIO, "Wikcionário")


class _Resultados(HTMLParser):
    """Lê a página de resultados do buscador leve: cada resultado é um link ``result-link``
    seguido, linhas abaixo, de uma célula ``result-snippet`` com o trecho."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.achados: list[Achado] = []
        self._onde: str | None = None   # "titulo" ou "trecho": onde cai o texto que vier agora
        self._texto: list[str] = []
        self._url = ""

    def handle_starttag(self, etiqueta, atributos):
        atributos = dict(atributos)
        classes = (atributos.get("class") or "").split()
        if etiqueta == "a" and "result-link" in classes:
            self._onde, self._texto, self._url = "titulo", [], _destino(atributos.get("href") or "")
        elif etiqueta == "td" and "result-snippet" in classes:
            self._onde, self._texto = "trecho", []

    def handle_endtag(self, etiqueta):
        texto = _ESPACOS.sub(" ", "".join(self._texto)).strip()
        if etiqueta == "a" and self._onde == "titulo":
            if texto and self._url:
                self.achados.append(Achado(texto, self._url, "", "busca"))
            self._onde = None
        elif etiqueta == "td" and self._onde == "trecho":
            if self.achados and not self.achados[-1].texto:
                self.achados[-1].texto = texto
            self._onde = None

    def handle_data(self, dados):
        if self._onde:
            self._texto.append(dados)


def _destino(endereco: str) -> str:
    """O buscador embrulha cada resultado num endereço dele mesmo; o destino de verdade vem no parâmetro ``uddg``."""
    if endereco.startswith("//"):
        endereco = "https:" + endereco
    partes = urlsplit(endereco)
    if partes.hostname and partes.hostname.endswith("duckduckgo.com"):
        return parse_qs(partes.query).get("uddg", [""])[0]   # sem ``uddg`` é anúncio ou link interno: fica de fora
    return endereco if partes.scheme in ("http", "https") else ""


def resultados_do_buscador(html: str) -> list[Achado]:
    leitor = _Resultados()
    leitor.feed(html)
    leitor.close()
    return leitor.achados


def buscar_na_web(navegador: Navegador, termo: str, por_conta_propria: bool = True, k: int = 6) -> list[Achado]:
    """Os primeiros resultados do buscador para o termo: (título, endereço, trecho)."""
    try:
        resposta = navegador.abrir(BUSCADOR + urlencode({"q": termo, "kl": "br-pt"}), por_conta_propria)
    except ErroDeRede as erro:
        raise BuscadorIndisponivel(str(erro)) from erro
    achados = resultados_do_buscador(resposta.texto)
    if not achados and _DESAFIO.search(resposta.texto):
        raise BuscadorIndisponivel("o buscador pediu prova de que não é um robô")
    return achados[:k]
