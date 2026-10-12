"""Ferramenta: abrir um endereço da web no seu navegador.

É o único ponto em que ele toca nos seus navegadores, e só para ISTO: mostrar
uma página a você, no navegador padrão do Windows, depois da sua confirmação.
Ele não lê nada de dentro do seu navegador (histórico, senhas, contas abertas).
Para ler páginas ele usa o leitor próprio, em ``kernel/internet/rede.py``.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

from ..seguranca import Nivel
from .base import ErroFerramenta, Ferramenta

_ESTRANHOS = set(' "<>|^`\n\r\t')


def _conferir(url: str) -> str:
    url = str(url).strip()
    try:
        partes = urlsplit(url)
    except ValueError:
        partes = None
    if partes is None or partes.scheme not in ("http", "https") or not partes.hostname or _ESTRANHOS & set(url):
        raise ErroFerramenta("Só abro endereços da web (http ou https).")
    return url


class AbrirPagina(Ferramenta):
    nome = "abrir_pagina"
    descricao = "Abre um endereço da web no seu navegador padrão."
    nivel = Nivel.SISTEMA

    def __init__(self, lancar=None):
        self._lancar = lancar or os.startfile  # os testes trocam isto para não abrir nada de verdade

    def preparar(self, argumentos: dict) -> tuple[dict, str]:
        url = _conferir(argumentos.get("url", ""))
        return {"url": url}, f"Abrir {url} no seu navegador"

    def executar(self, argumentos: dict) -> str:
        url = _conferir(argumentos["url"])   # confere de novo: é isto que vai para o Windows
        self._lancar(url)
        return f"Abri {urlsplit(url).hostname} no seu navegador."
