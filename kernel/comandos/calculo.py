"""Contas em português: "quanto é 12 vezes 7?", "15% de 200", "raiz de 144".

Um analisador escrito à mão, em dois tempos: primeiro as palavras viram
símbolos ("vezes" -> "*"), depois uma descida recursiva calcula respeitando a
precedência (potência antes de multiplicação, multiplicação antes de soma).
Nada de ``eval``: só passa o que esta gramática reconhece.

    expressao = termo  { (+|-) termo }
    termo     = potencia { (*|/) potencia }
    potencia  = unario [ ^ potencia ]
    unario    = - unario | raiz unario | numero | ( expressao )
"""
from __future__ import annotations

import math
import re

from ..memoria.texto import normalizar

_ENTRADA = re.compile(r"^(?:kernel[, ]+)?(?:me diz |me diga |sabe )?(?:quanto (?:e|da|fica|sao|vale)|qual (?:e )?o resultado de|"
                      r"calcula|calcule|calcular|faz a conta|resolve|resolva)?\s*(?:a conta |o calculo )?(?:de )?")
_TROCAS = [
    (r"(\d+(?:[.,]\d+)?)\s*(?:%|por cento)\s*(?:de|do|da)\s*", r"(\1/100)*"),
    (r"\b(?:multiplicado por|vezes)\b", "*"),
    (r"(?<=\d)\s*x\s*(?=\d)", "*"),
    (r"\b(?:dividido por|sobre)\b", "/"),
    (r"\bmais\b", "+"),
    (r"\bmenos\b", "-"),
    (r"\b(?:elevado a|elevado ao)\b", "^"),
    (r"\bao quadrado\b", "^2"),
    (r"\bao cubo\b", "^3"),
    (r"\braiz(?: quadrada)?(?: de| do| da)?\b", "raiz"),
    (r"\bmetade (?:de|do|da)\b", "0.5*"),
    (r"\bdobro (?:de|do|da)\b", "2*"),
]
_SIMBOLO = re.compile(r"\s*(?:(\d+(?:\.\d+)?)|(raiz)|([-+*/^()]))")
_POR_EXTENSO = {palavra: valor for valor, palavra in enumerate(
    "zero um dois tres quatro cinco seis sete oito nove dez onze doze treze quatorze quinze dezesseis "
    "dezessete dezoito dezenove vinte".split())}
_POR_EXTENSO.update({"uma": 1, "duas": 2, "catorze": 14, "trinta": 30, "quarenta": 40, "cinquenta": 50,
                     "sessenta": 60, "setenta": 70, "oitenta": 80, "noventa": 90, "cem": 100, "mil": 1000})


class _Erro(Exception):
    pass


def _simbolos(texto: str) -> list:
    saida, posicao = [], 0
    texto = texto.strip()
    while posicao < len(texto):
        achado = _SIMBOLO.match(texto, posicao)
        if not achado:
            raise _Erro
        numero, raiz, operador = achado.groups()
        saida.append(float(numero) if numero else (raiz or operador))
        posicao = achado.end()
    return saida


class _Analisador:
    def __init__(self, simbolos: list):
        self.s, self.i = simbolos, 0

    def _olhar(self):
        return self.s[self.i] if self.i < len(self.s) else None

    def _pegar(self):
        self.i += 1
        return self.s[self.i - 1]

    def expressao(self) -> float:
        valor = self.termo()
        while self._olhar() in ("+", "-"):
            valor = valor + self.termo() if self._pegar() == "+" else valor - self.termo()
        return valor

    def termo(self) -> float:
        valor = self.potencia()
        while self._olhar() in ("*", "/"):
            if self._pegar() == "*":
                valor *= self.potencia()
            else:
                divisor = self.potencia()
                if divisor == 0:
                    raise ZeroDivisionError
                valor /= divisor
        return valor

    def potencia(self) -> float:
        base = self.unario()
        if self._olhar() == "^":
            self._pegar()
            expoente = self.potencia()
            if abs(expoente) > 200:
                raise OverflowError
            return base ** expoente
        return base

    def unario(self) -> float:
        simbolo = self._pegar() if self.i < len(self.s) else None
        if simbolo == "-":
            return -self.unario()
        if simbolo == "raiz":
            return math.sqrt(self.unario())
        if simbolo == "(":
            valor = self.expressao()
            if self._pegar() != ")":
                raise _Erro
            return valor
        if isinstance(simbolo, float):
            return simbolo
        raise _Erro


def _formatar(valor: float) -> str:
    if abs(valor - round(valor)) < 1e-9 and abs(valor) < 1e15:
        return f"{round(valor):,}".replace(",", ".")
    return f"{valor:,.4f}".rstrip("0").rstrip(".").replace(",", "§").replace(".", ",").replace("§", ".")


def tentar(texto: str) -> str | None:
    """Se o texto for uma conta, devolve a resposta em português; senão, None."""
    plano = normalizar(texto).strip(" ?!.=")
    plano = _ENTRADA.sub("", plano, count=1)
    plano = re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", plano)   # 1.000 -> 1000
    plano = re.sub(r"(?<=\d),(?=\d)", ".", plano)         # 3,5 -> 3.5
    plano = re.sub(r"[a-z]+", lambda m: str(_POR_EXTENSO.get(m.group(0), m.group(0))), plano)  # "dois" -> 2
    for padrao, troca in _TROCAS:
        plano = re.sub(padrao, troca, plano)
    try:
        simbolos = _simbolos(plano)
        if not any(s in ("+", "-", "*", "/", "^", "raiz") for s in simbolos):
            return None  # um número sozinho não é uma conta
        analisador = _Analisador(simbolos)
        valor = analisador.expressao()
        if analisador.i != len(simbolos) or isinstance(valor, complex) or not math.isfinite(valor):
            return None
    except ZeroDivisionError:
        return "Não dá para dividir por zero."
    except (_Erro, ValueError, OverflowError, IndexError):
        return None
    return f"Dá {_formatar(valor)}."
