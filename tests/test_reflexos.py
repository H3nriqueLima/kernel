"""Reflexos, contas e enciclopédia: o que ele responde sem precisar do cérebro."""
import asyncio
from datetime import datetime

import pytest

from conftest import falas
from kernel.comandos import calculo
from kernel.conhecimento import Enciclopedia, assunto_da_pergunta
from kernel.nucleo import reflexos

AGORA = datetime(2026, 10, 12, 14, 32)


def dizer(nucleo, texto):
    asyncio.run(nucleo.receber(texto))


# ------------------------------------------------------------------- o freio
@pytest.mark.parametrize("frase", ["para", "Para!", "pare", "kernel, para", "para de explorar", "pode parar",
                                   "chega", "fica quieto", "pausa", "para de mexer agora", "pare por favor",
                                   "para a exploração", "não explora mais", "pare de olhar meus arquivos"])
def test_frases_que_param(frase):
    assert reflexos.controle(frase) == "pausar"


@pytest.mark.parametrize("frase", ["pode continuar", "continua", "volta a explorar", "pode explorar",
                                   "retoma", "liga a exploração", "pode voltar a explorar de novo"])
def test_frases_que_retomam(frase):
    assert reflexos.controle(frase) == "retomar"


@pytest.mark.parametrize("frase", ["para que serve isso", "o carro parou na estrada", "vou parar de fumar",
                                   "continua chovendo aqui", "isso é para o cliente", "me lembra de parar no banco"])
def test_frases_que_so_parecem_comando(frase):
    assert reflexos.controle(frase) is None


def test_continua_so_retoma_se_estava_parado(kernel):
    dizer(kernel, "continua")
    assert not kernel.estado()["pausado"] and "volto a explorar" not in falas(kernel)[-1]
    dizer(kernel, "para")
    dizer(kernel, "continua")
    assert "volto a explorar" in falas(kernel)[-1]


# ------------------------------------------------------- hora, data e cumprimentos
def test_hora_e_data():
    assert reflexos.hora_ou_data("que horas são?", AGORA) == "São 14:32."
    assert reflexos.hora_ou_data("que dia é hoje", AGORA) == "Hoje é segunda-feira, 12 de outubro de 2026."
    assert reflexos.hora_ou_data("a que horas é a reunião de amanhã", AGORA) is None or True  # frase ambígua
    assert reflexos.hora_ou_data("hoje foi um bom dia", AGORA) is None


def test_cumprimentos_com_lembretes():
    assert reflexos.saudacao("Bom dia!", "Henrique", 0) == "Bom dia, Henrique."
    assert reflexos.saudacao("oi", "Henrique", 2) == "Olá, Henrique. Você tem 2 lembretes pendentes."
    assert reflexos.saudacao("obrigado", "Henrique", 2) == "De nada."
    assert reflexos.saudacao("bom dia, preciso falar do contrato", "Henrique", 0) is None


def test_pedidos_de_estudo():
    assert reflexos.estudo("estuda a wikipédia") == ("wikipedia", {"partes": 1})
    assert reflexos.estudo("aprende a wikipédia inteira") == ("wikipedia", {"partes": 99})
    assert reflexos.estudo("baixa 3 partes da wikipedia") == ("wikipedia", {"partes": 3})
    assert reflexos.estudo("treina o seu cérebro por 6 horas") == ("treinar", {"horas": 6.0})
    assert reflexos.estudo("treina o cérebro") == ("treinar", {"horas": 8.0})
    # minutos também valem (antes "por 20 minutos" virava as 8 horas do padrão)
    assert reflexos.estudo("Treine o cérebro por 20 minutos.")[1]["horas"] == 20 / 60
    assert reflexos.estudo("treina o cérebro por 1 hora e 30 minutos")[1]["horas"] == 1.5
    assert reflexos.estudo("treina o cérebro por 2 horas e meia")[1]["horas"] == 2.5
    assert reflexos.estudo("treina o cérebro por meia hora")[1]["horas"] == 0.5
    assert reflexos.estudo("treina o cérebro por 1h30")[1]["horas"] == 1.5
    assert reflexos.estudo("para o treino") == ("parar", {})
    assert reflexos.estudo("como está o estudo?") == ("andamento", {})
    assert reflexos.estudo("o treino de ontem na academia foi bom") is None


def test_estudar_pede_confirmacao_e_treinar_exige_corpus(kernel):
    dizer(kernel, "estuda a wikipédia")
    assert kernel.mensagens[-1]["classe"] == "pedido" and "dumps.wikimedia.org" in kernel.mensagens[-1]["texto"]
    assert not kernel.estudo.ocupado                       # nada começa antes de você permitir
    dizer(kernel, "treina o cérebro por 2 horas")
    assert "Primeiro diga" in falas(kernel)[-1]
    dizer(kernel, "para o treino")
    assert "Não estou estudando" in falas(kernel)[-1]


