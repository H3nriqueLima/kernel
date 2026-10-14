"""Cópias de segurança dos dados do K.E.R.N.E.L.

Uma cópia é uma pasta ``dados/copias/AAAA-MM-DD_HHMMSS-motivo/`` com:

- os bancos (memória, mapa e fila da internet), copiados pelo próprio SQLite: a cópia
  sai inteira mesmo com o serviço gravando no meio;
- o estado da mente, os aparelhos pareados, os comandos ensinados e o diário;
- o cérebro do dia a dia (``modelo.npz`` e tokenizador) e o checkpoint do treino;
- a sua configuração (``kernel.toml``), só como lembrança: restaurar nunca a sobrescreve,
  porque quem mexe nela é você;
- ``manifesto.json``: cada arquivo com tamanho e impressão digital (SHA-256), e o
  resultado da conferência de cada banco (``PRAGMA integrity_check``).

Fica de fora o que é grande e dá para refazer: a enciclopédia (``conhecimento.db``,
refeita com "estude a Wikipédia"), o corpus e os ``.bin`` do treino e o banco de voz.
O registro (``dados/registro``) também: ele só cresce e nunca volta no tempo.

As cópias ficam no mesmo disco: protegem de banco estragado, arquivo apagado sem
querer e treino que piorou o cérebro, mas não de perder o HD. Para isso, copie de vez
em quando a pasta ``dados/copias`` para outro disco.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from . import VERSAO

PASTA = "copias"
MANIFESTO = "manifesto.json"
BANCOS = ("kernel.db", "mapa.db", "internet.db")
ARQUIVOS = ("estado.json", "aparelhos.json")
PASTAS = ("comandos", "diario")
CEREBRO = ("modelo.npz", "modelo.npz.sha256", "tokenizador.json", "checkpoint.pt", "checkpoint.pt.sha256")
MANTER = 7
_FORMATO = "%Y-%m-%d_%H%M%S"


class ErroCopia(Exception):
    pass


def _impressao(arquivo: Path) -> str:
    resumo = hashlib.sha256()
    with open(arquivo, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def _conferir_banco(arquivo: Path) -> str:
    bd = sqlite3.connect(str(arquivo))
    try:
        return bd.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        bd.close()


def _copiar_banco(origem: Path, destino: Path) -> None:
    """Cópia feita pelo SQLite: consistente mesmo com outra conexão gravando."""
    de, para = sqlite3.connect(str(origem), timeout=30), sqlite3.connect(str(destino))
    try:
        de.backup(para)
        para.execute("PRAGMA journal_mode = DELETE")   # a cópia vira um arquivo só, sem -wal ao lado
    finally:
        para.close()
        de.close()


def pasta_das_copias(cfg) -> Path:
    return cfg.pasta(PASTA)


def listar(cfg) -> list[dict]:
    """As cópias, da mais nova para a mais antiga (só as completas: as que têm manifesto)."""
    copias = []
    for pasta in pasta_das_copias(cfg).iterdir():
        manifesto = pasta / MANIFESTO
        if pasta.is_dir() and not pasta.name.startswith(".") and manifesto.exists():
            try:
                dados = json.loads(manifesto.read_text(encoding="utf-8"))
            except ValueError:
                dados = {}
            copias.append({"nome": pasta.name, "quando": dados.get("quando", ""), "motivo": dados.get("motivo", "?"),
                           "bytes": sum(a["bytes"] for a in dados.get("arquivos", [])),
                           "arquivos": len(dados.get("arquivos", [])), "cerebro": dados.get("cerebro", "")})
    return sorted(copias, key=lambda c: c["nome"], reverse=True)


def ultima(cfg) -> datetime | None:
    for copia in listar(cfg):
        try:
            return datetime.fromisoformat(copia["quando"])
        except ValueError:
            continue
    return None


def precisa_da_diaria(cfg, agora: datetime) -> bool:
    quando = ultima(cfg)
    return quando is None or agora - quando >= timedelta(hours=24)


def fazer(cfg, motivo: str = "manual", com_cerebro: bool = True, manter: int | None = MANTER,
          poupar: set[str] = frozenset(), relogio=datetime.now) -> Path:
    """Faz uma cópia completa e confere cada banco copiado. Devolve a pasta da cópia."""
    raiz = pasta_das_copias(cfg)
    for sobra in raiz.glob(".*.parcial"):   # cópia que uma queda deixou pela metade
        shutil.rmtree(sobra, ignore_errors=True)
    agora = relogio()
    nome = f"{agora.strftime(_FORMATO)}-{motivo}"
    while (raiz / nome).exists():   # duas cópias no mesmo segundo (os testes fazem isso)
        nome += "+"
    parcial = raiz / f".{nome}.parcial"
    parcial.mkdir()
    dados = Path(cfg.dados)
    manifesto = {"versao": VERSAO, "quando": agora.isoformat(timespec="seconds"), "motivo": motivo,
                 "bancos": {}, "arquivos": []}
    try:
        for banco in BANCOS:
            if (dados / banco).exists():
                _copiar_banco(dados / banco, parcial / banco)
                manifesto["bancos"][banco] = _conferir_banco(parcial / banco)
        for nome_arquivo in ARQUIVOS:
            if (dados / nome_arquivo).exists():
                shutil.copy2(dados / nome_arquivo, parcial / nome_arquivo)
        for nome_pasta in PASTAS:
            if (dados / nome_pasta).is_dir():
                shutil.copytree(dados / nome_pasta, parcial / nome_pasta)
        if com_cerebro:
            (parcial / "cerebro").mkdir()
            for nome_arquivo in CEREBRO:
                if (dados / "cerebro" / nome_arquivo).exists():
                    shutil.copy2(dados / "cerebro" / nome_arquivo, parcial / "cerebro" / nome_arquivo)
            manifesto["cerebro"] = "copiado"
        else:
            manifesto["cerebro"] = "pulado (treino em andamento)"
        configuracao = cfg.arquivo
        if configuracao and Path(configuracao).exists():
            (parcial / "lembranca").mkdir()
            shutil.copy2(configuracao, parcial / "lembranca" / "kernel.toml")
        for arquivo in sorted(p for p in parcial.rglob("*") if p.is_file()):
            manifesto["arquivos"].append({"caminho": arquivo.relative_to(parcial).as_posix(),
                                          "bytes": arquivo.stat().st_size, "sha256": _impressao(arquivo)})
        ruins = {b: r for b, r in manifesto["bancos"].items() if r != "ok"}
        if ruins:
            raise ErroCopia(f"banco com problema já na origem: {ruins}")
        (parcial / MANIFESTO).write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
        final = raiz / nome
        parcial.rename(final)   # só vira cópia de verdade quando está inteira
    except BaseException:
        shutil.rmtree(parcial, ignore_errors=True)
        raise
    if manter:
        podar(cfg, manter, poupar | {final.name})
    return final


def podar(cfg, manter: int = MANTER, poupar: set[str] = frozenset()) -> list[str]:
    """Apaga as cópias mais antigas, deixando as ``manter`` mais novas (e as de ``poupar``)."""
    apagadas = []
    for copia in listar(cfg)[manter:]:
        if copia["nome"] in poupar:
            continue
        shutil.rmtree(pasta_das_copias(cfg) / copia["nome"])
        apagadas.append(copia["nome"])
    return apagadas


def conferir(pasta: Path) -> list[str]:
    """O que está errado nesta cópia (lista vazia = ela está inteira)."""
    pasta = Path(pasta)
    try:
        manifesto = json.loads((pasta / MANIFESTO).read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        return [f"sem manifesto legível ({type(erro).__name__})"]
    problemas = []
    for item in manifesto.get("arquivos", []):
        arquivo = pasta / item["caminho"]
        if not arquivo.exists():
            problemas.append(f"falta {item['caminho']}")
        elif arquivo.stat().st_size != item["bytes"] or _impressao(arquivo) != item["sha256"]:
            problemas.append(f"{item['caminho']} mudou depois da cópia")
    for banco in manifesto.get("bancos", {}):
        if (pasta / banco).exists() and f"{banco} mudou depois da cópia" not in problemas:
            resultado = _conferir_banco(pasta / banco)
            if resultado != "ok":
                problemas.append(f"{banco}: {resultado}")
    return problemas


def restaurar(cfg, nome: str) -> dict:
    """Volta os dados para os da cópia ``nome``. O serviço precisa estar desligado.

    Antes de mexer em qualquer coisa: confere a cópia e faz uma cópia do estado atual
    (motivo "antes-de-restaurar"), para dar para desfazer. Nunca mexe no ``kernel.toml``
    nem no registro. Arquivos que surgiram depois da cópia (um dia novo do diário, por
    exemplo) ficam onde estão.
    """
    pasta = pasta_das_copias(cfg) / nome
    if not (pasta / MANIFESTO).exists():
        raise ErroCopia(f"não existe a cópia {nome!r}")
    problemas = conferir(pasta)
    if problemas:
        raise ErroCopia(f"a cópia {nome} não confere: {'; '.join(problemas)}")
    seguranca = fazer(cfg, motivo="antes-de-restaurar", poupar={nome})
    dados = Path(cfg.dados)
    restaurados = []
    for banco in BANCOS:
        if (pasta / banco).exists():
            for sobra in (dados / f"{banco}-wal", dados / f"{banco}-shm"):
                sobra.unlink(missing_ok=True)   # o -wal do banco atual estragaria o banco restaurado
            temporario = dados / f"{banco}.restaurando"
            shutil.copy2(pasta / banco, temporario)
            temporario.replace(dados / banco)
            restaurados.append(banco)
    for nome_arquivo in ARQUIVOS:
        if (pasta / nome_arquivo).exists():
            shutil.copy2(pasta / nome_arquivo, dados / nome_arquivo)
            restaurados.append(nome_arquivo)
    for nome_pasta in PASTAS:
        if (pasta / nome_pasta).is_dir():
            shutil.copytree(pasta / nome_pasta, dados / nome_pasta, dirs_exist_ok=True)
            restaurados.append(nome_pasta + "/")
    if (pasta / "cerebro").is_dir():
        destino = cfg.pasta("cerebro")
        for arquivo in (pasta / "cerebro").iterdir():
            shutil.copy2(arquivo, destino / arquivo.name)
            restaurados.append(f"cerebro/{arquivo.name}")
    return {"restaurados": restaurados, "seguranca": seguranca.name}


def compactar(cfg) -> dict:
    """VACUUM nos bancos: devolve ao disco o espaço do que foi apagado. Com o serviço desligado."""
    tamanhos = {}
    for banco in BANCOS:
        arquivo = Path(cfg.dados) / banco
        if not arquivo.exists():
            continue
        antes = arquivo.stat().st_size
        bd = sqlite3.connect(str(arquivo))
        try:
            bd.execute("VACUUM")
            bd.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            bd.close()
        tamanhos[banco] = (antes, arquivo.stat().st_size)
    return tamanhos
