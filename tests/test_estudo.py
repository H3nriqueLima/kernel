"""Os trabalhos longos de estudo, com a internet e a placa de vídeo trocadas por dublês."""
import asyncio
import threading
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


def test_treino_aprovado_sobrevive_ao_reinicio_do_servico(cfg, relogio, monkeypatch):
    """Você aprova 8 horas de treino e reinicia o serviço aos 45 minutos: na partida seguinte ele retoma sozinho."""
    from kernel.nucleo import Kernel

    (cfg.pasta("cerebro") / "corpus.txt").write_text(CORPUS * 30, encoding="utf-8")
    comandos, liberar = [], threading.Event()

    class Processo:
        def __init__(self, comando, **opcoes):
            comandos.append(comando)

            def linhas():   # o treino falso só termina depois de o teste ler o anúncio da retomada
                liberar.wait(10)
                yield "parou no passo 100 com perda de validação 4.321. Reinicie o serviço para ele usar o cérebro novo.\n"
            self.stdout = linhas()

        def wait(self):
            return 0

    monkeypatch.setattr(modulo_estudo.subprocess, "Popen", Processo)
    primeiro = Kernel(cfg, relogio=relogio)
    assert primeiro.estudo.treino_pendente() == 0.0
    primeiro.estudo._arquivo_do_treino.write_text('{"ate": %f}' % (time.time() + 3 * 3600), encoding="utf-8")
    assert 2.9 < primeiro.estudo.treino_pendente() <= 3.0               # o reinício pegou o treino no meio
    primeiro.fechar()

    segundo = Kernel(cfg, relogio=relogio)
    segundo._retomar_treino()
    assert "Retomei o treino do cérebro" in falas(segundo)[-1] and "faltavam 3,0 horas" in falas(segundo)[-1]
    liberar.set()
    esperar(segundo, 60)
    assert comandos[0][1:5] == ["-m", "kernel", "cerebro", "treinar"] and 2.9 < float(comandos[0][-1]) <= 3.0
    assert segundo.estudo.treino_pendente() == 0.0                      # terminou: não há mais o que retomar
    assert not any("Reinicie o serviço" in e.get("resultado", "") for e in segundo.registro.ultimos(20) if e["tipo"] == "estudo")
    segundo.fechar()

    # quando é VOCÊ que manda parar, ele não retoma na partida seguinte
    terceiro = Kernel(cfg, relogio=relogio)
    terceiro.estudo._arquivo_do_treino.write_text('{"ate": %f}' % (time.time() + 3600), encoding="utf-8")
    dizer(terceiro, "para o treino")
    assert terceiro.estudo.treino_pendente() == 0.0
    terceiro._retomar_treino()
    assert not any("Retomei" in fala for fala in falas(terceiro))
    terceiro.fechar()


def test_motivo_do_fim_do_treino_vai_para_o_registro(kernel, monkeypatch):
    (kernel.cfg.pasta("cerebro") / "corpus.txt").write_text(CORPUS * 30, encoding="utf-8")
    saidas = iter([
        ["parou no passo 100 (o tempo da sessão acabou) com perda de validação 4.321.\n",
         'RESUMO {"motivo": "tempo", "passo": 100, "passo_inicial": 0, "melhor_validacao": 4.321, '
         '"segundos": 7200.0, "horas_pedidas": 2.0}\n'],
        ["parou no passo 30 (foi interrompido (Ctrl+C ou sinal do sistema)) com perda de validação 4.9.\n",
         'RESUMO {"motivo": "interrupcao", "passo": 30, "passo_inicial": 0, "melhor_validacao": 4.9, '
         '"segundos": 700.0, "horas_pedidas": 2.0}\n'],
    ])

    class Processo:
        def __init__(self, comando, **opcoes):
            self.stdout = iter(next(saidas))

        def wait(self):
            return 0

    monkeypatch.setattr(modulo_estudo.subprocess, "Popen", Processo)
    for _ in range(2):
        dizer(kernel, "treina o cérebro por 2 horas")
        (pedido,) = kernel.seguranca.pendentes()
        kernel.responder_pedido(pedido.id, True)
        esperar(kernel, 60)
        kernel.estudo._arquivo_do_treino.unlink(missing_ok=True)
    fins = [e for e in kernel.registro.ultimos(50) if e.get("evento") == "treino_acabou"]
    assert [f["motivo"] for f in fins] == ["tempo", "interrupcao"]
    assert fins[1]["segundos"] == 700.0 and fins[1]["horas_pedidas"] == 2.0
    assert "RESUMO" not in kernel.estudo.situacao
    fala_tempo, fala_interrompido = [f for f in falas(kernel) if f.startswith("Treino encerrado")]
    assert "Atenção" not in fala_tempo
    assert "parou antes da hora sem eu pedir" in fala_interrompido and "treino.log" in fala_interrompido


def test_desligar_espera_o_treino_salvar(kernel):
    import subprocess

    assert kernel.estudo.esperar_o_treino(0.1)                    # sem treino: nada a esperar

    class Processo:
        def __init__(self, demora):
            self.demora, self.esperas = demora, []

        def wait(self, timeout=None):
            self.esperas.append(timeout)
            if self.demora > timeout:
                raise subprocess.TimeoutExpired("treino", timeout)
            return 0

    kernel.estudo._processo = Processo(demora=5)
    assert kernel.estudo.esperar_o_treino(60) and kernel.estudo._processo.esperas == [60]
    kernel.estudo._processo = Processo(demora=999)
    assert not kernel.estudo.esperar_o_treino(60)                 # travou: o serviço segue desligando e anota
    kernel.estudo._processo = None
