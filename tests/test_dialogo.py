"""A conversa do dia a dia: as frases que antes viravam "Guardei." e agora têm resposta, a presença
(ele não fala sozinho quando você não está), o "fale mais", o modelo de si e o resumo por extração.

Várias frases daqui saíram do registro de uso de verdade: foi lendo o que não funcionou que estas
regras nasceram.
"""
import asyncio

import pytest

from conftest import falas
from kernel.conhecimento.resumo import frases, resumir
from kernel.nucleo import Kernel, dialogo, reflexos, sobre_si

ENCICLOPEDIA = """Astronomia

Astronomia é a ciência natural que estuda os corpos celestes e os fenômenos do cosmo. Ela usa a matemática e a física para explicar a origem e a evolução dos astros. Os astrônomos observam planetas, estrelas e galáxias com telescópios. A astronomia é uma das ciências mais antigas da humanidade. Povos antigos usavam o céu para marcar as estações do ano.
<|fim|>
"""


def dizer(nucleo, texto):
    asyncio.run(nucleo.receber(texto))


def intencoes(nucleo):
    return [e["intencao"] for e in nucleo.registro.ultimos(50) if e["tipo"] == "intencao"]


@pytest.fixture
def estudado(kernel, tmp_path):
    corpus = tmp_path / "corpus.txt"
    corpus.write_text(ENCICLOPEDIA, encoding="utf-8")
    kernel.enciclopedia.construir(corpus)
    return kernel


# ================================================================= as regras
def test_regras_que_leem_o_jeito_de_falar():
    assert dialogo.pede_mais("fale mais") == (3, "") and dialogo.pede_mais("Fale algo mais longo") == (6, "")
    assert dialogo.pede_mais("fale mais sobre buracos negros") == (3, "buracos negros")
    assert dialogo.pede_mais("explica melhor") and dialogo.pede_mais("e o que mais?") and dialogo.pede_mais("continua")
    assert dialogo.pede_mais("conta uma piada") is None and dialogo.pede_mais("hoje foi um bom dia") is None

    for frase in ("Explore o computador", "explora agora", "vasculha as pastas", "explorar"):
        assert dialogo.explorar_agora(frase), frase
    assert not dialogo.explorar_agora("olha isso") and not dialogo.explorar_agora("explora a pasta downloads")

    for frase in ("Qual a temperatura atual em Campinas", "como faço um bolo", "você tem sentimentos?", "isso funciona?"):
        assert dialogo.eh_pergunta(frase), frase
    assert not dialogo.eh_pergunta("hoje foi um bom dia") and not dialogo.eh_pergunta("Teste sua voz")

    assert dialogo.para_o_cerebro("completa: Era uma vez") == "Era uma vez"
    assert dialogo.para_o_cerebro("Kernel, continue a frase: O Brasil") == "O Brasil"
    assert dialogo.para_o_cerebro("o que seu cérebro diz sobre o brasil") == "O brasil é"
    assert dialogo.para_o_cerebro("completa o relatório para mim") is None
    assert dialogo.aprendeu_sobre("o que você aprendeu sobre redes neurais?") == "redes neurais"
    assert dialogo.aprendeu_sobre("o que você aprendeu hoje?") is None


def test_cumprimentos_do_jeito_que_as_pessoas_escrevem():
    for frase in ("Oiii", "Hello", "olaaa", "hi kernel", "oie"):
        assert reflexos.saudacao(frase, "Henrique", 0) == "Olá, Henrique.", frase
    assert reflexos.saudacao("bom diaaa", "Henrique", 0) == "Bom dia, Henrique."
    assert reflexos.saudacao("tudo bem?", "Henrique", 0).startswith("Tudo certo por aqui")
    assert reflexos.saudacao("fale mais", "Henrique", 0) is None


def test_erro_de_dedo_num_comando_de_estudo():
    assert reflexos.estudo("como está o etudo") == ("andamento", {})
    assert reflexos.estudo("como esta o treinameto?") == ("andamento", {})
    assert reflexos.estudo("como está o estado do pc") is None        # "estado" não é "estudo"


