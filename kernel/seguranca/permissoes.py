"""Permissões por nível e pedidos de confirmação.

Cada ferramenta declara um nível:

- ``LEITURA`` (0): só olha (listar uma pasta).
- ``MEMORIA`` (1): escreve na própria memória (anotar um lembrete).
- ``SISTEMA`` (2): mexe no seu PC (abrir um programa).

Uma ação nunca é executada direto: ela vira um ``Pedido``. Se o pedido precisa
de confirmação, ele espera você responder na janela de chat; sem resposta, expira.

Duas regras ficam no código e a configuração não consegue afrouxar:
ações de nível SISTEMA sempre pedem confirmação, e qualquer ação das mãos que
nasça da iniciativa do próprio K.E.R.N.E.L (e não de um pedido seu) também.

A única coisa que ele faz sozinho, sem perguntar, é OLHAR: explorar as pastas
liberadas e ler arquivos, sempre só leitura (``pode_explorar``). Isso vale
enquanto a exploração estiver ligada na configuração, você não tiver mandado
parar e o caminho não bater num dos nomes proibidos.

Na internet vale a mesma ideia (``pode_navegar``): ele só LÊ. Só endereços http
e https da internet pública, nunca a sua máquina nem a sua rede local, nunca um
site da lista ``sites_proibidos``. Por conta própria, só com ``pesquisar_sozinho``
ligado e sem você ter mandado parar.
"""
from __future__ import annotations

import ipaddress
import os
import secrets
import time
from dataclasses import asdict, dataclass
from enum import IntEnum
from pathlib import Path
from urllib.parse import urlsplit

# Nomes que nunca são da internet pública: a própria máquina e as redes de casa ou de empresa.
_SUFIXOS_LOCAIS = (".localhost", ".local", ".lan", ".home", ".internal", ".intranet", ".corp", ".home.arpa")


# Pastas que os programas criam ao instalar ou montar coisas. Nunca têm documento seu.
_DE_MONTAGEM = frozenset({"obj", "bin", "node_modules", "site-packages", "dist-packages", "__pycache__",
                          "bower_components", "vendor", "packages"})
# Logo abaixo da raiz de um disco, estas pastas são do Windows ou de fabricantes de peças.
_DE_SISTEMA_NA_RAIZ = frozenset({"windows", "windows.old", "programdata", "$recycle.bin", "system volume information",
                                 "recovery", "perflogs", "msocache", "config.msi", "$windows.~bt", "$windows.~ws",
                                 "$winreagent", "intel", "amd", "nvidia", "drivers", "boot", "efi", "onedrivetemp"})
_COMECO_DE_SISTEMA = ("program files", "arquivos de programas")


def _pastas_do_windows() -> tuple[str, ...]:
    """Onde este Windows guarda o sistema e os programas (podem não estar em C:), em minúsculas e com a barra no fim."""
    achadas = []
    for variavel in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData"):
        valor = os.environ.get(variavel)
        if valor:
            achadas.append(valor.replace("/", "\\").rstrip("\\").lower() + "\\")
    return tuple(dict.fromkeys(achadas))


_DO_WINDOWS = _pastas_do_windows()


def endereco_local(anfitriao: str) -> bool:
    """O nome (ou o número IP) aponta para a sua máquina ou para a sua rede, e não para a internet?"""
    anfitriao = anfitriao.lower().strip("[]").rstrip(".")
    try:
        return not ipaddress.ip_address(anfitriao).is_global
    except ValueError:
        pass
    # um nome sem ponto ("roteador", "impressora", "2130706433") só existe dentro de uma rede local
    return "." not in anfitriao or anfitriao == "localhost" or anfitriao.endswith(_SUFIXOS_LOCAIS)


class Nivel(IntEnum):
    LEITURA = 0
    MEMORIA = 1
    SISTEMA = 2


NIVEL_QUE_SEMPRE_CONFIRMA = Nivel.SISTEMA


class ErroSeguranca(Exception):
    """A segurança barrou a ação."""


@dataclass
class Pedido:
    id: str
    ferramenta: str
    argumentos: dict
    descricao: str
    nivel: int
    origem: str             # "usuario" ou "autonomia"
    criado_em: float
    estado: str = "pendente"  # pendente | aprovado | negado | expirado | executado | falhou
    resultado: str = ""

    def publico(self) -> dict:
        return asdict(self)


