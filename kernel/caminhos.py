"""Pastas conhecidas do Windows (Área de Trabalho, Documentos, Downloads...).

O Windows deixa o usuário mover essas pastas (para o OneDrive, por exemplo),
então o endereço certo está no registro do sistema, não em ``~/Documents``.
"""
from __future__ import annotations

import os
from pathlib import Path

_CHAVE = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"

# nome que usamos -> (valor no registro do Windows, subpasta padrão)
_PASTAS = {
    "area de trabalho": ("Desktop", "Desktop"),
    "documentos": ("Personal", "Documents"),
    "downloads": ("{374DE290-123F-4565-9164-39C4925E467B}", "Downloads"),
    "imagens": ("My Pictures", "Pictures"),
    "musicas": ("My Music", "Music"),
    "videos": ("My Video", "Videos"),
}


def pastas_conhecidas() -> dict[str, Path]:
    casa = Path.home()
    pastas = {nome: casa / padrao for nome, (_, padrao) in _PASTAS.items()}
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CHAVE) as chave:
            for nome, (valor, _) in _PASTAS.items():
                try:
                    bruto, _tipo = winreg.QueryValueEx(chave, valor)
                    pastas[nome] = Path(os.path.expandvars(bruto))
                except OSError:
                    pass
    except (ImportError, OSError):
        pass  # fora do Windows ficam os padrões
    return pastas
