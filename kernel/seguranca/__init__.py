"""Segurança: o freio. Toda ação passa por aqui antes de chegar às mãos.

Esta pasta, e os outros componentes que aplicam as regras, são selados (ver
``integridade.py``): se algum deles mudar sem você selar de novo, o K.E.R.N.E.L
entra em modo seguro, sem mãos e sem autonomia.
"""
from .permissoes import ErroSeguranca, Nivel, Pedido, Seguranca

__all__ = ["ErroSeguranca", "Nivel", "Pedido", "Seguranca"]
