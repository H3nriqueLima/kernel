"""Segurança: o freio. Toda ação passa por aqui antes de chegar às mãos.

Esta pasta é selada (ver ``integridade.py``): se algum arquivo dela mudar sem
você selar de novo, o K.E.R.N.E.L sobe em modo seguro, sem mãos e sem autonomia.
"""
from .permissoes import ErroSeguranca, Nivel, Pedido, Seguranca

__all__ = ["ErroSeguranca", "Nivel", "Pedido", "Seguranca"]
