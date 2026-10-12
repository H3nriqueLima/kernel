"""Ferramenta: listar o conteúdo de uma pasta.

Só enxerga dentro das pastas liberadas em ``[seguranca] pastas_permitidas``.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..caminhos import pastas_conhecidas
from ..memoria.texto import normalizar
from ..seguranca import Nivel
from .base import ErroFerramenta, Ferramenta

_APELIDOS = {"desktop": "area de trabalho", "meus documentos": "documentos", "fotos": "imagens",
             "musica": "musicas", "video": "videos", "kernel": "projeto"}
MAXIMO = 40


def _tamanho(n: float) -> str:
    for unidade in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unidade}"
        n /= 1024
    return f"{n:.1f} TB"


class ListarPasta(Ferramenta):
    nome = "listar_pasta"
    descricao = "Mostra o que há dentro de uma pasta liberada."
    nivel = Nivel.LEITURA

    def __init__(self, cfg, seguranca):
        self.cfg = cfg
        self.seguranca = seguranca

    def _resolver(self, pedido: str) -> Path:
        conhecidas = {**pastas_conhecidas(), "projeto": self.cfg.raiz}
        chave = normalizar(pedido).strip()
        chave = _APELIDOS.get(chave, chave)
        if chave in conhecidas:
            return conhecidas[chave]
        return Path(pedido.strip().strip('"')).expanduser()

    def preparar(self, argumentos: dict) -> tuple[dict, str]:
        pedido = str(argumentos.get("pasta", "")).strip()
        if not pedido:
            raise ErroFerramenta("Qual pasta você quer que eu liste?")
        pasta = self._resolver(pedido)
        if not pasta.is_absolute() or not pasta.is_dir():
            raise ErroFerramenta(f'Não achei a pasta "{pedido}".')
        if not self.seguranca.pasta_permitida(pasta):
            raise ErroFerramenta(
                f"A pasta {pasta} está fora das pastas liberadas. Para liberar, edite [seguranca] em kernel.toml."
            )
        return {"pasta": str(pasta.resolve())}, f"Listar o conteúdo de {pasta.resolve()}"

    def executar(self, argumentos: dict) -> str:
        pasta = Path(argumentos["pasta"])
        if not self.seguranca.pasta_permitida(pasta):  # confere de novo na hora de agir
            raise ErroFerramenta("Essa pasta não está mais liberada.")
        itens = sorted(pasta.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        linhas = []
        for item in itens[:MAXIMO]:
            try:
                dados = item.stat()
            except OSError:
                continue
            quando = datetime.fromtimestamp(dados.st_mtime).strftime("%d/%m/%Y")
            if item.is_dir():
                linhas.append(f"[pasta] {item.name}  ({quando})")
            else:
                linhas.append(f"{item.name}  ({_tamanho(dados.st_size)}, {quando})")
        resto = f"\n... e mais {len(itens) - MAXIMO} itens." if len(itens) > MAXIMO else ""
        if not linhas:
            return f"{pasta} está vazia."
        return f"{pasta} tem {len(itens)} itens:\n" + "\n".join(linhas) + resto
