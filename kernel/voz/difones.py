"""Síntese por concatenação de difones, com PSOLA.

Um **difone** vai do meio de um fonema ao meio do seguinte: ele carrega a
transição entre dois sons, que é a parte da fala mais difícil de imitar por
regra. O meio dos fonemas é o trecho mais estável, então é ali que se corta e
se emenda.

Aqui cada fonema gravado é guardado em duas **metades** (a esquerda e a direita).
Um difone é a metade direita de um fonema seguida da metade esquerda do próximo,
tiradas do mesmo ponto da gravação. Guardar as metades separadas dá uma saída
quando um difone nunca foi gravado: emendam-se duas metades de lugares
diferentes, pagando um custo maior.

Falar uma frase tem três passos:

1. **Escolher** (``Falante._escolher``): para cada metade pedida há vários
   candidatos no banco. Um caminho mínimo (Viterbi) escolhe a sequência que soma
   menos custo: o custo de alvo (vizinho certo? duração parecida? tônica?) mais o
   custo de emenda (as pontas soam parecidas?). Pedaços que já eram vizinhos na
   gravação emendam de graça, então o caminho prefere trechos longos originais.
2. **Dar a prosódia**: cada metade ganha uma duração-alvo e a frase ganha uma
   curva de tom.
3. **Colar** (``psola.sintetizar``): o PSOLA estica, encolhe e reafina cada
   pedaço e faz as emendas em sincronia com o tom.

É um sistema híbrido: o sintetizador de formantes continua aqui, como molde do
alinhamento que cortou o banco e como voz de reserva quando o banco não existe
ou não tem um som pedido.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import alinhador, corpus, fonemas, marcas, psola
from .sintetizador import PAUSAS

TAXA = 22_050
SILENCIO = "#"
CANDIDATOS = 24
# pesos da escolha (ajustados medindo a distância até gravações reais que ficaram fora do banco)
PESO_DA_NOTA = 0.25       # quanto pesa um corte mal alinhado
PESO_DO_ESPECTRO = 0.30   # quanto pesa o timbre diferente nas duas pontas de uma emenda
CUSTO_NO_LIMITE = 1.5     # emendar na fronteira entre dois fonemas (difone que não existia) custa caro
_VOGAIS = set("a A E e i O o u an en in on un".split())
# famílias de sons: quando falta o vizinho exato, um da mesma família serve melhor que um qualquer
_FAMILIAS = [set("i e E j in en jn".split()), set("a A an".split()), set("u o O w un on wn".split()),
             set("p b m mc".split()), set("t d n nc l r".split()), set("k g R".split()),
             set("f v".split()), set("s z".split()), set("S Z tS dZ L N".split()), {SILENCIO}]
_FAMILIA_DE = {fone: i for i, grupo in enumerate(_FAMILIAS) for fone in grupo}
_RESERVA = {"mc": "m", "nc": "n", "jn": "j", "wn": "w", "A": "a", "E": "e", "O": "o"}   # som parecido, se faltar


# =============================================================== construir
def construir(pasta_do_corpus: Path, destino: Path, frases: int | None = None, minutos: float = 45.0,
              avisar=print) -> dict:
    """Carrega as gravações baixadas e monta o banco em ``destino``."""
    lista = corpus.carregar_lista(pasta_do_corpus)
    lista.sort(key=lambda f: (f["mp3"], f["inicio"]))
    existentes = {a.name for a in (Path(pasta_do_corpus) / "mp3").glob("*.mp3")}
    lista = [f for f in lista if f["mp3"].rsplit("/", 1)[1] in existentes][:frases]
    if not lista:
        raise RuntimeError("não há gravações: rode antes 'python -m kernel voz baixar'")
    capitulos = corpus.Capitulos(Path(pasta_do_corpus) / "mp3")
    avisar(f"carregando {len(lista)} frases...")
    gravacoes = []
    for f in lista:
        som, taxa = capitulos.frase(f)
        gravacoes.append((corpus.reamostrar(som, taxa, TAXA), f["texto"]))
    fonte = ("Leitora 'Leni' (LibriVox, domínio público), 'Senhora' de José de Alencar; cortes e transcrições "
             "do Multilingual LibriSpeech (Pratap et al., 2020, CC BY 4.0).")
    return construir_de(gravacoes, destino, minutos, avisar, fonte)


def _nivel_da_fala(som: np.ndarray) -> float:
    """O volume da fala, sem contar as pausas: a média dos blocos de 10 ms mais fortes."""
    bloco = TAXA // 100
    n = len(som) // bloco
    if n < 5:
        return float(np.sqrt(np.mean(som ** 2)) + 1e-9)
    rms = np.sqrt((som[:n * bloco].reshape(n, bloco) ** 2).mean(axis=1))
    return float(np.sqrt((rms[rms >= np.percentile(rms, 40)] ** 2).mean()) + 1e-9)


def construir_de(gravacoes: list[tuple[np.ndarray, str]], destino: Path, minutos: float = 45.0, avisar=print,
                 fonte: str = "") -> dict:
    """Alinha gravações (som a 22050 Hz, texto), corta as metades de fonema e grava o banco."""
    sons = [som for som, _ in gravacoes]
    itens = [(corpus.reamostrar(som, TAXA, alinhador.TAXA), texto) for som, texto in gravacoes]
    avisar("alinhando (é a parte demorada)...")
    alinhados = alinhador.alinhar_corpus(itens, avisar=avisar)

    # fica com as frases que alinharam melhor, até completar os minutos pedidos
    ordem = sorted((k for k, a in enumerate(alinhados) if a is not None), key=lambda k: -alinhados[k].media)
    escolhidas, total = [], 0.0
    for k in ordem:
        if total >= minutos * 60:
            break
        escolhidas.append(k)
        total += len(sons[k]) / TAXA
    escolhidas.sort()
    avisar(f"{len(escolhidas)} frases entram no banco ({total / 60:.0f} min); cortando...")

    nomes: list[str] = [SILENCIO]
    numero = {SILENCIO: 0}
    colunas: dict[str, list] = {c: [] for c in ("fone", "lado", "vizinho", "tonico", "ini", "fim", "f0_ini", "f0_fim",
                                                "en_ini", "en_fim", "nota", "segue")}
    tr_ini, tr_fim = [], []
    audio, todas_marcas, todas_de_voz = [], [], []
    tons, duracao_por_fone, esquerda_por_fone = [], {}, {}
    base = 0
    for k in escolhidas:
        a, som = alinhados[k], sons[k]
        tr, _ = alinhador.tracos(itens[k][0])
        som = np.clip(som * (0.07 / _nivel_da_fala(som)), -0.98, 0.98)   # todas as frases no mesmo volume
        f0 = marcas.tom(som, TAXA)
        posicoes, de_voz = marcas.marcas(som, TAXA, f0)
        tons.append(f0[f0 > 0])

        def tom_em(t: float) -> float:
            q = int((t - marcas.JANELA / 2) / marcas.SALTO)
            perto = f0[max(q - 2, 0):q + 3]
            return float(np.median(perto[perto > 0])) if (perto > 0).sum() >= 2 else 0.0

        def energia_em(t: float) -> float:
            meio = int(t * TAXA)
            pedaco = som[max(meio - TAXA // 100, 0):meio + TAXA // 100]
            return float(10 * np.log10(np.mean(pedaco ** 2) + 1e-9)) if len(pedaco) else -90.0

        def tracos_em(t: float) -> np.ndarray:
            q = int(round((t - alinhador.CENTRO) / alinhador.QUADRO))
            return tr[max(q - 1, 0):q + 2, :13].mean(axis=0) if 0 <= q < len(tr) else np.zeros(13, dtype=np.float32)

        limpos = [f.lstrip("'") for f in a.fones]
        for i, (fone, limpo) in enumerate(zip(a.fones, limpos)):
            if limpo not in numero:
                numero[limpo] = len(nomes)
                nomes.append(limpo)
            antes = SILENCIO if (i == 0 or a.pausa_antes[i]) else limpos[i - 1]
            depois = SILENCIO if (i == len(limpos) - 1 or a.pausa_depois[i]) else limpos[i + 1]
            for vizinho in (antes, depois):
                if vizinho not in numero:
                    numero[vizinho] = len(nomes)
                    nomes.append(vizinho)
            duracao = a.fim[i] - a.inicio[i]
            # cortes suspeitos ficam fora da escolha, mas continuam na fila para não quebrar a vizinhança
            nota = float(a.nota[i]) if 0.015 <= duracao <= 0.35 else -1e9
            duracao_por_fone.setdefault((limpo, fone.startswith("'")), []).append(duracao)
            esquerda_por_fone.setdefault(limpo, []).append((a.meio[i] - a.inicio[i]) / max(duracao, 1e-3))
            for lado, (t0, t1), vizinho in ((0, (a.inicio[i], a.meio[i]), antes), (1, (a.meio[i], a.fim[i]), depois)):
                colunas["fone"].append(numero[limpo]); colunas["lado"].append(lado)
                colunas["vizinho"].append(numero[vizinho]); colunas["tonico"].append(fone.startswith("'"))
                colunas["ini"].append(base + int(t0 * TAXA)); colunas["fim"].append(base + int(t1 * TAXA))
                colunas["f0_ini"].append(tom_em(t0)); colunas["f0_fim"].append(tom_em(t1))
                colunas["en_ini"].append(energia_em(t0)); colunas["en_fim"].append(energia_em(t1))
                colunas["nota"].append(nota)
                # a metade seguinte na fila é a continuação natural desta? (só não é se houver pausa no meio)
                colunas["segue"].append(lado == 0 or (i < len(limpos) - 1 and not a.pausa_depois[i]))
                tr_ini.append(tracos_em(t0)); tr_fim.append(tracos_em(t1))
        colunas["segue"][-1] = False   # a última metade da frase não continua na frase seguinte
        audio.append((som * 32767).astype(np.int16))
        todas_marcas.append(posicoes + base)
        todas_de_voz.append(de_voz)
        base += len(som)

    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    np.save(destino / "som.npy", np.concatenate(audio))
    np.savez_compressed(
        destino / "unidades.npz", marcas=np.concatenate(todas_marcas), de_voz=np.concatenate(todas_de_voz),
        tr_ini=np.array(tr_ini, dtype=np.float32), tr_fim=np.array(tr_fim, dtype=np.float32),
        **{nome: np.array(valores) for nome, valores in colunas.items()})
    todos_os_tons = np.concatenate(tons)
    fone_ = np.array(colunas["fone"]); lado_ = np.array(colunas["lado"]); viz_ = np.array(colunas["vizinho"])
    boas = np.array(colunas["nota"]) > -1e8
    difones = {(int(f), int(v)) for f, v, lado, boa in zip(fone_, viz_, lado_, boas) if lado == 1 and boa}
    meta = {
        "taxa": TAXA, "nomes": nomes, "tom": float(np.median(todos_os_tons)),
        "tom_baixo": float(np.percentile(todos_os_tons, 10)), "tom_alto": float(np.percentile(todos_os_tons, 90)),
        "duracao": {f"{fone}|{int(tonico)}": float(np.median(v)) for (fone, tonico), v in duracao_por_fone.items()},
        "esquerda": {fone: float(np.median(v)) for fone, v in esquerda_por_fone.items()},
        "nota_mediana": float(np.median(np.array(colunas["nota"])[boas])),
        "frases": len(escolhidas), "minutos": round(base / TAXA / 60, 1), "metades": len(colunas["fone"]),
        "fonemas": len(nomes) - 1, "difones": len(difones),
        "fonte": fonte,
    }
    (destino / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


# ================================================================== falar
class Falante:
    """O banco carregado e pronto para falar."""

    def __init__(self, pasta: Path):
        pasta = Path(pasta)
        self.meta = json.loads((pasta / "meta.json").read_text(encoding="utf-8"))
        self.taxa = self.meta["taxa"]
        # Tudo na RAM (uns 110 MB): os grãos saem de pontos espalhados da gravação, e buscar cada um
        # no disco (ainda mais num HD) deixaria a fala várias vezes mais lenta.
        self.som = np.load(pasta / "som.npy")
        with np.load(pasta / "unidades.npz") as u:
            self.u = {nome: u[nome] for nome in u.files}
        self.nomes: list[str] = self.meta["nomes"]
        self.numero = {nome: i for i, nome in enumerate(self.nomes)}
        self.duracao = np.maximum((self.u["fim"] - self.u["ini"]) / self.taxa, 1e-3)
        self.familia = np.array([_FAMILIA_DE.get(nome, -1) for nome in self.nomes])
        boas = self.u["nota"] > -1e8
        self.indice: dict[tuple[int, int], np.ndarray] = {}
        for chave in {(int(f), int(l)) for f, l in zip(self.u["fone"][boas], self.u["lado"][boas])}:
            self.indice[chave] = np.where(boas & (self.u["fone"] == chave[0]) & (self.u["lado"] == chave[1]))[0]
        # as metades que têm exatamente o vizinho pedido (o difone de verdade) ficam à mão: são as primeiras a concorrer
        self.por_contexto: dict[tuple[int, int, int], np.ndarray] = {}
        ordem = np.lexsort((self.u["vizinho"], self.u["lado"], self.u["fone"]))
        ordem = ordem[boas[ordem]]
        chaves = np.stack([self.u["fone"][ordem], self.u["lado"][ordem], self.u["vizinho"][ordem]], axis=1)
        cortes = np.where(np.any(np.diff(chaves, axis=0) != 0, axis=1))[0] + 1
        for grupo in np.split(ordem, cortes):
            self.por_contexto[(int(self.u["fone"][grupo[0]]), int(self.u["lado"][grupo[0]]), int(self.u["vizinho"][grupo[0]]))] = grupo
        passo = int(self.taxa * marcas.SALTO)
        self._silencio = (np.zeros(self.taxa * 2, dtype=np.float32), np.arange(passo, self.taxa * 2 - passo, passo))

    # ------------------------------------------------------------------ alvos
    def _fone(self, nome: str) -> str | None:
        """O fonema pedido, ou um parecido que exista no banco."""
        for candidato in (nome, _RESERVA.get(nome)):
            if candidato and (self.numero.get(candidato, -1), 0) in self.indice:
                return candidato
        return None

    def _alvos(self, texto: str, velocidade: float) -> list[dict] | None:
        sequencia = fonemas.texto_para_fonemas(texto)
        if not sequencia:
            return []
        alvos: list[dict] = []
        sons = [(s.lstrip("'"), s.startswith("'")) for s in sequencia]
        for i, (bruto, tonico) in enumerate(sons):
            if bruto in PAUSAS:
                alvos.append({"pausa": bruto, "duracao": PAUSAS[bruto] / 1000 / velocidade})
                continue
            nome = self._fone(bruto)
            if nome is None:
                return None  # este som não existe no banco: quem chamou cai na voz de reserva
            antes = sons[i - 1][0] if i > 0 and sons[i - 1][0] not in PAUSAS else SILENCIO
            depois = sons[i + 1][0] if i + 1 < len(sons) and sons[i + 1][0] not in PAUSAS else SILENCIO
            duracao = self.meta["duracao"].get(f"{nome}|{int(tonico)}") or self.meta["duracao"].get(f"{nome}|{int(not tonico)}", 0.07)
            if depois == SILENCIO and nome in _VOGAIS:
                duracao *= 1.25  # a última vogal antes de uma pausa se alonga
            duracao = float(np.clip(duracao, 0.03, 0.22)) / velocidade
            esquerda = float(np.clip(self.meta["esquerda"].get(nome, 0.5), 0.25, 0.75))
            for lado, vizinho, parte in ((0, antes, esquerda), (1, depois, 1 - esquerda)):
                alvos.append({"fone": self.numero[nome], "lado": lado, "tonico": tonico, "nome": nome,
                              "vizinho": self.numero.get(self._fone(vizinho) or vizinho, self.numero[SILENCIO]) if vizinho != SILENCIO else self.numero[SILENCIO],
                              "duracao": duracao * parte, "silaba_final": depois == SILENCIO})
        return alvos

    # ---------------------------------------------------------------- escolha
    def _custo_de_alvo(self, candidatos: np.ndarray, alvo: dict) -> np.ndarray:
        u = self.u
        vizinho = u["vizinho"][candidatos]
        contexto = np.where(vizinho == alvo["vizinho"], 0.0,
                            np.where(self.familia[vizinho] == self.familia[alvo["vizinho"]], 0.6, 1.5))
        duracao = 0.5 * np.abs(np.log(self.duracao[candidatos] / max(alvo["duracao"], 1e-3)))
        tonica = 0.4 * (u["tonico"][candidatos] != alvo["tonico"]) if alvo["nome"] in _VOGAIS else 0.0
        nota = PESO_DA_NOTA * np.clip((self.meta["nota_mediana"] - u["nota"][candidatos]) / 4.0, 0.0, 2.0)
        return contexto + duracao + tonica + nota

    def _custo_de_emenda(self, antes: np.ndarray, depois: np.ndarray, no_limite: bool) -> np.ndarray:
        """Matriz (antes, depois): quanto custa colar cada par. Vizinhos na gravação colam de graça."""
        u = self.u
        natural = (antes[:, None] + 1 == depois[None, :]) & u["segue"][antes][:, None]
        espectro = np.sqrt(((u["tr_fim"][antes][:, None, :] - u["tr_ini"][depois][None, :, :]) ** 2).sum(-1))
        f_a, f_d = u["f0_fim"][antes][:, None], u["f0_ini"][depois][None, :]
        com_voz = (f_a > 0) & (f_d > 0)
        tom = np.abs(np.log(np.where(com_voz, f_a / np.maximum(f_d, 1e-3), 1.0)))
        troca = ((f_a > 0) != (f_d > 0)) * 0.8
        volume = np.abs(u["en_fim"][antes][:, None] - u["en_ini"][depois][None, :]) / 20.0
        custo = PESO_DO_ESPECTRO * espectro + 1.2 * tom + troca + 0.5 * volume + (CUSTO_NO_LIMITE if no_limite else 0.2)
        return np.where(natural, 0.0, custo)

    def _escolher(self, alvos: list[dict]) -> list[int | None]:
        escolhidos: list[int | None] = [None] * len(alvos)
        inicio = 0
        while inicio < len(alvos):   # cada trecho entre pausas é escolhido por si
            if "pausa" in alvos[inicio]:
                inicio += 1
                continue
            fim = inicio
            while fim < len(alvos) and "pausa" not in alvos[fim]:
                fim += 1
            candidatos, custos, voltas = [], [], []
            for k in range(inicio, fim):
                alvo = alvos[k]
                todos = self.por_contexto.get((alvo["fone"], alvo["lado"], alvo["vizinho"]), ())
                if len(todos) < CANDIDATOS:   # difone raro ou nunca gravado: concorrem todas as metades do fonema
                    todos = self.indice[(alvo["fone"], alvo["lado"])]
                ordem = np.argsort(self._custo_de_alvo(todos, alvo))[:CANDIDATOS]
                lista = todos[ordem]
                if candidatos:  # quem vinha logo depois dos candidatos anteriores na gravação também concorre
                    seguintes = candidatos[-1] + 1
                    seguintes = seguintes[(seguintes < len(self.u["fone"]))]
                    seguintes = seguintes[(self.u["fone"][seguintes] == alvo["fone"]) & (self.u["lado"][seguintes] == alvo["lado"])
                                          & (self.u["nota"][seguintes] > -1e8) & self.u["segue"][seguintes - 1]]
                    lista = np.unique(np.concatenate([lista, seguintes]))
                alvo_c = self._custo_de_alvo(lista, alvo)
                if not candidatos:
                    custos.append(alvo_c); voltas.append(np.zeros(len(lista), dtype=np.int64))
                else:
                    emenda = self._custo_de_emenda(candidatos[-1], lista, no_limite=alvo["lado"] == 0)
                    soma = custos[-1][:, None] + emenda
                    voltas.append(soma.argmin(axis=0))
                    custos.append(soma.min(axis=0) + alvo_c)
                candidatos.append(lista)
            j = int(custos[-1].argmin())
            for k in range(fim - 1, inicio - 1, -1):
                escolhidos[k] = int(candidatos[k - inicio][j])
                j = int(voltas[k - inicio][j])
            inicio = fim
        return escolhidos

    # ---------------------------------------------------------------- prosódia
    def _curva_de_tom(self, alvos: list[dict], altura: float, estilo: str) -> np.ndarray:
        """O tom desejado a cada 5 ms da fala final.

        ``natural``: a frase desce aos poucos, as tônicas sobem um pouco, a pergunta sobe no fim.
        ``robotica``: cada vogal fica numa nota fixa, sem deslizar, como uma voz afinada à força.
        """
        passo = marcas.SALTO
        base = self.meta["tom"] * altura
        curva = np.full(int(sum(a["duracao"] for a in alvos) / passo) + 2, base)
        t, inicio_da_frase, ultima_tonica = 0.0, 0.0, None
        for a in alvos:
            q0, q1 = int(t / passo), int((t + a["duracao"]) / passo) + 1
            if "pausa" in a:
                f0, f1 = int(inicio_da_frase / passo), q0
                if f1 > f0 and estilo == "natural":
                    curva[f0:f1] *= np.linspace(1.07, 0.92, f1 - f0)
                    if a["pausa"] == "?" and ultima_tonica:
                        # pergunta no português do Brasil: o tom sobe na última tônica e cede um pouco depois dela
                        t0, t1 = ultima_tonica
                        t0 = max(t0 - int(0.12 / passo), f0)     # começa a subir um pouco antes, para não dar um salto
                        curva[t0:t1] *= np.linspace(1.0, 1.32, t1 - t0)
                        curva[t1:f1] *= np.linspace(1.32, 1.12, max(f1 - t1, 0))
                    else:
                        cauda = min(f1 - f0, int(0.28 / passo))
                        curva[f1 - cauda:f1] *= np.linspace(1.0, {"?": 1.30, ",": 1.04, ".": 0.82}[a["pausa"]], cauda)
                elif f1 > f0 and ultima_tonica:
                    nota = {"?": 7, ",": 2, ".": -4}[a["pausa"]]
                    curva[ultima_tonica[0]:f1] = base * 2 ** (nota / 12)   # a última tônica dá o fecho da frase
                curva[f1:q1] = curva[max(f1 - 1, 0)]
                inicio_da_frase, ultima_tonica = t + a["duracao"], None
            elif a["nome"] in _VOGAIS:
                if estilo == "natural":
                    if a["tonico"]:
                        curva[q0:q1] *= 1.10
                else:
                    curva[q0:q1] = base * 2 ** ((3 if a["tonico"] else 0) / 12)
                if a["tonico"]:                      # guarda onde fica a última tônica (as duas metades da vogal)
                    ultima_tonica = (q0, q1) if a["lado"] == 0 or not ultima_tonica else (ultima_tonica[0], q1)
            t += a["duracao"]
        if estilo == "natural":
            janela = np.hanning(19)
            curva = np.convolve(np.pad(curva, 9, mode="edge"), janela / janela.sum(), mode="valid")
        return curva

    # ------------------------------------------------------------------ falar
    def falar(self, texto: str, velocidade: float = 1.0, altura: float = 1.0, estilo: str = "natural",
              detalhes: dict | None = None) -> np.ndarray | None:
        """Texto -> onda (float entre -1 e 1, a ``self.taxa``). None se algum som não existe no banco."""
        alvos = self._alvos(texto, velocidade)
        if alvos is None:
            return None
        if not alvos:
            return np.zeros(0, dtype=np.float32)
        escolhidos = self._escolher(alvos)
        u = self.u
        pedacos = []
        emendas = naturais = 0
        ganhos = np.ones((len(alvos), 2))
        for k in range(1, len(alvos)):       # iguala o volume dos dois lados de cada emenda
            a, b = escolhidos[k - 1], escolhidos[k]
            if a is None or b is None:
                continue
            if b == a + 1 and u["segue"][a]:
                naturais += 1
                continue
            emendas += 1
            meio = 0.5 * (u["en_fim"][a] + u["en_ini"][b])
            ganhos[k - 1, 1] = 10 ** (np.clip(meio - u["en_fim"][a], -5, 5) / 20)
            ganhos[k, 0] = 10 ** (np.clip(meio - u["en_ini"][b], -5, 5) / 20)
        for alvo, escolhido, ganho in zip(alvos, escolhidos, ganhos):
            if escolhido is None:
                pedacos.append(psola.Pedaco(self._silencio[0], self._silencio[1], np.zeros(len(self._silencio[1]), dtype=bool),
                                            0, int(min(alvo["duracao"], 1.9) * self.taxa), duracao=alvo["duracao"]))
            else:
                # a duração fica perto da gravada: PSOLA soa melhor quando mexe pouco
                natural = self.duracao[escolhido]
                duracao = float(np.clip(alvo["duracao"], 0.6 * natural, 1.7 * natural))
                pedacos.append(psola.Pedaco(self.som, u["marcas"], u["de_voz"], int(u["ini"][escolhido]),
                                            int(u["fim"][escolhido]), duracao=duracao, ganho=tuple(ganho)))
                alvo["duracao"] = duracao
        curva = self._curva_de_tom(alvos, altura, estilo)
        onda = psola.sintetizar(pedacos, self.taxa, curva) / 32768.0
        pico = np.abs(onda).max()
        if pico > 0:
            onda = onda / pico * 0.85
        if detalhes is not None:
            detalhes.update(emendas=emendas, naturais=naturais, metades=sum(e is not None for e in escolhidos))
        return onda.astype(np.float32)
