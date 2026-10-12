"""O selo do código de segurança.

O K.E.R.N.E.L pode mudar a própria memória, mas não o próprio freio. Nenhuma
ferramenta escreve em arquivos de código; este selo é o alarme caso isso mude
um dia. ``selo.json`` guarda a impressão digital (SHA-256) de cada arquivo desta
pasta. Na partida o serviço confere: se algo estiver diferente, ele sobe em modo
seguro.

Quando VOCÊ editar um arquivo daqui, leia a mudança e sele de novo:

    python -m kernel selar
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PASTA = Path(__file__).resolve().parent
SELO = PASTA / "selo.json"


def impressoes() -> dict[str, str]:
    digitais = {}
    for arquivo in sorted(PASTA.glob("*.py")):
        # O Git pode trocar o fim de linha (CRLF/LF) sem mudar o código: ignoramos isso.
        conteudo = arquivo.read_bytes().replace(b"\r\n", b"\n")
        digitais[arquivo.name] = hashlib.sha256(conteudo).hexdigest()
    return digitais


def selar() -> dict[str, str]:
    digitais = impressoes()
    SELO.write_text(json.dumps(digitais, indent=2) + "\n", encoding="utf-8")
    return digitais


def verificar() -> tuple[bool, list[str]]:
    """Devolve (está íntegro?, lista do que mudou)."""
    if not SELO.exists():
        return False, ["não existe selo (rode: python -m kernel selar)"]
    selado = json.loads(SELO.read_text(encoding="utf-8"))
    atual = impressoes()
    mudancas = [f"alterado: {nome}" for nome in atual if nome in selado and atual[nome] != selado[nome]]
    mudancas += [f"novo: {nome}" for nome in atual if nome not in selado]
    mudancas += [f"removido: {nome}" for nome in selado if nome not in atual]
    return not mudancas, mudancas