def test_de_que_parte_dele_a_frase_fala():
    casos = {"Fale mais das suas funções": "funcoes", "Quais suas caracteristicas?": "funcoes",
             "quais pastas e diretorios voce consegue explorar?": "pastas", "Quais pastas você tem acesso?": "pastas",
             "Como está seu cérebro agora?": "cerebro", "Me fale sobre voce": "quem", "Teste sua voz": "voz",
             "Você sabe que outra inteligência artificial faz ajustes em você?": "origem", "quem te criou?": "origem",
             "você tem sentimentos?": "consciencia", "qual o seu nome?": "nome", "você pesquisa na internet?": "internet"}
    for frase, esperado in casos.items():
        assert sobre_si.e_sobre_voce(frase) and sobre_si.topico(frase) == esperado, frase
    assert not sobre_si.e_sobre_voce("hoje foi um bom dia") and sobre_si.topico("o servidor caiu") is None


# ============================================================ a conversa em si
def test_frases_que_antes_viravam_guardei(kernel):
    """Do registro de uso: nenhuma destas tinha resposta; todas iam para a memória como se fossem um recado."""
    dizer(kernel, "Fale mais das suas funções")
    assert "O que eu sei fazer" in falas(kernel)[-1] and "lembretes" in falas(kernel)[-1]
    dizer(kernel, "Quais suas caracteristicas?")
    assert "O que eu sei fazer" in falas(kernel)[-1]
    dizer(kernel, "Me fale sobre voce")
    assert "K.E.R.N.E.L" in falas(kernel)[-1] and "Jarvis do Henrique" in falas(kernel)[-1]
    dizer(kernel, "quais pastas e diretorios voce consegue explorar?")
    assert "Posso olhar estas pastas" in falas(kernel)[-1] and "liberada" in falas(kernel)[-1]
    assert "exploração por conta própria está desligada" in falas(kernel)[-1]      # é o estado de verdade deste teste
    dizer(kernel, "Você sabe que outra inteligência artificial faz ajustes em você?")
    assert "Claude Code" in falas(kernel)[-1] and "não mudo o meu próprio código" in falas(kernel)[-1]
    dizer(kernel, "Teste sua voz")
    assert falas(kernel)[-1].startswith("Minha voz é")
    dizer(kernel, "você tem sentimentos?")
    assert "impulsos" in falas(kernel)[-1] and "Não tenho como afirmar" in falas(kernel)[-1]
    dizer(kernel, "Oiii")
    assert falas(kernel)[-1] == "Olá, Henrique."
    dizer(kernel, "como está o etudo")
    assert falas(kernel)[-1] == "Não estou estudando nem treinando agora."
    dizer(kernel, "Explore o computador")
    assert "exploração está desligada" in falas(kernel)[-1]
    assert kernel.memoria.contar().get("total", 0) == 0               # e nada disso foi parar na memória


def test_pergunta_que_o_classificador_nao_conhece_e_tratada_como_pergunta(kernel):
    dizer(kernel, "Qual a temperatura atual no bairro do Cambuí em Campinas, SP.")
    assert intencoes(kernel)[-1] == "pergunta"
    assert "Ainda não sei responder perguntas assim" in falas(kernel)[-1]
    assert kernel.memoria.contar().get("conversa", 0) == 0            # uma pergunta não é um recado para guardar
    dizer(kernel, "hoje foi um bom dia no escritório")                 # isto, sim, é conversa
    assert intencoes(kernel)[-1] == "conversa" and kernel.memoria.contar()["conversa"] == 1


def test_explorar_agora_nao_espera_a_curiosidade(cfg, relogio):
    cfg.exploracao.ligada = True
    nucleo = Kernel(cfg, relogio=relogio, lancar=lambda alvo: None)
    try:
        dizer(nucleo, "Explore o computador")
        assert falas(nucleo)[-1].startswith("Vou dar uma volta agora. Posso olhar:") and "kernel.toml" in falas(nucleo)[-1]
        assert nucleo.volta(5) == "explorar"                           # na volta seguinte, sem esperar o sossego
        dizer(nucleo, "para")
        dizer(nucleo, "explora agora")
        assert "Estou parado a seu pedido" in falas(nucleo)[-1]        # o freio continua valendo
    finally:
        nucleo.fechar()