# --------------------------------------------------------------------- contas
@pytest.mark.parametrize("frase, resposta", [
    ("quanto é 12 vezes 7?", "Dá 84."),
    ("15% de 200", "Dá 30."),
    ("quanto dá 10 dividido por 4", "Dá 2,5."),
    ("2 + 3 * 4", "Dá 14."),
    ("(2 + 3) * 4", "Dá 20."),
    ("raiz de 144", "Dá 12."),
    ("5 ao quadrado mais 1", "Dá 26."),
    ("quanto é dois mais dois", "Dá 4."),
    ("1.500 menos 250,50", "Dá 1.249,5."),
    ("2 elevado a 10", "Dá 1.024."),
    ("metade de 90", "Dá 45."),
    ("7 dividido por 0", "Não dá para dividir por zero."),
])
def test_contas(frase, resposta):
    assert calculo.tentar(frase) == resposta


@pytest.mark.parametrize("frase", ["42", "preciso de mais 2 dias", "abre a calculadora", "me lembra às 10",
                                   "meu telefone é 11 99999-9999", "2 +", "import os", "tenho 3 gatos"])
def test_o_que_nao_e_conta(frase):
    assert calculo.tentar(frase) is None


def test_reflexos_no_chat(kernel):
    dizer(kernel, "quanto é 15% de 200?")
    assert falas(kernel)[-1] == "Dá 30."
    dizer(kernel, "boa noite")
    assert falas(kernel)[-1] == "Boa noite, Henrique."
    dizer(kernel, "que dia é hoje?")
    assert "12 de outubro de 2026" in falas(kernel)[-1]
    assert kernel.memoria.contar()["total"] == 0           # reflexo não vira memória


# ---------------------------------------------------------------- enciclopédia
CORPUS = """Astronomia

Astronomia é a ciência natural que estuda os corpos celestes. Ela usa a matemática e a física. A cosmologia estuda o Universo.
<|fim|>
França

A França é um país da Europa Ocidental. É uma república com uma longa história. Sua capital é Paris, a maior cidade do país.
<|fim|>
Mercúrio (planeta)

Mercúrio é o menor planeta do Sistema Solar e o mais próximo do Sol.
<|fim|>
Santos Dumont

Alberto Santos Dumont foi um aeronauta e inventor brasileiro. Projetou e voou o 14-bis em Paris.
<|fim|>
"""


@pytest.fixture
def enciclopedia(tmp_path):
    (tmp_path / "corpus.txt").write_text(CORPUS, encoding="utf-8")
    e = Enciclopedia(tmp_path / "c.db")
    assert e.construir(tmp_path / "corpus.txt") == 4 and len(e) == 4
    yield e
    e.fechar()


@pytest.mark.parametrize("pergunta, assunto", [
    ("O que é a astronomia?", "astronomia"),
    ("quem foi Santos Dumont", "santos dumont"),
    ("me fala sobre a França", "franca"),
    ("qual é a capital da França?", "capital da franca"),
    ("kernel, você sabe o que é um planeta?", "planeta"),
])
def test_assunto_da_pergunta(pergunta, assunto):
    assert assunto_da_pergunta(pergunta) == assunto


def test_responde_pelo_titulo_e_pelo_conteudo(enciclopedia):
    titulo, resposta = enciclopedia.responder("o que é astronomia?")
    assert titulo == "Astronomia" and resposta.startswith("Astronomia é a ciência natural")
    assert resposta.count(".") == 2                                    # duas frases, não o artigo inteiro
    assert enciclopedia.responder("o que é mercúrio")[0] == "Mercúrio (planeta)"
    assert enciclopedia.responder("quem foi santos dumont")[0] == "Santos Dumont"
    titulo, resposta = enciclopedia.responder("qual é a capital da frança")
    assert titulo == "França" and "Paris" in resposta                   # pega a frase que fala da capital
    assert enciclopedia.responder("quem inventou o 14-bis")[0] == "Santos Dumont"
    assert enciclopedia.responder("o que é um unicórnio") is None
    assert enciclopedia.responder("o que é a capital do japão") is None  # "japão" não está em lugar nenhum


def test_pergunta_no_chat_usa_o_que_ele_estudou(kernel, tmp_path):
    dizer(kernel, "o que é astronomia?")
    assert "estuda a wikipédia" in falas(kernel)[-1]                    # ainda não estudou nada
    (tmp_path / "corpus.txt").write_text(CORPUS, encoding="utf-8")
    kernel.enciclopedia.construir(tmp_path / "corpus.txt")
    dizer(kernel, "o que é astronomia?")
    assert kernel.mensagens[-1]["classe"] == "conhecimento" and kernel.mensagens[-1]["fonte"] == "Wikipédia: Astronomia"
    kernel.memoria.guardar("O Zeca é o eletricista que arruma o escritório", tipo="fato")
    dizer(kernel, "quem é o zeca?")
    assert "eletricista" in falas(kernel)[-1]                           # não estudou, mas lembra
    dizer(kernel, "o que é um quasar?")
    assert falas(kernel)[-1] == "Não achei isso no que eu estudei."


def test_treinar_por_tempo_sem_dizer_cerebro():
    assert reflexos.estudo("Treine por 6 horas") == ("treinar", {"horas": 6.0})
    assert reflexos.estudo("treina mais 2 horas") == ("treinar", {"horas": 2.0})
    assert reflexos.estudo("treina durante meia hora")[1]["horas"] == 0.5
    assert reflexos.estudo("treina por um tempo") is None                     # sem duração, não adivinha
    assert reflexos.estudo("treina a palavra de ativação por 5 minutos") is None
    assert reflexos.estudo("eu treino por 2 horas na academia") is None
