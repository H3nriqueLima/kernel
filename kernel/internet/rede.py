"""O navegador do K.E.R.N.E.L: um leitor de páginas escrito aqui, que só sabe pedir e ler.

Ele não usa o Chrome, o Edge nem o Firefox do seu PC, e é de propósito: nos
seus navegadores estão as suas contas abertas (e-mail, banco, redes sociais).
Um programa que anda sozinho pela internet não deve carregar isso junto.
Este leitor:

- só faz pedidos de leitura (GET). Não envia formulário, não entra em conta e
  não guarda cookie de um pedido para o outro;
- só abre http e https na internet pública. A sua máquina e a sua rede local
  ficam de fora, inclusive quando um site tenta redirecionar para lá;
- só aceita texto (HTML, texto puro, JSON, XML). Programa, imagem, vídeo e PDF
  ele nem começa a baixar;
- lê no máximo ``LIMITE`` bytes de cada página e espera no máximo ``ESPERA`` segundos;
- respeita o robots.txt de cada site e dá um intervalo entre dois pedidos ao
  mesmo site;
- se um site responde que quer prova de que não é um robô, ele desiste e deixa
  o site em paz por meia hora. Não tenta contornar;
- por conta própria, tem um teto de pedidos por hora;
- anota cada pedido no registro (linhas do tipo ``internet``).

Quem decide se um endereço pode ser lido é a segurança (``pode_navegar``).
"""
from __future__ import annotations

import ipaddress
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from urllib.parse import quote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from .. import VERSAO

AGENTE = f"KERNEL/{VERSAO} (assistente pessoal de uma pessoa; so leitura, sem pressa)"
NOME_PARA_ROBOTS = "KERNEL"
LIMITE = 1_500_000      # bytes lidos de cada página
ESPERA = 15.0           # segundos por pedido
SALTOS = 5              # redirecionamentos seguidos, no máximo
DESCANSO = 1800.0       # segundos sem voltar a um site que mandou esperar ou desconfiou de robô
TIPOS_ACEITOS = ("text/html", "application/xhtml+xml", "text/plain", "application/json", "text/xml",
                 "application/xml", "application/rss+xml", "application/atom+xml")
_REDIRECIONA = (301, 302, 303, 307, 308)
_PEDE_CALMA = (202, 403, 429, 503)   # "volte depois" ou "prove que não é um robô"
# A Wikimedia fecha /w/ no robots.txt para rastreadores de página, mas oferece a API justamente
# para programas (com duas condições: identificar-se e ir devagar). Só este endereço conta como API.
_API_WIKIMEDIA = re.compile(r"^[a-z\-]+\.(?:wikipedia|wiktionary|wikibooks|wikinews|wikiquote|wikiversity|wikisource)\.org$")


class ErroDeRede(Exception):
    """Não deu para ler: barrado, fora do ar, não é texto, ou o site pediu para não insistir."""


class Interrompido(ErroDeRede):
    """Você falou, mandou parar ou pediu para desligar no meio de uma pesquisa feita por conta própria."""


def endereco_limpo(url: str) -> str:
    """Letras com acento e espaços num endereço viram a forma que a rede aceita (%C3%A9...)."""
    return quote(url.strip(), safe=":/?#[]@!$&'()*+,;=%~-._")


@dataclass
class Resposta:
    url: str       # o endereço final, depois dos redirecionamentos
    tipo: str      # o tipo de conteúdo que o site declarou
    texto: str


class _SemSeguir(urllib.request.HTTPRedirectHandler):
    """Não segue redirecionamento sozinho: cada destino novo tem de passar pela segurança antes."""

    def redirect_request(self, *args, **kwargs):
        return None


_ABRIDOR = urllib.request.build_opener(_SemSeguir)


def tipo_aceito(tipo: str) -> bool:
    return tipo.split(";")[0].strip().lower() in TIPOS_ACEITOS


def transporte_real(url: str, cabecalhos: dict, limite: int, espera: float) -> tuple[int, dict, bytes]:
    """Um pedido GET, sem seguir redirecionamento. Devolve (status, cabeçalhos em minúsculas, corpo)."""
    pedido = urllib.request.Request(url, headers=cabecalhos, method="GET")
    try:
        with _ABRIDOR.open(pedido, timeout=espera) as resposta:
            recebidos = {chave.lower(): valor for chave, valor in resposta.headers.items()}
            if not tipo_aceito(recebidos.get("content-type", "")):
                return resposta.status, recebidos, b""   # não é texto: fecha sem baixar o corpo
            return resposta.status, recebidos, resposta.read(limite)
    except urllib.error.HTTPError as erro:
        return erro.code, {chave.lower(): valor for chave, valor in erro.headers.items()}, b""


