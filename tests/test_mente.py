from datetime import datetime

from kernel.config import ConfigMente
from kernel.memoria import Memoria
from kernel.mente import Diario, Impulsos, Percepcao
from kernel.registro import Registro

AGORA = datetime(2026, 10, 12, 15, 0)


def percepcao(ocioso=0.0, bagunca=0):
    return Percepcao(agora=AGORA, segundos_ocioso=ocioso, memorias_por_organizar=bagunca)


def test_curiosidade_so_sobe_no_ocio():
    impulsos = Impulsos(ConfigMente())
    impulsos.atualizar(percepcao(ocioso=10), 600)
    assert impulsos.valores["curiosidade"] == 0.0       # conversando: não sobe
    impulsos.atualizar(percepcao(ocioso=120), 600)      # 10 minutos parado
    assert abs(impulsos.valores["curiosidade"] - 0.4) < 1e-9
    assert impulsos.dominante() is None                 # ainda abaixo do limiar: não fazer nada
    impulsos.atualizar(percepcao(ocioso=720), 600)
    assert impulsos.dominante() == "curiosidade"
    impulsos.satisfazer("curiosidade")
    assert impulsos.valores["curiosidade"] == 0.0 and impulsos.dominante() is None


def test_organizacao_acompanha_a_bagunca():
    impulsos = Impulsos(ConfigMente())
    impulsos.atualizar(percepcao(bagunca=5), 5)
    assert impulsos.dominante() is None
    impulsos.atualizar(percepcao(bagunca=12), 5)
    assert impulsos.dominante() == "organizacao"
    impulsos.atualizar(percepcao(bagunca=0), 5)         # arrumou: o impulso some
    assert impulsos.valores["organizacao"] == 0.0


def test_impulsos_voltam_do_arquivo_dentro_dos_limites():
    impulsos = Impulsos(ConfigMente(), {"curiosidade": 7, "organizacao": -1, "fome": 0.5})
    assert impulsos.valores == {"curiosidade": 1.0, "organizacao": 0.0, "social": 0.0}


def test_diario_conta_o_dia(cfg):
    relogio = lambda: AGORA  # noqa: E731
    registro = Registro(cfg.pasta("registro"), relogio)
    memoria = Memoria(cfg.dados / "kernel.db", relogio)
    registro.anotar("mensagem", autor="voce", classe="fala", texto="abre a calculadora")
    registro.anotar("mensagem", autor="voce", classe="fala", texto="hoje foi corrido")
    registro.anotar("intencao", texto="hmm talvez", intencao="conversa", confianca=0.41)
    registro.anotar("acao", ferramenta="abrir_programa", estado="executado", resultado="Abri calculadora.")
    registro.anotar("acao", ferramenta="listar_pasta", estado="falhou", resultado="Não consegui: sumiu")
    registro.anotar("confirmacao", resposta="negado")
    registro.anotar("memoria", classe="conversa")
    registro.anotar("laco", impulso="organizacao", decisao="organizar")
    registro.anotar("pulso", impulsos={"curiosidade": 0.2, "organizacao": 0.6})
    registro.anotar("pulso", impulsos={"curiosidade": 0.4, "organizacao": 0.0})
    memoria.guardar("comprar café", tipo="lembrete")

    diario = Diario(cfg, registro, memoria, relogio)
    texto = diario.escrever(AGORA.date())
    assert "segunda-feira, 12 de outubro de 2026" in texto
    assert "Henrique falou comigo 2 vezes." in texto
    assert "Executei 1 ação (abrir_programa × 1)." in texto
    assert "Henrique negou 1 pedido." in texto
    assert "arrumei a memória 1 vez." in texto
    assert "1 memória nova: 1 de conversa." in texto
    assert "Curiosidade: média 0.30, pico 0.40." in texto
    assert "listar_pasta: Não consegui: sumiu" in texto
    assert 'frases como "hmm talvez"' in texto
    assert "1 lembrete pendente: comprar café." in texto
    assert diario.ler(AGORA.date()) == texto
    assert memoria.buscar("diário", tipos=("diario",))  # amanhã ele lembra de hoje


def test_diario_fica_pendente_ate_o_dia_fechar(cfg):
    registro = Registro(cfg.pasta("registro"), lambda: AGORA)
    registro.anotar("servico", evento="inicio")
    diario = Diario(cfg, registro, Memoria(cfg.dados / "kernel.db"), lambda: AGORA)
    assert diario.pendentes(AGORA) == []                                # 15h: o dia ainda não fechou
    assert diario.pendentes(AGORA.replace(hour=23)) == [AGORA.date()]   # hora do diário
    assert diario.pendentes(datetime(2026, 10, 13, 8, 0)) == [AGORA.date()]  # ontem ficou sem diário