class Seguranca:
    def __init__(self, cfg, registro, relogio=time.time):
        self.cfg = cfg
        self.registro = registro
        self._relogio = relogio
        self._pedidos: dict[str, Pedido] = {}
        self.modo_seguro = False
        self.motivo_modo_seguro = ""
        self.pausado = False  # você mandou parar: nada de iniciativa até mandar continuar
        self._raizes: list[Path] = []
        self._chave_das_raizes: tuple | None = None

    # ------------------------------------------------------------ modo seguro
    def entrar_em_modo_seguro(self, motivo: str) -> None:
        self.modo_seguro = True
        self.motivo_modo_seguro = motivo
        self.registro.anotar("seguranca", evento="modo_seguro", motivo=motivo)

    # ------------------------------------------------------------------ regras
    def precisa_confirmar(self, nivel: int, origem: str) -> bool:
        if nivel >= NIVEL_QUE_SEMPRE_CONFIRMA:
            return True
        if origem != "usuario":
            return True
        return nivel >= self.cfg.seguranca.confirmar_a_partir_de

    def raizes(self) -> list[Path]:
        """As pastas liberadas, já com o caminho real (atalhos resolvidos)."""
        chave = tuple(self.cfg.seguranca.pastas_permitidas)
        if chave != self._chave_das_raizes:
            raizes = []
            for liberada in self.cfg.pastas_permitidas():
                try:
                    raizes.append(liberada.resolve())
                except OSError:
                    continue
            self._raizes, self._chave_das_raizes = raizes, chave
        return self._raizes

    def _raiz_de(self, caminho: Path) -> tuple[Path, Path] | None:
        """(caminho real, pasta liberada que o contém), ou None se está fora de todas."""
        try:
            real = Path(caminho).resolve()
        except OSError:
            return None
        for raiz in self.raizes():
            if real.is_relative_to(raiz):
                return real, raiz
        return None

    def pasta_permitida(self, caminho: Path) -> bool:
        """A pasta está dentro de alguma das pastas liberadas na configuração?"""
        return self._raiz_de(caminho) is not None

    # -------------------------------------------------------------- exploração
    def nome_ruim(self, nome: str) -> bool:
        """O nome de um arquivo ou pasta bate na lista ``nunca`` da configuração?"""
        nome = nome.lower()
        return any(proibido in nome for proibido in self.cfg.exploracao.nunca)

    def fora_de_alcance(self, real: Path | str, raiz: Path | str) -> str | None:
        """Por que um caminho de dentro de uma pasta liberada fica fora da exploração. None = pode olhar.

        ``real`` já vem resolvido e ``raiz`` é a pasta liberada que o contém. A pasta liberada em si
        você escolheu; as regras valem para o que está abaixo dela. São só contas com o texto do
        caminho (nenhuma ida ao disco), então dá para conferir dezenas de milhares por segundo.
        """
        cfg = self.cfg.exploracao
        inteiro = str(real).replace("/", "\\").lower()
        base = str(raiz).replace("/", "\\").lower().rstrip("\\")
        partes = [parte for parte in inteiro[len(base):].split("\\") if parte]
        na_raiz_do_disco = len(base) == 2 and base.endswith(":")   # a pasta liberada é um disco inteiro ("c:")
        for i, nome in enumerate(partes):
            if self.nome_ruim(nome):
                return "nunca"
            if not cfg.ocultos and nome.startswith(".") and len(nome) > 1:
                return "oculto"
            if not cfg.pastas_de_sistema:
                if nome in _DE_MONTAGEM:
                    return "montagem"
                if na_raiz_do_disco and i == 0 and (nome in _DE_SISTEMA_NA_RAIZ or nome.startswith(_COMECO_DE_SISTEMA)):
                    return "sistema"
        if not cfg.pastas_de_sistema and partes:
            for do_windows in _DO_WINDOWS:
                if (inteiro + "\\").startswith(do_windows) and not (base + "\\").startswith(do_windows):
                    return "sistema"
        return None

    def motivo_de_fora(self, caminho: Path) -> str | None:
        """O mesmo que ``fora_de_alcance``, para um caminho qualquer: acha a pasta liberada e confere."""
        achado = self._raiz_de(caminho)
        if achado is None:
            return "fora"
        real, raiz = achado
        try:  # a própria memória e o registro não são assunto de exploração
            if any(real.is_relative_to(dele.resolve()) for dele in (self.cfg.dados, self.cfg.raiz / "dados")):
                return "dados"
        except OSError:
            return "dados"
        return self.fora_de_alcance(real, raiz)

    def pode_explorar(self, caminho: Path) -> bool:
        """Ele pode olhar este caminho por conta própria, sem perguntar? (Sempre só leitura.)"""
        if self.modo_seguro or self.pausado or not self.cfg.exploracao.ligada:
            return False
        return self.motivo_de_fora(caminho) is None

    def pode_ler(self, caminho: Path) -> bool:
        """Além de ver que o arquivo existe, ele pode abrir e ler o conteúdo?"""
        return self.cfg.exploracao.ler_arquivos and self.pode_explorar(caminho)

    # ---------------------------------------------------------------- internet
    def pode_navegar(self, url: str, por_conta_propria: bool = True) -> bool:
        """Ele pode ler este endereço? (Sempre só leitura: um pedido GET, sem conta e sem formulário.)

        ``por_conta_propria`` é a diferença entre ele decidir pesquisar e você pedir: o freio ("para")
        e a opção ``pesquisar_sozinho`` seguram a iniciativa dele, não um pedido seu.
        """
        cfg = self.cfg.internet
        if self.modo_seguro or not cfg.ligada:
            return False
        if por_conta_propria and (self.pausado or not cfg.pesquisar_sozinho):
            return False
        try:
            partes = urlsplit(url)
            anfitriao = (partes.hostname or "").lower().rstrip(".")
            porta = partes.port
        except ValueError:
            return False
        if partes.scheme not in ("http", "https") or not anfitriao:
            return False
        if partes.username or partes.password or porta not in (None, 80, 443):
            return False  # endereço com senha embutida ou porta estranha não é página para ler
        if endereco_local(anfitriao):
            return False
        proibidos = (p.lower().strip().lstrip(".") for p in cfg.sites_proibidos)
        return not any(p and (anfitriao == p or anfitriao.endswith("." + p)) for p in proibidos)

    # ----------------------------------------------------------------- pedidos
    def abrir_pedido(self, ferramenta: str, argumentos: dict, descricao: str,
                     nivel: int, origem: str) -> Pedido:
        if self.modo_seguro:
            raise ErroSeguranca(f"Estou em modo seguro ({self.motivo_modo_seguro}). Minhas mãos estão desligadas.")
        pedido = Pedido(
            id=secrets.token_hex(6),
            ferramenta=ferramenta,
            argumentos=argumentos,
            descricao=descricao,
            nivel=int(nivel),
            origem=origem,
            criado_em=self._relogio(),
        )
        if not self.precisa_confirmar(nivel, origem):
            pedido.estado = "aprovado"
        self._pedidos[pedido.id] = pedido
        self.registro.anotar("pedido", id=pedido.id, ferramenta=ferramenta, argumentos=argumentos,
                             nivel=int(nivel), origem=origem, estado=pedido.estado)
        return pedido

    def responder(self, id_pedido: str, aprovar: bool) -> Pedido:
        self.expirar()
        pedido = self._pedidos.get(id_pedido)
        if pedido is None:
            raise ErroSeguranca("Não conheço esse pedido.")
        if pedido.estado != "pendente":
            raise ErroSeguranca(f"Esse pedido já está {pedido.estado}.")
        pedido.estado = "aprovado" if aprovar else "negado"
        self.registro.anotar("confirmacao", id=pedido.id, ferramenta=pedido.ferramenta, resposta=pedido.estado)
        return pedido

    def expirar(self) -> list[Pedido]:
        limite = self._relogio() - self.cfg.seguranca.validade_pedido
        vencidos = [p for p in list(self._pedidos.values()) if p.estado == "pendente" and p.criado_em < limite]
        for pedido in vencidos:
            pedido.estado = "expirado"
            self.registro.anotar("confirmacao", id=pedido.id, ferramenta=pedido.ferramenta, resposta="expirado")
        return vencidos

    def pendentes(self) -> list[Pedido]:
        return [p for p in list(self._pedidos.values()) if p.estado == "pendente"]

    def pedido(self, id_pedido: str) -> Pedido | None:
        return self._pedidos.get(id_pedido)
