"""Estudo: os trabalhos longos que deixam o K.E.R.N.E.L mais sabido.

- **Estudar a Wikipédia**: baixa partes do dump, limpa o texto e monta a
  enciclopédia local (e o corpus que o cérebro usa para treinar).
- **Treinar o cérebro**: tokeniza o corpus e roda o treino do mini GPT em outro
  processo (o PyTorch fica fora do serviço), por um número de horas.

Os dois começam por um pedido seu no chat e passam pela confirmação, porque
usam internet, disco e a placa de vídeo por bastante tempo. Roda um de cada
vez, em segundo plano, e pode ser interrompido.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from ..maos.base import ErroFerramenta, Ferramenta
from ..seguranca import Nivel

ARQUIVO_DE_PARADA = "PARAR"


class _Interrompido(Exception):
    pass


class Estudo:
    def __init__(self, cfg, registro, ao_terminar):
        self.cfg = cfg
        self.registro = registro
        self.ao_terminar = ao_terminar   # chamado (de outra thread) com (trabalho, mensagem)
        self.trabalho: str | None = None
        self.situacao = ""
        self._parar = threading.Event()
        self._processo: subprocess.Popen | None = None
        # Até quando vai o treino que você aprovou. Se o serviço reiniciar antes, ele retoma sozinho.
        self._arquivo_do_treino = Path(cfg.dados) / "treino_pendente.json"
        self._mantendo = False

    @property
    def ocupado(self) -> bool:
        return self.trabalho is not None

    def _comecar(self, nome: str, funcao, *argumentos) -> None:
        if self.ocupado:
            raise ErroFerramenta(f"Já estou ocupado: {self.trabalho} ({self.situacao}).")
        self.trabalho, self.situacao = nome, "começando"
        self._parar.clear()
        self.registro.anotar("estudo", evento="inicio", trabalho=nome)

        def rodar():
            try:
                mensagem = funcao(*argumentos)
            except _Interrompido:
                mensagem = f"Parei o trabalho ({nome}) como você pediu."
            except Exception as erro:  # sem internet, disco cheio, treino que falhou...
                mensagem = f"Não consegui terminar ({nome}): {erro}"
            self.registro.anotar("estudo", evento="fim", trabalho=nome, resultado=mensagem)
            self.trabalho, self.situacao = None, ""
            self.ao_terminar(nome, mensagem)

        threading.Thread(target=rodar, name=f"estudo-{nome}", daemon=True).start()

    def _andar(self, situacao: str) -> None:
        if self._parar.is_set():
            raise _Interrompido
        self.situacao = situacao

    def treino_pendente(self) -> float:
        """Horas que faltam de um treino aprovado que um reinício do serviço interrompeu (0 = nenhum)."""
        try:
            ate = float(json.loads(self._arquivo_do_treino.read_text(encoding="utf-8"))["ate"])
        except (OSError, ValueError, KeyError, TypeError):
            return 0.0
        return max(ate - time.time(), 0.0) / 3600

    def parar(self, manter: bool = False) -> bool:
        """Para o trabalho em curso. ``manter`` é o serviço desligando: o treino fica pendente para ser
        retomado na próxima partida. Sem ``manter`` foi você que mandou parar, e ele não retoma."""
        if not manter:
            self._arquivo_do_treino.unlink(missing_ok=True)
        if not self.ocupado:
            return False
        self._mantendo = manter
        self._parar.set()
        (self.cfg.pasta("cerebro") / ARQUIVO_DE_PARADA).write_text("parar\n")  # o treino confere a cada passo
        return True

    # ---------------------------------------------------------------- wikipédia
    def estudar_wikipedia(self, partes: int) -> None:
        self._comecar("estudar a Wikipédia", self._wikipedia, partes)

    def _wikipedia(self, partes: int) -> str:
        from ..cerebro import wikipedia
        from ..conhecimento import Enciclopedia

        pasta = self.cfg.pasta("cerebro")
        (pasta / "wiki").mkdir(exist_ok=True)
        self._andar("procurando o dump mais recente")
        disponiveis = wikipedia.listar_partes()
        if not disponiveis:
            raise RuntimeError("não achei o dump da Wikipédia")
        arquivos = []
        escolhidas = disponiveis[:partes]
        for i, (nome, tamanho) in enumerate(escolhidas, 1):
            arquivos.append(wikipedia.baixar(
                nome, pasta / "wiki",
                ao_progredir=lambda feito, tudo, i=i: self._andar(
                    f"baixando a parte {i} de {len(escolhidas)}: {feito / 1e6:.0f} de {tudo / 1e6:.0f} MB")))
        corpus = pasta / "corpus.txt"
        resumo = wikipedia.extrair(arquivos, corpus, ao_progredir=lambda n, c: self._andar(
            f"lendo e limpando: {n} artigos, {c / 1e6:.0f} MB de texto"))
        self._andar("montando a enciclopédia")
        enciclopedia = Enciclopedia(self.cfg.dados / "conhecimento.db")
        try:
            quantos = enciclopedia.construir(corpus, ao_progredir=lambda n: self._andar(
                f"montando a enciclopédia: {n} de {resumo['artigos']} artigos"))
        finally:
            enciclopedia.fechar()
        return (f"Terminei de estudar a Wikipédia: {quantos} artigos. Agora você pode me perguntar "
                '"o que é...?" e "quem foi...?".')

    # ------------------------------------------------------------------- treino
    def treinar_cerebro(self, horas: float) -> None:
        self._mantendo = False
        self._comecar("treinar o cérebro", self._treinar, horas)
        self._arquivo_do_treino.write_text(json.dumps({"ate": time.time() + horas * 3600}), encoding="utf-8")

    def _treinar(self, horas: float) -> str:
        from ..cerebro import dados, tokenizador

        pasta = self.cfg.pasta("cerebro")
        corpus = pasta / "corpus.txt"
        (pasta / ARQUIVO_DE_PARADA).unlink(missing_ok=True)
        if not (pasta / "tokenizador.json").exists():
            self._andar("treinando o tokenizador")
            with open(corpus, encoding="utf-8") as f:
                amostra = f.read(20 * 1024 * 1024)
            tokenizador.treinar([amostra], 4096, lambda feito, tudo: self._andar(
                f"treinando o tokenizador: {feito} de {tudo} tokens")).salvar(pasta / "tokenizador.json")
        if not (pasta / "treino.bin").exists():
            tok = tokenizador.Tokenizador.carregar(pasta / "tokenizador.json")
            dados.preparar(corpus, tok, pasta, lambda lido, tudo, n: self._andar(
                f"tokenizando o texto: {100 * lido / tudo:.0f}%"))
        self._andar("ligando a placa de vídeo")
        self._processo = subprocess.Popen(
            [sys.executable.replace("pythonw.exe", "python.exe"), "-m", "kernel", "cerebro", "treinar",
             "--horas", str(horas)],
            cwd=str(self.cfg.raiz), env={**os.environ, "KERNEL_DADOS": str(self.cfg.dados)},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        ultima = ""
        for linha in self._processo.stdout:
            linha = linha.strip()
            if linha:
                ultima = linha
                self.situacao = linha[:160]
        codigo = self._processo.wait()
        self._processo = None
        if not self._mantendo:
            self._arquivo_do_treino.unlink(missing_ok=True)
        if codigo != 0:
            raise RuntimeError(ultima or f"o treino saiu com código {codigo}")
        ultima = ultima.replace(" Reinicie o serviço para ele usar o cérebro novo.", "")
        return f"Treino encerrado. {ultima} Já estou usando o cérebro novo."


class EstudarWikipedia(Ferramenta):
    nome = "estudar_wikipedia"
    descricao = "Baixa a Wikipédia em português e monta a enciclopédia local."
    nivel = Nivel.SISTEMA

    def __init__(self, estudo: Estudo):
        self.estudo = estudo

    def preparar(self, argumentos: dict) -> tuple[dict, str]:
        partes = max(1, min(int(argumentos.get("partes", 1)), 99))
        quanto = "a Wikipédia inteira (uns 2,8 GB)" if partes >= 8 else \
            f"{partes} parte{'s' if partes > 1 else ''} da Wikipédia (uns {partes * 250} MB)"
        return {"partes": partes}, (f"Baixar {quanto} de dumps.wikimedia.org e estudar. "
                                    "Leva de 20 minutos a algumas horas, em segundo plano")

    def executar(self, argumentos: dict) -> str:
        self.estudo.estudar_wikipedia(argumentos["partes"])
        return "Comecei a estudar. Aviso quando terminar; para acompanhar, pergunte como está o estudo."


class TreinarCerebro(Ferramenta):
    nome = "treinar_cerebro"
    descricao = "Treina o mini GPT na placa de vídeo por algumas horas."
    nivel = Nivel.SISTEMA

    def __init__(self, estudo: Estudo):
        self.estudo = estudo

    def preparar(self, argumentos: dict) -> tuple[dict, str]:
        if not (self.estudo.cfg.pasta("cerebro") / "corpus.txt").exists():
            raise ErroFerramenta('Ainda não tenho texto para treinar. Primeiro diga: "estuda a wikipédia".')
        horas = max(0.05, min(float(argumentos.get("horas", 8)), 72))
        quanto = f"{round(horas * 60)} minutos" if horas < 1 else f"{horas:g} hora{'s' if horas != 1 else ''}"
        return {"horas": horas}, f"Treinar meu cérebro por {quanto}. A placa de vídeo fica ocupada nesse tempo"

    def executar(self, argumentos: dict) -> str:
        self.estudo.treinar_cerebro(argumentos["horas"])
        return ('Comecei a treinar. Para parar antes, diga "para o treino": eu salvo o ponto em que estiver.')
