"""O núcleo de ponta a ponta, sem servidor web: mensagens entram, o laço dá voltas."""
import asyncio

from conftest import falas
from kernel.seguranca import integridade


def dizer(kernel, texto):
    asyncio.run(kernel.receber(texto))


def pedido_pendente(kernel) -> str:
    (pendente,) = kernel.seguranca.pendentes()
    return pendente.id


def test_abrir_programa_pede_confirmacao_e_so_entao_abre(kernel):
    dizer(kernel, "abre a calculadora")
    assert kernel.abertos == []
    assert kernel.mensagens[-1]["classe"] == "pedido" and "calc.exe" in kernel.mensagens[-1]["texto"]
    kernel.responder_pedido(pedido_pendente(kernel), True)
    assert kernel.abertos == ["calc.exe"]
    assert falas(kernel)[-1] == "Abri calculadora."


def test_negar_um_pedido(kernel):
    dizer(kernel, "abre o bloco de notas")
    kernel.responder_pedido(pedido_pendente(kernel), False)
    assert kernel.abertos == [] and falas(kernel)[-1] == "Tudo bem, não fiz."
    kernel.responder_pedido("nao-existe", True)
    assert kernel.mensagens[-1]["classe"] == "aviso"


def test_programa_desconhecido_vira_aviso(kernel):
    dizer(kernel, "abre o formatador de discos")
    assert kernel.mensagens[-1]["classe"] == "aviso" and kernel.seguranca.pendentes() == []


def test_listar_pasta_liberada_e_recusar_a_proibida(kernel, tmp_path):
    dizer(kernel, f"lista o conteúdo de {tmp_path / 'liberada'}")
    kernel.responder_pedido(pedido_pendente(kernel), True)
    assert "relatorio.txt" in falas(kernel)[-1]
    dizer(kernel, r"lista o conteúdo de C:\Windows")
    assert "fora das pastas liberadas" in falas(kernel)[-1]


def test_lembrete_com_hora_avisa_quando_vence(kernel, relogio):
    dizer(kernel, "me lembra de tirar a pizza do forno em 20 minutos")
    kernel.responder_pedido(pedido_pendente(kernel), True)
    assert "Aviso você em 12/10 às 10:20" in falas(kernel)[-1]
    dizer(kernel, "quais são meus lembretes")
    assert "tirar a pizza do forno" in falas(kernel)[-1]

    relogio.avancar(minutes=19)
    kernel.volta(5)
    assert "Lembrete:" not in falas(kernel)[-1]
    relogio.avancar(minutes=2)
    kernel.volta(5)
    assert kernel.mensagens[-1]["classe"] == "iniciativa"
    assert "Lembrete:" in falas(kernel)[-1] and "pizza" in falas(kernel)[-1]
    kernel.volta(5)
    assert sum("Lembrete:" in f for f in falas(kernel)) == 1  # avisa uma vez só


def test_lembra_de_conversa_antiga(kernel, relogio):
    dizer(kernel, "o fornecedor de embalagens só entrega na quinta")
    relogio.avancar(days=3)
    dizer(kernel, "o que você lembra sobre o fornecedor")
    assert "só entrega na quinta" in falas(kernel)[-1] and "12/10/2026" in falas(kernel)[-1]
    dizer(kernel, "o que você lembra sobre dinossauros")
    assert "Não achei nada" in falas(kernel)[-1]


def test_conversa_sem_cerebro_explica_uma_vez_e_cita_memorias(kernel):
    dizer(kernel, "o servidor de backup fica na sala dos fundos")
    assert "cérebro não foi treinado" in falas(kernel)[-1]
    dizer(kernel, "preciso trocar o disco do servidor de backup")
    assert kernel.mensagens[-1]["classe"] == "lembranca" and "sala dos fundos" in falas(kernel)[-1]
    assert sum("cérebro não foi treinado" in f for f in falas(kernel)) == 1


def test_sobre_si(kernel):
    dizer(kernel, "quem é você")
    resposta = falas(kernel)[-1]
    assert "K.E.R.N.E.L" in resposta and "Kinetic Extended Resolution Network and Evolutionary Logic" in resposta
    assert "ainda não treinado" in kernel.apresentacao()
    dizer(kernel, "como está o seu cérebro?")
    assert "ainda não foi treinado" in falas(kernel)[-1]


def test_organizacao_arruma_a_memoria_sozinha(kernel):
    for i in range(13):
        kernel.memoria.guardar(f"anotação número {i % 5}")  # várias repetidas
    assert kernel.volta(5) == "organizar"
    assert kernel.memoria.por_organizar() == 0 and kernel.memoria.contar()["total"] == 5
    assert kernel.volta(5) == "nada"
    ultimo = kernel.registro.ultimos(1)[0]
    assert ultimo["tipo"] == "laco" and "apaguei 8 repetidas" in ultimo["reflexao"]


