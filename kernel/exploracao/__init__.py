"""Exploração: o K.E.R.N.E.L olhando o PC por conta própria para aprender.

Ele só olha (nunca escreve, apaga ou abre programas), só dentro das pastas
liberadas, e cada passo pergunta antes à segurança e fica no registro.

- ``mapa.py``       — o que ele já viu: pastas, arquivos e nomes que se repetem.
- ``leitores.py``   — como tirar texto de cada tipo de arquivo.
- ``explorador.py`` — um passo de cada vez: visitar uma pasta ou ler um arquivo.
- ``sistema.py``    — o que ele sabe sobre a máquina (processador, memória, discos).
"""
from .explorador import Explorador
from .mapa import Mapa

__all__ = ["Explorador", "Mapa"]
