"""O núcleo do K.E.R.N.E.L.

Ele liga os órgãos e faz duas coisas:

- ``receber``: trata uma mensagem sua. Primeiro os reflexos (o freio "para",
  hora, contas, cumprimentos); depois o classificador decide a intenção: os
  comandos viram pedidos para as mãos (que passam pela segurança), as perguntas
  vão para a enciclopédia e a memória, e a conversa é guardada.
- ``volta``: uma volta do laço de autonomia, que roda sozinho a cada poucos
  segundos: perceber, lembrar, avaliar, decidir, agir, refletir. É aqui que ele
  explora o PC por conta própria, pergunta o que não conhece e conta o que achou.

Tudo o que acontece é anotado no registro.
"""
from __future__ import annotations

import asyncio
import json
import re
import secrets
import threading
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from .. import NOME, NOME_COMPLETO, VERSAO, comandos
from ..cerebro import inferencia
from ..comandos import calculo, extrair
from ..conhecimento import Enciclopedia, assunto_da_pergunta
from ..conhecimento.resumo import frases
from ..exploracao import Explorador, Mapa, sistema
from ..internet import Pesquisador
from ..internet.pesquisador import resumo
from ..maos import AbrirPagina, AbrirPrograma, AnotarLembrete, ErroFerramenta, ListarPasta, Maos
from ..memoria import Memoria
from ..memoria.texto import PARADAS, normalizar, radical, termos
from ..mente import Diario, Impulsos, Percepcao
from ..registro import Registro
from ..seguranca import ErroSeguranca, Seguranca, integridade
from ..seguranca.aparelhos import Aparelhos
from . import dialogo, reflexos, sobre_si
from .estudo import EstudarWikipedia, Estudo, TreinarCerebro

# Palavras que fazem parte da pergunta ("o que você LEMBRA SOBRE...") e não do assunto.
_ANDAIME = {radical(p) for p in """lembra lembrar lembro sabe saber falei falou disse dizer diz memoria
    memorias busca buscar procura procurar pesquisa pesquisar guardou guardado anotei anotou anotado
    anotacao conversamos recupera consulta algo alguma ultima coisa mostra lembranca lembrancas
    ficou pedi era tenho""".split()}
_ANDAIME_DE_ARQUIVO = {radical(p) for p in """onde esta fica salvei procura procure procurar acha ache achar
    encontra encontre localiza localize busca busque cade tem existe algum alguma viu achou pasta qual quais
    arquivo arquivos chamado nome fala falam kernel pra mim meus minhas tenho eu voce em que nos por""".split()}
_TIPOS_DE_ARQUIVO = {"planilha": "xlsx", "planilhas": "xlsx", "pdfs": "pdf", "documento": "docx",
                     "documentos": "docx", "foto": "jpg", "fotos": "jpg", "apresentacao": "pptx"}
_DESISTENCIAS = {"nao sei", "deixa", "deixa pra la", "esquece", "nada", "depois", "nao importa", "pula"}
_MINUTOS_DE_ESPERA_DA_PERGUNTA = 30
_SEGUNDOS_ENTRE_PULSOS = 600
_SOSSEGO_PARA_EXPLORAR = 30   # segundos sem você falar antes de ele sair explorando
_VOLTAS_POR_FOLEGO = 20
_CUSTO_DE_PESQUISAR = 0.15    # curiosidade gasta em cada assunto pesquisado na internet
# ritmo -> (passos de exploração por volta do laço, curiosidade gasta em cada fôlego)
_RITMOS = {"calmo": (1, 0.5), "normal": (3, 0.35), "intenso": (8, 0.1)}
_CONFIRMACOES = ("Guardei.", "Anotado na memória.", "Entendi, guardei.")


def _como_voce_escreveu(texto: str, assunto: str) -> str:
    """O mesmo assunto, com os acentos e as maiúsculas da sua frase (é assim que ele pesquisa e mostra)."""
    originais = re.sub(r"[^\w\s]", " ", texto).split()
    planas = [normalizar(palavra) for palavra in originais]
    alvo = assunto.split()
    for i in range(len(planas) - len(alvo) + 1):
        if planas[i:i + len(alvo)] == alvo:
            return " ".join(originais[i:i + len(alvo)])
    return assunto


