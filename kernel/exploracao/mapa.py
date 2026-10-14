"""O mapa: tudo o que ele já viu no PC.

Três tabelas num arquivo SQLite (``dados/mapa.db``):

- ``pastas``: cada pasta descoberta e quando foi visitada pela última vez.
- ``arquivos``: nome, tamanho, data, e se já foi lido.
- ``nomes``: palavras com inicial maiúscula que se repetem nos arquivos (pessoas,
  empresas, produtos). É daqui que saem as perguntas de curiosidade.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from ..memoria.texto import normalizar, termos

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS pastas (
    caminho       TEXT PRIMARY KEY,
    profundidade  INTEGER NOT NULL,
    descoberta_em TEXT NOT NULL,
    visitada_em   TEXT,
    itens         INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS arquivos (
    caminho    TEXT PRIMARY KEY,
    nome       TEXT NOT NULL,
    busca      TEXT NOT NULL,           -- o nome em minúsculas, sem acento nem pontuação
    extensao   TEXT NOT NULL,
    tamanho    INTEGER NOT NULL,
    modificado REAL NOT NULL,
    visto_em   TEXT NOT NULL,
    estado     TEXT NOT NULL DEFAULT 'novo',   -- novo | lido | pulado
    assunto    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS arquivos_estado ON arquivos (estado, extensao);
CREATE TABLE IF NOT EXISTS anotacoes (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nomes (
    termo      TEXT PRIMARY KEY,
    palavra    TEXT NOT NULL,
    proprias   INTEGER NOT NULL DEFAULT 0,   -- vezes em que apareceu com inicial maiúscula
    comuns     INTEGER NOT NULL DEFAULT 0,   -- vezes em que apareceu em minúsculas
    arquivos   INTEGER NOT NULL DEFAULT 0,
    exemplo    TEXT NOT NULL DEFAULT ''
);
"""


