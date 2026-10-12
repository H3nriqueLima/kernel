"""Aparelhos pareados: quem, além deste PC, pode falar com o K.E.R.N.E.L.

Na sua máquina (127.0.0.1) a janela de chat já entra autenticada. Um celular na
rede local precisa ser pareado uma vez:

1. No PC, você pede um código de pareamento (6 dígitos, vale 5 minutos).
2. No celular, você digita o código. Se bater, o celular recebe uma chave longa
   e passa a mandá-la em todo pedido.

Só o resumo (SHA-256) de cada chave fica guardado em ``dados/aparelhos.json``.
O código de pareamento aguenta 5 tentativas erradas e morre, então não dá para
adivinhá-lo na força bruta. Apagar um aparelho da lista corta o acesso na hora.

A conversa pela rede local vai sem criptografia (HTTP): use só em rede de casa.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from pathlib import Path

VALIDADE_DO_CODIGO = 300.0   # segundos
TENTATIVAS = 5


def _resumo(chave: str) -> str:
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


class Aparelhos:
    def __init__(self, arquivo: Path, registro, relogio=time.time):
        self.arquivo = Path(arquivo)
        self.registro = registro
        self._relogio = relogio
        self._codigo: str | None = None
        self._expira = 0.0
        self._tentativas = 0
        try:
            self._aparelhos: list[dict] = json.loads(self.arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._aparelhos = []

    def _salvar(self) -> None:
        self.arquivo.write_text(json.dumps(self._aparelhos, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------- pareamento
    def novo_codigo(self) -> str:
        """Gera o código que você vai digitar no celular. Só pode ser pedido no próprio PC."""
        self._codigo = f"{secrets.randbelow(1_000_000):06d}"
        self._expira = self._relogio() + VALIDADE_DO_CODIGO
        self._tentativas = 0
        self.registro.anotar("aparelho", evento="codigo_gerado")
        return self._codigo

    def parear(self, codigo: str, nome: str) -> str | None:
        """Confere o código. Se bater, devolve a chave do novo aparelho (mostrada uma única vez)."""
        if self._codigo is None or self._relogio() > self._expira:
            self._codigo = None
            return None
        self._tentativas += 1
        certo = secrets.compare_digest(codigo.strip(), self._codigo)
        if not certo:
            if self._tentativas >= TENTATIVAS:
                self._codigo = None  # errou demais: precisa gerar outro no PC
            self.registro.anotar("aparelho", evento="codigo_errado", tentativa=self._tentativas)
            return None
        self._codigo = None  # cada código serve para um aparelho só
        chave = secrets.token_urlsafe(32)
        nome = (nome.strip() or "celular")[:40]
        self._aparelhos.append({"id": secrets.token_hex(4), "nome": nome, "resumo": _resumo(chave),
                                "desde": time.strftime("%Y-%m-%dT%H:%M:%S")})
        self._salvar()
        self.registro.anotar("aparelho", evento="pareado", nome=nome)
        return chave

    # ------------------------------------------------------------------ acesso
    def reconhece(self, chave: str) -> bool:
        if not chave:
            return False
        resumo = _resumo(chave)
        return any(secrets.compare_digest(resumo, aparelho["resumo"]) for aparelho in self._aparelhos)

    def lista(self) -> list[dict]:
        return [{"id": a["id"], "nome": a["nome"], "desde": a["desde"]} for a in self._aparelhos]

    def esquecer(self, id_aparelho: str) -> bool:
        antes = len(self._aparelhos)
        self._aparelhos = [a for a in self._aparelhos if a["id"] != id_aparelho]
        if len(self._aparelhos) == antes:
            return False
        self._salvar()
        self.registro.anotar("aparelho", evento="esquecido", id=id_aparelho)
        return True
