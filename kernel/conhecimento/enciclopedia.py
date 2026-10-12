"""A enciclopédia: título e começo de cada artigo, com busca BM25.

``construir`` lê o ``corpus.txt`` que o pipeline da Wikipédia produziu e guarda,
de cada artigo, o título e os primeiros parágrafos. A busca tenta primeiro o
título exato ("o que é astronomia?" -> artigo "Astronomia"); se não achar, usa
o mesmo BM25 da memória, com as palavras do título valendo o triplo.
"""
from __future__ import annotations

import re
import sqlite3
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from ..cerebro.tokenizador import FIM
from ..memoria import bm25
from ..memoria.texto import normalizar, termos

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS artigos (
    id      INTEGER PRIMARY KEY,
    titulo  TEXT NOT NULL,
    chave   TEXT NOT NULL,      -- título em minúsculas, sem acento e sem o que vem entre parênteses
    texto   TEXT NOT NULL,
    tamanho INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS artigos_chave ON artigos (chave);
CREATE TABLE IF NOT EXISTS indice (
    termo     TEXT NOT NULL,
    id_artigo INTEGER NOT NULL,
    tf        INTEGER NOT NULL,
    PRIMARY KEY (termo, id_artigo)
) WITHOUT ROWID;
"""
CARACTERES = 1500       # quanto de cada artigo fica guardado
PESO_DO_TITULO = 3

_ANDAIME = re.compile(
    r"^(?:kernel[, ]+)?(?:voce sabe |sabe |me diz |me diga |me fala |me fale |me conta |me explica |explica |fala |"
    r"conta )?(?:o que (?:e|sao|foi|era|significa)|quem (?:e|foi|era|sao|foram|descobriu|inventou|criou)|"
    r"onde (?:fica|e|esta|ficam)|quando (?:foi|e|aconteceu|comecou)|qual (?:e|foi|era)|quais (?:sao|foram)|"
    r"como funciona|sobre|defina|definicao de|significado de)?\s*(?:sobre |de |do |da )?(?:o |a |os |as |um |uma )?")
_FRASE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÀ\"])")


def assunto_da_pergunta(pergunta: str) -> str:
    """ "o que é a astronomia?" -> "astronomia" """
    plano = " ".join(re.sub(r"[^\w\s]", " ", normalizar(pergunta)).split())
    return _ANDAIME.sub("", plano, count=1).strip()


def _chave(titulo: str) -> str:
    sem_parenteses = re.sub(r"\s*\(.*?\)", "", titulo)
    return " ".join(re.sub(r"[^\w\s]", " ", normalizar(sem_parenteses)).split())


@dataclass
class Artigo:
    titulo: str
    texto: str
    pontos: float = 0.0


class Enciclopedia:
    def __init__(self, arquivo: Path | str):
        self._trava = threading.RLock()
        self._bd = sqlite3.connect(str(arquivo), check_same_thread=False)
        self._bd.executescript(_ESQUEMA)
        self._quantos = 0

    def fechar(self) -> None:
        self._bd.close()

    def __len__(self) -> int:
        """Quantos artigos há.

        Enquanto um estudo regrava o banco (por outra conexão), a contagem fica trancada. Em vez de
        esperar segundos e falhar, espera um instante e devolve a última contagem conhecida: quem
        pergunta é a tela de estado, a cada segundo e meio.
        """
        with self._trava:
            self._bd.execute("PRAGMA busy_timeout = 50")
            try:
                self._quantos = self._bd.execute("SELECT COUNT(*) FROM artigos").fetchone()[0]
            except sqlite3.OperationalError:
                pass
            finally:
                self._bd.execute("PRAGMA busy_timeout = 5000")
            return self._quantos

    # --------------------------------------------------------------- construir
    def construir(self, corpus: Path, ao_progredir=None) -> int:
        """Recria a enciclopédia a partir do corpus (um artigo por bloco, título na primeira linha)."""
        with self._trava, self._bd:
            self._bd.execute("DELETE FROM indice")
            self._bd.execute("DELETE FROM artigos")
            quantos = 0
            for titulo, texto in _artigos_do_corpus(corpus):
                contagem = Counter(termos(texto))
                for termo in termos(titulo):
                    contagem[termo] += PESO_DO_TITULO
                cursor = self._bd.execute(
                    "INSERT INTO artigos (titulo, chave, texto, tamanho) VALUES (?,?,?,?)",
                    (titulo, _chave(titulo), texto, sum(contagem.values())))
                self._bd.executemany("INSERT INTO indice (termo, id_artigo, tf) VALUES (?,?,?)",
                                     [(termo, cursor.lastrowid, tf) for termo, tf in contagem.items()])
                quantos += 1
                if ao_progredir and quantos % 2000 == 0:
                    ao_progredir(quantos)
        return quantos

    # ----------------------------------------------------------------- procurar
    def procurar(self, pergunta: str, k: int = 3) -> list[Artigo]:
        assunto = assunto_da_pergunta(pergunta)
        if not assunto:
            return []
        with self._trava:
            exatos = self._bd.execute(
                "SELECT titulo, texto FROM artigos WHERE chave = ? ORDER BY tamanho DESC LIMIT ?",
                (assunto, k)).fetchall()
            if exatos:
                return [Artigo(titulo, texto, 100.0) for titulo, texto in exatos]
            total, medio = self._bd.execute("SELECT COUNT(*), AVG(tamanho) FROM artigos").fetchone()
            if not total:
                return []
            pontos: dict[int, float] = defaultdict(float)
            acertos: dict[int, int] = defaultdict(int)
            da_busca = list(dict.fromkeys(termos(assunto)))
            for termo in da_busca:
                achados = self._bd.execute(
                    "SELECT i.id_artigo, i.tf, a.tamanho FROM indice i JOIN artigos a ON a.id = i.id_artigo "
                    "WHERE i.termo = ?", (termo,)).fetchall()
                peso = bm25.idf(total, len(achados))
                for id_artigo, tf, tamanho in achados:
                    pontos[id_artigo] += bm25.pontuacao(tf, tamanho, medio, peso)
                    acertos[id_artigo] += 1
            # só vale artigo que fala de todos os termos pedidos (ou de quase todos, se forem muitos)
            minimo = len(da_busca) if len(da_busca) <= 2 else len(da_busca) - 1
            melhores = sorted((i for i in pontos if acertos[i] >= minimo), key=lambda i: -pontos[i])[:k]
            saida = []
            for id_artigo in melhores:
                titulo, texto = self._bd.execute("SELECT titulo, texto FROM artigos WHERE id = ?",
                                                 (id_artigo,)).fetchone()
                saida.append(Artigo(titulo, texto, pontos[id_artigo]))
        return saida

    def responder(self, pergunta: str, frases: int = 2) -> tuple[str, str] | None:
        """(título do artigo, resposta curta) ou None se ele não tiver estudado isso."""
        achados = self.procurar(pergunta, k=1)
        if not achados:
            return None
        artigo = achados[0]
        todas = [f.strip() for f in _FRASE.split(artigo.texto.replace("\n", " ")) if f.strip()]
        escolhidas = todas[:frases]
        # Se a pergunta tem uma palavra que não está no título ("capital" em "capital da França"),
        # a frase do artigo que fala dela vale mais do que a segunda frase.
        extras = set(termos(assunto_da_pergunta(pergunta))) - set(termos(artigo.titulo))
        for frase in todas[frases:]:
            if extras & set(termos(frase)):
                escolhidas = [todas[0], frase]
                break
        return artigo.titulo, " ".join(escolhidas)


def _artigos_do_corpus(corpus: Path):
    """Lê o corpus bloco a bloco: título, linha em branco, parágrafos, linha <|fim|>."""
    linhas: list[str] = []
    with open(corpus, encoding="utf-8") as f:
        for linha in f:
            if linha.strip() == FIM:
                if len(linhas) >= 2:
                    corpo = "\n".join(l for l in linhas[1:] if l)
                    yield linhas[0], corpo[:CARACTERES]
                linhas = []
            else:
                linhas.append(linha.strip())
