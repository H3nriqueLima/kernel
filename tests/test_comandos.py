from datetime import datetime

import pytest

from kernel import comandos
from kernel.comandos import extrair

AGORA = datetime(2026, 10, 12, 20, 0)

# Frases que NÃO estão em exemplos.txt: o que importa é acertar o que ele nunca viu.
NOVAS = [
    ("abre o gimp", "abrir_programa"),
    ("abra o libreoffice pra mim", "abrir_programa"),
    ("executa o audacity", "abrir_programa"),
    ("inicia o blender", "abrir_programa"),
    ("lista a pasta de músicas", "listar_pasta"),
    ("o que tem na pasta imagens", "listar_pasta"),
    ("mostra os arquivos de downloads", "listar_pasta"),
    ("quais arquivos tem em documentos", "listar_pasta"),
    ("me lembra de regar as plantas", "anotar_lembrete"),
    ("anota que o gato tomou vacina", "anotar_lembrete"),
    ("me avisa às 16h da reunião", "anotar_lembrete"),
    ("lembra de pagar a academia amanhã", "anotar_lembrete"),
    ("o que você lembra sobre o gato", "consultar_memoria"),
    ("mostra meus lembretes de hoje", "consultar_memoria"),
    ("o que eu falei sobre a academia", "consultar_memoria"),
    ("quem é você afinal", "sobre_si"),
    ("o que você faz", "sobre_si"),
    ("qual seu nome", "sobre_si"),
    ("bom dia kernel", "conversa"),
    ("hoje estou animado", "conversa"),
    ("qual é a capital da argentina", "pergunta"),
    ("quem foi tiradentes", "pergunta"),
    ("onde está a planilha de orçamento", "procurar_arquivo"),
    ("quanto espaço livre tem no meu hd", "sistema"),
    ("o que você descobriu explorando", "descobertas"),
    ("o jogo ontem foi ótimo", "conversa"),
    ("estou cansado de trabalhar", "conversa"),
    # o assunto parece de comando, mas a frase é só conversa
    ("o fornecedor de embalagens só entrega na quinta", "conversa"),
    ("preciso trocar o disco do servidor de backup", "conversa"),
    ("o excel fechou sozinho e perdi a planilha", "conversa"),
    ("os downloads estão demorando", "conversa"),
    ("acho que o hd está morrendo", "conversa"),
    (r"lista o conteúdo de C:\Windows", "listar_pasta"),
    ("o que você sabe sobre a marcela", "consultar_memoria"),
]


@pytest.fixture(scope="module")
def classificador(classificador_treinado):
    return comandos.Classificador.carregar(classificador_treinado)


def test_acerta_frases_que_nunca_viu(classificador):
    erros = [(f, esperado, classificador.classificar(f)[0]) for f, esperado in NOVAS
             if classificador.classificar(f)[0] != esperado]
    assert len(erros) <= 2, erros  # tolera 2 em 30; mais que isso, faltam exemplos


def test_na_duvida_e_conversa(classificador):
    assert classificador.classificar("xyzzy plugh")[0] == "conversa"
    # um classificador sem opinião (pesos zerados) dá 1/6 para cada intenção: abaixo da confiança mínima
    em_branco = comandos.Classificador(classificador.pesos * 0, classificador.vies * 0)
    em_branco.vies[1] = 0.01  # leve preferência por abrir_programa
    intencao, confianca = em_branco.classificar("abre a calculadora")
    assert intencao == "conversa" and confianca < comandos.classificador.CONFIANCA_MINIMA


def test_salvar_e_carregar_da_o_mesmo_resultado(classificador, tmp_path):
    classificador.salvar(tmp_path / "c.npz")
    outro = comandos.Classificador.carregar(tmp_path / "c.npz")
    assert outro.probabilidades("abre o chrome") == classificador.probabilidades("abre o chrome")


def test_exemplos_tem_todas_as_intencoes():
    exemplos = comandos.carregar_exemplos(comandos.classificador.EXEMPLOS)
    assert {intencao for _, intencao in exemplos} == set(comandos.INTENCOES)


@pytest.mark.parametrize("frase, esperado", [
    ("pode abrir o bloco de notas pra mim?", "bloco de notas"),
    ("abre a calculadora", "calculadora"),
    ("kernel, abre o chrome por favor", "chrome"),
    ("bota o spotify pra abrir", "spotify"),
    ("abre aí o HL Finance", "HL Finance"),
])
def test_extrai_o_programa(frase, esperado):
    assert extrair.programa(frase) == esperado


@pytest.mark.parametrize("frase, esperado", [
    ("o que tem na pasta de downloads?", "downloads"),
    ("lista a área de trabalho", "area de trabalho"),
    (r"lista o conteúdo de C:\Users\henri\Downloads", r"C:\Users\henri\Downloads"),
    ("lista a pasta relatorios 2026", "relatorios 2026"),
])
def test_extrai_a_pasta(frase, esperado):
    assert extrair.pasta(frase) == esperado


@pytest.mark.parametrize("frase, corpo, quando", [
    ("me lembra de pagar o boleto amanhã às 10h", "pagar o boleto", datetime(2026, 10, 13, 10, 0)),
    ("anota aí: reunião com o cliente sexta", "reunião com o cliente sexta", None),
    ("cria um lembrete para tomar o remédio às 22h", "tomar o remédio", datetime(2026, 10, 12, 22, 0)),
    ("não me deixa esquecer de renovar o domínio", "renovar o domínio", None),
    ("kernel, me lembra de pagar o aluguel", "pagar o aluguel", None),
    ("guarda que o carro está na oficina", "o carro está na oficina", None),
    ("marca um lembrete de reunião às 14h30", "reunião", datetime(2026, 10, 13, 14, 30)),
    ("me lembra em 20 minutos de tirar a comida do forno", "tirar a comida do forno", datetime(2026, 10, 12, 20, 20)),
    ("me lembra de beber água em 1 minuto", "beber água", datetime(2026, 10, 12, 20, 1)),
    ("me avisa às 21:15", "às 21:15", datetime(2026, 10, 12, 21, 15)),  # sem assunto: fica o texto original
])
def test_extrai_o_lembrete(frase, corpo, quando):
    assert extrair.lembrete(frase, AGORA) == (corpo, quando)


@pytest.mark.parametrize("frase, quando", [
    ("em 20 minutos", datetime(2026, 10, 12, 20, 20)),
    ("daqui a uma hora", datetime(2026, 10, 12, 21, 0)),
    ("em meia hora", datetime(2026, 10, 12, 20, 30)),
    ("às 8h", datetime(2026, 10, 13, 8, 0)),          # 8h já passou hoje: é amanhã
    ("às 21:15", datetime(2026, 10, 12, 21, 15)),
    ("amanhã", datetime(2026, 10, 13, 9, 0)),
    ("depois de amanhã às 7", datetime(2026, 10, 14, 7, 0)),
    ("um dia desses", None),
    ("às 25h", None),
])
def test_horario(frase, quando):
    assert extrair.horario(frase, AGORA) == quando
