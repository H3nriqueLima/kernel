"""Alinhador: descobrir, numa gravação, onde começa e acaba cada fonema.

Para cortar difones de uma gravação é preciso saber o instante de cada som, e a
gravação só vem com o texto. O alinhamento é feito em dois tempos, sem nenhum
modelo pronto:

1. **Pela síntese.** O sintetizador de formantes fala a mesma frase. Dele se sabe
   onde cada fonema cai. As duas falas (a sintética e a gravada) são comparadas
   quadro a quadro por MFCC e casadas no tempo (DTW); os limites conhecidos da
   fala sintética são transportados para a gravação. O resultado é aproximado.
2. **Pela própria voz.** Com esse primeiro corte, calcula-se como soa cada fonema
   *nesta* voz (média e variância dos MFCC, em 1 a 3 estados por fonema). Depois
   cada frase é realinhada contra esses modelos pelo caminho mais provável
   (Viterbi), os modelos são recalculados, e assim algumas vezes. A cada volta os
   limites ficam mais justos. É o treino de um reconhecedor mínimo, só para esta voz.

Entre as palavras pode haver silêncio (a leitora respira onde quer): um estado
"silêncio" opcional absorve essas pausas.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..ouvidos.audio import banco_mel, matriz_dct
from . import fonemas as fon
from . import sintetizador as formantes
from .corpus import reamostrar

TAXA = 16_000
SALTO = 80          # 5 ms
JANELA = 400        # 25 ms
N_FFT = 512
QUADRO = SALTO / TAXA
CENTRO = (JANELA - SALTO) / 2 / TAXA   # o limite entre dois quadros cai 10 ms depois do começo do segundo

# quantos estados cada fonema tem (sons longos e que mudam por dentro ganham mais)
_TRES = set("a A E e i O o u an en in on un f s S v z Z tS dZ".split())
_UM = {"r", "mc", "nc"}
SILENCIO = "#"


def estados_de(fone: str) -> int:
    return 3 if fone in _TRES else 1 if fone in _UM or fone == SILENCIO else 2


def tracos(som: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Som a 16 kHz -> (MFCC + variação no tempo, energia em dB), um quadro a cada 5 ms."""
    som = som.astype(np.float32)
    som = np.append(som[:1], som[1:] - 0.97 * som[:-1])
    quadros = 1 + (len(som) - JANELA) // SALTO
    indices = np.arange(JANELA)[None, :] + SALTO * np.arange(quadros)[:, None]
    janelas = som[indices] * np.hanning(JANELA).astype(np.float32)
    potencia = np.abs(np.fft.rfft(janelas, N_FFT)) ** 2 / N_FFT
    energia = 10 * np.log10(potencia.sum(axis=1) + 1e-10)
    cepstro = np.log(potencia @ banco_mel().T + 1e-8) @ matriz_dct().T
    cepstro = cepstro - cepstro.mean(axis=0)                     # tira o "canal" (microfone, sala)
    cepstro = cepstro / (cepstro.std(axis=0) + 1e-6)
    variacao = np.gradient(cepstro, axis=0)
    variacao = variacao / (variacao.std(axis=0) + 1e-6)
    return np.hstack([cepstro, variacao]).astype(np.float32), energia


def fones_da_frase(texto: str) -> tuple[list[str], list[int]]:
    """Os fonemas da frase (com a marca de tônica) e em que posição começa cada palavra."""
    fones: list[str] = []
    palavras: list[int] = []
    for pedaco in fon.preparar(texto).split():
        for palavra in fon._PALAVRA.findall(pedaco):
            for parte in palavra.split("-"):
                sons = fon.palavra_para_fonemas(parte)
                if sons:
                    palavras.append(len(fones))
                    fones += sons
    return fones, palavras


def pausas(energia: np.ndarray, minimo: int = 30) -> np.ndarray:
    """Verdadeiro nos quadros que estão dentro de um silêncio de pelo menos 150 ms."""
    piso, fala = np.percentile(energia, 5), np.percentile(energia, 95)
    quieto = energia < piso + 0.25 * (fala - piso)
    dentro = np.zeros(len(energia), dtype=bool)
    inicio = 0
    while inicio < len(quieto):
        fim = inicio
        while fim < len(quieto) and quieto[fim] == quieto[inicio]:
            fim += 1
        if quieto[inicio] and fim - inicio >= minimo:
            dentro[inicio:fim] = True
        inicio = fim
    return dentro