def test_curiosidade_pergunta_e_guarda_a_resposta(kernel, relogio):
    dizer(kernel, "hoje almocei com a Marcela do financeiro")
    kernel.impulsos.valores["curiosidade"] = 0.9
    relogio.avancar(minutes=5)
    assert kernel.volta(5) == "perguntar"
    assert kernel.mensagens[-1]["classe"] == "iniciativa" and '"Marcela"' in falas(kernel)[-1]
    assert kernel.impulsos.valores["curiosidade"] == 0.0
    kernel.impulsos.valores["curiosidade"] = 0.9
    assert kernel.volta(5) == "nada"  # uma pergunta por vez: espera a resposta

    dizer(kernel, "é a gerente financeira do cliente da padaria")
    assert 'Guardei isso sobre "Marcela"' in falas(kernel)[-1]
    dizer(kernel, "o que você sabe sobre a Marcela")
    assert "gerente financeira" in falas(kernel)[-1]

    relogio.avancar(hours=2)
    kernel.impulsos.valores["curiosidade"] = 0.9
    assert kernel.volta(5) == "nada"               # você saiu: ele não fica perguntando para ninguém
    dizer(kernel, "voltei")
    relogio.avancar(minutes=5)
    kernel.impulsos.valores["curiosidade"] = 0.9
    assert kernel.volta(5) == "procurar_novidade"  # não repete a mesma pergunta
    assert kernel.impulsos.valores["curiosidade"] < 0.9


def test_sem_autonomia_ele_nao_toma_iniciativa(kernel):
    kernel.cfg.nucleo.autonomia = False
    kernel.impulsos.valores["curiosidade"] = 1.0
    for i in range(20):
        kernel.memoria.guardar(f"nota {i}")
    assert kernel.volta(5) == "sem autonomia"
    assert kernel.memoria.por_organizar() == 20


def test_pedido_sem_resposta_expira(kernel, monkeypatch):
    dizer(kernel, "abre a calculadora")
    monkeypatch.setattr(kernel.seguranca, "_relogio", lambda: 10 ** 12)
    kernel.volta(5)
    assert "expirou sem resposta" in falas(kernel)[-1] and kernel.seguranca.pendentes() == []


def test_arquivo_desligar_para_o_laco(kernel):
    parou = []
    kernel.ao_desligar = lambda: parou.append(True)
    (kernel.cfg.dados / "DESLIGAR").write_text("x")
    assert kernel.volta(5) == "desligar"
    assert parou == [True]
    assert kernel.registro.ultimos(1)[0]["motivo"] == "arquivo DESLIGAR"


def test_codigo_de_seguranca_alterado_liga_o_modo_seguro(cfg, relogio, monkeypatch):
    from kernel.nucleo import Kernel

    monkeypatch.setattr(integridade, "verificar", lambda: (False, ["alterado: permissoes.py"]))
    kernel = Kernel(cfg, relogio=relogio, lancar=lambda alvo: None)
    assert kernel.estado()["modo_seguro"] and not kernel.estado()["autonomia"]
    asyncio.run(kernel.receber("abre a calculadora"))
    assert "modo seguro" in falas(kernel)[-1] and kernel.seguranca.pendentes() == []
    assert kernel.volta(5) == "sem autonomia"
    kernel.fechar()


def test_estado_e_impulsos_sobrevivem_ao_reinicio(cfg, relogio):
    from kernel.nucleo import Kernel

    primeiro = Kernel(cfg, relogio=relogio)
    primeiro.impulsos.valores["curiosidade"] = 0.37
    primeiro.termos_perguntados.add("marcela")
    primeiro.desligar("teste")
    primeiro.fechar()
    segundo = Kernel(cfg, relogio=relogio)
    assert segundo.impulsos.valores["curiosidade"] == 0.37
    assert "marcela" in segundo.termos_perguntados
    segundo.fechar()


def test_defeito_ao_tratar_a_mensagem_vira_aviso_e_nao_erro(kernel, monkeypatch):
    """Se o tratamento quebrasse com erro 500, a página devolveria o texto ao campo e a fala iria em dobro."""
    def quebrar(texto):
        raise RuntimeError("defeito de mentira")

    monkeypatch.setattr(kernel.classificador, "classificar", quebrar)
    dizer(kernel, "abre a calculadora")                       # não levanta
    assert falas(kernel, "voce") == ["abre a calculadora"]     # a sua fala ficou registrada uma vez só
    assert "erro interno" in falas(kernel)[-1]
    erros = [e for e in kernel.registro.ultimos(10) if e["tipo"] == "erro"]
    assert erros and "defeito de mentira" in erros[-1]["erro"]


def test_bancos_do_servico_em_modo_wal(kernel):
    for banco in (kernel.memoria, kernel.mapa, kernel.pesquisador):
        assert banco._bd.execute("PRAGMA journal_mode").fetchone()[0] == "wal", type(banco).__name__
