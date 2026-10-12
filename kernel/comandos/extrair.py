"""Tirar os argumentos de dentro do pedido.

O classificador diz QUE tipo de pedido é; estas funções descobrem O QUE:
qual programa, qual pasta, qual lembrete e para quando. São regras escritas à
mão (expressões regulares), simples de ler e de consertar.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from ..memoria.texto import normalizar

_CHAMADO = r"^\s*(?:kernel\s*[,:]?\s+)?"
_VERBO_ABRIR = r"(?:abr\w+|inici\w+|execut\w+|rod[ae]\w*|lan[cç]\w+|lig[au]\w*|bot[ae]\w*)"
_ARTIGOS = r"^(?:(?:o|a|os|as|um|uma|meu|minha|programa|aplicativo|app|software)\s+)+"
_CORTESIA = r"[\s,]*(?:pra mim|para mim|por favor|por gentileza|pra abrir|a[ií]|agora|pfv)[\s.!?]*$"


def _limpar_fim(texto: str) -> str:
    anterior = None
    while anterior != texto:
        anterior = texto
        texto = re.sub(_CORTESIA, "", texto, flags=re.I)
    return texto.strip(" .!?\"'")


def programa(texto: str) -> str:
    """ "pode abrir o bloco de notas pra mim?" -> "bloco de notas" """
    achado = re.search(rf"\b{_VERBO_ABRIR}\s+(.*)", texto, flags=re.I)
    resto = achado.group(1) if achado else re.sub(_CHAMADO, "", texto, flags=re.I)
    resto = re.sub(r"^a[ií]\s+", "", resto, flags=re.I)
    resto = re.sub(_ARTIGOS, "", resto, flags=re.I)
    return _limpar_fim(resto)


_PASTAS_FALADAS = ("area de trabalho", "meus documentos", "documentos", "downloads", "desktop",
                   "imagens", "fotos", "musicas", "musica", "videos", "video", "projeto")


def pasta(texto: str) -> str:
    """ "o que tem na pasta de downloads?" -> "downloads"; aceita também um caminho completo."""
    caminho = re.search(r'[A-Za-z]:[\\/][^"<>|?*\n]*', texto)
    if caminho:
        return caminho.group(0).strip(" .")
    plano = normalizar(texto)
    for nome in _PASTAS_FALADAS:
        if re.search(rf"\b{nome}\b", plano):
            return nome
    depois = re.search(r"\bpasta\s+(?:de\s+|do\s+|da\s+)?([\w .-]+)", plano)
    return _limpar_fim(depois.group(1)) if depois else ""


_PREFIXO_LEMBRETE = re.compile(
    _CHAMADO
    + r"(?:por favor,?\s+)?(?:"
    r"n[aã]o\s+(?:me\s+)?(?:deix\w+|esque\w+)\s+(?:esquecer\s+)?(?:de\s+)?(?:me\s+lembrar\s+)?|"
    r"(?:quero|preciso|cri\w+|adicion\w+|marc\w+|agend\w+|anot\w+)\s+(?:um\s+|o\s+)?lembrete\s*|"
    r"(?:preciso\s+)?(?:me\s+)?(?:lembr\w+|anot\w+|guard\w+|registr\w+|memoriz\w+|avis\w+|toma\s+nota)(?:-me)?\s*|"
    r"lembrete\s*)"
    r"(?:a[ií]\s*|isso\s*|pra mim\s*|para mim\s*)*[:,]?\s*"
    r"(?:(?:de que|de|que|para|pra)\s+)?",
    flags=re.I,
)

_NUMEROS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5,
            "dez": 10, "quinze": 15, "vinte": 20, "trinta": 30, "meia": 0.5}


def horario(texto: str, agora: datetime) -> datetime | None:
    """Acha "em 20 minutos", "às 15h30", "amanhã", "amanhã às 8h"... ou devolve None."""
    plano = normalizar(texto)

    relativo = re.search(r"\b(?:em|daqui a|daqui)\s+(\d+|[a-z]+)\s*(min|hora|dia)", plano)
    if relativo:
        bruto = relativo.group(1)
        quanto = float(bruto) if bruto.isdigit() else _NUMEROS.get(bruto)
        if quanto is not None:
            unidade = {"min": timedelta(minutes=1), "hora": timedelta(hours=1), "dia": timedelta(days=1)}
            return (agora + quanto * unidade[relativo.group(2)]).replace(microsecond=0)

    dias = 2 if "depois de amanha" in plano else 1 if re.search(r"\bamanha\b", plano) else 0
    hora = (re.search(r"\b(?:as|a)\s+(\d{1,2})(?:[:h](\d{2}))?\s*(?:h|hs|horas?)?\b", plano)
            or re.search(r"\b(\d{1,2})h(\d{2})?\b", plano)
            or re.search(r"\b(\d{1,2}):(\d{2})\b", plano))
    if hora and int(hora.group(1)) < 24 and int(hora.group(2) or 0) < 60:
        quando = (agora + timedelta(days=dias)).replace(
            hour=int(hora.group(1)), minute=int(hora.group(2) or 0), second=0, microsecond=0)
        if dias == 0 and quando <= agora:
            quando += timedelta(days=1)  # "às 8h" dito às 20h quer dizer amanhã
        return quando
    if dias:
        return (agora + timedelta(days=dias)).replace(hour=9, minute=0, second=0, microsecond=0)
    return None


_EXPRESSOES_DE_TEMPO = re.compile(
    r"\b(?:em|daqui a|daqui)\s+\S+\s*(?:minutos?|min|horas?|dias?)\b"
    r"|\bdepois de amanh[aã]\b|\bamanh[aã]\b"
    r"|\b(?:[aà]s|[aà])\s+\d{1,2}(?:[:h]\d{2})?\s*(?:hs|horas?|h)?(?!\w)"
    r"|\b\d{1,2}h(?:\d{2})?\b|\b\d{1,2}:\d{2}\b",
    flags=re.I,
)


def lembrete(texto: str, agora: datetime) -> tuple[str, datetime | None]:
    """ "me lembra de pagar o boleto amanhã às 10h" -> ("pagar o boleto", amanhã às 10h)"""
    corpo = _PREFIXO_LEMBRETE.sub("", texto, count=1).strip(" .!?\"'")
    quando = horario(texto, agora)
    if quando:
        # A data já foi entendida; no aviso, "amanhã" e "em 20 minutos" não fariam mais sentido.
        sem_tempo = " ".join(_EXPRESSOES_DE_TEMPO.sub(" ", corpo).split())
        sem_tempo = re.sub(r"^(?:de|para|pra|que)\s+", "", sem_tempo, flags=re.I).strip(" ,.")
        corpo = sem_tempo or corpo
    return corpo, quando
