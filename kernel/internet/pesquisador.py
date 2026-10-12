"""O pesquisador: como ele aprende um assunto na internet e guarda o que leu.

Um assunto entra na fila (``dados/internet.db``) por um destes caminhos:

- você pediu ("pesquisa sobre buracos negros");
- você perguntou uma coisa que ele não sabia;
- foi assunto de uma pergunta sua de hoje ou de ontem (ele estuda mais a fundo aquilo
  sobre o que você quis saber);
- está na lista ``interesses`` do kernel.toml;
- apareceu ao lado de um assunto que ele acabou de pesquisar (um "relacionado",
  até dois passos de distância do que você pediu);
- só se você ligar ``assuntos_dos_arquivos``: os assuntos que mais se repetem nos
  arquivos que ele leu. Fica desligado de fábrica porque a palavra pesquisada sai
  do PC, e o que está nos seus arquivos pode ser de outras pessoas.

Pesquisar um assunto é:

1. procurar na Wikipédia e ler o artigo que trata dele (ou o verbete do
   Wikcionário, se for uma palavra só);
2. se o buscador estiver ligado, achar páginas da web sobre o assunto e ler
   algumas (as que o navegador dele conseguir e puder ler);
3. guardar o texto em pedaços na memória, tipo ``pesquisa``, cada pedaço com o
   endereço de onde veio. É por isso que toda resposta tirada daqui cita a fonte.

O que vem da internet é guardado como texto para consulta. Nunca é tratado como
ordem: nenhuma frase lida numa página vira comando para as mãos dele.
"""
from __future__ import annotations

import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit

