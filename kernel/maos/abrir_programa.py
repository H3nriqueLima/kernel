"""Ferramenta: abrir um programa.

Ele só abre o que está numa de duas listas: a tabela ``[maos.programas]`` do
``kernel.toml`` e os atalhos do Menu Iniciar. Não existe "rodar um comando
qualquer": o alvo sempre sai dessas listas, nunca do texto que você digitou.
"""
from __future__ import annotations

import difflib
import os
import time
from pathlib import Path

from ..memoria.texto import normalizar
from ..seguranca import Nivel
from .base import ErroFerramenta, Ferramenta

_IGNORAR = ("uninstall", "desinstalar", "remover", "readme", "leia-me", "manual", "help", "ajuda")
_VAZIAS = {"o", "a", "os", "as", "um", "uma", "programa", "aplicativo", "app", "software", "do", "da", "de", "meu", "minha"}


def _atalhos_do_menu_iniciar() -> dict[str, tuple[str, str]]:
    pastas = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    ]
    achados = {}
    for pasta in pastas:
        if not pasta.is_dir():
            continue
        for atalho in pasta.rglob("*.lnk"):
            chave = normalizar(atalho.stem)
            if any(palavra in chave for palavra in _IGNORAR):
                continue
            achados.setdefault(chave, (atalho.stem, str(atalho)))
    return achados


class AbrirPrograma(Ferramenta):
    nome = "abrir_programa"
    descricao = "Abre um programa da sua lista ou do Menu Iniciar."
    nivel = Nivel.SISTEMA

    def __init__(self, cfg, lancar=None):
        self.cfg = cfg
        self._lancar = lancar or os.startfile  # os testes trocam isto para não abrir nada de verdade
        self._catalogo: dict[str, tuple[str, str]] = {}
        self._lido_em = 0.0

    def catalogo(self) -> dict[str, tuple[str, str]]:
        """nome normalizado -> (nome para mostrar, alvo). Relido a cada 5 minutos."""
        if not self._catalogo or time.time() - self._lido_em > 300:
            catalogo = _atalhos_do_menu_iniciar() if self.cfg.maos.atalhos_menu_iniciar else {}
            for nome, alvo in self.cfg.maos.programas.items():  # a sua lista vence o Menu Iniciar
                catalogo[normalizar(nome)] = (nome, alvo)
            self._catalogo, self._lido_em = catalogo, time.time()
        return self._catalogo

    def _achar(self, pedido: str) -> tuple[str, str]:
        catalogo = self.catalogo()
        palavras = [p for p in normalizar(pedido).split() if p not in _VAZIAS]
        if not palavras:
            raise ErroFerramenta("Qual programa você quer abrir?")
        chave = " ".join(palavras)
        if chave in catalogo:
            return catalogo[chave]
        # todas as palavras pedidas aparecem no nome; fica o nome mais curto
        contem = [nome for nome in catalogo if all(p in nome.split() for p in palavras)]
        if not contem:
            contem = [nome for nome in catalogo if all(p in nome for p in palavras)]
        if contem:
            return catalogo[min(contem, key=len)]
        parecidos = difflib.get_close_matches(chave, list(catalogo), n=3, cutoff=0.8)
        if parecidos:
            return catalogo[parecidos[0]]
        sugestoes = difflib.get_close_matches(chave, list(catalogo), n=3, cutoff=0.5)
        dica = f" Parecidos: {', '.join(catalogo[s][0] for s in sugestoes)}." if sugestoes else ""
        raise ErroFerramenta(
            f'Não conheço o programa "{pedido}".{dica} Você pode ensinar em kernel.toml, na tabela [maos.programas].'
        )

    def preparar(self, argumentos: dict) -> tuple[dict, str]:
        nome, alvo = self._achar(str(argumentos.get("programa", "")))
        return {"programa": nome, "alvo": alvo}, f'Abrir "{nome}" ({alvo})'

    def executar(self, argumentos: dict) -> str:
        alvo = argumentos["alvo"]
        if alvo not in {a for _, a in self.catalogo().values()}:
            raise ErroFerramenta("Esse alvo não está na lista de programas permitidos.")
        self._lancar(alvo)
        return f"Abri {argumentos['programa']}."
