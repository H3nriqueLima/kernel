"""Impulsos: números entre 0 e 1 que sobem e descem e dão iniciativa ao K.E.R.N.E.L.

São três:

- ``curiosidade``: sobe enquanto ninguém pede nada. Quando passa do limiar, ele
  sai explorando as pastas liberadas (um fôlego de alguns passos) e, se achar
  um nome que não conhece, pergunta.
- ``organizacao``: acompanha a bagunça. Cada memória ainda não arrumada soma um
  pouco. Quando passa do limiar, ele arruma a memória.
- ``social``: vontade de contar. Cada descoberta da exploração soma um pouco;
  quando passa do limiar, ele conta o que achou.

A regra de decisão é uma só: agir para reduzir o impulso mais alto que estiver
acima do limiar. Se nenhum estiver, a decisão é não fazer nada. Por serem só
números e uma regra, dá para prever e auditar cada iniciativa no registro.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

NOMES = ("curiosidade", "organizacao", "social")


@dataclass
class Percepcao:
    """O que o núcleo percebeu nesta volta do laço."""
    agora: datetime
    segundos_ocioso: float        # tempo desde a sua última mensagem
    memorias_por_organizar: int
    novidades: int = 0            # descobertas da exploração que ele ainda não contou


class Impulsos:
    def __init__(self, cfg_mente, valores: dict[str, float] | None = None):
        self.cfg = cfg_mente
        self.valores = {nome: 0.0 for nome in NOMES}
        for nome, valor in (valores or {}).items():
            if nome in self.valores:
                self.valores[nome] = min(1.0, max(0.0, float(valor)))

    def atualizar(self, percepcao: Percepcao, segundos: float) -> None:
        if percepcao.segundos_ocioso > 60:  # conversando ele está ocupado, não curioso
            subida = self.cfg.curiosidade_por_minuto * segundos / 60
            self.valores["curiosidade"] = min(1.0, self.valores["curiosidade"] + subida)
        bagunca = percepcao.memorias_por_organizar * self.cfg.organizacao_por_memoria
        self.valores["organizacao"] = min(1.0, bagunca)
        self.valores["social"] = min(1.0, percepcao.novidades * self.cfg.social_por_novidade)

    def dominante(self, ignorar: tuple[str, ...] = ()) -> str | None:
        """O impulso mais alto acima do limiar, ou None (= não fazer nada)."""
        candidatos = [n for n in NOMES if n not in ignorar]
        nome = max(candidatos, key=lambda n: self.valores[n])
        return nome if self.valores[nome] >= self.cfg.limiar_impulso else None

    def acima_do_limiar(self) -> list[str]:
        """Todos os impulsos que pedem ação, do mais forte para o mais fraco."""
        fortes = [n for n in NOMES if self.valores[n] >= self.cfg.limiar_impulso]
        return sorted(fortes, key=lambda n: -self.valores[n])

    def satisfazer(self, nome: str, quanto: float = 1.0) -> None:
        self.valores[nome] = max(0.0, self.valores[nome] - quanto)
