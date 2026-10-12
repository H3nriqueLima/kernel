"""Tom, marcas de período e PSOLA, conferidos em sons de que se sabe a resposta."""
import numpy as np
import pytest

from kernel.voz import marcas as m
from kernel.voz import psola
from kernel.voz import sintetizador as s

TAXA = 22050


def vogal(frequencia: float, segundos: float = 0.8, taxa: int = TAXA, vibrato: float = 0.0) -> np.ndarray:
    """Uma "voz" de mentira: harmônicos com um formante em 800 Hz, de tom conhecido."""
    t = np.arange(int(segundos * taxa)) / taxa
    fase = 2 * np.pi * np.cumsum(frequencia * (1 + vibrato * np.sin(2 * np.pi * 4 * t))) / taxa
    som = np.zeros_like(t)
    for k in range(1, 20):
        f = k * frequencia
        som += np.sin(k * fase) / (1 + ((f - 800) / 250) ** 2) / k ** 0.3
    return (0.5 * som / np.abs(som).max()).astype(np.float32)


def tom_medido(som: np.ndarray, taxa: int = TAXA) -> float:
    f0 = m.tom(som, taxa)
    return float(np.median(f0[f0 > 0]))


@pytest.mark.parametrize("frequencia", [140.0, 200.0, 310.0])
def test_mede_o_tom_de_um_som_periodico(frequencia):
    f0 = m.tom(vogal(frequencia), TAXA)
    assert (f0 > 0).mean() > 0.9
    assert abs(np.median(f0[f0 > 0]) - frequencia) < 0.02 * frequencia


def test_ruido_e_silencio_nao_tem_tom():
    sorteio = np.random.default_rng(0)
    ruido = (0.2 * sorteio.normal(size=TAXA)).astype(np.float32)
    assert (m.tom(ruido, TAXA) > 0).mean() < 0.1
    misto = np.concatenate([vogal(200.0, 0.5), np.zeros(TAXA // 2, dtype=np.float32), vogal(200.0, 0.5)])
    f0 = m.tom(misto, TAXA)
    meio = slice(int(0.6 / m.SALTO), int(0.9 / m.SALTO))
    assert (f0[meio] == 0).all() and (f0[:int(0.4 / m.SALTO)] > 0).mean() > 0.9


def test_marcas_caem_uma_por_periodo():
    som = np.concatenate([vogal(200.0, 0.6, vibrato=0.03), (0.1 * np.random.default_rng(1).normal(size=TAXA // 3)).astype(np.float32)])
    posicoes, de_voz = m.marcas(som, TAXA)
    assert (np.diff(posicoes) > 0).all()
    periodos = np.diff(posicoes[de_voz])
    periodos = periodos[periodos < TAXA / 100]                      # só dentro do trecho com voz
    assert abs(np.median(periodos) - TAXA / 200.0) < 3              # um período de 200 Hz (110 amostras)
    assert periodos.std() < 8                                        # acompanha o vibrato, sem pular período
    sem_voz = np.diff(posicoes[~de_voz])
    assert abs(np.median(sem_voz) - TAXA * m.SALTO) <= 1             # no ruído, de 5 em 5 ms


def test_psola_sem_mudanca_devolve_o_mesmo_som():
    som = vogal(180.0, vibrato=0.02)
    posicoes, de_voz = m.marcas(som, TAXA)
    igual = psola.modificar(som, TAXA, posicoes, de_voz)
    meio = slice(TAXA // 10, len(som) - TAXA // 10)
    assert abs(len(igual) - len(som)) <= 2
    assert np.corrcoef(som[meio], igual[meio][:len(som[meio])])[0, 1] > 0.98


@pytest.mark.parametrize("fator", [0.75, 1.3, 1.6])
def test_psola_muda_o_tom_e_mantem_a_duracao_e_o_timbre(fator):
    som = vogal(200.0)
    posicoes, de_voz = m.marcas(som, TAXA)
    novo = psola.modificar(som, TAXA, posicoes, de_voz, tom=fator, f0=m.tom(som, TAXA))
    assert abs(len(novo) - len(som)) <= 2
    assert abs(tom_medido(novo) - 200.0 * fator) < 0.03 * 200.0 * fator

    def formante(x):  # onde está o pico do espectro (o "timbre" do som de teste: 800 Hz)
        meio = x[len(x) // 4: 3 * len(x) // 4]
        espectro = np.abs(np.fft.rfft(meio * np.hanning(len(meio))))
        freq = np.fft.rfftfreq(len(meio), 1 / TAXA)
        faixa = (freq > 400) & (freq < 1400)
        return float((freq[faixa] * espectro[faixa] ** 2).sum() / (espectro[faixa] ** 2).sum())

    assert abs(formante(novo) - formante(som)) < 90                  # o tom mudou; o formante ficou


@pytest.mark.parametrize("fator", [0.6, 1.5, 2.0])
def test_psola_muda_a_duracao_e_mantem_o_tom(fator):
    som = vogal(220.0)
    posicoes, de_voz = m.marcas(som, TAXA)
    novo = psola.modificar(som, TAXA, posicoes, de_voz, duracao=fator)
    assert abs(len(novo) - fator * len(som)) < 0.02 * len(som)
    assert abs(tom_medido(novo) - 220.0) < 5
    assert 0.5 < np.sqrt((novo ** 2).mean()) / np.sqrt((som ** 2).mean()) < 1.6   # sem estourar nem sumir


def test_psola_cola_dois_pedacos_com_duracoes_e_tom_alvo():
    a, b = vogal(180.0, 0.5), vogal(260.0, 0.5)
    ma, va = m.marcas(a, TAXA)
    mb, vb = m.marcas(b, TAXA)
    pedacos = [psola.Pedaco(a, ma, va, TAXA // 10, 4 * TAXA // 10, duracao=0.4),
               psola.Pedaco(b, mb, vb, TAXA // 10, 4 * TAXA // 10, duracao=0.2)]
    alvo = np.full(int(0.6 / 0.005), 210.0)                          # os dois pedaços passam a ter 210 Hz
    novo = psola.sintetizar(pedacos, TAXA, alvo)
    assert abs(len(novo) - 0.6 * TAXA) < 10
    assert abs(tom_medido(novo[:int(0.38 * TAXA)]) - 210.0) < 6
    assert abs(tom_medido(novo[int(0.42 * TAXA):]) - 210.0) < 6
    assert np.abs(novo).max() < 1.0 and np.isfinite(novo).all()


def test_marcas_e_psola_na_fala_do_sintetizador():
    """Um som mais parecido com fala: vogais, chiados e silêncio, a 24 kHz."""
    som = s.sintetizar("A casa azul fica em cima da serra.", tom=190.0, escala=1.15)
    f0 = m.tom(som, s.TAXA)
    assert 0.3 < (f0 > 0).mean() < 0.95 and abs(np.median(f0[f0 > 0]) - 190) < 30
    posicoes, de_voz = m.marcas(som, s.TAXA, f0)
    lento = psola.modificar(som, s.TAXA, posicoes, de_voz, duracao=1.4, tom=1.2, f0=f0)
    assert abs(len(lento) - 1.4 * len(som)) < 0.03 * len(som)
    f0_novo = m.tom(lento, s.TAXA)
    assert abs(np.median(f0_novo[f0_novo > 0]) / np.median(f0[f0 > 0]) - 1.2) < 0.08
