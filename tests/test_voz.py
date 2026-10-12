"""A voz: as regras de pronúncia e o sintetizador (o que dá para conferir sem ouvidos)."""
import io
import wave

import numpy as np
import pytest

from kernel.voz import fonemas, sintetizador as s


@pytest.mark.parametrize("palavra, esperado", [
    ("casa", "k 'a z A"),                 # s entre vogais vira z; a final fraco
    ("Brasil", "b r a z 'i w"),           # oxítona; l final vira u
    ("leite", "l 'e j tS i"),             # te final vira tchi
    ("cidade", "s i d 'a dZ i"),          # c antes de i; de final vira dji
    ("história", "i s t 'O r i A"),       # h mudo; acento marca a tônica
    ("quando", "k w 'an nc d u"),         # qu + a; vogal nasal fecha numa nasal curta
    ("queijo", "k 'e j Z u"),             # qu + e: u mudo
    ("guerra", "g 'e R A"),               # gu + e; rr forte
    ("gente", "Z 'en nc tS i"),           # g antes de e
    ("juiz", "Z u 'i s"),                 # hiato; z final vira s
    ("ainda", "a 'in nc d A"),
    ("bairro", "b 'a j R u"),             # ditongo antes de rr
    ("pão", "p 'an wn"),                  # ditongo nasal
    ("mãe", "m 'an jn"),
    ("também", "t an mc b 'en jn"),
    ("banho", "b 'A N u"),                # nh; a antes de nasal se fecha
    ("filho", "f 'i L u"),
    ("chave", "S 'a v i"),
    ("exemplo", "e z 'en mc p l u"),      # ex + vogal
    ("caixa", "k 'a j S A"),
    ("táxi", "t 'a k i s i"),             # x = ks, e o k ganha um i
    ("advogado", "a dZ i v o g 'a d u"),  # consoante muda ganha um i
    ("porta", "p 'o R t A"),              # r no fim da sílaba: aspirado
    ("alto", "'a w t u"),
    ("kernel", "k 'E r n e w"),           # o nome dele, pela lista de exceções
    ("você", "v o s 'e"),
    ("HL", "a g 'a 'E l i"),              # sigla sem vogal: soletra
])
def test_pronuncia(palavra, esperado):
    assert " ".join(fonemas.palavra_para_fonemas(palavra)) == esperado


@pytest.mark.parametrize("n, extenso", [
    (0, "zero"), (16, "dezesseis"), (21, "vinte e um"), (100, "cem"), (101, "cento e um"),
    (1000, "mil"), (1249, "mil duzentos e quarenta e nove"), (2026, "dois mil e vinte e seis"),
    (2100, "dois mil e cem"), (1_500_000, "um milhão quinhentos mil"),
])
def test_numeros_por_extenso(n, extenso):
    assert fonemas.por_extenso(n) == extenso


def test_prepara_o_texto_para_a_fala():
    assert fonemas.preparar("São 14:32.") == "São quatorze e trinta e dois ."
    assert fonemas.preparar("15% de 200 = 30") == "quinze por cento de duzentos igual a trinta"
    assert fonemas.preparar("Dá 1.249,5.") == "Dá mil duzentos e quarenta e nove vírgula cinco ."
    assert fonemas.preparar(r"Achei em C:\Users\henri\Meus Documentos\a.txt (12/10/2026)") == "Achei em"
    assert fonemas.preparar("Eu sou o K.E.R.N.E.L.") == "Eu sou o Kernel."
    assert fonemas.texto_para_fonemas("Oi, tudo bem?")[-1] == "?"
    assert fonemas.texto_para_fonemas("") == []


def test_sintetizador_produz_fala_no_formato_certo():
    onda = s.sintetizar("Olá, Henrique. Eu sou o Kernel.")
    assert onda.dtype == np.float32 and 1.5 * s.TAXA < len(onda) < 5 * s.TAXA
    assert 0.8 < np.abs(onda).max() <= 0.86 and abs(float(onda.mean())) < 0.01
    assert len(s.sintetizar("")) == 0
    with wave.open(io.BytesIO(s.falar("sim")), "rb") as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (s.TAXA, 1, 2) and w.getnframes() > 4000
    assert np.array_equal(onda, s.sintetizar("Olá, Henrique. Eu sou o Kernel."))   # mesma frase, mesma onda


def _espectro(fonema, tom=112.0):
    tabela = s._tabela(s._trechos([fonema] * 8, 1.0), tom)
    onda = (s._voz(tabela, np.random.default_rng(0)) + s._chiado(tabela, np.random.default_rng(0)))
    meio = onda[len(onda) // 4: 3 * len(onda) // 4]
    return np.fft.rfftfreq(len(meio), 1 / s.TAXA), np.abs(np.fft.rfft(meio * np.hanning(len(meio))))


def _energia(freq, espectro, de, ate):
    return float((espectro[(freq >= de) & (freq < ate)] ** 2).sum())


def test_cada_vogal_tem_os_formantes_no_lugar():
    def parte(fonema, de, ate):
        freq, espectro = _espectro(fonema)
        return _energia(freq, espectro, de, ate) / _energia(freq, espectro, 0, 12000)   # fração da energia

    # "i": segundo formante lá em cima (2250 Hz); "u": lá embaixo (800 Hz); "a": primeiro formante alto (760 Hz)
    assert parte("i", 1900, 2700) > 20 * parte("u", 1900, 2700)
    assert parte("u", 600, 1000) > 5 * parte("i", 600, 1000)
    assert parte("a", 600, 900) > 5 * parte("i", 600, 900)


def test_voz_tem_harmonicos_e_chiado_tem_ruido_agudo():
    freq, a = _espectro("a", tom=120.0)
    pico = freq[np.argmax(a)]
    assert abs(pico / 120.0 - round(pico / 120.0)) < 0.06         # a energia está em múltiplos do tom
    freq, sibilo = _espectro("s")
    assert _energia(freq, sibilo, 4500, 9000) > 20 * _energia(freq, sibilo, 0, 2000)
    freq, chiado = _espectro("S")
    assert _energia(freq, chiado, 2200, 4600) > _energia(freq, chiado, 5500, 9000)   # "ch" é mais grave que "s"


def test_pergunta_sobe_e_afirmacao_desce():
    def tom_final(frase):
        tabela = s._tabela(s._trechos(fonemas.texto_para_fonemas(frase), 1.0), 112.0)
        falado = np.where(tabela["voz"] > 0.3)[0]
        return tabela["tom"][falado[-1]], tabela["tom"][falado[len(falado) // 2]]

    fim, meio = tom_final("Você chega agora?")
    assert fim > meio * 1.1
    fim, meio = tom_final("Você chega agora.")
    assert fim < meio * 0.95


def test_e_rapido_o_bastante_para_conversar():
    import time

    inicio = time.time()
    onda = s.sintetizar("Explorei quinze pastas e li três arquivos novos hoje, enquanto você estava fora.")
    assert time.time() - inicio < 0.6 * len(onda) / s.TAXA       # bem mais rápido que o tempo real
