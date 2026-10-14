"""Peças comuns aos testes: uma pasta de dados descartável, um relógio de mentira e um núcleo."""
from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from kernel import comandos
from kernel.config import carregar
from kernel.nucleo import Kernel


class Relogio:
    """Um relógio que só anda quando o teste manda."""

    def __init__(self, agora: datetime = datetime(2026, 10, 12, 10, 0, 0)):
        self.agora = agora

    def __call__(self) -> datetime:
        return self.agora

    def avancar(self, **quanto) -> None:
        self.agora += timedelta(**quanto)


@pytest.fixture(scope="session")
def classificador_treinado(tmp_path_factory) -> Path:
    """Treina o classificador uma vez só para a sessão inteira de testes."""
    arquivo = tmp_path_factory.mktemp("comandos") / "modelo.npz"
    comandos.treinar(comandos.carregar_exemplos(comandos.classificador.EXEMPLOS)).salvar(arquivo)
    return arquivo


@pytest.fixture
def cfg(tmp_path, classificador_treinado):
    liberada = tmp_path / "liberada"
    liberada.mkdir()
    (liberada / "relatorio.txt").write_text("oi")
    (liberada / "fotos").mkdir()
    cfg = carregar(arquivo=tmp_path / "sem-arquivo.toml", dados=tmp_path / "dados")
    cfg.seguranca.pastas_permitidas = [str(liberada)]
    cfg.maos.atalhos_menu_iniciar = False  # os testes não dependem do que está instalado no PC
    cfg.ouvidos.ativo = False
    cfg.exploracao.ligada = False  # cada teste liga a exploração quando quer testá-la
    cfg.copias.diaria = False  # a cópia diária tem o próprio teste
    shutil.copy(classificador_treinado, cfg.pasta("comandos") / "modelo.npz")
    return cfg


@pytest.fixture
def relogio():
    return Relogio()


@pytest.fixture
def kernel(cfg, relogio):
    abertos = []
    nucleo = Kernel(cfg, relogio=relogio, lancar=abertos.append)
    nucleo.abertos = abertos  # o que as mãos "abriram" durante o teste
    yield nucleo
    nucleo.fechar()


def falas(nucleo, autor: str = "kernel") -> list[str]:
    return [m["texto"] for m in nucleo.mensagens if m["autor"] == autor]