from ..exploracao.leitores import pedacos
from ..memoria.texto import normalizar, termos
from . import fontes
from .pagina import ler_html
from .rede import ErroDeRede, Interrompido, Navegador

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS assuntos (
    termo        TEXT PRIMARY KEY,               -- sem acento e em minúsculas: não pesquisa a mesma coisa duas vezes
    mostrar      TEXT NOT NULL,                  -- como foi pedido
    origem       TEXT NOT NULL,                  -- pedido | pergunta | interesse | conversa | arquivos | relacionado
    profundidade INTEGER NOT NULL DEFAULT 0,     -- a quantos passos está do que você pediu
    criado_em    TEXT NOT NULL,
    estado       TEXT NOT NULL DEFAULT 'novo',   -- novo | feito | vazio (pesquisou e não achou nada)
    feito_em     TEXT,
    tentativas   INTEGER NOT NULL DEFAULT 0,
    paginas      INTEGER NOT NULL DEFAULT 0,
    trechos      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS paginas (
    url     TEXT PRIMARY KEY,
    titulo  TEXT NOT NULL,
    fonte   TEXT NOT NULL,
    assunto TEXT NOT NULL,
    lida_em TEXT NOT NULL,
    letras  INTEGER NOT NULL
);
"""
_ORDEM = ("CASE origem WHEN 'pedido' THEN 0 WHEN 'pergunta' THEN 0 WHEN 'interesse' THEN 1 WHEN 'conversa' THEN 1 "
          "WHEN 'arquivos' THEN 2 ELSE 3 END")
PROFUNDIDADE_MAXIMA = 2     # relacionados de relacionados, e para aí
FILA_CHEIA = 30             # com isso na fila, os relacionados deixam de entrar
ENTRE_BUSCAS = 20.0         # segundos entre duas consultas ao buscador, por conta própria
# Sites em que a página é vídeo, imagem ou exige conta: não há texto para ler.
_SEM_TEXTO = ("youtube.com", "youtu.be", "facebook.com", "instagram.com", "tiktok.com", "twitter.com", "x.com",
              "linkedin.com", "pinterest.com", "play.google.com", "apps.apple.com", "wikipedia.org")
_NAO_E_PAGINA = re.compile(r"\.(?:pdf|docx?|xlsx?|pptx?|zip|rar|7z|exe|msi|apk|jpe?g|png|gif|webp|mp[34]|avi|mkv)$", re.I)
_FRASE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÀ\"0-9])")
_CONTROLE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


@dataclass
class Fonte:
    titulo: str
    url: str
    fonte: str      # Wikipédia | Wikcionário | web
    letras: int

    @property
    def site(self) -> str:
        return (urlsplit(self.url).hostname or "").removeprefix("www.")


@dataclass
class Resultado:
    termo: str
    fontes: list[Fonte] = field(default_factory=list)
    trechos: int = 0
    resposta: str = ""                  # duas ou três frases da melhor fonte
    relacionados: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)   # o que não deu certo, em palavras
    respondeu: bool = False             # alguma fonte chegou a responder (mesmo que sem nada sobre o assunto)


def fala_de(termo: str, texto: str) -> bool:
    """O texto trata do assunto? Vale se pelo menos metade das palavras do assunto aparece nele."""
    pedidas = set(termos(termo))
    if not pedidas:
        return False
    return len(pedidas & set(termos(texto))) >= max(1, (len(pedidas) + 1) // 2)


def resumo(texto: str, termo: str, frases: int = 2, limite: int = 420) -> str:
    """As primeiras frases do texto a partir da primeira que cita o assunto."""
    todas = [f.strip() for f in _FRASE.split(texto.replace("\n", " ")) if len(f.strip()) > 20]
    if not todas:
        return texto.strip()[:limite]
    pedidas = set(termos(termo))
    comeco = next((i for i, f in enumerate(todas[:12]) if pedidas & set(termos(f))), 0)
    saida = " ".join(todas[comeco:comeco + frases])
    return saida if len(saida) <= limite else saida[:limite].rsplit(" ", 1)[0] + "…"


def melhor_artigo(termo: str, achados: list) -> object | None:
    """O artigo que trata DO assunto, e não um que só o cita.

    A busca da Wikipédia devolve qualquer artigo em que a palavra aparece. Vale o artigo em que pelo
    menos metade das palavras do título são do assunto pedido ("Buraco negro" para "buracos negros";
    não "Receita Garantida (Inadimplência Escolar Zero)" para "inadimplência").
    """
    pedidas = set(termos(termo))
    melhor, nota_do_melhor = None, 0.0
    for achado in achados:
        do_titulo = set(termos(re.sub(r"\(.*?\)", " ", achado.titulo))) or set(termos(achado.titulo))
        em_comum = len(pedidas & do_titulo)
        nota = em_comum / len(do_titulo) if do_titulo else 0.0
        # E o inverso: o artigo "Guarulhos" não responde "temperatura atual no centro de Guarulhos".
        # O título (ou o começo do artigo) tem de dar conta de pelo menos metade do que foi pedido.
        cobre = em_comum * 2 >= len(pedidas) or fala_de(termo, achado.titulo + " " + achado.texto[:600])
        if cobre and nota > nota_do_melhor:   # no empate fica o que a busca pôs primeiro
            melhor, nota_do_melhor = achado, nota
    return melhor if nota_do_melhor >= 0.5 else None


def _chave(termo: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", normalizar(termo)).split())


class Pesquisador:
    def __init__(self, cfg, seguranca, memoria, registro, relogio=datetime.now, transporte=None, resolver=None,
                 assuntos_dos_arquivos=None, assuntos_das_conversas=None):
        self.cfg = cfg
        self.seguranca = seguranca
        self.memoria = memoria
        self.registro = registro
        self._relogio = relogio
        self.navegador = Navegador(cfg, seguranca, registro, transporte=transporte, resolver=resolver)
        self._assuntos_dos_arquivos = assuntos_dos_arquivos or (lambda: [])
        self._assuntos_das_conversas = assuntos_das_conversas or (lambda: [])
        self._trava = threading.RLock()
        self._bd = sqlite3.connect(str(cfg.dados / "internet.db"), check_same_thread=False)
        self._bd.executescript(_ESQUEMA)
        self._ultima_busca = -1e9
        self._buscador_volta_em = 0.0

    def fechar(self) -> None:
        self._bd.close()

    def _agora(self) -> str:
        return self._relogio().isoformat(timespec="seconds")

    # ------------------------------------------------------------------- fila
    def pedir(self, termo: str, origem: str, profundidade: int = 0) -> bool:
        """Põe um assunto na fila. Devolve False se já estava lá (ou se não serve para pesquisa)."""
        mostrar = " ".join(termo.split())
        chave = _chave(mostrar)
        # um caminho de arquivo, um endereço ou um número solto não são assunto
        if not (3 <= len(chave) <= 80) or chave.isdigit() or re.search(r"[\\/@]|://", mostrar):
            return False
        with self._trava, self._bd:
            cursor = self._bd.execute(
                "INSERT OR IGNORE INTO assuntos (termo, mostrar, origem, profundidade, criado_em) VALUES (?,?,?,?,?)",
                (chave, mostrar, origem, profundidade, self._agora()))
        return cursor.rowcount == 1

    def _proximo(self) -> tuple[str, str, str, int] | None:
        with self._trava:
            return self._bd.execute(
                f"SELECT termo, mostrar, origem, profundidade FROM assuntos WHERE estado = 'novo' "
                f"ORDER BY {_ORDEM}, criado_em, rowid LIMIT 1").fetchone()

    def proximo_assunto(self) -> str | None:
        """O que ele pesquisaria agora (a interface mostra enquanto ele pesquisa)."""
        proximo = self._proximo()
        return proximo[1] if proximo else None

    def na_fila(self) -> int:
        with self._trava:
            return self._bd.execute("SELECT COUNT(*) FROM assuntos WHERE estado = 'novo'").fetchone()[0]

    def _semear(self) -> None:
        """Fila vazia: entram os seus interesses, os assuntos das suas perguntas recentes e, se você
        liberou, os assuntos dos seus arquivos. Quem já foi pesquisado não entra de novo."""
        for interesse in self.cfg.internet.interesses:
            self.pedir(str(interesse), "interesse")
        for assunto in self._assuntos_das_conversas():
            self.pedir(assunto, "conversa")
        if self.cfg.internet.assuntos_dos_arquivos:
            for assunto in self._assuntos_dos_arquivos():
                self.pedir(assunto, "arquivos")

    def _anotar_assunto(self, termo: str, origem: str, profundidade: int, resultado: Resultado) -> None:
        chave = _chave(termo)
        if not chave:
            return
        with self._trava, self._bd:
            self._bd.execute(
                "INSERT OR IGNORE INTO assuntos (termo, mostrar, origem, profundidade, criado_em) VALUES (?,?,?,?,?)",
                (chave, termo, origem, profundidade, self._agora()))
            if resultado.fontes:
                self._bd.execute("UPDATE assuntos SET estado = 'feito', feito_em = ?, paginas = ?, trechos = ? WHERE termo = ?",
                                 (self._agora(), len(resultado.fontes), resultado.trechos, chave))
            else:
                # Sem resposta de ninguém (sem rede, barrado): tenta de novo outra hora, até três vezes.
                desiste = resultado.respondeu
                self._bd.execute(
                    "UPDATE assuntos SET tentativas = tentativas + 1, feito_em = ?, "
                    "estado = CASE WHEN ? OR tentativas >= 2 THEN 'vazio' ELSE estado END WHERE termo = ? AND estado != 'feito'",
                    (self._agora(), int(desiste), chave))

    # --------------------------------------------------------------- pesquisar
    def pode_sozinho(self) -> bool:
        """Ele pode sair pesquisando agora, por conta própria?"""
        return (self.seguranca.pode_navegar(f"https://{fontes.WIKIPEDIA}/", True)
                and self.navegador.restam() >= 3)

    def passo(self) -> dict | None:
        """Um passo por conta própria: pesquisa o próximo assunto da fila. None se não há o que fazer (ou não pode)."""
        if not self.pode_sozinho():
            return None
        proximo = self._proximo()
        if proximo is None:
            self._semear()
            proximo = self._proximo()
            if proximo is None:
                return None
        _, mostrar, origem, profundidade = proximo
        try:
            resultado = self.pesquisar(mostrar, True, origem, profundidade)
        except Interrompido:
            return {"acao": "interrompido", "termo": mostrar}
        return {"acao": "pesquisar", "termo": mostrar, "origem": origem, "paginas": len(resultado.fontes),
                "trechos": resultado.trechos, "sites": [f.site for f in resultado.fontes]}

    def pesquisar(self, termo: str, por_conta_propria: bool = True, origem: str = "pedido",
                  profundidade: int = 0) -> Resultado:
        """Pesquisa um assunto agora e guarda o que leu. ``Interrompido`` sobe se mandarem parar no meio."""
        termo = " ".join(termo.split())[:120]
        resultado = Resultado(termo)
        tem_wikipedia = False
        try:
            achados = fontes.wikipedia(self.navegador, termo, por_conta_propria)
            resultado.respondeu = True
            escolhido = melhor_artigo(termo, achados)
            if escolhido:
                inteiro = fontes.artigo(self.navegador, escolhido.titulo, por_conta_propria) or escolhido
                self._guardar(resultado, inteiro, termo)
                tem_wikipedia = True
                resultado.relacionados = [a.titulo for a in achados
                                          if a is not escolhido and fala_de(termo, a.texto[:600])][:3]
            elif len(termo.split()) == 1:
                verbete = fontes.wikcionario(self.navegador, termo, por_conta_propria)
                if verbete:
                    self._guardar(resultado, verbete, termo)
        except Interrompido:
            raise
        except ErroDeRede as erro:
            resultado.avisos.append(f"Wikipédia: {erro}")

        if self.cfg.internet.buscador and self.cfg.internet.paginas_por_assunto > 0:
            self._pela_web(resultado, termo, por_conta_propria)

        self._anotar_assunto(termo, origem, profundidade, resultado)
        if resultado.fontes:
            self.memoria.podar("pesquisa", self.cfg.internet.trechos_maximos)
            if tem_wikipedia and profundidade < PROFUNDIDADE_MAXIMA and self.na_fila() < FILA_CHEIA:
                for relacionado in resultado.relacionados:
                    self.pedir(relacionado, "relacionado", profundidade + 1)
        self.registro.anotar("pesquisar", termo=termo, origem=origem, sozinho=por_conta_propria,
                             fontes=[f.url for f in resultado.fontes], trechos=resultado.trechos,
                             avisos=resultado.avisos[:6])
        return resultado

    def _pela_web(self, resultado: Resultado, termo: str, por_conta_propria: bool) -> None:
        agora = self.navegador.agora()
        if agora < self._buscador_volta_em:
            resultado.avisos.append("buscador: descansando depois de uma recusa")
            return
        if por_conta_propria and agora - self._ultima_busca < ENTRE_BUSCAS:
            return
        self._ultima_busca = agora
        try:
            achados = fontes.buscar_na_web(self.navegador, termo, por_conta_propria)
            resultado.respondeu = True
        except Interrompido:
            raise
        except fontes.BuscadorIndisponivel as erro:
            self._buscador_volta_em = agora + 3600    # uma hora sem insistir
            resultado.avisos.append(f"buscador: {erro}")
            return
        lidas = 0
        for achado in achados:
            if lidas >= self.cfg.internet.paginas_por_assunto:
                break
            partes = urlsplit(achado.url)
            site = (partes.hostname or "").lower()
            if any(site == s or site.endswith("." + s) for s in _SEM_TEXTO) or _NAO_E_PAGINA.search(partes.path):
                continue
            try:
                resposta = self.navegador.abrir(achado.url, por_conta_propria)
            except Interrompido:
                raise
            except ErroDeRede as erro:
                resultado.avisos.append(f"{site}: {erro}")
                continue
            pagina = ler_html(resposta.texto, resposta.url)
            if len(pagina.texto) < 300 or not fala_de(termo, pagina.texto[:4000]):
                resultado.avisos.append(f"{site}: sem texto sobre o assunto")
                continue
            self._guardar(resultado, fontes.Achado(pagina.titulo or achado.titulo, resposta.url, pagina.texto, "web"), termo)
            lidas += 1

    def ler_pagina(self, url: str, por_conta_propria: bool = False) -> Resultado:
        """Lê um endereço que você indicou e guarda o texto."""
        resultado = Resultado(url)
        try:
            resposta = self.navegador.abrir(url, por_conta_propria)
            resultado.respondeu = True
        except ErroDeRede as erro:
            resultado.avisos.append(str(erro))
            return resultado
        if "html" in resposta.tipo.lower() or "<html" in resposta.texto[:2000].lower():
            pagina = ler_html(resposta.texto, resposta.url)
            titulo, texto = pagina.titulo, pagina.texto
        else:
            titulo, texto = "", resposta.texto
        if len(texto.strip()) < 80:
            resultado.avisos.append("não achei texto para ler nessa página (pode ser uma página feita só de código)")
            return resultado
        titulo = titulo or (urlsplit(resposta.url).hostname or "página")
        self._guardar(resultado, fontes.Achado(titulo, resposta.url, texto, "web"), titulo)
        self.memoria.podar("pesquisa", self.cfg.internet.trechos_maximos)
        self.registro.anotar("pesquisar", termo=url, origem="pagina", sozinho=por_conta_propria,
                             fontes=[resposta.url], trechos=resultado.trechos, avisos=[])
        return resultado

    def _guardar(self, resultado: Resultado, achado: fontes.Achado, assunto: str) -> None:
        """Corta o texto em pedaços e guarda na memória, cada pedaço com o endereço de onde veio."""
        texto = _CONTROLE.sub(" ", achado.texto)[: self.cfg.internet.caracteres_por_pagina]
        titulo = " ".join(achado.titulo.split())[:120]
        trechos = [f"{titulo}: {pedaco}" for pedaco in pedacos(texto)]
        if not trechos:
            return
        self.memoria.apagar_origem("pesquisa", achado.url)   # releu a página: sai a leitura antiga
        self.memoria.guardar_varios(trechos, tipo="pesquisa", origem=achado.url)
        with self._trava, self._bd:
            self._bd.execute("INSERT OR REPLACE INTO paginas (url, titulo, fonte, assunto, lida_em, letras) VALUES (?,?,?,?,?,?)",
                             (achado.url, titulo, achado.fonte, assunto, self._agora(), len(texto)))
        resultado.fontes.append(Fonte(titulo, achado.url, achado.fonte, len(texto)))
        resultado.trechos += len(trechos)
        if not resultado.resposta:
            resultado.resposta = resumo(texto, assunto)

    # ---------------------------------------------------------------- relatos
    def numeros(self) -> dict:
        with self._trava:
            feitos = self._bd.execute("SELECT COUNT(*) FROM assuntos WHERE estado = 'feito'").fetchone()[0]
            paginas = self._bd.execute("SELECT COUNT(*) FROM paginas").fetchone()[0]
        return {"pesquisados": feitos, "paginas": paginas, "na_fila": self.na_fila(),
                "na_ultima_hora": self.navegador.na_ultima_hora(), "teto": self.cfg.internet.paginas_por_hora}

    def feitos_desde(self, desde: str | None, n: int = 6) -> list[str]:
        """Os assuntos pesquisados com proveito a partir de um instante (os mais recentes primeiro)."""
        with self._trava:
            linhas = self._bd.execute(
                "SELECT mostrar FROM assuntos WHERE estado = 'feito' AND feito_em >= ? ORDER BY feito_em DESC, rowid DESC LIMIT ?",
                (desde or "", n)).fetchall()
        return [mostrar for (mostrar,) in linhas]

    def relato(self) -> str:
        """O que ele já pesquisou, em uma fala."""
        n = self.numeros()
        if not n["pesquisados"]:
            return "Ainda não pesquisei nada na internet."
        partes = [f"Já pesquisei {n['pesquisados']} {'assunto' if n['pesquisados'] == 1 else 'assuntos'} na internet "
                  f"e li {n['paginas']} {'página' if n['paginas'] == 1 else 'páginas'}. "
                  f"Os últimos: {', '.join(self.feitos_desde(None))}."]
        if n["na_fila"]:
            partes.append(f"Tenho mais {n['na_fila']} na fila para pesquisar.")
        return " ".join(partes)