def test_fale_mais_continua_o_assunto(estudado):
    dizer(estudado, "fale mais")
    assert falas(estudado)[-1].startswith("Mais sobre o quê?")
    dizer(estudado, "o que é astronomia?")
    primeira = estudado.mensagens[-1]
    assert primeira["classe"] == "conhecimento" and primeira["texto"].startswith("Astronomia é a ciência natural")
    dizer(estudado, "fale mais")
    segunda = estudado.mensagens[-1]
    assert segunda["classe"] == "conhecimento" and segunda["fonte"] == "Wikipédia: Astronomia"
    assert "telescópios" in segunda["texto"] and "ciência natural" not in segunda["texto"]   # continua, não repete
    assert "Povos antigos" in segunda["texto"]                         # três frases novas de cada vez
    dizer(estudado, "e o que mais?")
    assert falas(estudado)[-1] == "É tudo o que eu tenho sobre Astronomia."
    assert [e["intencao"] for e in estudado.registro.ultimos(20) if e["tipo"] == "intencao"][-2:] == ["mais", "mais"]
    dizer(estudado, "fale mais sobre astronomia")                      # com assunto, começa por ele
    assert falas(estudado)[-1].startswith("Astronomia é a ciência natural")


def test_a_pergunta_dele_so_aceita_resposta_que_parece_resposta(kernel, relogio):
    """Antes, a fala seguinte, qualquer que fosse, virava "fato" sobre o que ele tinha perguntado."""
    dizer(kernel, "hoje almocei com a Marcela do financeiro")
    kernel.impulsos.valores["curiosidade"] = 0.9
    relogio.avancar(minutes=5)
    assert kernel.volta(5) == "perguntar" and '"Marcela"' in falas(kernel)[-1]
    dizer(kernel, "Teste sua voz")                                     # mudou de assunto: não é resposta
    assert falas(kernel)[-1].startswith("Minha voz é") and kernel.memoria.contar().get("fato", 0) == 0
    assert kernel.pergunta_aberta and kernel.pergunta_aberta["termo"] == "Marcela"   # a dúvida continua aberta
    dizer(kernel, "você sabe quem é ela?")                             # uma pergunta sua também não é resposta
    assert kernel.memoria.contar().get("fato", 0) == 0
    dizer(kernel, "é a gerente financeira do cliente da padaria")
    assert 'Guardei isso sobre "Marcela"' in falas(kernel)[-1] and kernel.memoria.contar()["fato"] == 1
    assert kernel.pergunta_aberta is None


def test_o_cerebro_so_entra_na_conversa_se_voce_ligar(kernel):
    class Cerebro:
        descricao = "mini GPT de mentira"
        pedidos = []

        def responder(self, texto, *resto):
            self.pedidos.append(texto)
            return "um país da América do Sul."

    kernel.cerebro = Cerebro()
    dizer(kernel, "hoje choveu bastante por aqui")
    assert Cerebro.pedidos == [] and "completa texto, não dialoga" in falas(kernel)[-1]   # de fábrica ele não se mete
    dizer(kernel, "completa: O Brasil é")
    assert kernel.mensagens[-1]["classe"] == "cerebro" and falas(kernel)[-1] == "O Brasil é um país da América do Sul."
    dizer(kernel, "como está o seu cérebro?")
    assert "mini GPT de mentira" in falas(kernel)[-1] and "completa texto, não conversa" in falas(kernel)[-1]
    kernel.cfg.cerebro.na_conversa = True
    dizer(kernel, "amanhã deve fazer sol")
    assert kernel.mensagens[-1]["classe"] == "cerebro" and "amanhã deve fazer sol" in Cerebro.pedidos

    kernel.cerebro = None
    dizer(kernel, "completa: Era uma vez")
    assert "ainda não foi treinado" in falas(kernel)[-1]


# ================================================================== presença
def test_sem_voce_por_perto_ele_trabalha_calado_e_conta_na_volta(cfg, relogio, tmp_path):
    liberada = tmp_path / "liberada"
    for i in range(3):
        (liberada / f"ata da reunião {i}.txt").write_text(
            f"Ata da reunião {i} com a Padaria Estrela: foi combinado o prazo de entrega do relatório do mês.", encoding="utf-8")
    cfg.exploracao.ligada = True
    nucleo = Kernel(cfg, relogio=relogio, lancar=lambda alvo: None)
    try:
        relogio.avancar(hours=3)                                       # você saiu
        nucleo.impulsos.valores["curiosidade"] = 0.9
        for _ in range(60):
            nucleo.volta(5)
            nucleo.impulsos.valores["curiosidade"] = max(nucleo.impulsos.valores["curiosidade"], 0.7)
        assert nucleo.mapa.numeros()["arquivos_lidos"] >= 3            # ele trabalhou...
        assert falas(nucleo) == [] and nucleo.novidades > 0            # ...sem dizer uma palavra, nem perguntar nada
        assert nucleo.estado()["presente"] is False

        dizer(nucleo, "que horas são?")                                # você voltou
        resposta, resumo = falas(nucleo)[-2:]
        assert resposta.startswith("São ")
        assert resumo.startswith("Enquanto você esteve fora (3 h), li ") and "arquivos seus" in resumo and "ata da reunião" in resumo
        assert nucleo.novidades == 0 and nucleo.estado()["presente"] is True
        dizer(nucleo, "oi")                                            # e não repete o resumo
        assert falas(nucleo)[-1] == "Olá, Henrique."
    finally:
        nucleo.fechar()


