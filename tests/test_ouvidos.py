"""Os ouvidos testados com som sintético (assobios), já que o teste não tem a sua voz."""
import numpy as np

from kernel.ouvidos import audio, escutar, treinar
from kernel.ouvidos.modelo import RedeDeAtivacao

T = np.arange(int(1.5 * audio.TAXA)) / audio.TAXA


def assobio(sorteio, sobe: bool) -> np.ndarray:
    """Um som de 0,5 s no meio de 1,5 s de quase silêncio: sobe (a "palavra") ou desce (outra coisa)."""
    inicio, fim = (600, 1800) if sobe else (1800, 600)
    inicio, fim = inicio * sorteio.uniform(0.9, 1.1), fim * sorteio.uniform(0.9, 1.1)
    comeco = sorteio.uniform(0.3, 0.6)
    dentro = (T >= comeco) & (T < comeco + 0.5)
    frequencia = inicio + (fim - inicio) * np.clip((T - comeco) / 0.5, 0, 1)
    sinal = 0.3 * np.sin(2 * np.pi * np.cumsum(frequencia) / audio.TAXA) * dentro
    return (sinal + sorteio.normal(0, 0.002, len(T))).astype(np.float32)


def test_mfcc_tem_o_formato_esperado():
    quadros = audio.mfcc(np.zeros(audio.AMOSTRAS, dtype=np.float32))
    assert quadros.shape == (98, 13) and audio.ENTRADAS == 98 * 13
    assert audio.caracteristicas(np.zeros(100, dtype=np.float32)).shape == (audio.ENTRADAS,)


def test_banco_mel_poe_cada_tom_na_faixa_certa():
    t = np.arange(audio.AMOSTRAS) / audio.TAXA
    faixa_mais_forte = []
    for hz in (300, 1000, 3000):
        janelas = np.sin(2 * np.pi * hz * t)[:audio.JANELA] * np.hanning(audio.JANELA)
        potencia = np.abs(np.fft.rfft(janelas, audio.N_FFT)) ** 2
        faixa_mais_forte.append(int(np.argmax(audio.banco_mel() @ potencia)))
    assert faixa_mais_forte == sorted(faixa_mais_forte) and len(set(faixa_mais_forte)) == 3


def test_recortar_centra_na_parte_mais_alta():
    sinal = np.zeros(3 * audio.TAXA, dtype=np.float32)
    sinal[2 * audio.TAXA:2 * audio.TAXA + 4000] = 0.5
    trecho = audio.recortar(sinal)
    assert len(trecho) == audio.AMOSTRAS and audio.volume(trecho) > 0.2


def test_wav_vai_e_volta(tmp_path):
    sinal = (0.5 * np.sin(np.linspace(0, 100, 8000))).astype(np.float32)
    audio.gravar_wav(tmp_path / "a.wav", sinal)
    assert np.abs(audio.ler_wav(tmp_path / "a.wav") - sinal).max() < 1e-3


def test_gradiente_da_rede_bate_com_o_numerico():
    sorteio = np.random.default_rng(0)
    rede = RedeDeAtivacao(6, ocultas=(5, 4))
    for i in range(len(rede.pesos)):  # float64 para a conta numérica ter precisão
        rede.pesos[i] = rede.pesos[i].astype(np.float64)
        rede.vieses[i] = sorteio.normal(0, 0.1, rede.vieses[i].shape)
    rede.media, rede.desvio = np.zeros(6), np.ones(6)
    X, y = sorteio.normal(size=(7, 6)), sorteio.integers(0, 2, 7).astype(np.float64)

    def perda():
        p, _ = rede._ida(X)
        return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))

    p, ativacoes = rede._ida(X)
    grad_pesos, grad_vieses = rede._volta(p, y, ativacoes)
    for camada, i, j in [(0, 2, 3), (1, 4, 1), (2, 3, 0)]:
        original = rede.pesos[camada][i, j]
        rede.pesos[camada][i, j] = original + 1e-6
        mais = perda()
        rede.pesos[camada][i, j] = original - 1e-6
        menos = perda()
        rede.pesos[camada][i, j] = original
        assert abs(grad_pesos[camada][i, j] - (mais - menos) / 2e-6) < 1e-6
    assert grad_vieses[0].shape == (5,)


def test_aprende_a_separar_dois_sons_e_salva(tmp_path):
    sorteio = np.random.default_rng(0)
    gravacoes = {
        "positivo": [assobio(sorteio, True) for _ in range(30)],
        "negativo": [assobio(sorteio, False) for _ in range(30)],
        "ruido": [sorteio.normal(0, 0.003, 10 * audio.TAXA).astype(np.float32)],
    }
    rede, medidas = treinar.treinar(gravacoes, copias=6, epocas=25)
    assert medidas["acerto"] > 0.9 and medidas["alarme_falso"] < 0.1, medidas

    rede.salvar(tmp_path / "ativacao.npz")
    outra = RedeDeAtivacao.carregar(tmp_path / "ativacao.npz")
    x = audio.caracteristicas(audio.recortar(assobio(sorteio, True)))
    assert outra.prever(x)[0] == rede.prever(x)[0] > 0.5

    # ponta a ponta: blocos de 0,1 s chegando do "microfone"
    ouvidas = []
    ouvidos = escutar.Ouvidos(outra, limiar=0.8, ao_ouvir=ouvidas.append)
    fluxo = np.concatenate([assobio(sorteio, False), assobio(sorteio, True), np.zeros(audio.TAXA, dtype=np.float32)])
    for n, i in enumerate(range(0, len(fluxo) - escutar.BLOCO + 1, escutar.BLOCO)):
        ouvidos.processar(fluxo[i:i + escutar.BLOCO], agora=n * 0.1)
    assert len(ouvidas) == 1  # disparou uma vez, só para o som certo


def test_detector_exige_repeticao_e_descansa():
    detector = escutar.Detector(limiar=0.8, seguidas=2, descanso=2.0)
    assert detector.avaliar(0.9, 0.0) is False       # uma vez só não basta
    assert detector.avaliar(0.5, 0.1) is False       # a sequência quebrou
    assert detector.avaliar(0.9, 0.2) is False
    assert detector.avaliar(0.95, 0.3) is True       # duas seguidas: disparou
    assert detector.avaliar(0.99, 0.4) is False      # descansando
    assert detector.avaliar(0.99, 1.0) is False
    assert detector.avaliar(0.9, 2.4) is False and detector.avaliar(0.9, 2.5) is True