def endereco_publico(anfitriao: str, resolver=socket.getaddrinfo) -> bool:
    """Todos os números para onde este nome aponta são da internet pública?

    O nome pode parecer de fora e apontar para dentro (um site malicioso pode registrar um nome
    que resolve para 127.0.0.1 ou para o seu roteador). Por isso confere-se o número, não o nome.
    """
    try:
        numeros = {achado[4][0] for achado in resolver(anfitriao, None)}
    except (OSError, UnicodeError):
        return False
    try:
        return bool(numeros) and all(ipaddress.ip_address(n.split("%")[0]).is_global for n in numeros)
    except ValueError:
        return False


def decodificar(corpo: bytes, tipo: str) -> str:
    """Bytes -> texto, pela codificação que o site declarou (ou a que estiver escrita na página)."""
    declarada = re.search(r"charset=([\w\-]+)", tipo, re.I)
    if not declarada:
        declarada = re.search(rb"<meta[^>]+charset=[\"']?([\w\-]+)", corpo[:3000], re.I)
    nome = declarada.group(1) if declarada else "utf-8"
    if isinstance(nome, bytes):
        nome = nome.decode("ascii", "replace")
    try:
        return corpo.decode(nome, errors="replace")
    except LookupError:
        return corpo.decode("utf-8", errors="replace")


