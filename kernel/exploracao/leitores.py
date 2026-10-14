"""Como tirar texto de cada tipo de arquivo.

Texto puro é só abrir. Word, Excel e PowerPoint são arquivos .zip com XML
dentro, então dá para ler com a biblioteca padrão. PDF é o único que precisa de
ajuda de fora (``pypdf``); sem ela, o PDF entra no mapa só pelo nome.
"""
from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path

TEXTO_PURO = {".txt", ".md", ".csv", ".log", ".json", ".ini", ".toml", ".yaml", ".yml", ".xml", ".html", ".htm",
              ".py", ".js", ".ts", ".cs", ".java", ".c", ".cpp", ".h", ".sql", ".bat", ".ps1", ".tex"}
OFFICE = {".docx": ("word/document.xml",), ".xlsx": ("xl/sharedStrings.xml",), ".pptx": ("ppt/slides/",)}
LEGIVEIS = TEXTO_PURO | set(OFFICE) | {".pdf"}
# O que é documento (texto feito para gente ler) e o que é código ou configuração (feito para máquina).
DOCUMENTOS = {".txt", ".md", ".csv", ".tex", ".html", ".htm", ".docx", ".xlsx", ".pptx", ".pdf"}
CODIGO = LEGIVEIS - DOCUMENTOS
# Nestes tipos qualquer coisa pode estar escrita: só vale guardar se for prosa (ver ``parece_leitura``).
SO_SE_FOR_PROSA = {".txt", ".md", ".html", ".htm", ".log"}
PAGINAS_DE_PDF = 8

# Arquivos que vêm junto com todo programa e não dizem nada sobre você.
_DE_ENFEITE = {"license", "licence", "licenca", "copying", "notice", "eula", "authors", "contributors",
               "changelog", "changes", "history", "thirdpartynotices", "patents", "credits", "copyright"}
_VAZIAS_EM_INGLES = frozenset("""the and of to in is for that with this it as on are be by or an at from not you your can
    will have has if we was which their all""".split())
_LETRAS = re.compile(r"[^\W\d_]+")


def de_enfeite(caminho: Path) -> bool:
    """LICENSE.txt, CHANGELOG.md, third-party-notices.txt e parecidos."""
    nome = re.sub(r"[\W_\d]+", "", caminho.stem.lower())
    return nome in _DE_ENFEITE


def parece_leitura(texto: str) -> bool:
    """O texto é prosa em português ou inglês? (E não uma lista de arquivos, um código ou outra língua.)

    Em qualquer prosa, de uma em cada três a uma em cada duas palavras é "vazia" (de, que, para, the,
    of...). Numa lista de caminhos ou numa língua que ele não fala, quase nenhuma é.
    """
    from ..memoria.texto import PARADAS, sem_acento

    palavras = _LETRAS.findall(texto[:6000].lower())
    if len(palavras) < 5:
        return False
    vazias = sum(1 for p in palavras if p in _VAZIAS_EM_INGLES or sem_acento(p) in PARADAS)
    return vazias / len(palavras) >= 0.15

_ETIQUETA = re.compile(r"<[^>]+>")
_FIM_DE_PARAGRAFO = re.compile(r"</w:p>|</a:p>|</si>|<w:br\s*/>")


def _texto_puro(caminho: Path, limite: int) -> str | None:
    with open(caminho, "rb") as f:
        bruto = f.read(limite * 4)
    if b"\x00" in bruto[:2000]:
        return None  # parece binário disfarçado
    try:
        texto = bruto.decode("utf-8")
    except UnicodeDecodeError:
        texto = bruto.decode("cp1252", errors="replace")  # o jeito antigo do Windows
    if caminho.suffix.lower() in (".html", ".htm", ".xml"):
        texto = html.unescape(_ETIQUETA.sub(" ", re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", texto)))
    return texto


def _office(caminho: Path, alvos: tuple[str, ...]) -> str | None:
    partes = []
    with zipfile.ZipFile(caminho) as pacote:
        for nome in sorted(pacote.namelist()):
            if nome.startswith(alvos) and nome.endswith(".xml"):
                xml = pacote.read(nome).decode("utf-8", errors="replace")
                xml = _FIM_DE_PARAGRAFO.sub("\n", xml)
                partes.append(html.unescape(_ETIQUETA.sub("", xml)))
    return "\n".join(partes) if partes else None


def _pdf(caminho: Path) -> str | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    leitor = PdfReader(str(caminho))
    paginas = [pagina.extract_text() or "" for pagina in leitor.pages[:PAGINAS_DE_PDF]]
    return "\n".join(paginas)


def ler(caminho: Path, limite: int = 6000) -> str | None:
    """O texto do arquivo (até ``limite`` caracteres), ou None se não der para ler."""
    extensao = caminho.suffix.lower()
    try:
        if extensao in TEXTO_PURO:
            texto = _texto_puro(caminho, limite)
        elif extensao in OFFICE:
            texto = _office(caminho, OFFICE[extensao])
        elif extensao == ".pdf":
            texto = _pdf(caminho)
        else:
            return None
    except Exception:  # arquivo corrompido, protegido por senha, em uso...
        return None
    if not texto:
        return None
    texto = re.sub(r"[ \t\r\f\v]+", " ", texto)
    texto = re.sub(r" ?\n\s*", "\n", texto).strip()  # sem linhas em branco nem espaço sobrando
    return texto[:limite] or None


def pedacos(texto: str, tamanho: int = 500) -> list[str]:
    """Corta o texto em pedaços de mais ou menos ``tamanho`` letras, sem partir linhas no meio."""
    saida, atual = [], ""
    for linha in texto.split("\n"):
        linha = linha.strip()
        if not linha:
            continue
        while len(linha) > tamanho * 2:  # uma linha gigante (CSV, JSON de uma linha só)
            saida.append(linha[:tamanho])
            linha = linha[tamanho:]
        if atual and len(atual) + len(linha) > tamanho:
            saida.append(atual)
            atual = linha
        else:
            atual = f"{atual} {linha}".strip()
    if atual:
        saida.append(atual)
    return saida
