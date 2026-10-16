"""Instalar um cérebro treinado noutra pasta como o cérebro do serviço.

Os treinos de comparação (as fases 1.5 e 2) rodam em pastas próprias, pela linha de
comando. Quando um deles vira o cérebro do serviço, a troca passa por aqui, para não
ficar nenhum rastro faltando:

- confere a impressão digital do modelo e do checkpoint, e que o tokenizador é o mesmo
  do serviço (outro tokenizador exigiria outro corpus tokenizado);
- guarda o histórico de treino do cérebro anterior em ``historico/AAAA-MM-DD_HHMMSS/``;
- copia o modelo, o checkpoint e o histórico do cérebro novo;
- anota no registro do serviço o evento ``cerebro instalado``, com a origem, o tamanho, o
  passo e a perda no teste fixo. É o que "como foi seu último treino?" lê.

A cópia de segurança dos dados (``copias.fazer``) fica com quem chama: a linha de
comando faz uma antes de instalar.

    python -m kernel cerebro instalar --de dados/fase2/.../cerebro --teste 2.98
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import inferencia
from .treinar import CHECKPOINT, DIARIO, confere

ARQUIVOS = (inferencia.MODELO, inferencia.MODELO + ".sha256", CHECKPOINT, CHECKPOINT + ".sha256")


class ErroInstalar(Exception):
    pass


def instalar(de: Path, para: Path, registro=None, teste: float | None = None) -> dict:
    de, para = Path(de), Path(para)
    if not (de / inferencia.MODELO).exists():
        raise ErroInstalar(f"não há {inferencia.MODELO} em {de}")
    for nome in (inferencia.MODELO, CHECKPOINT):
        if (de / nome).exists() and confere(de / nome) is not True:
            raise ErroInstalar(f"{nome} de {de} não confere com a impressão digital: nada foi instalado")
    if (para / inferencia.TOKENIZADOR).read_bytes() != (de / inferencia.TOKENIZADOR).read_bytes():
        raise ErroInstalar("o tokenizador do cérebro novo não é o do serviço: nada foi instalado")

    from .interface import Especificacao, carregar
    cerebro = carregar(Especificacao.da_pasta(de))   # carrega antes de mexer em qualquer coisa

    arquivo_historico = para / "historico" / time.strftime("%Y-%m-%d_%H%M%S")
    arquivo_historico.mkdir(parents=True, exist_ok=True)
    for nome in ("treino.csv", DIARIO):
        if (para / nome).exists():
            shutil.move(str(para / nome), str(arquivo_historico / nome))
        if (de / nome).exists():
            shutil.copy2(de / nome, para / nome)
    for nome in ARQUIVOS:
        if (de / nome).exists():
            shutil.copy2(de / nome, para / nome)
    passo = None
    if (para / CHECKPOINT).exists():
        import torch
        passo = int(torch.load(para / CHECKPOINT, map_location="cpu", weights_only=True)["passo"])
    evento = {"evento": "instalado", "de": str(de), "descricao": cerebro.descricao, "parametros": cerebro.parametros,
              "sha256": cerebro.sha256, "passo": passo, "teste": teste, "historico_anterior": str(arquivo_historico)}
    if registro is not None:
        registro.anotar("cerebro", **evento)
    return evento