def test_duas_perguntas_sem_resposta_e_ele_para_de_perguntar(kernel, relogio):
    kernel.cfg.mente.minutos_de_presenca = 600                         # você está por perto, mas não responde
    kernel.cfg.mente.minutos_entre_perguntas = 1
    dizer(kernel, "falei com a Marcela e com o Rogério sobre o contrato da Estrela Azul")
    feitas = 0
    for _ in range(12):
        relogio.avancar(minutes=31)                                    # a pergunta anterior expira sem resposta
        kernel.impulsos.valores["curiosidade"] = 0.9
        feitas += kernel.volta(5) == "perguntar"
    assert feitas == 2                                                 # perguntou duas vezes, ninguém respondeu, parou
    dizer(kernel, "oi")                                                # você falou: ele pode voltar a perguntar
    relogio.avancar(minutes=5)
    kernel.impulsos.valores["curiosidade"] = 0.9
    assert kernel.volta(5) == "perguntar"


# ============================================================ o modelo de si
def test_o_que_ele_diz_de_si_vem_do_estado_de_verdade(kernel):
    kernel.memoria.guardar("o portão abre com o controle azul", tipo="fato")
    assert "1 fatos que você me ensinou" in sobre_si.responder(kernel, "como está a sua memória?")
    assert "desligada na minha configuração" in sobre_si.responder(kernel, "você usa a internet?")
    kernel.cfg.internet.ligada = True
    assert "sempre só lendo" in sobre_si.responder(kernel, "você usa a internet?")
    kernel.cfg.voz.motor, kernel.cfg.voz.estilo = "difones", "robotica"
    assert "leitora de verdade" in sobre_si.responder(kernel, "como é a sua voz?") and "robótico" in sobre_si.responder(kernel, "sua voz")
    kernel.cfg.exploracao.ler_codigo = True
    assert "documentos e código" in sobre_si.responder(kernel, "quais pastas você pode ver?")
    kernel.seguranca.pausado = True
    assert "parado a seu pedido" in sobre_si.responder(kernel, "o que você faz sozinho?")
    assert "selado" in sobre_si.responder(kernel, "quais são os seus limites?")
    assert sobre_si.responder(kernel, "blá blá").startswith("Eu sou o K.E.R.N.E.L")   # sem tópico, ele se apresenta


# ==================================================================== resumo
def test_resumo_por_extracao():
    texto = ("Fotossíntese é o processo pelo qual as plantas transformam a luz em energia química. "
             "O site também vende adubo e vasos de cerâmica para o seu jardim. "
             "Na fotossíntese, a planta consome gás carbônico e água e libera oxigênio. "
             "A clorofila é o pigmento que capta a luz usada na fotossíntese. "
             "Clique aqui para assinar a nossa lista de novidades. "
             "A clorofila é o pigmento que capta a luz usada na fotossíntese.")
    assert len(frases(texto)) == 6 and frases("Curta. Oi.") == []
    resumo = resumir(texto, "fotossíntese", quantas=3)
    assert resumo.startswith("Fotossíntese é o processo") and "oxigênio" in resumo and "clorofila" in resumo
    assert "adubo" not in resumo and "Clique aqui" not in resumo        # o que não é do assunto fica de fora
    assert resumo.count("A clorofila é o pigmento") == 1                # e frase repetida não entra duas vezes
    assert resumir("", "qualquer") == "" and resumir(["a", "b"], "x") == ""
    assert len(resumir(texto * 3, "fotossíntese", quantas=9, limite=200)) <= 201