def _casar(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """DTW: para cada quadro de ``a``, o quadro de ``b`` que casa com ele."""
    custo = (a ** 2).sum(1)[:, None] + (b ** 2).sum(1)[None, :] - 2 * a @ b.T
    custo = np.sqrt(np.maximum(custo, 0)).astype(np.float32)
    n, m = custo.shape
    desvio = 0.15 * float(custo.mean())           # andar torto (repetir um quadro) custa um pouco
    acumulado = np.empty((n, m), dtype=np.float32)
    acumulado[0] = np.cumsum(custo[0] + desvio)
    for i in range(1, n):
        d = custo[i]
        cima = acumulado[i - 1] + desvio
        diagonal = np.concatenate([[np.inf], acumulado[i - 1, :-1]])
        chegada = np.minimum(cima, diagonal) + d
        prefixo = np.cumsum(d + desvio)
        acumulado[i] = np.minimum.accumulate(chegada - prefixo) + prefixo
    par = np.zeros(n, dtype=np.int64)             # volta do fim ao começo guardando o caminho
    i, j = n - 1, m - 1
    par[i] = j
    while i > 0:
        de_cima = acumulado[i - 1, j] + desvio
        da_diagonal = acumulado[i - 1, j - 1] if j > 0 else np.inf
        do_lado = acumulado[i, j - 1] + desvio if j > 0 else np.inf
        if do_lado < de_cima and do_lado < da_diagonal:
            j -= 1
        elif da_diagonal <= de_cima:
            i, j = i - 1, j - 1
            par[i] = j
        else:
            i -= 1
            par[i] = j
    return par


def pela_sintese(tr: np.ndarray, energia: np.ndarray, fones: list[str]) -> np.ndarray | None:
    """Primeiro corte: limites dos fonemas (em quadros da gravação) copiados da fala sintética."""
    referencia = fones + ["."]
    sintetica = formantes.sintetizar_fonemas(referencia, tom=200.0, escala=1.17)
    tr_ref, _ = tracos(reamostrar(sintetica, formantes.TAXA, TAXA))
    fala = ~pausas(energia)                         # tira as pausas longas antes de casar
    if fala.sum() < 20 or len(tr_ref) < 20:
        return None
    onde = np.where(fala)[0]
    par = _casar(tr_ref[::2], tr[onde][::2])        # a cada 10 ms basta para o primeiro corte
    limites = np.zeros(len(fones) + 1, dtype=np.int64)
    for posicao, inicio, fim in formantes.duracoes(referencia):
        if posicao < len(fones):
            q = min(int(inicio / QUADRO) // 2, len(par) - 1)
            limites[posicao] = onde[min(par[q] * 2, len(onde) - 1)]
    limites[-1] = onde[-1] + 1
    limites = np.maximum.accumulate(limites)
    return limites


class Modelos:
    """Como soa cada estado de cada fonema nesta voz: média e variância dos traços."""

    def __init__(self, dimensao: int):
        self.nomes: dict[tuple[str, int], int] = {}
        self.media = np.zeros((0, dimensao), dtype=np.float64)
        self.variancia = np.ones((0, dimensao), dtype=np.float64)
        self.dimensao = dimensao

    def indice(self, fone: str, estado: int) -> int:
        chave = (fone, estado)
        if chave not in self.nomes:
            self.nomes[chave] = len(self.nomes)
            self.media = np.vstack([self.media, np.zeros((1, self.dimensao))])
            self.variancia = np.vstack([self.variancia, np.ones((1, self.dimensao))])
        return self.nomes[chave]

    def verossimilhanca(self, tr: np.ndarray) -> np.ndarray:
        """log P(quadro | estado) para todo quadro e todo estado: matriz (quadros, estados)."""
        saida = np.empty((len(tr), len(self.nomes)), dtype=np.float32)
        for k in range(len(self.nomes)):
            desvio = (tr - self.media[k]) ** 2 / self.variancia[k]
            saida[:, k] = -0.5 * (desvio.sum(axis=1) + np.log(self.variancia[k]).sum())
        return saida


def _cadeia(fones: list[str], palavras: list[int], modelos: Modelos):
    """A fila de estados da frase: silêncio opcional antes de cada palavra e no fim."""
    de_palavra = set(palavras)
    ids, opcional, dono = [], [], []
    for i, fone in enumerate(fones):
        if i in de_palavra:
            ids.append(modelos.indice(SILENCIO, 0)); opcional.append(True); dono.append(-1)
        limpo = fone.lstrip("'")
        for e in range(estados_de(limpo)):
            ids.append(modelos.indice(limpo, e)); opcional.append(False); dono.append(i)
    ids.append(modelos.indice(SILENCIO, 0)); opcional.append(True); dono.append(-1)
    return np.array(ids), np.array(opcional), np.array(dono)


def viterbi(tr: np.ndarray, fones: list[str], palavras: list[int], modelos: Modelos):
    """O caminho mais provável pelos estados. Devolve (estado de cada quadro, dono, ids, nota por quadro)."""
    ids, opcional, dono = _cadeia(fones, palavras, modelos)
    S, T = len(ids), len(tr)
    if T < (~opcional).sum():
        return None
    ll = modelos.verossimilhanca(tr)[:, ids]
    menos = np.float32(-1e30)
    delta = np.full(S, menos, dtype=np.float32)
    delta[0] = ll[0, 0]
    if opcional[0]:
        delta[1] = ll[0, 1]
    pode_pular = np.concatenate([[False, False], opcional[1:-1]])   # chega em s vindo de s-2 se s-1 é opcional
    veio = np.zeros((T, S), dtype=np.int8)
    for t in range(1, T):
        avanca = np.concatenate([[menos], delta[:-1]])
        pula = np.where(pode_pular, np.concatenate([[menos, menos], delta[:-2]]), menos)
        opcoes = np.stack([delta, avanca, pula])
        veio[t] = opcoes.argmax(axis=0)
        delta = opcoes.max(axis=0) + ll[t]
    s = S - 1 if (not opcional[-1] or delta[-1] >= delta[-2]) else S - 2
    nota = float(delta[s]) / T
    caminho = np.zeros(T, dtype=np.int64)
    for t in range(T - 1, -1, -1):
        caminho[t] = s
        s -= int(veio[t, s])
    return caminho, dono, ids, nota, ll


@dataclass
class Alinhamento:
    fones: list[str]         # com a marca de tônica
    inicio: np.ndarray       # segundos
    fim: np.ndarray
    meio: np.ndarray         # onde cortar o fonema em duas metades
    nota: np.ndarray         # quão bem cada fonema casou com o seu modelo
    pausa_antes: np.ndarray  # havia silêncio colado antes deste fonema?
    pausa_depois: np.ndarray
    media: float             # nota média da frase


def _limites_do_caminho(caminho, dono, n_fones):
    inicio = np.full(n_fones, -1, dtype=np.int64)
    fim = np.full(n_fones, -1, dtype=np.int64)
    donos = dono[caminho]
    mudou = np.concatenate([[True], donos[1:] != donos[:-1]])
    comecos = np.where(mudou)[0]
    finais = np.concatenate([comecos[1:], [len(caminho)]])
    for a, b in zip(comecos, finais):
        if donos[a] >= 0:
            inicio[donos[a]], fim[donos[a]] = a, b
    return inicio, fim


def alinhar_corpus(itens: list[tuple[np.ndarray, str]], iteracoes: int = 4, avisar=print) -> list[Alinhamento | None]:
    """Alinha todas as frases (som a 16 kHz, texto). Devolve um alinhamento por frase, ou None onde falhou."""
    preparados = []
    for k, (som, texto) in enumerate(itens):
        fones, palavras = fones_da_frase(texto)
        tr, energia = tracos(som)
        limites = pela_sintese(tr, energia, fones) if len(fones) >= 3 else None
        preparados.append((tr, energia, fones, palavras, limites))
        if (k + 1) % 25 == 0:
            avisar(f"  primeiro corte (pela síntese): {k + 1} de {len(itens)} frases")
    dimensao = next(p[0].shape[1] for p in preparados)
    modelos = Modelos(dimensao)

    # modelos iniciais: os quadros de cada fonema repartidos por igual entre os seus estados
    soma: dict[int, np.ndarray] = {}
    quadrado: dict[int, np.ndarray] = {}
    conta: dict[int, int] = {}

    def acumular(indice, quadros):
        if len(quadros):
            soma[indice] = soma.get(indice, 0) + quadros.sum(axis=0, dtype=np.float64)
            quadrado[indice] = quadrado.get(indice, 0) + (quadros.astype(np.float64) ** 2).sum(axis=0)
            conta[indice] = conta.get(indice, 0) + len(quadros)

    def reestimar():
        geral = np.mean([quadrado[i] / conta[i] - (soma[i] / conta[i]) ** 2 for i in soma], axis=0)
        for indice in soma:
            media = soma[indice] / conta[indice]
            modelos.media[indice] = media
            modelos.variancia[indice] = np.maximum(quadrado[indice] / conta[indice] - media ** 2, 0.05 * geral)
        soma.clear(); quadrado.clear(); conta.clear()

    for tr, energia, fones, palavras, limites in preparados:
        if limites is None:
            continue
        acumular(modelos.indice(SILENCIO, 0), tr[pausas(energia)])
        for i, fone in enumerate(fones):
            limpo = fone.lstrip("'")
            n = estados_de(limpo)
            cortes = np.linspace(limites[i], limites[i + 1], n + 1).astype(int)
            for e in range(n):
                acumular(modelos.indice(limpo, e), tr[cortes[e]:cortes[e + 1]])
    for fone in {f.lstrip("'") for p in preparados for f in p[2]} | {SILENCIO}:   # estados que ficaram sem quadro
        for e in range(estados_de(fone)):
            indice = modelos.indice(fone, e)
            if indice not in soma:
                acumular(indice, np.zeros((1, dimensao), dtype=np.float32))
    reestimar()

    resultados: list = [None] * len(preparados)
    for volta in range(iteracoes):
        notas = []
        for k, (tr, energia, fones, palavras, limites) in enumerate(preparados):
            if limites is None:
                continue
            achado = viterbi(tr, fones, palavras, modelos)
            if achado is None:
                resultados[k] = None
                continue
            caminho, dono, ids, nota, ll = achado
            resultados[k] = (caminho, dono, ids, nota, ll[np.arange(len(caminho)), caminho].copy())
            notas.append(nota)
            for indice in np.unique(ids[caminho]):
                acumular(int(indice), tr[ids[caminho] == indice])
        reestimar()
        avisar(f"  realinhamento {volta + 1} de {iteracoes}: verossimilhança média por quadro {np.mean(notas):.2f}")

    saida: list[Alinhamento | None] = []
    for (tr, energia, fones, palavras, limites), resultado in zip(preparados, resultados):
        if resultado is None:
            saida.append(None)
            continue
        caminho, dono, ids, nota, por_quadro = resultado
        inicio, fim = _limites_do_caminho(caminho, dono, len(fones))
        if (inicio < 0).any():
            saida.append(None)
            continue
        notas_dos_fones = np.array([por_quadro[a:b].mean() for a, b in zip(inicio, fim)])
        meio = (inicio + fim) / 2.0
        for i, fone in enumerate(fones):            # oclusivas: corta no fim do fechamento, antes do estouro
            if fone.lstrip("'") in formantes.OCLUSIVAS:
                do_fone = np.where(dono[caminho] == i)[0]
                estouro = do_fone[ids[caminho[do_fone]] == modelos.indice(fone.lstrip("'"), 1)]
                if len(estouro):
                    meio[i] = max(inicio[i] + 0.5, estouro[0] - 1.0)
        em_silencio = dono[caminho] < 0
        antes = np.array([a > 0 and em_silencio[a - 1] for a in inicio]) | (inicio == 0)
        depois = np.array([b < len(caminho) and em_silencio[b] for b in fim]) | (fim == len(caminho))
        saida.append(Alinhamento(fones, inicio * QUADRO + CENTRO, fim * QUADRO + CENTRO, meio * QUADRO + CENTRO,
                                 notas_dos_fones, antes, depois, float(nota)))
    return saida
