from datetime import datetime

from kernel.memoria import Memoria, bm25
from kernel.memoria.texto import termos


def test_termos_tira_acento_plural_e_palavras_vazias():
    assert termos("As Reuniões com os clientes") == ["reuniao", "cliente"]
    assert termos("o que é isso?") == []


def test_idf_vale_mais_para_termo_raro():
    assert bm25.idf(100, 1) > bm25.idf(100, 50) > 0


def test_pontuacao_satura_e_desconta_texto_longo():
    uma, duas, dez = (bm25.pontuacao(tf, 10, 10, 1.0) for tf in (1, 2, 10))
    assert uma < duas < dez < 2.5 * uma           # repetir o termo rende cada vez menos
    assert bm25.pontuacao(1, 50, 10, 1.0) < uma   # mesma contagem num texto maior vale menos


def test_busca_acha_a_memoria_certa(tmp_path):
    m = Memoria(tmp_path / "m.db")
    m.guardar("O contador pediu as notas fiscais de setembro")
    alvo = m.guardar("A senha do wifi do escritório está no caderno azul")
    m.guardar("Reunião com o cliente da padaria na sexta")
    achados = m.buscar("qual a senha do wifi?")
    assert achados[0].id == alvo
    assert m.buscar("unicórnio") == []
    assert m.buscar("de a o") == []  # só palavras vazias


def test_termos_em_comum_ignoram_palavras_que_estao_em_toda_parte(tmp_path):
    m = Memoria(tmp_path / "m.db")
    for i in range(20):
        m.guardar(f"hoje o dia foi {i}")
    alvo = m.guardar("hoje troquei o disco do servidor")
    achados = {a.id: a for a in m.buscar("hoje o servidor ficou sem disco", k=30)}
    assert achados[alvo].em_comum == 2                       # servidor e disco; "hoje" está em todas
    assert all(a.em_comum == 0 for id_, a in achados.items() if id_ != alvo)


def test_busca_filtra_por_tipo_e_ignora_ids(tmp_path):
    m = Memoria(tmp_path / "m.db")
    fato = m.guardar("o servidor reinicia toda segunda", tipo="fato")
    conversa = m.guardar("o servidor caiu hoje", tipo="conversa")
    assert [a.id for a in m.buscar("servidor", tipos=("fato",))] == [fato]
    assert [a.id for a in m.buscar("servidor", ignorar=(fato,))] == [conversa]


def test_lembretes_vencem_e_sao_marcados(tmp_path):
    m = Memoria(tmp_path / "m.db")
    cedo = m.guardar("pagar boleto", tipo="lembrete", quando="2026-10-12T09:00:00")
    m.guardar("ligar para o banco", tipo="lembrete", quando="2026-10-12T18:00:00")
    m.guardar("comprar café", tipo="lembrete")
    vencidos = m.lembretes_vencidos(datetime(2026, 10, 12, 10, 0))
    assert [l.id for l in vencidos] == [cedo]
    m.marcar_feito(cedo)
    assert m.lembretes_vencidos(datetime(2026, 10, 12, 10, 0)) == []
    assert len(m.lembretes()) == 2


def test_organizar_apaga_repetidas(tmp_path):
    m = Memoria(tmp_path / "m.db")
    m.guardar("comprar pão")
    m.guardar("Comprar  pão")   # mesma coisa com outra caixa e espaço
    m.guardar("comprar leite")
    assert m.por_organizar() == 3
    assert m.organizar() == {"repetidas_apagadas": 1, "arrumadas": 2}
    assert m.por_organizar() == 0
    assert m.contar()["total"] == 2
    assert len(m.buscar("pão")) == 1  # o índice também foi limpo


def test_leitor_de_fora_nao_trava_quem_grava(tmp_path):
    """Um script lendo o banco (ou uma cópia de segurança) não pode fazer o serviço esperar 5 s e falhar."""
    import sqlite3
    import time

    memoria = Memoria(tmp_path / "kernel.db")
    memoria.guardar("A reunião com o cliente é na sexta.")
    assert memoria._bd.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    leitor = sqlite3.connect(str(tmp_path / "kernel.db"))
    leitor.execute("BEGIN")
    assert leitor.execute("SELECT COUNT(*) FROM memorias").fetchone()[0] == 1   # leitura aberta, segurando o banco
    try:
        t0 = time.time()
        memoria.guardar("O relatório sai na segunda.")
        assert time.time() - t0 < 1.0
        assert leitor.execute("SELECT COUNT(*) FROM memorias").fetchone()[0] == 1   # o leitor vê o seu retrato
    finally:
        leitor.rollback()
        leitor.close()
    assert memoria._bd.execute("SELECT COUNT(*) FROM memorias").fetchone()[0] == 2
    memoria.fechar()
