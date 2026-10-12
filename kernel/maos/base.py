"""O contrato de uma ferramenta e o caminho que toda ação percorre.

    propor  -> a ferramenta valida os argumentos e descreve o que vai fazer
            -> a segurança abre um pedido (e decide se precisa de confirmação)
    concluir -> você respondeu; se aprovou, a ferramenta executa

Para criar uma ferramenta nova: herde de ``Ferramenta``, escolha o nível,
escreva ``preparar`` e ``executar`` e registre-a em ``kernel/nucleo/servico.py``.
"""
from __future__ import annotations

from ..seguranca import ErroSeguranca, Nivel, Pedido, Seguranca


class ErroFerramenta(Exception):
    """A ferramenta não consegue fazer o que foi pedido (a mensagem vai para o chat)."""


class Ferramenta:
    nome: str = ""
    descricao: str = ""
    nivel: Nivel = Nivel.LEITURA

    def preparar(self, argumentos: dict) -> tuple[dict, str]:
        """Valida e devolve (argumentos resolvidos, frase que descreve a ação)."""
        raise NotImplementedError

    def executar(self, argumentos: dict) -> str:
        """Faz a ação e devolve o resultado em texto."""
        raise NotImplementedError


class Maos:
    def __init__(self, seguranca: Seguranca, registro, ferramentas: list[Ferramenta]):
        self.seguranca = seguranca
        self.registro = registro
        self.ferramentas = {f.nome: f for f in ferramentas}

    def propor(self, nome: str, argumentos: dict, origem: str = "usuario") -> Pedido:
        """Abre um pedido. Se ele não precisar de confirmação, já volta executado."""
        ferramenta = self.ferramentas.get(nome)
        if ferramenta is None:
            raise ErroFerramenta(f"Não tenho a ferramenta '{nome}'.")
        resolvidos, descricao = ferramenta.preparar(argumentos)
        pedido = self.seguranca.abrir_pedido(nome, resolvidos, descricao, ferramenta.nivel, origem)
        if pedido.estado == "aprovado":
            self._executar(pedido)
        return pedido

    def concluir(self, id_pedido: str, aprovar: bool) -> Pedido:
        """Você respondeu a um pedido pendente."""
        pedido = self.seguranca.responder(id_pedido, aprovar)
        if pedido.estado == "aprovado":
            self._executar(pedido)
        return pedido

    def _executar(self, pedido: Pedido) -> None:
        if self.seguranca.modo_seguro:
            raise ErroSeguranca("Estou em modo seguro. Minhas mãos estão desligadas.")
        try:
            pedido.resultado = self.ferramentas[pedido.ferramenta].executar(pedido.argumentos)
            pedido.estado = "executado"
        except Exception as erro:  # qualquer falha da ferramenta vira resultado, não derruba o serviço
            pedido.resultado = f"Não consegui: {erro}"
            pedido.estado = "falhou"
        self.registro.anotar("acao", id=pedido.id, ferramenta=pedido.ferramenta,
                             argumentos=pedido.argumentos, estado=pedido.estado, resultado=pedido.resultado)
