"""O alinhador conferido num corpus de mentira: frases ditas pelo sintetizador de formantes com
outra voz, outro ritmo e pausas, das quais se sabe exatamente onde cada fonema começa."""
import numpy as np
import pytest

from kernel.voz import alinhador
from kernel.voz import sintetizador as s
from kernel.voz.corpus import reamostrar

FRASES = [
    "a casa azul fica em cima da serra", "o menino comprou um livro novo na cidade",
    "hoje o dia amanheceu claro e bonito", "ela gosta de cantar quando está sozinha",
    "os barcos voltaram do mar no fim da tarde", "nunca vi tanta gente junta na praça",
    "o velho relógio parou de bater às sete", "chegou uma carta do banco para você",
    "a chuva caiu forte durante a madrugada", "preciso falar com o gerente amanhã cedo",
    "o cachorro correu atrás da bola vermelha", "minha mãe faz um pão muito gostoso",
    "os alunos estudaram para a prova de história", "ninguém sabia onde estava a chave do carro",
    "o trem partiu da estação com atraso", "ela guardou o dinheiro dentro da gaveta",
    "o vento frio balançava as folhas da árvore", "quero um café quente e um copo de água",
    "o médico pediu um exame de sangue", "as crianças brincavam felizes no jardim",
    "o jornal de hoje trouxe uma boa notícia", "ele vendeu a fazenda e mudou de cidade",
    "a lua cheia iluminava todo o caminho", "o professor explicou a lição com paciência",
    "vamos jantar juntos na sexta feira", "o gato dormia tranquilo em cima do sofá",
]
VELOCIDADE = 0.85


@pytest.fixture(scope="module")
def corpus_de_mentira():
    sorteio = np.random.default_rng(3)
    itens, verdade = [], []
    for frase in FRASES:
        fones, palavras = alinhador.fones_da_frase(frase)
        pausa_em = int(sorteio.choice(palavras[2:-1])) if len(palavras) > 4 else -1   # uma pausa no meio da frase
        com_pausa = fones[:pausa_em] + [","] + fones[pausa_em:] if pausa_em > 0 else list(fones)
        tudo = com_pausa + ["."]
        som = s.sintetizar_fonemas(tudo, tom=185.0, escala=1.12, velocidade=VELOCIDADE, semente=int(sorteio.integers(99)))
        limites = [(inicio, fim) for posicao, inicio, fim in s.duracoes(tudo, VELOCIDADE)
                   if tudo[posicao] not in s.PAUSAS]
        som16 = reamostrar(som, s.TAXA, alinhador.TAXA)
        som16 = som16 + sorteio.normal(0, 0.002, len(som16)).astype(np.float32)
        itens.append((som16, frase))
        verdade.append(np.array(limites))
    return itens, verdade


def test_fones_e_palavras():
    fones, palavras = alinhador.fones_da_frase("a casa azul")
    assert [f.lstrip("'") for f in fones] == ["A", "k", "a", "z", "A", "a", "z", "u", "w"] and palavras == [0, 1, 5]
    assert alinhador.estados_de("a") == 3 and alinhador.estados_de("p") == 2 and alinhador.estados_de("r") == 1


def test_pausas_sao_achadas_pela_energia():
    energia = np.concatenate([np.full(100, -20.0), np.full(60, -70.0), np.full(100, -22.0), np.full(10, -70.0),
                              np.full(50, -20.0)])
    dentro = alinhador.pausas(energia)
    assert dentro[110:150].all() and not dentro[:95].any() and not dentro[262:268].any()   # pausa curta não conta


def test_alinha_perto_da_verdade(corpus_de_mentira):
    itens, verdade = corpus_de_mentira
    alinhados = alinhador.alinhar_corpus(itens, iteracoes=3, avisar=lambda _: None)
    assert all(a is not None for a in alinhados)
    erros = []
    for achado, certo in zip(alinhados, verdade):
        assert len(achado.fones) == len(certo)
        assert (achado.fim > achado.inicio).all() and (np.diff(achado.inicio) >= 0).all()
        assert ((achado.meio > achado.inicio) & (achado.meio < achado.fim)).all()
        erros.append(np.abs(achado.inicio - certo[:, 0]))
    erros = np.concatenate(erros)
    assert np.median(erros) < 0.020, f"erro mediano de {np.median(erros) * 1000:.0f} ms"
    assert (erros < 0.050).mean() > 0.85, f"só {(erros < 0.050).mean():.0%} dos limites a menos de 50 ms"

    # a pausa do meio da frase foi percebida como silêncio em quase todas as frases
    com_pausa = sum(a.pausa_antes[1:].any() for a in alinhados)
    assert com_pausa >= 0.7 * len(alinhados)
