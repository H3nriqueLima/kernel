"""Ferramenta: anotar um lembrete na memória.

Se o pedido trouxer um horário ("amanhã às 10h", "em 20 minutos"), o lembrete
ganha uma data e o laço de autonomia avisa quando ela chegar.
"""
from __future__ import annotations

from datetime import datetime

from ..seguranca import Nivel
from .base import ErroFerramenta, Ferramenta


class AnotarLembrete(Ferramenta):
    nome = "anotar_lembrete"
    descricao = "Guarda um lembrete na memória, com data se você disser uma."
    nivel = Nivel.MEMORIA

    def __init__(self, memoria):
        self.memoria = memoria

    def preparar(self, argumentos: dict) -> tuple[dict, str]:
        texto = str(argumentos.get("texto", "")).strip()
        if not texto:
            raise ErroFerramenta("O que eu devo anotar?")
        quando = argumentos.get("quando")
        descricao = f'Anotar o lembrete "{texto}"'
        if quando:
            descricao += f" para {datetime.fromisoformat(quando):%d/%m/%Y às %H:%M}"
        return {"texto": texto, "quando": quando}, descricao

    def executar(self, argumentos: dict) -> str:
        self.memoria.guardar(argumentos["texto"], tipo="lembrete", origem="usuario", quando=argumentos["quando"])
        if argumentos["quando"]:
            return f"Anotado. Aviso você em {datetime.fromisoformat(argumentos['quando']):%d/%m às %H:%M}."
        return "Anotado."