class Mapa:
    def __init__(self, arquivo: Path | str, relogio=datetime.now):
        self._relogio = relogio
        self._trava = threading.RLock()
        self._bd = sqlite3.connect(str(arquivo), check_same_thread=False)
        self._bd.executescript(_ESQUEMA)
        self._em_lote = 0
        self._por_gravar = 0

    def fechar(self) -> None:
        self._bd.close()

    # --------------------------------------------------------------- gravação
    @contextmanager
    def _gravando(self):
        """Uma anotação no banco. Fora de um lote, grava em disco na hora; dentro, espera o lote."""
        with self._trava:
            try:
                yield
            except BaseException:
                if not self._em_lote:
                    self._bd.rollback()
                raise
            if not self._em_lote:
                self._bd.commit()
            else:
                self._por_gravar += 1
                if self._por_gravar >= 400:  # de tempos em tempos, para um corte de energia não levar a pasta inteira
                    self._bd.commit()
                    self._por_gravar = 0

    @contextmanager
    def lote(self):
        """Muitas anotações, poucas gravações em disco.

        Gravar arquivo por arquivo custa uma ida ao disco para cada um: uma pasta com 3 000 arquivos
        levava minutos. A trava não fica presa durante o lote: quem consulta o mapa nesse meio-tempo
        (a tela de estado, por exemplo) é atendido entre uma anotação e outra.
        """
        with self._trava:
            self._em_lote += 1
        try:
            yield
        finally:
            with self._trava:
                self._em_lote -= 1
                if not self._em_lote:
                    self._bd.commit()
                    self._por_gravar = 0

    def _agora(self) -> str:
        return self._relogio().isoformat(timespec="seconds")

    # ------------------------------------------------------------------ pastas
    def descobrir_pasta(self, caminho: Path, profundidade: int) -> bool:
        with self._gravando():
            cursor = self._bd.execute(
                "INSERT OR IGNORE INTO pastas (caminho, profundidade, descoberta_em) VALUES (?,?,?)",
                (str(caminho), profundidade, self._agora()))
        return cursor.rowcount == 1

    def proxima_pasta(self) -> tuple[Path, int] | None:
        """A pasta ainda não visitada mais perto da raiz."""
        with self._trava:
            linha = self._bd.execute(
                "SELECT caminho, profundidade FROM pastas WHERE visitada_em IS NULL "
                "ORDER BY profundidade, descoberta_em LIMIT 1").fetchone()
        return (Path(linha[0]), linha[1]) if linha else None

    def pasta_para_revisitar(self, antes_de: str) -> tuple[Path, int] | None:
        """A pasta visitada há mais tempo (para notar arquivos novos)."""
        with self._trava:
            linha = self._bd.execute(
                "SELECT caminho, profundidade FROM pastas WHERE visitada_em < ? "
                "ORDER BY visitada_em LIMIT 1", (antes_de,)).fetchone()
        return (Path(linha[0]), linha[1]) if linha else None

    def registrar_visita(self, caminho: Path, itens: int) -> None:
        with self._gravando():
            self._bd.execute("UPDATE pastas SET visitada_em = ?, itens = ? WHERE caminho = ?",
                             (self._agora(), itens, str(caminho)))

    # ---------------------------------------------------------------- arquivos
    def registrar_arquivo(self, caminho: Path, tamanho: int, modificado: float) -> str:
        """Anota o arquivo. Devolve "novo", "mudou" ou "igual"."""
        with self._gravando():
            antes = self._bd.execute("SELECT modificado, tamanho FROM arquivos WHERE caminho = ?",
                                     (str(caminho),)).fetchone()
            if antes and abs(antes[0] - modificado) < 1 and antes[1] == tamanho:
                return "igual"
            busca = " ".join(normalizar(caminho.stem).replace("_", " ").replace("-", " ").replace(".", " ").split())
            self._bd.execute(
                "INSERT OR REPLACE INTO arquivos (caminho, nome, busca, extensao, tamanho, modificado, visto_em) "
                "VALUES (?,?,?,?,?,?,?)",
                (str(caminho), caminho.name, busca, caminho.suffix.lower(), tamanho, modificado, self._agora()))
        return "mudou" if antes else "novo"

    def proximo_arquivo(self, extensoes: set[str], tamanho_maximo: int) -> Path | None:
        """Um arquivo legível que ele viu e ainda não leu. Os mexidos por último primeiro:
        é mais provável que sejam os que importam para você agora."""
        marcas = ",".join("?" * len(extensoes))
        with self._trava:
            linha = self._bd.execute(
                f"SELECT caminho FROM arquivos WHERE estado = 'novo' AND extensao IN ({marcas}) "
                "AND tamanho <= ? ORDER BY modificado DESC, caminho LIMIT 1", (*extensoes, tamanho_maximo)).fetchone()
        return Path(linha[0]) if linha else None

    # ------------------------------------------------------------------ faxina
    def regras_mudaram(self, versao: int) -> bool:
        """As regras de leitura são outras desde a última vez? (Anota a versão nova.)"""
        with self._gravando():
            antes = self._bd.execute("SELECT valor FROM anotacoes WHERE chave = 'regras_de_leitura'").fetchone()
            self._bd.execute("INSERT OR REPLACE INTO anotacoes (chave, valor) VALUES ('regras_de_leitura', ?)", (str(versao),))
        return antes is None or antes[0] != str(versao)

    def reler_tudo(self) -> int:
        """Marca todos os arquivos como não lidos e esquece os nomes anotados (as regras de leitura mudaram)."""
        with self._gravando():
            quantos = self._bd.execute("UPDATE arquivos SET estado = 'novo', assunto = '' WHERE estado != 'novo'").rowcount
            self._bd.execute("DELETE FROM nomes")
        return quantos

    def esquecer(self, fora) -> tuple[int, list[str]]:
        """Tira do mapa as pastas e os arquivos para os quais ``fora(caminho)`` é verdadeiro.
        Devolve (pastas tiradas, arquivos tirados que já tinham sido lidos)."""
        with self._gravando():
            pastas = [(c,) for (c,) in self._bd.execute("SELECT caminho FROM pastas") if fora(c)]
            arquivos = [(c, estado) for c, estado in self._bd.execute("SELECT caminho, estado FROM arquivos") if fora(c)]
            self._bd.executemany("DELETE FROM pastas WHERE caminho = ?", pastas)
            self._bd.executemany("DELETE FROM arquivos WHERE caminho = ?", [(c,) for c, _ in arquivos])
        return len(pastas), [c for c, estado in arquivos if estado == "lido"]

    def marcar(self, caminho: Path, estado: str, assunto: str = "") -> None:
        with self._gravando():   # ``visto_em`` passa a ser a hora em que ele leu (ou desistiu de ler)
            self._bd.execute("UPDATE arquivos SET estado = ?, assunto = ?, visto_em = ? WHERE caminho = ?",
                             (estado, assunto, self._agora(), str(caminho)))

    def procurar(self, texto: str, k: int = 8) -> list[dict]:
        """Arquivos cujo nome (ou assunto) contém as palavras pedidas; os que acertam mais vêm antes."""
        palavras = [t for t in dict.fromkeys(normalizar(texto).replace(".", " ").split()) if len(t) > 1]
        radicais = termos(texto)
        if not palavras:
            return []
        with self._trava:
            linhas = self._bd.execute(
                "SELECT caminho, nome, busca, extensao, tamanho, modificado, estado, assunto FROM arquivos").fetchall()
        achados = []
        for caminho, nome, busca, extensao, tamanho, modificado, estado, assunto in linhas:
            alvo = f"{busca} {extensao.lstrip('.')}"
            pontos = sum(2 for p in palavras if p in alvo) + sum(1 for r in radicais if r in assunto)
            if pontos:
                achados.append((pontos, modificado, {"caminho": caminho, "nome": nome, "tamanho": tamanho,
                                                     "modificado": modificado, "lido": estado == "lido",
                                                     "assunto": assunto}))
        achados.sort(key=lambda a: (-a[0], -a[1]))
        return [arquivo for _, _, arquivo in achados[:k]]

    # ------------------------------------------------------------------- nomes
    def anotar_nomes(self, contagem: dict[str, tuple[str, int, int]], arquivo: str) -> None:
        """``contagem``: termo -> (palavra como apareceu, vezes com maiúscula, vezes em minúsculas)."""
        with self._gravando():
            for termo, (palavra, proprias, comuns) in contagem.items():
                self._bd.execute(
                    "INSERT INTO nomes (termo, palavra, proprias, comuns, arquivos, exemplo) VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT(termo) DO UPDATE SET proprias = proprias + excluded.proprias, "
                    "comuns = comuns + excluded.comuns, arquivos = arquivos + excluded.arquivos",
                    (termo, palavra, proprias, comuns, 1 if proprias else 0, arquivo))

    def nome_curioso(self, ignorar: set[str], minimo_de_arquivos: int = 3) -> tuple[str, str, int, str] | None:
        """Um nome próprio que aparece em vários arquivos: (termo, palavra, em quantos, exemplo).
        Nomes de duas palavras ou mais ("Padaria Estrela") vêm antes: é mais certo que sejam nomes."""
        with self._trava:
            linhas = self._bd.execute(
                "SELECT termo, palavra, arquivos, exemplo FROM nomes "
                "WHERE arquivos >= ? AND proprias >= 4 * comuns AND LENGTH(palavra) >= 4 "
                "ORDER BY (palavra LIKE '% %') DESC, arquivos DESC LIMIT 50",
                (minimo_de_arquivos,)).fetchall()
        for termo, palavra, arquivos, exemplo in linhas:
            if termo not in ignorar:
                return termo, palavra, arquivos, exemplo
        return None

    # ----------------------------------------------------------------- resumos
    def numeros(self) -> dict:
        with self._trava:
            pastas, visitadas = self._bd.execute(
                "SELECT COUNT(*), COUNT(visitada_em) FROM pastas").fetchone()
            arquivos, lidos = self._bd.execute(
                "SELECT COUNT(*), COALESCE(SUM(estado = 'lido'), 0) FROM arquivos").fetchone()
            tipos = self._bd.execute(
                "SELECT extensao, COUNT(*) FROM arquivos GROUP BY extensao ORDER BY COUNT(*) DESC LIMIT 6").fetchall()
        return {"pastas": pastas, "pastas_visitadas": visitadas, "arquivos": arquivos, "arquivos_lidos": lidos,
                "tipos": [[extensao or "(sem extensão)", n] for extensao, n in tipos]}

    def lidos_desde(self, desde: str, n: int = 4) -> tuple[int, list[str]]:
        """Quantos arquivos ele leu a partir de um instante, e o nome de alguns (os mais recentes)."""
        with self._trava:
            quantos = self._bd.execute(
                "SELECT COUNT(*) FROM arquivos WHERE estado = 'lido' AND visto_em >= ?", (desde,)).fetchone()[0]
            nomes = self._bd.execute(
                "SELECT nome FROM arquivos WHERE estado = 'lido' AND visto_em >= ? ORDER BY visto_em DESC LIMIT ?",
                (desde, n)).fetchall()
        return quantos, [nome for (nome,) in nomes]

    def assuntos(self, n: int = 8) -> list[str]:
        """Os assuntos que mais se repetem nos arquivos lidos."""
        from collections import Counter

        with self._trava:
            linhas = self._bd.execute("SELECT assunto FROM arquivos WHERE estado = 'lido' AND assunto != ''").fetchall()
        contagem = Counter(palavra for (assunto,) in linhas for palavra in assunto.split(", "))
        return [palavra for palavra, _ in contagem.most_common(n)]

    def esquecer_fora_de(self, raizes: list[Path]) -> list[str]:
        """Você tirou uma pasta da lista: ele esquece o que viu lá. Devolve os arquivos esquecidos."""
        def dentro(caminho: str) -> bool:
            return any(Path(caminho).is_relative_to(raiz) for raiz in raizes)

        with self._gravando():
            fora_pastas = [c for (c,) in self._bd.execute("SELECT caminho FROM pastas") if not dentro(c)]
            fora_arquivos = [c for (c,) in self._bd.execute("SELECT caminho FROM arquivos") if not dentro(c)]
            self._bd.executemany("DELETE FROM pastas WHERE caminho = ?", [(c,) for c in fora_pastas])
            self._bd.executemany("DELETE FROM arquivos WHERE caminho = ?", [(c,) for c in fora_arquivos])
        return fora_arquivos
