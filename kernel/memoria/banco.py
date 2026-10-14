"""A memória longa: um arquivo SQLite que só cresce.

Duas tabelas:

- ``memorias``: o texto de cada lembrança, de que tipo ela é e quando nasceu.
- ``indice``: o índice invertido. Para cada termo, em quais memórias ele
  aparece e quantas vezes. É isso que deixa a busca rápida: em vez de ler
  todas as memórias, olhamos só as que contêm os termos pedidos.

Tipos: ``conversa`` (o que você disse), ``fato`` (algo que ele aprendeu),
``lembrete``, ``diario`` e ``leitura`` (trechos de arquivos que ele leu
explorando; a origem é o caminho do arquivo).
"""
from __future__ import annotations

import sqlite3
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import bm25
from .texto import normalizar, termos

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS memorias (
    id         INTEGER PRIMARY KEY,
    criado_em  TEXT    NOT NULL,
    tipo       TEXT    NOT NULL,
    texto      TEXT    NOT NULL,
    origem     TEXT    NOT NULL DEFAULT '',
    quando     TEXT,                         -- lembrete: para quando é
    feito      INTEGER NOT NULL DEFAULT 0,   -- lembrete: já avisado
    organizada INTEGER NOT NULL DEFAULT 0,   -- já passou pela arrumação
    tamanho    INTEGER NOT NULL DEFAULT 0    -- número de termos (o BM25 usa)
);
CREATE TABLE IF NOT EXISTS indice (
    termo      TEXT    NOT NULL,
    id_memoria INTEGER NOT NULL,
    tf         INTEGER NOT NULL,
    PRIMARY KEY (termo, id_memoria)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS indice_da_memoria ON indice (id_memoria);   -- para apagar uma memória sem ler o índice todo
CREATE INDEX IF NOT EXISTS memorias_tipo ON memorias (tipo, feito);
CREATE INDEX IF NOT EXISTS memorias_origem ON memorias (tipo, origem);
"""

_COLUNAS = "id, criado_em, tipo, texto, origem, quando, feito"


@dataclass
class Lembranca:
    id: int
    criado_em: str
    tipo: str
    texto: str
    origem: str
    quando: str | None
    feito: bool
    pontos: float = 0.0   # nota BM25 na busca
    em_comum: int = 0     # quantos termos pouco comuns da busca aparecem aqui


def _lembranca(linha, pontos: float = 0.0, em_comum: int = 0) -> Lembranca:
    return Lembranca(linha[0], linha[1], linha[2], linha[3], linha[4], linha[5], bool(linha[6]), pontos, em_comum)


class Memoria:
    def __init__(self, arquivo: Path | str, relogio=datetime.now):
        self._relogio = relogio
        self._trava = threading.RLock()
        self._bd = sqlite3.connect(str(arquivo), check_same_thread=False)
        self._bd.executescript(_ESQUEMA)

    def fechar(self) -> None:
        self._bd.close()

    # ---------------------------------------------------------------- guardar
    def guardar(self, texto: str, tipo: str = "fato", origem: str = "usuario",
                quando: str | None = None, arrumada: bool = False) -> int:
        with self._trava, self._bd:
            return self._inserir(texto, tipo, origem, quando, arrumada)

    def guardar_varios(self, textos: list[str], tipo: str, origem: str) -> int:
        """Vários textos numa transação só (o que ele lê de um arquivo). Já entram arrumados."""
        with self._trava, self._bd:
            for texto in textos:
                self._inserir(texto, tipo, origem, None, True)
        return len(textos)

    def _inserir(self, texto: str, tipo: str, origem: str, quando: str | None, arrumada: bool) -> int:
        texto = texto.strip()
        contagem = Counter(termos(texto))
        agora = self._relogio().isoformat(timespec="seconds")
        cursor = self._bd.execute(
            "INSERT INTO memorias (criado_em, tipo, texto, origem, quando, tamanho, organizada) VALUES (?,?,?,?,?,?,?)",
            (agora, tipo, texto, origem, quando, sum(contagem.values()), int(arrumada)),
        )
        self._bd.executemany(
            "INSERT INTO indice (termo, id_memoria, tf) VALUES (?,?,?)",
            [(termo, cursor.lastrowid, tf) for termo, tf in contagem.items()],
        )
        return cursor.lastrowid

    def apagar_origem(self, tipo: str, origem: str) -> int:
        """Apaga tudo o que veio de uma origem (ex.: o que ele leu de um arquivo que mudou)."""
        with self._trava, self._bd:
            ids = [i for (i,) in self._bd.execute(
                "SELECT id FROM memorias WHERE tipo = ? AND origem = ?", (tipo, origem))]
            self._bd.executemany("DELETE FROM indice WHERE id_memoria = ?", [(i,) for i in ids])
            self._bd.executemany("DELETE FROM memorias WHERE id = ?", [(i,) for i in ids])
        return len(ids)

    def apagar_origens(self, tipo: str, origens: list[str]) -> int:
        """Apaga, numa transação só, tudo o que veio de várias origens (uma faxina de arquivos esquecidos)."""
        apagadas = 0
        with self._trava, self._bd:
            for origem in origens:
                ids = [(i,) for (i,) in self._bd.execute(
                    "SELECT id FROM memorias WHERE tipo = ? AND origem = ?", (tipo, origem))]
                self._bd.executemany("DELETE FROM indice WHERE id_memoria = ?", ids)
                self._bd.executemany("DELETE FROM memorias WHERE id = ?", ids)
                apagadas += len(ids)
        return apagadas

    def apagar_tipo(self, tipo: str) -> int:
        """Apaga todas as memórias de um tipo (as leituras, quando as regras de leitura mudam)."""
        with self._trava, self._bd:
            self._bd.execute("DELETE FROM indice WHERE id_memoria IN (SELECT id FROM memorias WHERE tipo = ?)", (tipo,))
            return self._bd.execute("DELETE FROM memorias WHERE tipo = ?", (tipo,)).rowcount

    def podar(self, tipo: str, manter: int) -> int:
        """Apaga as memórias mais antigas de um tipo até sobrarem ``manter`` (o que ele leu na internet tem teto)."""
        with self._trava, self._bd:
            ids = [i for (i,) in self._bd.execute(
                "SELECT id FROM memorias WHERE tipo = ? ORDER BY id DESC LIMIT -1 OFFSET ?", (tipo, max(manter, 0)))]
            self._bd.executemany("DELETE FROM indice WHERE id_memoria = ?", [(i,) for i in ids])
            self._bd.executemany("DELETE FROM memorias WHERE id = ?", [(i,) for i in ids])
        return len(ids)

    def apagar(self, id_memoria: int) -> None:
        with self._trava, self._bd:
            self._bd.execute("DELETE FROM indice WHERE id_memoria = ?", (id_memoria,))
            self._bd.execute("DELETE FROM memorias WHERE id = ?", (id_memoria,))

    # ----------------------------------------------------------------- buscar
    def buscar(self, consulta: str, k: int = 5, tipos: tuple[str, ...] | None = None,
               ignorar: tuple[int, ...] = ()) -> list[Lembranca]:
        """As ``k`` memórias com maior nota BM25 para a consulta."""
        termos_da_busca = list(dict.fromkeys(termos(consulta)))
        if not termos_da_busca:
            return []
        with self._trava:
            total, medio = self._bd.execute("SELECT COUNT(*), AVG(tamanho) FROM memorias").fetchone()
            pontos: dict[int, float] = defaultdict(float)
            em_comum: dict[int, int] = defaultdict(int)
            for termo in termos_da_busca:
                achados = self._bd.execute(
                    "SELECT i.id_memoria, i.tf, m.tamanho FROM indice i "
                    "JOIN memorias m ON m.id = i.id_memoria WHERE i.termo = ?",
                    (termo,),
                ).fetchall()
                peso = bm25.idf(total, len(achados))
                pouco_comum = len(achados) <= max(2, total // 5)  # "hoje" e "dia" não contam como assunto
                for id_memoria, tf, tamanho in achados:
                    pontos[id_memoria] += bm25.pontuacao(tf, tamanho, medio, peso)
                    em_comum[id_memoria] += pouco_comum
            saida = []
            for id_memoria in sorted(pontos, key=lambda i: (-pontos[i], -i)):
                if id_memoria in ignorar:
                    continue
                linha = self._bd.execute(f"SELECT {_COLUNAS} FROM memorias WHERE id = ?", (id_memoria,)).fetchone()
                if tipos and linha[2] not in tipos:
                    continue
                saida.append(_lembranca(linha, pontos[id_memoria], em_comum[id_memoria]))
                if len(saida) == k:
                    break
        return saida

    def frequencia(self, termo: str) -> int:
        """Em quantas memórias o termo aparece."""
        with self._trava:
            return self._bd.execute("SELECT COUNT(*) FROM indice WHERE termo = ?", (termo,)).fetchone()[0]

    # -------------------------------------------------------------- consultas
    def recentes(self, n: int = 10, tipo: str | None = None, desde: str | None = None) -> list[Lembranca]:
        filtros, valores = [], []
        if tipo:
            filtros.append("tipo = ?")
            valores.append(tipo)
        if desde:
            filtros.append("criado_em >= ?")
            valores.append(desde)
        onde = f"WHERE {' AND '.join(filtros)}" if filtros else ""
        with self._trava:
            linhas = self._bd.execute(
                f"SELECT {_COLUNAS} FROM memorias {onde} ORDER BY id DESC LIMIT ?", (*valores, n)
            ).fetchall()
        return [_lembranca(linha) for linha in linhas]

    def lembretes(self, pendentes: bool = True) -> list[Lembranca]:
        filtro = "AND feito = 0" if pendentes else ""
        with self._trava:
            linhas = self._bd.execute(
                f"SELECT {_COLUNAS} FROM memorias WHERE tipo = 'lembrete' {filtro} "
                "ORDER BY quando IS NULL, quando, id"
            ).fetchall()
        return [_lembranca(linha) for linha in linhas]

    def lembretes_vencidos(self, agora: datetime) -> list[Lembranca]:
        limite = agora.isoformat(timespec="seconds")
        return [l for l in self.lembretes() if l.quando and l.quando <= limite]

    def marcar_feito(self, id_memoria: int) -> None:
        with self._trava, self._bd:
            self._bd.execute("UPDATE memorias SET feito = 1 WHERE id = ?", (id_memoria,))

    def contar(self) -> dict[str, int]:
        with self._trava:
            linhas = self._bd.execute("SELECT tipo, COUNT(*) FROM memorias GROUP BY tipo").fetchall()
        contagem = dict(linhas)
        contagem["total"] = sum(contagem.values())
        return contagem

    # -------------------------------------------------------------- arrumação
    def por_organizar(self) -> int:
        with self._trava:
            return self._bd.execute("SELECT COUNT(*) FROM memorias WHERE organizada = 0").fetchone()[0]

    def organizar(self) -> dict[str, int]:
        """Apaga memórias repetidas (mesmo tipo, texto e data) e marca todas como arrumadas."""
        with self._trava:
            linhas = self._bd.execute(
                "SELECT id, tipo, texto, quando FROM memorias WHERE tipo NOT IN ('leitura', 'pesquisa') ORDER BY id").fetchall()
            vistas, repetidas = set(), []
            for id_memoria, tipo, texto, quando in linhas:
                chave = (tipo, " ".join(normalizar(texto).split()), quando)
                if chave in vistas:
                    repetidas.append(id_memoria)
                vistas.add(chave)
            for id_memoria in repetidas:
                self.apagar(id_memoria)
            with self._bd:
                arrumadas = self._bd.execute("UPDATE memorias SET organizada = 1 WHERE organizada = 0").rowcount
        return {"repetidas_apagadas": len(repetidas), "arrumadas": arrumadas}
