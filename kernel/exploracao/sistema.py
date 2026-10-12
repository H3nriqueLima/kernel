"""O que ele sabe sobre a máquina onde mora: processador, memória, discos, placa de vídeo.

Tudo lido direto do Windows com a biblioteca padrão (registro e ctypes).
"""
from __future__ import annotations

import ctypes
import os
import platform
import shutil
import string


def _do_registro(chave: str, valor: str) -> str | None:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, chave) as k:
            return str(winreg.QueryValueEx(k, valor)[0]).strip()
    except (ImportError, OSError):
        return None


def processador() -> str:
    return _do_registro(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString") or platform.processor()


def placas_de_video() -> list[str]:
    classe = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    nomes = [_do_registro(rf"{classe}\{i:04d}", "DriverDesc") for i in range(6)]
    return list(dict.fromkeys(n for n in nomes if n))


def memoria() -> tuple[float, float]:
    """(total, livre) em GB."""
    class Estado(ctypes.Structure):
        _fields_ = [("tamanho", ctypes.c_ulong), ("carga", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                    ("livre", ctypes.c_ulonglong), ("resto", ctypes.c_ulonglong * 5)]

    estado = Estado()
    estado.tamanho = ctypes.sizeof(Estado)
    try:
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado))
    except AttributeError:  # fora do Windows
        return 0.0, 0.0
    return estado.total / 2 ** 30, estado.livre / 2 ** 30


def discos() -> list[tuple[str, float, float]]:
    """[(letra, total em GB, livre em GB)]."""
    saida = []
    for letra in string.ascii_uppercase:
        raiz = f"{letra}:\\"
        if os.path.exists(raiz):
            try:
                uso = shutil.disk_usage(raiz)
                saida.append((letra, uso.total / 2 ** 30, uso.free / 2 ** 30))
            except OSError:
                pass
    return saida


def descrever() -> str:
    total, livre = memoria()
    linhas = [
        f"Eu moro num {platform.system()} {platform.release()} chamado {platform.node()}.",
        f"Processador: {processador()} ({os.cpu_count()} núcleos).",
        f"Memória: {total:.0f} GB, {livre:.1f} GB livres agora.",
    ]
    placas = placas_de_video()
    if placas:
        linhas.append("Vídeo: " + " e ".join(placas) + ".")
    for letra, tamanho, sobra in discos():
        linhas.append(f"Disco {letra}: {sobra:.0f} GB livres de {tamanho:.0f} GB.")
    return "\n".join(linhas)
