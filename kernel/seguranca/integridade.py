"""O selo do código que aplica as regras.

O K.E.R.N.E.L pode mudar a própria memória, mas não o próprio freio. Nenhuma
ferramenta escreve em arquivos de código; este selo é o alarme caso isso mude
um dia. ``selo.json`` guarda a impressão digital (SHA-256) de cada componente
crítico (a lista ``CRITICOS`` abaixo): o que decide quando parar, quem pode
falar com ele, o que ele pode fazer e o que ele pode executar. Na partida, e
de 10 em 10 minutos com ele ligado, o serviço confere: se algo estiver
diferente, ele entra em modo seguro (sem mãos e sem autonomia).

Quando VOCÊ editar um desses arquivos, leia a mudança e sele de novo:

    python -m kernel selar
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PASTA = Path(__file__).resolve().parent   # kernel/seguranca
PACOTE = PASTA.parent                      # kernel/
SELO = PASTA / "selo.json"

# Caminhos relativos a kernel/. Um arquivo novo que caia num destes padrões também
# dispara o alarme (aparece como "novo"): uma ferramenta nova em maos/, por exemplo.
CRITICOS = (
    "seguranca/*.py",            # permissões, confirmações, pareamento do celular e este selo
    "interface/api.py",          # quem pode falar com ele: código da sessão, chave do celular
    "nucleo/servico.py",         # o freio, o desligar e o caminho de toda confirmação
    "nucleo/reflexos.py",        # o "para" que interrompe tudo
    "nucleo/estudo.py",          # o único lugar que lança outro programa (o treino)
    "maos/*.py",                 # as ferramentas: tudo o que ele faz fora de si passa por aqui
    "internet/rede.py",          # a única porta para a internet
    "exploracao/explorador.py",  # até onde ele anda no seu PC
    "cerebro/treinar.py",        # o checkpoint lido só como números
    "copias.py",                 # restaurar mexe em todos os dados
    "config.py",                 # as regras de fábrica (nomes proibidos, limites)
    "__main__.py",               # em que endereço o serviço escuta; o próprio comando selar
)


def impressoes() -> dict[str, str]:
    digitais = {}
    for padrao in CRITICOS:
        for arquivo in sorted(PACOTE.glob(padrao)):
            # O Git pode trocar o fim de linha (CRLF/LF) sem mudar o código: ignoramos isso.
            conteudo = arquivo.read_bytes().replace(b"\r\n", b"\n")
            digitais[arquivo.relative_to(PACOTE).as_posix()] = hashlib.sha256(conteudo).hexdigest()
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
