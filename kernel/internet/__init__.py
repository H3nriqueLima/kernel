"""Internet: como o K.E.R.N.E.L sai do PC para aprender, sempre só lendo.

- ``rede.py``: o navegador dele. Um leitor escrito aqui, sem as suas contas, que
  só faz pedidos de leitura, só na internet pública, só de texto, com teto e registro.
- ``pagina.py``: de HTML para texto (o que numa página é leitura).
- ``fontes.py``: onde ele procura: Wikipédia, Wikcionário e um buscador.
- ``pesquisador.py``: a fila de assuntos, a pesquisa de um assunto e a guarda do
  que foi lido na memória, com a fonte.

Fica desligada de fábrica. Liga-se em ``kernel.toml``, seção ``[internet]``.
"""
from .fontes import Achado, BuscadorIndisponivel
from .pagina import Pagina, ler_html
from .pesquisador import Pesquisador, Resultado
from .rede import ErroDeRede, Interrompido, Navegador, Resposta

__all__ = ["Achado", "BuscadorIndisponivel", "ErroDeRede", "Interrompido", "Navegador", "Pagina", "Pesquisador",
           "Resposta", "Resultado", "ler_html"]
