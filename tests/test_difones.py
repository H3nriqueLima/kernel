"""O banco de difones de ponta a ponta, num corpus de mentira: as "gravações" são frases ditas
pelo sintetizador de formantes com outra voz. Dá para conferir tudo sem baixar nada."""
import numpy as np
import pytest

from kernel import voz
from kernel.voz import corpus, difones, marcas
from kernel.voz import sintetizador as s
from test_alinhador import FRASES


@pytest.fixture(scope="module")
def banco(tmp_path_factory):
    sorteio = np.random.default_rng(5)
    gravacoes = []
    for frase in FRASES:
        som = s.sintetizar(frase, tom=190.0, escala=1.12, velocidade=0.9, semente=int(sorteio.integers(99)))
        som = corpus.reamostrar(som, s.TAXA, difones.TAXA)
        gravacoes.append((som + sorteio.normal(0, 0.002, len(som)).astype(np.float32), frase))
    pasta = tmp_path_factory.mktemp("banco")
    meta = difones.construir_de(gravacoes, pasta, minutos=10, avisar=lambda _: None, fonte="corpus de teste")
    return difones.Falante(pasta), meta, pasta


def test_o_banco_tem_o_que_foi_gravado(banco):
    falante, meta, pasta = banco
    assert meta["frases"] == len(FRASES) and meta["fonemas"] >= 30 and meta["difones"] > 250
    assert abs(meta["tom"] - 190) < 20                               # o tom da "leitora" de mentira
    assert (pasta / "som.npy").exists() and meta["fonte"] == "corpus de teste"
    u = falante.u
    assert len(u["fone"]) == meta["metades"] and (u["fim"] >= u["ini"]).all()
    assert (np.diff(u["marcas"]) > 0).all()
    # as duas metades de um fonema são vizinhas na gravação: a esquerda sempre "segue" para a direita
    esquerdas = np.where(u["lado"] == 0)[0]
    assert u["segue"][esquerdas].all() and (u["fim"][esquerdas] == u["ini"][esquerdas + 1]).all()


def test_frase_gravada_sai_quase_toda_em_pedacos_vizinhos(banco):
    falante, _, _ = banco
    detalhes = {}
    onda = falante.falar("o menino comprou um livro novo na cidade.", detalhes=detalhes)
    assert onda is not None and 1.5 < len(onda) / falante.taxa < 5
    assert detalhes["naturais"] > 4 * detalhes["emendas"]            # ele reaproveita o trecho original


def test_frase_nova_e_montada_com_emendas(banco):
    falante, _, _ = banco
    detalhes = {}
    onda = falante.falar("O gato comprou uma carta nova.", detalhes=detalhes)
    assert onda is not None and np.isfinite(onda).all() and 0.5 < np.abs(onda).max() <= 0.86
    assert detalhes["emendas"] >= 3 and detalhes["metades"] > 30
    f0 = marcas.tom(onda, falante.taxa)
    assert (f0 > 0).mean() > 0.4                                     # continua sendo fala com voz


def test_altura_velocidade_e_pausas(banco):
    falante, meta, _ = banco

    def tom_de(onda):
        f0 = marcas.tom(onda, falante.taxa)
        return float(np.median(f0[f0 > 0]))

    normal = falante.falar("a casa azul fica em cima da serra.")
    aguda = falante.falar("a casa azul fica em cima da serra.", altura=1.3)
    rapida = falante.falar("a casa azul fica em cima da serra.", velocidade=1.4)
    com_pausa = falante.falar("a casa azul, fica em cima da serra.")
    assert abs(tom_de(normal) / meta["tom"] - 1.0) < 0.12
    assert abs(tom_de(aguda) / tom_de(normal) - 1.3) < 0.1           # o PSOLA impõe o tom pedido
    assert len(rapida) < 0.85 * len(normal)
    assert len(com_pausa) > len(normal) + 0.1 * falante.taxa         # a vírgula vira silêncio


def test_pergunta_termina_mais_aguda_que_afirmacao(banco):
    falante, _, _ = banco

    def fim(frase):
        f0 = marcas.tom(falante.falar(frase), falante.taxa)
        return float(np.median(f0[f0 > 0][-25:]))                    # o último oitavo de segundo com voz

    assert fim("o menino comprou um livro novo?") > 1.2 * fim("o menino comprou um livro novo.")


def test_estilo_robotico_fica_em_poucas_notas(banco):
    falante, meta, _ = banco

    def semitons(estilo):
        f0 = marcas.tom(falante.falar("a lua cheia iluminava todo o caminho.", estilo=estilo), falante.taxa)
        return 12 * np.log2(f0[f0 > 0] / meta["tom"])

    natural, robotica = semitons("natural"), semitons("robotica")
    notas = np.array([-4.0, 0.0, 3.0])                                # as únicas notas do estilo robótico
    perto = lambda x: (np.abs(x[:, None] - notas[None, :]).min(axis=1) < 0.6).mean()   # noqa: E731
    assert perto(robotica) > 0.75 and perto(robotica) > perto(natural) + 0.15


def test_som_que_nao_existe_no_banco_devolve_none(banco):
    falante, _, _ = banco
    falante.indice.pop((falante.numero["S"], 0), None)               # some com o "ch"
    assert falante.falar("a chave") is None
    assert falante.falar("") is not None and len(falante.falar("")) == 0


def test_motor_da_configuracao_e_reserva_de_formantes(cfg, banco):
    _, _, pasta = banco
    cfg.voz.motor = "difones"
    onda, taxa, motor = voz.onda_com(cfg, "bom dia")                  # sem banco em dados/voz/banco
    assert (taxa, motor) == (s.TAXA, "formantes") and len(onda) > 0
    destino = cfg.pasta("voz", "banco")
    for arquivo in pasta.iterdir():
        (destino / arquivo.name).write_bytes(arquivo.read_bytes())
    voz._falantes.clear()
    onda, taxa, motor = voz.onda_com(cfg, "o gato dormia no sofá")
    assert (taxa, motor) == (difones.TAXA, "difones")
    falante = voz.falante_de(cfg)
    falante.indice.pop((falante.numero["S"], 0), None)               # um som some do banco...
    onda, taxa, motor = voz.onda_com(cfg, "a chave está na caixa")
    assert (taxa, motor) == (s.TAXA, "formantes (reserva)")           # ...e a reserva fala a frase inteira
    f0 = marcas.tom(onda, taxa)
    assert abs(np.median(f0[f0 > 0]) / falante.meta["tom"] - 1.0) < 0.2   # na altura da voz gravada, não a 112 Hz
    cfg.voz.motor = "formantes"
    assert voz.onda_com(cfg, "o gato dormia no sofá")[2] == "formantes"
    assert voz.falar_com(cfg, "bom dia")[:4] == b"RIFF"
    voz._falantes.clear()
