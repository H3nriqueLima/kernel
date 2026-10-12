"""Diário: no fim do dia ele relê o registro e escreve o que aconteceu.

Na v0.1 o texto sai de contas e modelos de frase sobre o registro do dia
(quantas conversas, o que fez, o que deu errado, como os impulsos andaram).
Ainda não é o cérebro escrevendo: isso entra quando ele souber escrever.
Cada dia vira um arquivo em ``dados/diario`` e um resumo na memória, para que
amanhã ele consiga lembrar de hoje.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime

_DIAS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")
_MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
          "setembro", "outubro", "novembro", "dezembro")


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


class Diario:
    def __init__(self, cfg, registro, memoria, relogio=datetime.now):
        self.cfg = cfg
        self.registro = registro
        self.memoria = memoria
        self._relogio = relogio
        self.pasta = cfg.pasta("diario")

    def _arquivo(self, dia: date):
        return self.pasta / f"{dia:%Y-%m-%d}.md"

    def ler(self, dia: date) -> str | None:
        arquivo = self._arquivo(dia)
        return arquivo.read_text(encoding="utf-8") if arquivo.exists() else None

    def dias(self) -> list[date]:
        return sorted(date.fromisoformat(a.stem) for a in self.pasta.glob("????-??-??.md"))

    def pendentes(self, agora: datetime) -> list[date]:
        """Dias com registro e sem diário: os passados, e hoje depois da hora do diário."""
        hora = self.cfg.mente.hora_do_diario
        saida = []
        for dia in self.registro.dias()[-7:]:
            if not (dia < agora.date() or agora.hour >= hora):
                continue  # o dia ainda não fechou
            arquivo = self._arquivo(dia)
            if not arquivo.exists():
                saida.append(dia)
                continue
            escrito_em = datetime.fromtimestamp(arquivo.stat().st_mtime)
            if escrito_em.date() == dia and escrito_em.hour < hora:
                saida.append(dia)  # era um rascunho pedido no meio do dia: reescreve com o dia inteiro
        return saida

    def escrever(self, dia: date) -> str:
        eventos = self.registro.do_dia(dia)
        texto, resumo = self._compor(dia, eventos)
        self._arquivo(dia).write_text(texto, encoding="utf-8")
        self.memoria.guardar(resumo, tipo="diario", origem="kernel")
        self.registro.anotar("diario", dia=dia.isoformat())
        return texto

    # ----------------------------------------------------------------- compor
    def _compor(self, dia: date, eventos: list[dict]) -> tuple[str, str]:
        usuario = self.cfg.usuario
        falas = [e for e in eventos if e["tipo"] == "mensagem" and e.get("autor") == "voce"]
        acoes = [e for e in eventos if e["tipo"] == "acao"]
        respostas = Counter(e.get("resposta") for e in eventos if e["tipo"] == "confirmacao")
        voltas = [e for e in eventos if e["tipo"] == "laco"]
        pulsos = [e["impulsos"] for e in eventos if e["tipo"] == "pulso" and "impulsos" in e]
        erros = [e for e in eventos if e["tipo"] == "erro"]
        duvidas = [e for e in eventos if e["tipo"] == "intencao" and e.get("confianca", 1) < 0.6]
        novas = Counter(e.get("classe") for e in eventos if e["tipo"] == "memoria")
        ativacoes = sum(1 for e in eventos if e["tipo"] == "ativacao")

        titulo = f"{_DIAS[dia.weekday()]}, {dia.day} de {_MESES[dia.month - 1]} de {dia.year}"
        if falas:
            abertura = f"{usuario} falou comigo {_plural(len(falas), 'vez', 'vezes')}."
        else:
            abertura = f"Foi um dia quieto: {usuario} não falou comigo."
        linhas = [f"# Diário — {titulo}", "", abertura, ""]

        linhas.append("## O que fiz")
        executadas = [a for a in acoes if a.get("estado") == "executado"]
        if acoes or respostas:
            por_ferramenta = Counter(a["ferramenta"] for a in executadas)
            detalhe = ", ".join(f"{nome} × {n}" for nome, n in por_ferramenta.most_common())
            linhas.append(f"- Executei {_plural(len(executadas), 'ação', 'ações')}"
                          + (f" ({detalhe})." if detalhe else "."))
            if respostas.get("negado"):
                linhas.append(f"- {usuario} negou {_plural(respostas['negado'], 'pedido', 'pedidos')}.")
            if respostas.get("expirado"):
                linhas.append(f"- {_plural(respostas['expirado'], 'pedido expirou', 'pedidos expiraram')} sem resposta.")
        else:
            linhas.append("- Nenhuma ação com as mãos.")
        iniciativas = Counter(v.get("decisao") for v in voltas)
        if iniciativas.get("organizar"):
            linhas.append(f"- Por conta própria, arrumei a memória {_plural(iniciativas['organizar'], 'vez', 'vezes')}.")
        if iniciativas.get("perguntar"):
            linhas.append(f"- Por curiosidade, fiz {_plural(iniciativas['perguntar'], 'pergunta', 'perguntas')}.")
        pesquisas = [e for e in eventos if e["tipo"] == "pesquisar" and e.get("fontes")]
        if pesquisas:
            sozinho = sum(1 for e in pesquisas if e.get("sozinho"))
            assuntos = ", ".join(dict.fromkeys(str(e["termo"]) for e in pesquisas[-8:]))
            linhas.append(f"- Na internet, pesquisei {_plural(len(pesquisas), 'assunto', 'assuntos')} "
                          f"({sozinho} por conta própria): {assuntos}.")
        if ativacoes:
            linhas.append(f"- Ouvi meu nome {_plural(ativacoes, 'vez', 'vezes')}.")

        linhas += ["", "## O que guardei"]
        if novas:
            detalhe = ", ".join(f"{n} de {classe}" for classe, n in novas.most_common())
            linhas.append(f"- {_plural(sum(novas.values()), 'memória nova', 'memórias novas')}: {detalhe}.")
        else:
            linhas.append("- Nada novo na memória.")

        linhas += ["", "## Como eu estava"]
        if pulsos:
            for nome in pulsos[0]:
                valores = [p[nome] for p in pulsos if nome in p]
                rotulo = nome.replace("organizacao", "organização").capitalize()
                linhas.append(f"- {rotulo}: média {sum(valores) / len(valores):.2f}, pico {max(valores):.2f}.")
        else:
            linhas.append("- Fiquei pouco tempo acordado para medir meus impulsos.")

        linhas += ["", "## O que deu errado"]
        falhas = [a for a in acoes if a.get("estado") == "falhou"]
        if not (falhas or erros or duvidas):
            linhas.append("- Nada que eu tenha percebido.")
        for falha in falhas:
            linhas.append(f"- {falha['ferramenta']}: {falha.get('resultado', '')}")
        if erros:
            linhas.append(f"- {_plural(len(erros), 'erro interno', 'erros internos')} no registro.")
        if duvidas:
            linhas.append(f"- Fiquei em dúvida sobre o que {usuario} quis dizer em "
                          f"{_plural(len(duvidas), 'frase', 'frases')}.")

        linhas += ["", "## Para amanhã"]
        if respostas.get("negado"):
            linhas.append("- Rever os pedidos negados: talvez eu tenha entendido errado o comando.")
        if duvidas:
            exemplo = duvidas[0].get("texto", "")
            linhas.append(f'- Pedir exemplos de frases como "{exemplo}" para o classificador de comandos.')
        pendentes = self.memoria.lembretes()
        if pendentes:
            linhas.append(f"- {_plural(len(pendentes), 'lembrete pendente', 'lembretes pendentes')}: "
                          + "; ".join(l.texto for l in pendentes[:5]) + ".")
        if linhas[-1] == "## Para amanhã":
            linhas.append("- Continuar aprendendo.")

        resumo = (f"Diário de {dia:%d/%m/%Y}: {abertura} Executei {_plural(len(executadas), 'ação', 'ações')} "
                  f"e guardei {_plural(sum(novas.values()), 'memória nova', 'memórias novas')}.")
        return "\n".join(linhas) + "\n", resumo