class Navegador:
    def __init__(self, cfg, seguranca, registro, transporte=None, resolver=None, relogio=time.time, dormir=time.sleep):
        self.cfg = cfg
        self.seguranca = seguranca
        self.registro = registro
        self._transporte = transporte or transporte_real
        self._resolver = resolver or socket.getaddrinfo
        self._relogio = relogio
        self._dormir = dormir
        self.interromper = lambda: False     # o núcleo pendura aqui: você falou, ou pediram para desligar?
        self._trava = threading.Lock()       # um pedido de cada vez
        self._ultimo: dict[str, float] = {}  # site -> quando foi o último pedido
        self._descansando: dict[str, float] = {}   # site -> até quando ele não volta lá
        self._robots: dict[str, tuple[float, RobotFileParser | None]] = {}
        self._sozinho: deque[float] = deque()      # quando foram os pedidos feitos por conta própria

    # ------------------------------------------------------------------- teto
    def restam(self) -> int:
        """Quantos pedidos por conta própria ainda cabem nesta hora."""
        agora = self._relogio()
        while self._sozinho and agora - self._sozinho[0] > 3600:
            self._sozinho.popleft()
        return max(self.cfg.internet.paginas_por_hora - len(self._sozinho), 0)

    def na_ultima_hora(self) -> int:
        self.restam()
        return len(self._sozinho)

    def agora(self) -> float:
        return self._relogio()

    # ------------------------------------------------------------------ abrir
    def abrir(self, url: str, por_conta_propria: bool = True) -> Resposta:
        """Lê um endereço e devolve o texto. Levanta ``ErroDeRede`` se não puder ou não conseguir."""
        url = endereco_limpo(url)
        with self._trava:
            if por_conta_propria:
                if self.restam() <= 0:
                    self._barrar(url, "o teto de pedidos desta hora acabou", por_conta_propria)
                self._sozinho.append(self._relogio())
            vistos: set[str] = set()
            for _ in range(SALTOS + 1):
                if url in vistos:
                    self._barrar(url, "o site redireciona em círculo", por_conta_propria)
                vistos.add(url)
                self._conferir(url, por_conta_propria)
                status, cabecalhos, corpo = self._pedir(url, por_conta_propria)
                if status not in _REDIRECIONA:
                    break
                if not cabecalhos.get("location"):
                    self._barrar(url, "o site redirecionou sem dizer para onde", por_conta_propria)
                url = endereco_limpo(urljoin(url, cabecalhos["location"]))   # o destino passa pela mesma conferência
            else:
                self._barrar(url, "redirecionamentos demais", por_conta_propria)

            site = urlsplit(url).hostname or ""
            tipo = cabecalhos.get("content-type", "")
            if status in _PEDE_CALMA:
                self._descansando[site] = self._relogio() + DESCANSO
                self._barrar(url, f"o site respondeu {status} (pediu calma ou desconfiou de robô)", por_conta_propria)
            if status != 200:
                self._barrar(url, f"o site respondeu {status}", por_conta_propria)
            if not tipo_aceito(tipo):
                self._barrar(url, f"não é texto ({tipo.split(';')[0] or 'tipo não declarado'})", por_conta_propria)
            texto = decodificar(corpo[:LIMITE], tipo)
            self.registro.anotar("internet", url=url, status=status, letras=len(texto), sozinho=por_conta_propria)
            return Resposta(url, tipo, texto)

    def _barrar(self, url: str, motivo: str, por_conta_propria: bool):
        self.registro.anotar("internet", url=url, barrado=motivo, sozinho=por_conta_propria)
        raise ErroDeRede(motivo)

    def _conferir(self, url: str, por_conta_propria: bool) -> None:
        if not self.seguranca.pode_navegar(url, por_conta_propria):
            self._barrar(url, "a segurança não deixa abrir este endereço", por_conta_propria)
        partes = urlsplit(url)
        site = partes.hostname or ""
        if not endereco_publico(site, self._resolver):
            self._barrar(url, "o nome não aponta para a internet pública", por_conta_propria)
        if self._descansando.get(site, 0) > self._relogio():
            self._barrar(url, "o site pediu calma; volto mais tarde", por_conta_propria)
        if _API_WIKIMEDIA.match(site) and partes.path == "/w/api.php":
            return
        regras = self._regras_de(f"{partes.scheme}://{partes.netloc}", por_conta_propria)
        if regras is None or not regras.can_fetch(NOME_PARA_ROBOTS, url):
            self._barrar(url, "o robots.txt do site pede para não ler isto", por_conta_propria)

    def _regras_de(self, raiz: str, por_conta_propria: bool) -> RobotFileParser | None:
        """O robots.txt do site (guardado por um dia). None = não deu para saber, então não lê."""
        guardado = self._robots.get(raiz)
        if guardado and guardado[0] > self._relogio():
            return guardado[1]
        regras: RobotFileParser | None = RobotFileParser()
        validade = 86400.0
        url, status, corpo = raiz + "/robots.txt", 599, b""
        try:
            for _ in range(3):   # muitos sites mandam o robots.txt de http para https, ou para o "www"
                status, cabecalhos, corpo = self._pedir(url, por_conta_propria)
                if status not in _REDIRECIONA or not cabecalhos.get("location"):
                    break
                url = endereco_limpo(urljoin(url, cabecalhos["location"]))
                if not (self.seguranca.pode_navegar(url, por_conta_propria)
                        and endereco_publico(urlsplit(url).hostname or "", self._resolver)):
                    status = 599
                    break
        except Interrompido:
            raise
        except ErroDeRede:
            status = 599
        if status == 200:
            regras.parse(decodificar(corpo[:200_000], "").splitlines())
        elif 400 <= status < 500 and status not in (401, 403, 429):
            regras.parse([])                      # o site não tem robots.txt: nada é proibido
        else:
            regras, validade = None, 600.0        # fora do ar ou fechado: na dúvida, não lê (e tenta de novo depois)
        self._robots[raiz] = (self._relogio() + validade, regras)
        return regras

    def _pedir(self, url: str, por_conta_propria: bool) -> tuple[int, dict, bytes]:
        """Um pedido de verdade, depois de esperar a vez daquele site."""
        site = urlsplit(url).hostname or ""
        espera = self._ultimo.get(site, -1e9) + self.cfg.internet.segundos_entre_pedidos - self._relogio()
        while espera > 0:
            if por_conta_propria and self.interromper():
                raise Interrompido("interrompido")
            self._dormir(min(espera, 0.2))
            espera = self._ultimo.get(site, -1e9) + self.cfg.internet.segundos_entre_pedidos - self._relogio()
        if por_conta_propria and self.interromper():
            raise Interrompido("interrompido")
        self._ultimo[site] = self._relogio()
        cabecalhos = {"User-Agent": AGENTE, "Accept": "text/html,application/json;q=0.9,text/plain;q=0.8",
                      "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5"}
        try:
            return self._transporte(url, cabecalhos, LIMITE, ESPERA)
        except (OSError, ValueError) as erro:   # sem rede, nome que não existe, tempo esgotado, endereço torto
            self.registro.anotar("internet", url=url, barrado=f"sem resposta: {type(erro).__name__}", sozinho=por_conta_propria)
            raise ErroDeRede(f"sem resposta ({type(erro).__name__})") from erro
