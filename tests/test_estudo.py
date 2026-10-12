"""Os trabalhos longos de estudo, com a internet e a placa de vídeo trocadas por dublês."""
import asyncio
import time

from conftest import falas
from kernel.cerebro import wikipedia
from kernel.nucleo import estudo as modulo_estudo

CORPUS = """Astronomia

Astronomia é a ciência natural que estuda os corpos celestes e os fenômenos do cosmo.
<|fim|>
Brasil

O Brasil é o maior país da América do Sul. Sua capital é Brasília.
<|fim|>
"""


def esperar(nucleo, segundos=10.0):
    limite = time.time() + segundos
    while nucleo.estudo.ocupado and time.time() < limite:
        time.sleep(0.02)
    assert not nucleo.estudo.ocupado, nucleo.estudo.situacao


def dizer(nucleo, texto):
    asyncio.run(nucleo.receber(texto))


def falsificar_wikipedia(monkeypatch, baixados, demora=0.0):
    monkeypatch.setattr(wikipedia, "listar_partes", lambda: [("parte1.bz2", 1000), ("parte2.bz2", 2000)])

    def baixar(nome, pasta, max_mb=None, ao_progredir=None):
        for feito in (300, 600, 1000):
            time.sleep(demora)
            ao_progredir(feito, 1000)
        baixados.append(nome)
        return pasta / nome

    def extrair(arquivos, saida, max_artigos=None, minimo=500, ao_progredir=None):
        saida.write_text(CORPUS, encoding="utf-8")
        return {"artigos": 2, "caracteres": len(CORPUS)}

    monkeypatch.setattr(wikipedia, "baixar", baixar)
    monkeypatch.setattr(wikipedia, "extrair", extrair)


def test_estudar_a_wikipedia_pelo_chat(kernel, monkeypatch):
    baixados = []
    falsificar_wikipedia(monkeypatch, baixados)
    dizer(kernel, "estuda a wikipédia")
    assert baixados == [] and not kernel.estudo.ocupado          # ainda falta você permitir
    (pedido,) = kernel.seguranca.pendentes()
    kernel.responder_pedido(pedido.id, True)
    assert "Comecei a estudar" in falas(kernel)[-1]
    esperar(kernel)
    assert baixados == ["parte1.bz2"]                              # uma parte só, como pedido
    assert "Terminei de estudar a Wikipédia: 2 artigos" in falas(kernel)[-1]
    assert kernel.mensagens[-1]["classe"] == "iniciativa" and kernel.estado()["conhecimento"] == 2
    dizer(kernel, "qual é a capital do brasil?")
    assert "Brasília" in falas(kernel)[-1] and kernel.mensagens[-1]["fonte"] == "Wikipédia: Brasil"
    eventos = [e["evento"] for e in kernel.registro.ultimos(200) if e["tipo"] == "estudo"]
    assert eventos == ["inicio", "fim"]


def test_negar_o_estudo_nao_baixa_nada(kernel, monkeypatch):
    baixados = []
    falsificar_wikipedia(monkeypatch, baixados)
    dizer(kernel, "estuda a wikipédia inteira")
    (pedido,) = kernel.seguranca.pendentes()
    assert "inteira" in pedido.descricao
    kernel.responder_pedido(pedido.id, False)
    time.sleep(0.1)
    assert baixados == [] and not kernel.estudo.ocupado and kernel.estado()["conhecimento"] == 0


def test_andamento_e_parar_no_meio(kernel, monkeypatch):
    baixados = []
    falsificar_wikipedia(monkeypatch, baixados, demora=0.4)
    dizer(kernel, "aprende a wikipédia")
    kernel.responder_pedido(kernel.seguranca.pendentes()[0].id, True)
    time.sleep(0.6)
    assert kernel.estado()["atividade"] == "estudando"
    dizer(kernel, "como está o estudo?")
    assert "baixando a parte 1 de 1" in falas(kernel)[-1]
    dizer(kernel, "estuda a wikipédia")                              # um trabalho de cada vez
    kernel.responder_pedido(kernel.seguranca.pendentes()[0].id, True)
    assert "Já estou ocupado" in falas(kernel)[-1]
    dizer(kernel, "para o estudo")
    esperar(kernel)
    assert baixados == [] and "Parei o trabalho" in falas(kernel)[-1]


def test_treinar_o_cerebro_pelo_chat(kernel, monkeypatch, tmp_path):
    pasta = kernel.cfg.pasta("cerebro")
    (pasta / "corpus.txt").write_text(CORPUS * 30, encoding="utf-8")
    chamadas = []

    class Processo:
        def __init__(self, comando, **opcoes):
            chamadas.append((comando, opcoes))
            self.stdout = iter(["dispositivo: de mentira\n", "passo 50/100 | perda 5.000\n",
                                "parou no passo 100 com perda de validação 4.321.\n"])

        def wait(self):
            return 0

    monkeypatch.setattr(modulo_estudo.subprocess, "Popen", Processo)
    dizer(kernel, "treina o cérebro por 2 horas")
    (pedido,) = kernel.seguranca.pendentes()
    assert "2 horas" in pedido.descricao
    kernel.responder_pedido(pedido.id, True)
    esperar(kernel, 60)
    comando, opcoes = chamadas[0]
    assert comando[1:] == ["-m", "kernel", "cerebro", "treinar", "--horas", "2.0"]
    assert opcoes["env"]["KERNEL_DADOS"] == str(kernel.cfg.dados)   # o treino usa a mesma pasta de dados
    assert (pasta / "tokenizador.json").exists() and (pasta / "treino.bin").exists()   # preparou sozinho
    assert "Treino encerrado. parou no passo 100" in falas(kernel)[-1]


def test_treino_pedido_em_minutos_e_proposto_em_minutos(kernel):
    (kernel.cfg.pasta("cerebro") / "corpus.txt").write_text(CORPUS * 30, encoding="utf-8")
    dizer(kernel, "Treine o cérebro por 20 minutos.")
    (pedido,) = kernel.seguranca.pendentes()
    assert "20 minutos" in pedido.descricao and abs(pedido.argumentos["horas"] - 1 / 3) < 1e-9
    kernel.responder_pedido(pedido.id, False)


def test_contar_artigos_nao_trava_enquanto_um_estudo_regrava_o_banco(tmp_path):
    """A tela de estado pergunta a contagem a cada segundo e meio: ela não pode esperar o estudo acabar."""
    import sqlite3
    import time

    from kernel.conhecimento import Enciclopedia

    arquivo = tmp_path / "conhecimento.db"
    enciclopedia = Enciclopedia(arquivo)
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("Astronomia\n\nA astronomia estuda os astros.\n<|fim|>\nBotânica\n\nA botânica estuda as plantas.\n<|fim|>\n",
                      encoding="utf-8")
    enciclopedia.construir(corpus)
    quantos = len(enciclopedia)
    assert quantos == 2
    estudo = sqlite3.connect(str(arquivo), isolation_level=None)     # outra conexão, como a do estudo
    estudo.execute("BEGIN EXCLUSIVE")
    try:
        t0 = time.time()
        assert len(enciclopedia) == quantos                          # devolve a última contagem conhecida
        assert time.time() - t0 < 1.0                                # sem esperar os 5 s do SQLite
    finally:
        estudo.execute("ROLLBACK")
        estudo.close()
    assert len(enciclopedia) == quantos
    enciclopedia.fechar()