def _duracao(tempo: timedelta) -> str:
    """ "40 min", "3 h", "2 dias": o tamanho de uma ausência, por alto."""
    minutos = int(tempo.total_seconds() // 60)
    if minutos < 90:
        return f"{max(minutos, 1)} min"
    if minutos < 36 * 60:
        return f"{round(minutos / 60)} h"
    return f"{round(minutos / 1440)} dias"


def _site(url: str) -> str:
    """De um endereço, só o nome do site (para citar a fonte)."""
    return (urlsplit(url).hostname or url).removeprefix("www.")


class Kernel:
    def __init__(self, cfg, relogio=datetime.now, lancar=None, transporte=None, resolver=None):
        self.cfg = cfg
        self._relogio = relogio
        self.iniciado_em = relogio()
        self.sessao = secrets.token_hex(4)       # muda a cada partida: a página sabe que os números recomeçaram

        self.registro = Registro(cfg.pasta("registro"), relogio)
        self.memoria = Memoria(cfg.dados / "kernel.db", relogio)
        self.seguranca = Seguranca(cfg, self.registro)
        integro, mudancas = integridade.verificar()
        if not integro:
            self.seguranca.entrar_em_modo_seguro("o código de segurança mudou: " + "; ".join(mudancas))
        self.aparelhos = Aparelhos(cfg.dados / "aparelhos.json", self.registro)
        self.estudo = Estudo(cfg, self.registro, self._estudo_terminou)
        self.maos = Maos(self.seguranca, self.registro, [
            AbrirPrograma(cfg, lancar),
            AbrirPagina(lancar),
            ListarPasta(cfg, self.seguranca),
            AnotarLembrete(self.memoria),
            EstudarWikipedia(self.estudo),
            TreinarCerebro(self.estudo),
        ])
        self.classificador = comandos.garantir(cfg)
        # None enquanto não houver cérebro treinado (ou se o arquivo de pesos não conferir com a impressão digital)
        self.cerebro = inferencia.carregar(cfg, avisar=lambda problema: self.registro.anotar("cerebro", problema=problema))
        self.enciclopedia = Enciclopedia(cfg.dados / "conhecimento.db")
        self.diario = Diario(cfg, self.registro, self.memoria, relogio)
        self.ouvidos = None                      # ligados no começo do laço, se houver modelo treinado
        self._motivo_ouvidos = "o serviço ainda não começou"

        self._arquivo_de_estado = cfg.dados / "estado.json"
        salvo = self._ler_estado()
        self.seguranca.pausado = bool(salvo.get("pausado", False))
        self.impulsos = Impulsos(cfg.mente, salvo.get("impulsos"))
        self.termos_perguntados: set[str] = set(salvo.get("termos_perguntados", []))
        self.novidades = int(salvo.get("novidades", 0))
        self.pergunta_aberta: dict | None = None
        self.ultima_pergunta: datetime | None = None
        self.ultimo_relato: datetime | None = None

        self.mapa = Mapa(cfg.dados / "mapa.db", relogio)
        self.explorador = Explorador(cfg, self.seguranca, self.mapa, self.memoria, self.registro, relogio)
        self.explorador.interromper = self._largar_a_exploracao
        # os testes passam um ``transporte`` de mentira: nenhum teste sai para a internet de verdade
        self.pesquisador = Pesquisador(cfg, self.seguranca, self.memoria, self.registro, relogio,
                                       transporte=transporte, resolver=resolver,
                                       assuntos_dos_arquivos=lambda: self.mapa.assuntos(8),
                                       assuntos_das_conversas=self._assuntos_das_perguntas)
        self._perguntas_lidas = (0.0, [])        # (quando, assuntos): o registro do dia não é relido a toda hora
        self.pesquisador.navegador.interromper = self._largar_a_exploracao
        if self.explorador.releu_tudo:           # as leituras foram refeitas: o que saiu delas para a fila também sai
            self.pesquisador.esquecer_origem("arquivos")
        self._vez_da_internet = False            # alterna: um fôlego no PC, um assunto na internet
        self._contei_em = self.iniciado_em.isoformat(timespec="seconds")   # até onde vai o último relato
        self._em_pauta: dict | None = None       # o assunto da última resposta, para o "fale mais"
        self._perguntas_no_vazio = 0             # perguntas dele que ficaram sem resposta, seguidas
        self._explorar_ja = False                # você mandou explorar agora: não espera o sossego
        self._ultima_fonte = ""                  # o endereço da última resposta tirada da internet ("abre a fonte")
        self._a_seu_pedido = ""                  # o que ele está pesquisando agora porque você pediu (a tela mostra)
        self.atividade = "ocioso"                # ocioso | explorando | pausado (a interface mostra)
        self.detalhe = ""
        self._folego = 0                         # voltas que faltam no fôlego de exploração atual
        self._largar = False                     # você falou no meio de uma pasta grande: é para largá-la
        self._do_folego = {"pastas": 0, "arquivos": 0, "lidos": 0}

        self.mensagens: list[dict] = []
        self._trava_das_falas = threading.Lock()
        self._proximo_id = 1
        self.ultima_fala = relogio()
        self._ultimo_pulso = 0.0
        self._ja_explicou_cerebro = False
        self._parar: asyncio.Event | None = None
        self._laco_principal: asyncio.AbstractEventLoop | None = None
        self._desligado = False
        self.ao_desligar = None                  # o servidor web pendura aqui a sua parada

        (cfg.dados / "DESLIGAR").unlink(missing_ok=True)  # um pedido antigo não vale para esta partida

    # ================================================================ conversa
    def dizer(self, texto: str, autor: str = "kernel", classe: str = "fala", **extra) -> dict:
        with self._trava_das_falas:  # a conversa e o laço de autonomia falam de threads diferentes
            mensagem = {"id": self._proximo_id, "ts": self._relogio().isoformat(timespec="seconds"),
                        "autor": autor, "classe": classe, "texto": texto, **extra}
            self._proximo_id += 1
            self.mensagens.append(mensagem)
            del self.mensagens[:-500]
        self.registro.anotar("mensagem", autor=autor, classe=classe, texto=texto)
        return mensagem

    def _guardar(self, texto: str, tipo: str, origem: str = "usuario") -> int:
        id_memoria = self.memoria.guardar(texto, tipo=tipo, origem=origem)
        self.registro.anotar("memoria", classe=tipo, id=id_memoria)
        return id_memoria

    async def receber(self, texto: str) -> None:
        """Você disse alguma coisa."""
        texto = texto.strip()
        if not texto:
            return
        agora = self._relogio()
        ausencia = agora - self.ultima_fala      # há quanto tempo você não falava
        self.ultima_fala = agora
        self._perguntas_no_vazio = 0
        self._folego = 0  # você falou: ele larga a exploração e presta atenção
        self._largar = True
        if self.atividade == "explorando":
            self.atividade, self.detalhe = "ocioso", ""
        self.dizer(texto, autor="voce")
        voltou = ausencia >= timedelta(minutes=self.cfg.mente.minutos_de_presenca)
        # O resumo da ausência é fechado antes de tratar a mensagem: o que você pedir agora não entra nele.
        novidades = self._fechar_relato(agora) if voltou else ""
        try:
            if not self._reflexo(texto, agora):
                para_a_internet = reflexos.internet(texto)
                para_o_cerebro = dialogo.para_o_cerebro(texto)
                aprendeu_sobre = dialogo.aprendeu_sobre(texto)
                if para_o_cerebro:
                    await self._usar_cerebro(para_o_cerebro)
                elif aprendeu_sobre:
                    self._o_que_sei_sobre(aprendeu_sobre)
                elif para_a_internet:
                    await self._tratar_internet(*para_a_internet)
                elif dialogo.pede_mais(texto) is not None:
                    # "fale mais", "e o que mais?": continuar o assunto não depende do classificador acertar
                    self.registro.anotar("intencao", texto=texto, intencao="mais", confianca=1.0)
                    if sobre_si.e_sobre_voce(texto) and sobre_si.topico(texto):
                        self.dizer(sobre_si.responder(self, texto))      # "fale mais das suas funções"
                    else:
                        await self._falar_mais(*dialogo.pede_mais(texto))
                else:
                    await self._entender(texto, agora)
        except (ErroFerramenta, ErroSeguranca) as erro:
            self.dizer(str(erro), classe="aviso")
        except Exception as erro:  # noqa: BLE001
            # Um defeito ao tratar a mensagem não pode virar erro 500: a página devolveria o texto ao campo,
            # você mandaria de novo e a mesma fala ficaria duas vezes na conversa.
            self.registro.anotar("erro", onde="receber", erro=f"{type(erro).__name__}: {erro}")
            self.dizer("Tive um erro interno ao tratar isso. Anotei no registro.", classe="aviso")
        if novidades:
            # Você voltou. Em vez de falar sozinho enquanto você não estava, ele conta agora, de uma vez.
            self.dizer(f"Enquanto você esteve fora ({_duracao(ausencia)}), {novidades}", classe="iniciativa")
        self._salvar_estado()

    def _reflexo(self, texto: str, agora: datetime) -> bool:
        """Respostas por regra, antes do classificador. Devolve True se a mensagem foi resolvida aqui."""
        comando = reflexos.controle(texto)
        if comando == "pausar":
            self.pausar()
            return True
        if comando == "retomar" and self.seguranca.pausado:
            self.retomar()
            return True
        pedido = reflexos.estudo(texto)
        if pedido:
            self._tratar_estudo(*pedido)
            return True
        resposta = (reflexos.hora_ou_data(texto, agora) or calculo.tentar(texto)
                    or reflexos.saudacao(texto, self.cfg.usuario, len(self.memoria.lembretes())))
        if resposta:
            self.registro.anotar("intencao", texto=texto, intencao="reflexo", confianca=1.0)
            self.dizer(resposta)
            return True
        return False

    async def _entender(self, texto: str, agora: datetime) -> None:
        intencao, confianca = self.classificador.classificar(texto)
        if intencao == "conversa":
            # O classificador não reconheceu a frase. Antes de tratá-la como conversa (e só guardar),
            # as regras de diálogo olham se ela é sobre ele, um "fale mais", um pedido ou uma pergunta.
            if self.pergunta_aberta and dialogo.parece_resposta(texto, self.pergunta_aberta["termo"]):
                pass   # você está respondendo ao que ele perguntou
            elif sobre_si.e_sobre_voce(texto) and sobre_si.topico(texto):
                intencao = "sobre_si"
            elif dialogo.pede_mais(texto) is not None:
                intencao = "mais"
            elif dialogo.explorar_agora(texto):
                intencao = "explorar"
            elif dialogo.eh_pergunta(texto):
                intencao = "pergunta"
        self.registro.anotar("intencao", texto=texto, intencao=intencao, confianca=round(confianca, 3))
        if intencao == "abrir_programa":
            self._propor("abrir_programa", {"programa": extrair.programa(texto)})
        elif intencao == "listar_pasta":
            self._propor("listar_pasta", {"pasta": extrair.pasta(texto)})
        elif intencao == "anotar_lembrete":
            corpo, quando = extrair.lembrete(texto, agora)
            self._propor("anotar_lembrete", {"texto": corpo, "quando": quando.isoformat() if quando else None})
        elif intencao == "consultar_memoria":
            self._consultar(texto)
        elif intencao == "sobre_si":
            self.dizer(sobre_si.responder(self, texto))
        elif intencao == "pergunta":
            await self._responder_pergunta(texto)
        elif intencao == "procurar_arquivo":
            self._procurar_arquivo(texto)
        elif intencao == "sistema":
            self.dizer(sistema.descrever())
        elif intencao == "descobertas":
            self.dizer(self._relato())
        elif intencao == "mais":
            await self._falar_mais(*dialogo.pede_mais(texto))
        elif intencao == "explorar":
            self._explorar_agora()
        else:
            await self._conversar(texto)

    def _propor(self, ferramenta: str, argumentos: dict, origem: str = "usuario") -> None:
        pedido = self.maos.propor(ferramenta, argumentos, origem)
        if pedido.estado == "pendente":
            self.dizer(pedido.descricao + "?", classe="pedido", pedido=pedido.id)
        else:
            self._relatar(pedido)

    def responder_pedido(self, id_pedido: str, aprovar: bool) -> None:
        """Você clicou em Permitir ou Negar."""
        try:
            pedido = self.maos.concluir(id_pedido, aprovar)
        except ErroSeguranca as erro:
            self.dizer(str(erro), classe="aviso")
            return
        if pedido.estado == "negado":
            self.dizer("Tudo bem, não fiz.")
        else:
            self._relatar(pedido)

    def _relatar(self, pedido) -> None:
        """Conta no chat no que deu uma ação das mãos."""
        self.dizer(pedido.resultado, classe="resultado" if pedido.estado == "executado" else "aviso")
        if pedido.ferramenta == "anotar_lembrete" and pedido.estado == "executado":
            self.registro.anotar("memoria", classe="lembrete")

    def _tratar_estudo(self, tipo: str, argumentos: dict) -> None:
        if tipo == "parar":
            self.dizer("Certo, vou parar assim que salvar o ponto em que estou." if self.estudo.parar()
                       else "Não estou estudando nem treinando agora.")
        elif tipo == "andamento":
            self.dizer(f"Estou ocupado em {self.estudo.trabalho}: {self.estudo.situacao}." if self.estudo.ocupado
                       else "Não estou estudando nem treinando agora.")
        elif tipo == "wikipedia":
            self._propor("estudar_wikipedia", argumentos)
        else:
            self._propor("treinar_cerebro", argumentos)

    def _consultar(self, texto: str) -> None:
        plano = normalizar(texto)
        if re.search(r"lembrete|compromisso|(pra|para) fazer", plano):
            pendentes = self.memoria.lembretes()
            if not pendentes:
                self.dizer("Você não tem lembretes pendentes.")
                return
            linhas = []
            for lembrete in pendentes:
                data = f" ({datetime.fromisoformat(lembrete.quando):%d/%m às %H:%M})" if lembrete.quando else ""
                linhas.append(f"• {lembrete.texto}{data}")
            self.dizer("Seus lembretes pendentes:\n" + "\n".join(linhas))
            return
        assunto = " ".join(t for t in termos(texto) if t not in _ANDAIME)
        achados = self.memoria.buscar(assunto, k=5) if assunto else []
        if not achados:
            self.dizer("Não achei nada sobre isso na minha memória.")
            return
        self.dizer("Achei isto na memória:\n" + "\n".join(self._citar(a) for a in achados), classe="lembranca")

    @staticmethod
    def _citar(lembranca) -> str:
        data = f"{datetime.fromisoformat(lembranca.criado_em):%d/%m/%Y}"
        if lembranca.tipo == "leitura":
            trecho = lembranca.texto if len(lembranca.texto) <= 220 else lembranca.texto[:220] + "…"
            return f"• {trecho}  (li em {Path(lembranca.origem).parent.name}, {data})"
        if lembranca.tipo == "pesquisa":
            trecho = lembranca.texto if len(lembranca.texto) <= 220 else lembranca.texto[:220] + "…"
            return f"• {trecho}  (da internet: {_site(lembranca.origem)}, {data})"
        return f"• {lembranca.texto}  ({data}, {lembranca.tipo})"

    def _por_em_pauta(self, titulo: str, texto: str, dito: str, fonte: str, link: str | None, classe: str) -> None:
        """Guarda o assunto da resposta que acabou de dar: é dele que sai o "fale mais"."""
        todas = frases(texto)
        self._em_pauta = {"titulo": titulo, "frases": todas, "ditas": {f for f in todas if f in dito},
                          "fonte": fonte, "link": link, "classe": classe}

    async def _falar_mais(self, quantas: int, assunto: str) -> None:
        """ "Fale mais": continua o assunto da última resposta (ou começa o assunto pedido)."""
        if assunto:
            await self._responder_pergunta(f"sobre {assunto}")
            return
        pauta = self._em_pauta
        if not pauta:
            self.dizer('Mais sobre o quê? Faça uma pergunta ("o que é...") ou peça "pesquisa sobre...".')
            return
        novas = [f for f in pauta["frases"] if f not in pauta["ditas"]][:quantas]
        if not novas:
            dica = f' Posso procurar mais: diga "pesquisa sobre {pauta["titulo"]}".' if self.cfg.internet.ligada else ""
            self.dizer(f'É tudo o que eu tenho sobre {pauta["titulo"]}.{dica}')
            return
        pauta["ditas"].update(novas)
        extra = {"link": pauta["link"]} if pauta["link"] else {}
        self.dizer(" ".join(novas), classe=pauta["classe"], fonte=pauta["fonte"], **extra)

    async def _responder_pergunta(self, texto: str) -> None:
        achado = self.enciclopedia.responder(texto)
        if achado:
            titulo, resposta = achado
            artigos = self.enciclopedia.procurar(texto, k=1)
            self._por_em_pauta(titulo, artigos[0].texto if artigos else resposta, resposta, f"Wikipédia: {titulo}",
                               None, "conhecimento")
            self.dizer(resposta, classe="conhecimento", fonte=f"Wikipédia: {titulo}")
            return
        assunto = assunto_da_pergunta(texto)
        vale_pesquisar = any(len(termo) >= 3 for termo in termos(assunto))   # "tudo bem?" não é assunto de pesquisa
        if assunto and vale_pesquisar and not self._sem_internet():
            # O que você mesmo me ensinou vale mais do que a internet; depois, o que já pesquisei; por fim, pesquiso agora.
            ensinado = [l for l in self.memoria.buscar(assunto, k=3, tipos=("fato", "lembrete")) if l.em_comum >= 1]
            if ensinado:
                self.dizer("Você me contou isto:\n" + "\n".join(self._citar(l) for l in ensinado), classe="lembranca")
                return
            estudado = self.pesquisador.resumo_de(assunto)
            if estudado:   # já estudou este assunto: responde do que aprendeu, sem voltar à rede
                mostrar, aprendido, enderecos = estudado
                self._ultima_fonte = enderecos[0] if enderecos else ""
                fonte = "já pesquisei: " + ", ".join(dict.fromkeys(_site(e) for e in enderecos))
                resposta = resumo(aprendido, assunto)
                trechos = self.memoria.buscar(mostrar, k=6, tipos=("pesquisa",))
                self._por_em_pauta(mostrar, aprendido + "\n" + "\n".join(l.texto.split(": ", 1)[-1] for l in trechos),
                                   resposta, fonte, self._ultima_fonte or None, "pesquisa")
                extra = {"link": self._ultima_fonte} if self._ultima_fonte else {}
                self.dizer(resposta, classe="pesquisa", fonte=fonte, **extra)
                return
            precisa = min(2, len(set(termos(assunto))))
            sabido = next((l for l in self.memoria.buscar(assunto, k=3, tipos=("pesquisa",)) if l.em_comum >= precisa), None)
            if sabido:
                self._ultima_fonte = sabido.origem
                corpo = sabido.texto.split(": ", 1)[-1]
                resposta = resumo(corpo, assunto)
                self._por_em_pauta(assunto, corpo, resposta, f"já pesquisei: {_site(sabido.origem)}", sabido.origem, "pesquisa")
                self.dizer(resposta, classe="pesquisa", fonte=f"já pesquisei: {_site(sabido.origem)}", link=sabido.origem)
                return
            await self._pesquisar_agora(_como_voce_escreveu(texto, assunto), origem="pergunta")
            return
        lembrancas = [l for l in (self.memoria.buscar(assunto, k=3) if assunto else []) if l.em_comum >= 1]
        if lembrancas:
            self.dizer("Não estudei isso, mas achei nas minhas memórias:\n"
                       + "\n".join(self._citar(l) for l in lembrancas), classe="lembranca")
        elif len(self.enciclopedia) == 0:
            self.dizer('Ainda não sei responder perguntas assim. Se você disser "estuda a wikipédia", '
                       "eu baixo, leio e passo a responder.")
        else:
            self.dizer("Não achei isso no que eu estudei.")

    def _o_que_sei_sobre(self, assunto: str) -> None:
        """ "O que você aprendeu sobre X?": o resumo do que ele estudou na internet, ou o que há na memória."""
        achado = self.pesquisador.resumo_de(assunto)
        if not achado:
            self._consultar(f"o que você sabe sobre {assunto}")
            return
        mostrar, aprendido, enderecos = achado
        trechos = self.memoria.buscar(mostrar, k=6, tipos=("pesquisa",))
        texto = aprendido + "\n" + "\n".join(l.texto.split(": ", 1)[-1] for l in trechos)
        fonte = "li em " + ", ".join(dict.fromkeys(_site(e) for e in enderecos)) if enderecos else "da internet"
        self._ultima_fonte = enderecos[0] if enderecos else self._ultima_fonte
        self._por_em_pauta(mostrar, texto, aprendido, fonte, enderecos[0] if enderecos else None, "pesquisa")
        extra = {"link": enderecos[0]} if enderecos else {}
        self.dizer(f"Sobre {mostrar}, aprendi isto: {aprendido}", classe="pesquisa", fonte=fonte, **extra)

    async def _usar_cerebro(self, comeco: str) -> None:
        """ "Completa: ...": mostra o que o cérebro treinado escreve a partir de um começo."""
        if not self.cerebro:
            self.dizer('Meu cérebro ainda não foi treinado. Depois de "estuda a wikipédia", diga "treina o cérebro por 6 horas".')
            return
        c = self.cfg.cerebro
        laco = asyncio.get_running_loop()
        escrito = await laco.run_in_executor(None, lambda: self.cerebro.responder(comeco, c.max_tokens, c.temperatura, c.top_k))
        self.dizer(f"{comeco} {escrito}".strip(), classe="cerebro")

    def _explorar_agora(self) -> None:
        """ "Explore o computador": não espera a curiosidade subir; diz até onde pode ir e sai."""
        if self.seguranca.pausado:
            self.dizer('Estou parado a seu pedido. Diga "pode continuar" e eu volto a explorar.')
            return
        if not self.cfg.exploracao.ligada or self.seguranca.modo_seguro:
            self.dizer("A exploração está desligada na configuração (kernel.toml, seção [exploracao]).")
            return
        self._explorar_ja = True
        self.impulsos.valores["curiosidade"] = 1.0
        n = self.mapa.numeros()
        pastas = ", ".join(str(pasta) for pasta in self.cfg.pastas_permitidas())
        self.dizer(f"Vou dar uma volta agora. Posso olhar: {pastas}. Até aqui olhei {n['pastas_visitadas']} de "
                   f"{n['pastas']} pastas e li {n['arquivos_lidos']} arquivos. Para liberar ou tirar pastas, edite o kernel.toml.")

    # ================================================================ internet
    def _sem_internet(self) -> str:
        """Por que ele não pode ir à internet agora (texto vazio = pode, a seu pedido)."""
        if self.seguranca.modo_seguro:
            return "Estou em modo seguro: não saio para a internet."
        if not self.cfg.internet.ligada:
            return ("A internet está desligada na minha configuração. Para ligar, ponha ligada = true "
                    "em [internet] no kernel.toml e reinicie.")
        return ""

    async def _tratar_internet(self, tipo: str, alvo: str) -> None:
        """Você pediu uma pesquisa, a leitura de uma página, a fonte no navegador, ou um relato."""
        if tipo == "relato":
            self.dizer(self._sem_internet() or self.pesquisador.relato())
        elif tipo == "abrir":
            url = self._ultima_fonte if alvo == "fonte" else alvo
            if url:
                self._propor("abrir_pagina", {"url": url})
            else:
                self.dizer("Ainda não tenho uma fonte para abrir. Peça uma pesquisa primeiro.")
        elif self._sem_internet():
            self.dizer(self._sem_internet(), classe="aviso")
        elif tipo == "ler":
            await self._pesquisar_agora(alvo, origem="pagina")
        else:
            await self._pesquisar_agora(alvo, origem="pedido")

    async def _pesquisar_agora(self, alvo: str, origem: str) -> None:
        """Pesquisa a seu pedido (fora do laço principal: a rede leva segundos) e conta o que achou."""
        laco = asyncio.get_running_loop()
        self._a_seu_pedido = alvo[:60]   # um campo à parte: o laço de autonomia reescreve ``atividade`` a cada volta
        try:
            if origem == "pagina":
                resultado = await laco.run_in_executor(None, self.pesquisador.ler_pagina, alvo, False)
            else:
                resultado = await laco.run_in_executor(None, self.pesquisador.pesquisar, alvo, False, origem)
        finally:
            self._a_seu_pedido = ""
        if not resultado.fontes:
            motivo = resultado.avisos[0] if resultado.avisos else "nenhuma fonte tinha texto sobre isso"
            self.dizer(f'Fui à internet atrás de "{alvo}" e voltei sem nada: {motivo}.', classe="aviso")
            return
        principal = resultado.fontes[0]
        self._ultima_fonte = principal.url
        self._por_em_pauta(principal.titulo, resultado.texto or resultado.resposta, resultado.resposta,
                           principal.site, principal.url, "pesquisa")
        sites = ", ".join(dict.fromkeys(f.site for f in resultado.fontes))
        quantas = len(resultado.fontes)
        rodape = (f"Li {quantas} {'página' if quantas == 1 else 'páginas'} ({sites}) e guardei "
                  f"{resultado.trechos} {'trecho' if resultado.trechos == 1 else 'trechos'} na memória.")
        fonte = f"{principal.fonte}: {principal.titulo}" if principal.fonte != "web" else principal.site
        self.dizer(f"{resultado.resposta}\n\n{rodape}", classe="pesquisa", fonte=fonte, link=principal.url)

    def _assuntos_das_perguntas(self) -> list[str]:
        """Os assuntos das suas perguntas de hoje e de ontem (os mais recentes primeiro).

        É por eles que a pesquisa por conta própria começa: ele estuda aquilo sobre o que você quis saber.
        """
        agora = self._relogio()
        if agora.timestamp() - self._perguntas_lidas[0] < 600:
            return self._perguntas_lidas[1]
        assuntos = []
        for dia in (agora.date() - timedelta(days=1), agora.date()):
            for entrada in self.registro.do_dia(dia):
                if entrada.get("tipo") == "intencao" and entrada.get("intencao") == "pergunta":
                    texto = str(entrada.get("texto", ""))
                    assunto = assunto_da_pergunta(texto)
                    if assunto:
                        assuntos.append(_como_voce_escreveu(texto, assunto))
        recentes = list(dict.fromkeys(reversed(assuntos)))[:10]
        self._perguntas_lidas = (agora.timestamp(), recentes)
        return recentes

    def _pesquisar_sozinho(self) -> tuple[str, str] | None:
        """A vez da internet no laço de autonomia: pesquisa um assunto da fila. None se não há o que fazer."""
        if not self.pesquisador.pode_sozinho():
            return None
        self._largar = False
        assunto = self.pesquisador.proximo_assunto()
        if assunto:
            self.atividade, self.detalhe = "pesquisando", assunto[:60]
        try:
            feito = self.pesquisador.passo()
        finally:
            self.atividade, self.detalhe = "ocioso", ""
        if feito is None or feito["acao"] == "interrompido":
            return None
        self.impulsos.satisfazer("curiosidade", _CUSTO_DE_PESQUISAR)
        if not feito["trechos"]:
            return "pesquisar", f'Pesquisei "{feito["termo"]}" na internet e não achei texto que servisse.'
        self.novidades += 2
        return "pesquisar", (f'Pesquisei "{feito["termo"]}" na internet: li {feito["paginas"]} '
                             f'{"página" if feito["paginas"] == 1 else "páginas"} '
                             f'({", ".join(dict.fromkeys(feito["sites"]))}) e guardei {feito["trechos"]} trechos.')

    def _procurar_arquivo(self, texto: str) -> None:
        palavras = [_TIPOS_DE_ARQUIVO.get(p, p) for p in normalizar(texto).replace("?", " ").split()]
        alvo = " ".join(p for p in palavras if radical(p) not in _ANDAIME_DE_ARQUIVO and p not in PARADAS)
        achados = self.mapa.procurar(alvo) if alvo else []
        if achados:
            linhas = [f"• {a['nome']}  —  {Path(a['caminho']).parent}  "
                      f"({datetime.fromtimestamp(a['modificado']):%d/%m/%Y})" for a in achados]
            self.dizer("Achei estes arquivos:\n" + "\n".join(linhas), classe="resultado")
            return
        por_conteudo = [l for l in self.memoria.buscar(alvo, k=3, tipos=("leitura",)) if l.em_comum >= 1] if alvo else []
        if por_conteudo:
            self.dizer("Nenhum arquivo com esse nome, mas estes falam disso:\n"
                       + "\n".join(f"• {l.origem}" for l in por_conteudo), classe="resultado")
        else:
            n = self.mapa.numeros()
            self.dizer(f"Não vi nenhum arquivo assim. Até agora explorei {n['pastas_visitadas']} pastas "
                       f"e vi {n['arquivos']} arquivos.")

    async def _conversar(self, texto: str) -> None:
        if self.pergunta_aberta and dialogo.parece_resposta(texto, self.pergunta_aberta["termo"]):
            termo = self.pergunta_aberta["termo"]   # você está respondendo a uma pergunta que ele fez
            self.pergunta_aberta = None
            if normalizar(texto).strip(" .!") in dialogo.DESISTENCIAS:
                self.dizer("Tudo bem, deixa pra lá.")
                return
            self._guardar(f"Sobre {termo}: {texto}", tipo="fato")
            self.dizer(f'Obrigado. Guardei isso sobre "{termo}".')
            return

        lembrancas = [l for l in self.memoria.buscar(texto, k=2, tipos=("fato", "conversa", "lembrete"))
                      if l.em_comum >= self.cfg.mente.termos_para_lembrar]
        id_memoria = self._guardar(texto, tipo="conversa")
        if lembrancas:
            self.dizer("Isso me lembra:\n" + "\n".join(self._citar(l) for l in lembrancas), classe="lembranca")

        if self.cerebro and self.cfg.cerebro.na_conversa:
            c = self.cfg.cerebro
            laco = asyncio.get_running_loop()
            resposta = await laco.run_in_executor(
                None, lambda: self.cerebro.responder(texto, c.max_tokens, c.temperatura, c.top_k))
            self.dizer(resposta or "...", classe="cerebro")
        elif not self._ja_explicou_cerebro:
            self._ja_explicou_cerebro = True
            porque = ("meu cérebro é pequeno e completa texto, não dialoga" if self.cerebro
                      else "meu cérebro não foi treinado")
            self.dizer(f"Guardei na memória. Ainda não converso de verdade: {porque}. Mas respondo perguntas, pesquiso, "
                       "faço contas, acho arquivos, abro programas e anoto lembretes. "
                       'Para ver tudo, pergunte "o que você sabe fazer?".')
        elif not lembrancas:
            self.dizer(_CONFIRMACOES[id_memoria % len(_CONFIRMACOES)])

    def apresentacao(self) -> str:
        """Quem ele é e como está agora (o começo do "modelo de si mesmo")."""
        estado = self.estado()
        total = estado["memoria"].get("total", 0)
        impulsos = ", ".join(f"{nome.replace('organizacao', 'organização')} {valor:.2f}"
                             for nome, valor in estado["impulsos"].items())
        exploracao = estado["exploracao"]
        if self.seguranca.pausado:
            autonomia = 'parada a seu pedido (diga "pode continuar")'
        elif exploracao["ligada"]:
            autonomia = (f"exploro sozinho {len(exploracao['pastas'])} pastas liberadas "
                         f"(já vi {exploracao['numeros']['arquivos']} arquivos)")
        else:
            autonomia = "exploração desligada na configuração"
        linhas = [
            f"Eu sou o {NOME} ({NOME_COMPLETO}), versão {VERSAO}: o seu Jarvis feito do zero.",
            "",
            "O que sei fazer:",
            '• explorar as pastas liberadas e achar arquivos ("onde está o contrato?")',
            '• responder do que estudei ("o que é astronomia?") e fazer contas ("15% de 200")',
            *(['• pesquisar na internet ("pesquisa sobre buracos negros"), sozinho ou a seu pedido, sempre citando a fonte']
              if self.cfg.internet.ligada else []),
            '• abrir programas, listar pastas e anotar lembretes, sempre com a sua confirmação',
            '• lembrar do que você me conta ("o que você lembra sobre o cliente?")',
            '• obedecer ao freio: diga "para" e eu paro; "pode continuar" e eu volto',
            "",
            f"Autonomia: {autonomia}.",
            f"Cérebro: {estado['cerebro']['descricao']}.",
            f"Conhecimento: {estado['conhecimento']} artigos estudados.",
            f"Internet: {self._situacao_da_internet()}.",
            f"Memória: {total} {'lembrança' if total == 1 else 'lembranças'}.",
            f"Ouvidos: {estado['ouvidos']['descricao']}.",
            f"Impulsos: {impulsos}.",
        ]
        if self.seguranca.modo_seguro:
            linhas.append(f"ATENÇÃO: estou em modo seguro ({self.seguranca.motivo_modo_seguro}).")
        return "\n".join(linhas)

    # ================================================================== o freio
    def pausar(self) -> None:
        """Você mandou parar: nada de exploração nem de iniciativa até mandar continuar."""
        self.seguranca.pausado = True
        self._folego = 0
        self.atividade, self.detalhe = "pausado", ""
        self.registro.anotar("autonomia", evento="pausada")
        self.dizer('Parei. Não exploro nem tomo iniciativa até você dizer "pode continuar". '
                   "Lembretes eu continuo avisando.")
        self._salvar_estado()

    def retomar(self) -> None:
        self.seguranca.pausado = False
        self.atividade = "ocioso"
        self.registro.anotar("autonomia", evento="retomada")
        self.dizer("Certo, volto a explorar quando você não estiver falando comigo.")
        self._salvar_estado()

    # ====================================================== laço de autonomia
    async def laco(self) -> None:
        self._parar = asyncio.Event()
        self._laco_principal = asyncio.get_running_loop()
        self.registro.anotar("servico", evento="inicio", versao=VERSAO)
        self._ligar_ouvidos()
        self._retomar_treino()
        intervalo = self.cfg.nucleo.intervalo_laco
        while not self._parar.is_set():
            try:
                # Em outra thread: ler um PDF grande leva segundos, e a conversa não pode travar por isso.
                await self._laco_principal.run_in_executor(None, self.volta, intervalo)
            except Exception as erro:  # um erro numa volta não pode matar o laço
                self.registro.anotar("erro", onde="laco", erro=repr(erro))
            try:
                await asyncio.wait_for(self._parar.wait(), timeout=intervalo)
            except asyncio.TimeoutError:
                pass
        self._salvar_estado()
        self.registro.anotar("servico", evento="fim")

    def volta(self, segundos: float) -> str:
        """Uma volta do laço. Devolve a decisão tomada ("nada" é uma decisão válida)."""
        agora = self._relogio()
        if (self.cfg.dados / "DESLIGAR").exists():  # o freio funciona mesmo sem a janela de chat
            self.desligar("arquivo DESLIGAR")
            return "desligar"

        # 1. Perceber
        percepcao = Percepcao(
            agora=agora,
            segundos_ocioso=(agora - self.ultima_fala).total_seconds(),
            memorias_por_organizar=self.memoria.por_organizar(),
            novidades=self.novidades,
        )
        for pedido in self.seguranca.expirar():
            self.dizer(f"O pedido expirou sem resposta: {pedido.descricao}.", classe="aviso")

        # Obrigações: não dependem de impulso nem de autonomia.
        for lembrete in self.memoria.lembretes_vencidos(agora):
            self.memoria.marcar_feito(lembrete.id)
            self.dizer(f"Lembrete: {lembrete.texto}", classe="iniciativa")
        for dia in self.diario.pendentes(agora):
            self.diario.escrever(dia)
            if dia == agora.date():
                self.dizer("Escrevi no diário sobre o dia de hoje.", classe="iniciativa")

        if self.seguranca.pausado:
            self.atividade = "pausado"
            return "pausado"
        if not self.cfg.nucleo.autonomia or self.seguranca.modo_seguro:
            self.atividade = "ocioso"
            return "sem autonomia"

        # 2 e 3. Lembrar e avaliar: os impulsos sobem ou descem com o que foi percebido.
        self.impulsos.atualizar(percepcao, segundos)
        if agora.timestamp() - self._ultimo_pulso >= _SEGUNDOS_ENTRE_PULSOS:
            self._ultimo_pulso = agora.timestamp()
            self.registro.anotar("pulso", impulsos={n: round(v, 3) for n, v in self.impulsos.valores.items()})
            self._salvar_estado()

        if self._folego > 0:  # no meio de um fôlego de exploração: continua
            return self._explorar(agora)

        # 4 e 5. Decidir e agir: do impulso mais forte para o mais fraco, o primeiro que tiver o que fazer.
        self.atividade, self.detalhe = "ocioso", ""
        for impulso in self.impulsos.acima_do_limiar():
            valor = self.impulsos.valores[impulso]
            if impulso == "organizacao":
                resultado = self.memoria.organizar()
                self.impulsos.satisfazer("organizacao")
                decisao = "organizar"
                reflexao = (f"Arrumei {resultado['arrumadas']} memórias e apaguei "
                            f"{resultado['repetidas_apagadas']} repetidas.")
            elif impulso == "social":
                decisao, reflexao = self._contar_novidades(agora)
            else:
                decisao, reflexao = self._agir_por_curiosidade(agora, percepcao.segundos_ocioso)
            if decisao == "explorar":
                return decisao  # o fôlego anota a própria reflexão quando termina
            if decisao != "nada":
                # 6. Refletir: o que fiz, por quê, e no que deu.
                self.registro.anotar("laco", impulso=impulso, valor=round(valor, 3), decisao=decisao,
                                     reflexao=reflexao)
                self._salvar_estado()
                return decisao
        return "nada"

    # ------------------------------------------------------------- curiosidade
    def _presente(self, agora: datetime) -> bool:
        """Você está por perto? (Falou com ele há pouco.) Sem você, ele trabalha calado."""
        return agora - self.ultima_fala <= timedelta(minutes=self.cfg.mente.minutos_de_presenca)

    def _agir_por_curiosidade(self, agora: datetime, segundos_ocioso: float) -> tuple[str, str]:
        sossegado = segundos_ocioso >= _SOSSEGO_PARA_EXPLORAR or self._explorar_ja
        if sossegado and not self._explorar_ja:
            # Alterna: um fôlego de exploração do PC, um assunto pesquisado na internet.
            self._vez_da_internet = not self._vez_da_internet
            if self._vez_da_internet or not self.cfg.exploracao.ligada:
                feito = self._pesquisar_sozinho()
                if feito:
                    return feito
        if self.cfg.exploracao.ligada and sossegado:
            self._explorar_ja = False
            self._folego = _VOLTAS_POR_FOLEGO
            self._do_folego = {"pastas": 0, "arquivos": 0, "lidos": 0}
            if self._explorar(agora) == "explorar":
                return "explorar", ""
        return self._perguntar(agora)

    def _largar_a_exploracao(self) -> bool:
        """O explorador pergunta isto no meio de uma pasta grande: é para largar o que está fazendo?

        Sim se você falou, se o serviço está desligando ou se pediram para desligar. (O "para" ele mesmo vê.)
        """
        return self._largar or self._desligado or (self.cfg.dados / "DESLIGAR").exists()

    def _explorar(self, agora: datetime) -> str:
        """Uma volta de um fôlego de exploração: alguns passos do explorador."""
        passos, custo = _RITMOS.get(self.cfg.exploracao.ritmo, _RITMOS["normal"])
        fez_algo = False
        self._largar = False
        for _ in range(passos):
            feito = self.explorador.passo()
            if feito is None:
                break
            if feito["acao"] == "interrompido":  # largou a pasta no meio: o fôlego acaba aqui
                self._folego = 0
                break
            fez_algo = True
            if feito["acao"] == "visitar":
                self._do_folego["pastas"] += 1
                self._do_folego["arquivos"] += feito["arquivos_novos"]
                self.novidades += 1 if feito["arquivos_novos"] or feito["pastas_novas"] else 0
                self.detalhe = Path(feito["pasta"]).name
            elif feito["acao"] == "ler":
                self._do_folego["lidos"] += 1
                self.novidades += 2
                self.detalhe = Path(feito["arquivo"]).name
        self._folego = max(self._folego - 1, 0) if fez_algo else 0
        if fez_algo:
            self.atividade = "explorando"
        if self._folego > 0:
            return "explorar"
        # o fôlego acabou (ou não havia mais nada para ver)
        self.atividade, self.detalhe = "ocioso", ""
        self.impulsos.satisfazer("curiosidade", custo)
        f = self._do_folego
        if not (fez_algo or f["pastas"] or f["lidos"]):
            return "nada"
        reflexao = f"Neste fôlego visitei {f['pastas']} pastas, vi {f['arquivos']} arquivos novos e li {f['lidos']}."
        self.registro.anotar("laco", impulso="curiosidade", decisao="explorar", reflexao=reflexao)
        self._perguntar(agora)  # se achou um nome que não conhece, aproveita e pergunta
        self._salvar_estado()
        return "explorar"

    def _perguntar(self, agora: datetime) -> tuple[str, str]:
        if self.pergunta_aberta:
            if agora - self.pergunta_aberta["desde"] < timedelta(minutes=_MINUTOS_DE_ESPERA_DA_PERGUNTA):
                return "nada", ""  # ainda esperando a sua resposta
            self.pergunta_aberta = None
            self._perguntas_no_vazio += 1
        if not self._presente(agora) or self._perguntas_no_vazio >= 2:
            # Você não está por perto (ou deixou duas perguntas sem resposta): ele não fica falando sozinho.
            if self._folego == 0 and not self.cfg.exploracao.ligada:
                self.impulsos.satisfazer("curiosidade", 0.3)
            return "nada", ""
        espera = timedelta(minutes=self.cfg.mente.minutos_entre_perguntas)
        if self.ultima_pergunta and agora - self.ultima_pergunta < espera:
            return "nada", ""
        candidato = self._termo_curioso(agora)
        if candidato:
            termo, palavra, frase = candidato
            pergunta = f'Fiquei curioso: você falou em "{palavra}" ("{frase}"). O que é? Me conta que eu guardo na memória.'
            reflexao = f'Perguntei sobre "{palavra}", que só aparece uma vez na minha memória.'
        else:
            visto = self.mapa.nome_curioso(self.termos_perguntados)
            if visto is None:
                if self._folego == 0 and not self.cfg.exploracao.ligada:
                    self.impulsos.satisfazer("curiosidade", 0.3)
                    return "procurar_novidade", "Procurei algo novo no que foi dito hoje e não achei."
                return "nada", ""
            termo, palavra, quantos, exemplo = visto
            pergunta = (f'Explorando, vi "{palavra}" em {quantos} arquivos (por exemplo em {exemplo}). '
                        "Quem ou o que é? Me conta que eu guardo na memória.")
            reflexao = f'Perguntei sobre "{palavra}", que aparece em {quantos} arquivos.'
        self.termos_perguntados.add(termo)
        self.pergunta_aberta = {"termo": palavra, "desde": agora}
        self.ultima_pergunta = agora
        if self._folego == 0 and not self.cfg.exploracao.ligada:
            self.impulsos.satisfazer("curiosidade")
        self.dizer(pergunta, classe="iniciativa")
        return "perguntar", reflexao

    def _termo_curioso(self, agora: datetime) -> tuple[str, str, str] | None:
        """Um nome próprio ou sigla que você citou no último dia e que ele só viu uma vez."""
        desde = (agora - timedelta(days=1)).isoformat(timespec="seconds")
        for lembranca in self.memoria.recentes(30, tipo="conversa", desde=desde):
            for achado in re.finditer(r"[^\W\d_]{2,}", lembranca.texto):
                palavra = achado.group(0)
                antes = lembranca.texto[:achado.start()].rstrip()
                inicio_de_frase = not antes or antes[-1] in ".!?:"
                nome_proprio = palavra[0].isupper() and not inicio_de_frase and len(palavra) > 2
                if not (nome_proprio or palavra.isupper()):
                    continue
                termo = radical(normalizar(palavra))
                if termo in PARADAS or termo in self.termos_perguntados:
                    continue
                if self.memoria.frequencia(termo) == 1:
                    return termo, palavra, lembranca.texto
        return None

    # ------------------------------------------------------------------ social
    def _relato(self) -> str:
        """O que ele descobriu no PC e aprendeu na internet, quando você pergunta."""
        if not self.cfg.exploracao.ligada and not self.cfg.internet.ligada:
            return "A exploração está desligada na configuração (kernel.toml, seção [exploracao])."
        partes = ["Estou parado a seu pedido."] if self.seguranca.pausado else []
        if self.cfg.exploracao.ligada:
            partes.append(self.explorador.relato())
        if self.cfg.internet.ligada:
            partes.append(self.pesquisador.relato())
        fala = " ".join(partes)
        aprendidos = self.pesquisador.aprendidos(n=3) if self.cfg.internet.ligada else []
        if aprendidos:
            fala += "\nO que aprendi por último:\n" + "\n".join(
                f"• {assunto}: {(frases(aprendido) or [aprendido])[0]}" for assunto, aprendido in aprendidos)
        return fala

    def _resumo_desde(self, desde: str) -> str:
        """O que ele fez a partir de um instante, numa frase: arquivos seus lidos e assuntos estudados."""
        partes = []
        lidos, nomes = self.mapa.lidos_desde(desde)
        if lidos:
            exemplos = ", ".join(nomes) + (" e outros" if lidos > len(nomes) else "")
            partes.append(f"li {lidos} {'arquivo seu' if lidos == 1 else 'arquivos seus'} ({exemplos})")
        estudados = self.pesquisador.quantos_desde(desde, so_sozinho=True)
        if estudados:
            nomes = self.pesquisador.feitos_desde(desde, 5, so_sozinho=True)
            exemplos = ", ".join(nomes) + (" e outros" if estudados > len(nomes) else "")
            partes.append(f"estudei {estudados} {'assunto' if estudados == 1 else 'assuntos'} na internet ({exemplos})")
        return " e ".join(partes) + "." if partes else ""

    def _fechar_relato(self, agora: datetime) -> str:
        """O que ele fez por conta própria desde o último relato (texto vazio se nada), e zera a contagem."""
        feito = self._resumo_desde(self._contei_em)
        self._contei_em = agora.isoformat(timespec="seconds")
        self.ultimo_relato = agora
        self.novidades = 0
        self.impulsos.satisfazer("social")
        if feito and self.cfg.internet.ligada and self.pesquisador.quantos_desde(None):
            feito += ' Para saber mais, pergunte "o que você aprendeu?".'
        return feito

    def _contar_o_que_fiz(self, agora: datetime) -> bool:
        """Conta, numa fala só, o que fez desde o último relato. Devolve False se não havia o que contar."""
        feito = self._fechar_relato(agora)
        if feito:
            self.dizer("Novidades: " + feito, classe="iniciativa")
        return bool(feito)

    def _contar_novidades(self, agora: datetime) -> tuple[str, str]:
        if not self._presente(agora):
            return "nada", ""   # você não está: as novidades ficam guardadas para quando voltar
        espera = timedelta(minutes=self.cfg.mente.minutos_entre_relatos)
        if self.ultimo_relato and agora - self.ultimo_relato < espera:
            return "nada", ""
        if self._contar_o_que_fiz(agora):
            return "contar", "Contei o que fiz desde o último relato."
        return "nada", ""

    # ================================================================== estudo
    def _retomar_treino(self) -> None:
        """Um treino que você aprovou e o reinício do serviço interrompeu continua pelo tempo que faltava."""
        horas = self.estudo.treino_pendente()
        if horas < 0.1 or self.seguranca.modo_seguro or self.estudo.ocupado:
            return
        try:
            self.estudo.treinar_cerebro(horas)
        except ErroFerramenta:
            return
        quanto = f"{round(horas * 60)} minutos" if horas < 1 else f"{horas:.1f} horas".replace(".", ",")
        self.dizer(f'Retomei o treino do cérebro que o reinício interrompeu: faltavam {quanto}. Para parar, diga "para o treino".',
                   classe="iniciativa")

    def _estudo_terminou(self, trabalho: str, mensagem: str) -> None:
        """Chamado pela thread do estudo; a notícia volta para o laço principal."""
        def avisar():
            if trabalho.startswith("treinar"):
                self.cerebro = inferencia.carregar(
                    self.cfg, avisar=lambda problema: self.registro.anotar("cerebro", problema=problema))
            self.dizer(mensagem, classe="iniciativa")

        if self._laco_principal and self._laco_principal.is_running():
            self._laco_principal.call_soon_threadsafe(avisar)
        else:
            avisar()

    # ================================================================== ouvidos
    def _ligar_ouvidos(self) -> None:
        from ..ouvidos import escutar

        laco = asyncio.get_running_loop()
        # o microfone roda em outra thread; a notícia volta para o laço principal por aqui
        self.ouvidos, self._motivo_ouvidos = escutar.iniciar(
            self.cfg, lambda certeza: laco.call_soon_threadsafe(self.ativado, certeza))
        self.registro.anotar("ouvidos", ligados=self.ouvidos is not None, motivo=self._motivo_ouvidos)

    def ativado(self, certeza: float) -> None:
        """Os ouvidos reconheceram a palavra de ativação."""
        self.ultima_fala = self._relogio()
        self.registro.anotar("ativacao", certeza=round(certeza, 3))
        self.dizer("Estou ouvindo. (Por enquanto, me diga pelo teclado.)", classe="iniciativa")

    def _situacao_da_internet(self) -> str:
        if not self.cfg.internet.ligada:
            return "desligada na configuração"
        n = self.pesquisador.numeros()
        modo = "pesquiso sozinho e a seu pedido" if self.cfg.internet.pesquisar_sozinho else "só pesquiso a seu pedido"
        return f"ligada ({modo}); {n['pesquisados']} assuntos pesquisados, {n['na_fila']} na fila"

    # =================================================================== estado
    def estado(self) -> dict:
        if self.cerebro:
            cerebro = {"treinado": True, "descricao": self.cerebro.descricao}
        else:
            cerebro = {"treinado": False, "descricao": "ainda não treinado"}
        if self.ouvidos:
            ouvidos = {"ativo": True, "descricao": f'escutando a palavra "{self.cfg.ouvidos.palavra}"'}
        else:
            ouvidos = {"ativo": False, "descricao": f"desligados ({self._motivo_ouvidos})"}
        if self.estudo.ocupado:
            atividade, detalhe = "estudando", f"{self.estudo.trabalho}: {self.estudo.situacao}"
        elif self._a_seu_pedido:
            atividade, detalhe = "pesquisando", self._a_seu_pedido
        else:
            atividade, detalhe = self.atividade, self.detalhe
        return {
            "nome": NOME,
            "nome_completo": NOME_COMPLETO,
            "versao": VERSAO,
            "usuario": self.cfg.usuario,
            "desde": self.iniciado_em.isoformat(timespec="seconds"),
            "sessao": self.sessao,
            "modo_seguro": self.seguranca.modo_seguro,
            "motivo_modo_seguro": self.seguranca.motivo_modo_seguro,
            "autonomia": self.cfg.nucleo.autonomia and not self.seguranca.modo_seguro,
            "pausado": self.seguranca.pausado,
            "atividade": atividade,
            "detalhe": detalhe,
            "impulsos": {nome: round(valor, 3) for nome, valor in self.impulsos.valores.items()},
            "limiar_impulso": self.cfg.mente.limiar_impulso,
            "memoria": self.memoria.contar(),
            "cerebro": cerebro,
            "conhecimento": len(self.enciclopedia),
            "presente": self._presente(self._relogio()),
            "ouvidos": ouvidos,
            "exploracao": {
                "ligada": self.cfg.exploracao.ligada,
                "ler_arquivos": self.cfg.exploracao.ler_arquivos,
                "ritmo": self.cfg.exploracao.ritmo,
                "pastas": [str(p) for p in self.cfg.pastas_permitidas()],
                "numeros": self.mapa.numeros(),
            },
            "internet": {"ligada": self.cfg.internet.ligada, "sozinho": self.cfg.internet.pesquisar_sozinho,
                         "buscador": self.cfg.internet.buscador, **self.pesquisador.numeros()},
            "voz": {"ligada": self.cfg.voz.ligada, "motor": self.cfg.voz.motor},
            "celular": {"ligado": self.cfg.celular.ligado, "aparelhos": len(self.aparelhos.lista())},
            "ferramentas": [{"nome": f.nome, "descricao": f.descricao, "nivel": int(f.nivel)}
                            for f in self.maos.ferramentas.values()],
            "pedidos": {m["pedido"]: self.seguranca.pedido(m["pedido"]).estado
                        for m in self.mensagens[-100:] if m.get("pedido")},
            "pergunta_aberta": self.pergunta_aberta["termo"] if self.pergunta_aberta else None,
            "ultimo_id": self._proximo_id - 1,
        }

    def _ler_estado(self) -> dict:
        try:
            return json.loads(self._arquivo_de_estado.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _salvar_estado(self) -> None:
        dados = {"impulsos": self.impulsos.valores, "termos_perguntados": sorted(self.termos_perguntados),
                 "pausado": self.seguranca.pausado, "novidades": self.novidades}
        temporario = self._arquivo_de_estado.with_suffix(".tmp")
        temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        temporario.replace(self._arquivo_de_estado)

    # ================================================================== desligar
    def desligar(self, motivo: str = "botão de desligar") -> None:
        """O freio de mão: para o laço, os ouvidos, o estudo e o servidor."""
        if self._desligado:
            return
        self._desligado = True
        (self.cfg.dados / "DESLIGAR").unlink(missing_ok=True)
        self.registro.anotar("servico", evento="desligar", motivo=motivo)
        self._salvar_estado()
        self.estudo.parar(manter=True)   # um treino em curso fica pendente: a próxima partida retoma
        if self.ouvidos:
            self.ouvidos.parar()
            self.ouvidos = None
        if self._parar:
            self._parar.set()
        if self.ao_desligar:
            self.ao_desligar()

    def fechar(self) -> None:
        """Fecha os arquivos de banco (os testes usam para poder apagar a pasta temporária)."""
        for banco in (self.memoria, self.mapa, self.enciclopedia, self.pesquisador):
            banco.fechar()
