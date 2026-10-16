"""Checagens do pipeline do cérebro: cada peça conferida contra uma referência independente.

Uma perda que cai não prova que o treino está certo: um erro na máscara causal,
por exemplo, deixa o modelo "colar" do futuro e a perda cai mais ainda. Por isso
cada peça é medida contra algo escrito por outra pessoa, ou contra a matemática:

- o tokenizador vai e volta sem perder um byte;
- o alvo de cada posição é o token seguinte;
- a máscara não deixa o futuro vazar;
- a normalização, a GELU, a atenção e a perda batem com as funções do PyTorch;
- a perda inicial é ln(vocabulário) (o modelo começa sem preferência);
- os gradientes batem com os de um GPT de referência e com diferenças finitas;
- o AdamW e o corte de gradiente batem com os do PyTorch;
- o checkpoint volta idêntico e o treino continua igual depois de restaurado;
- a inferência em NumPy (a que o serviço usa) dá as mesmas notas que o PyTorch;
- e o teste de memorizar: o modelo aprende de cor um texto pequeno e depois o
  repete sozinho. Se isso falhar, há erro no pipeline, por mais que a perda caia.

    python -m kernel cerebro verificar
"""
from __future__ import annotations

import math
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from . import inferencia
from .dados import Lotes
from .gpt import GPT, ConfigGPT, Linear, NormaDeCamada, TAMANHOS, gelu
from .otimizador import AdamW
from .tokenizador import Tokenizador


@dataclass
class Resultado:
    nome: str
    ok: bool
    detalhe: str
    segundos: float = 0.0


def _tempo(funcao):
    def medir(*args, **kwargs):
        inicio = time.time()
        resultado = funcao(*args, **kwargs)
        resultado.segundos = time.time() - inicio
        return resultado
    medir.__name__ = funcao.__name__
    return medir


def _mini_gpt(vocab=97, contexto=16, camadas=2, cabecas=2, dim=24, semente=0, dtype=torch.float64) -> GPT:
    torch.manual_seed(semente)
    return GPT(ConfigGPT(vocab=vocab, contexto=contexto, camadas=camadas, cabecas=cabecas, dim=dim)).to(dtype)


# ------------------------------------------------------------------ tokenizador
@_tempo
def tokenizador(tok: Tokenizador, texto: str, ids_gravados: np.ndarray) -> Resultado:
    """Texto -> ids -> texto sem perder um byte; e os ids gravados no treino são os que ele produz hoje."""
    ida = tok.codificar(texto)
    volta = tok.decodificar(ida)
    sem_perda = volta == texto
    recodificados = tok.codificar(tok.decodificar(ids_gravados.tolist()))
    iguais = recodificados == ids_gravados.tolist()
    usados = len(np.unique(ids_gravados))
    caracteres_por_token = len(texto) / max(len(ida), 1)
    ok = sem_perda and iguais
    return Resultado("tokenizador", ok,
                     f"ida e volta sem perda: {sem_perda} | ids gravados = ids de hoje: {iguais} | "
                     f"{caracteres_por_token:.2f} caracteres por token | {usados} de {tok.tamanho} tokens aparecem "
                     f"em {len(ids_gravados):,} tokens de amostra".replace(",", "."))


# ------------------------------------------------------------------ alvos
@_tempo
def alvos() -> Resultado:
    """O alvo de cada posição é o token seguinte (num arquivo em que cada token vale a sua posição)."""
    with tempfile.TemporaryDirectory() as pasta:
        arquivo = Path(pasta) / "dados.bin"
        np.arange(5000, dtype=np.uint16).tofile(arquivo)
        lotes = Lotes(arquivo, contexto=32, lote=8, pedaco=1000, semente=1)
        certos = 0
        for _ in range(50):
            x, y = lotes.pegar("cpu")
            certos += int(((y - x) == 1).all())
        del lotes
    return Resultado("alvos", certos == 50, f"y = x + 1 em {certos} de 50 lotes (inclusive depois de trocar de pedaço)")


# ------------------------------------------------------------------ máscara causal
@_tempo
def mascara() -> Resultado:
    """Trocar um token do futuro não pode mudar as notas de nenhuma posição anterior."""
    modelo = _mini_gpt().eval()
    ids = torch.randint(0, 97, (1, 16), generator=torch.Generator().manual_seed(3))
    with torch.no_grad():
        antes = modelo(ids)[0]
        vazamento = 0.0
        for t in range(1, 16):
            mexido = ids.clone()
            mexido[0, t] = (mexido[0, t] + 1) % 97
            depois = modelo(mexido)[0]
            vazamento = max(vazamento, float((depois[0, :t] - antes[0, :t]).abs().max()))
            if float((depois[0, t:] - antes[0, t:]).abs().max()) == 0.0:   # e o presente tem de mudar
                return Resultado("mascara", False, f"mudar o token {t} não mudou a própria posição")
    return Resultado("mascara", vazamento == 0.0, f"maior mudança no passado ao mexer no futuro: {vazamento:.1e}")


# ------------------------------------------------------------------ camadas
@_tempo
def camadas() -> Resultado:
    """LayerNorm, GELU, atenção e perda contra as funções prontas do PyTorch (em float64)."""
    torch.manual_seed(0)
    x = torch.randn(3, 16, 24, dtype=torch.float64)
    norma = NormaDeCamada(24).double()
    with torch.no_grad():
        norma.ganho.uniform_(0.5, 1.5)
        norma.vies.uniform_(-0.5, 0.5)
    erros = {"normalização": float((norma(x) - F.layer_norm(x, (24,), norma.ganho, norma.vies, 1e-5)).abs().max()),
             "gelu": float((gelu(x) - F.gelu(x, approximate="tanh")).abs().max())}
    modelo = _mini_gpt()
    bloco = modelo.blocos[0].atencao
    with torch.no_grad():
        q, k, v = bloco.qkv(x).split(24, dim=2)
        dividir = lambda t: t.view(3, 16, 2, 12).transpose(1, 2)   # noqa: E731
        referencia = F.scaled_dot_product_attention(dividir(q), dividir(k), dividir(v), is_causal=True)
        referencia = bloco.saida(referencia.transpose(1, 2).reshape(3, 16, 24))
        erros["atenção"] = float((bloco(x) - referencia).abs().max())
        ids = torch.randint(0, 97, (3, 16))
        logits, perda = modelo(ids, ids)
        manual = -torch.log_softmax(logits, -1).gather(-1, ids.unsqueeze(-1)).mean()
        erros["perda"] = abs(float(perda - manual))
    ok = all(erro < 1e-10 for erro in erros.values())
    return Resultado("camadas", ok, " | ".join(f"{nome} {erro:.1e}" for nome, erro in erros.items()))


# ------------------------------------------------------------------ inicialização
@_tempo
def inicializacao(vocab: int = 4096, tamanho: str = "mini", ids: np.ndarray | None = None) -> Resultado:
    """Recém-criado, o modelo não prefere token nenhum: a perda é ln(vocabulário), e a via residual não explode."""
    torch.manual_seed(0)
    modelo = GPT(ConfigGPT(vocab=vocab, **TAMANHOS[tamanho])).eval()
    T = modelo.cfg.contexto
    if ids is None:
        ids = np.random.default_rng(0).integers(0, vocab, size=4 * (T + 1))
    janelas = torch.from_numpy(np.asarray(ids[:4 * (T + 1)], dtype=np.int64).reshape(4, T + 1))
    desvios = []
    with torch.no_grad():
        logits, perda = modelo(janelas[:, :-1], janelas[:, 1:])
        x = F.embedding(janelas[:, :-1], modelo.emb_token) + modelo.emb_posicao[:T]
        for bloco in modelo.blocos:
            x = bloco(x)
            desvios.append(float(x.std()))
    # Notas pequenas e ao acaso (desvio s) custam s²/2 a mais que o uniforme: com os pesos amarrados,
    # s ≈ raiz(dim) · 0,02 ≈ 0,28 no mini, então a perda esperada fica um pouco acima de ln(vocabulário).
    s = float(logits.std())
    uniforme = math.log(vocab)
    esperado = uniforme + s * s / 2
    ok = abs(float(perda) - esperado) < 0.03 and float(perda) - uniforme < 0.15 and max(desvios) < 1.0
    return Resultado("inicializacao", ok, f"perda inicial {float(perda):.3f} (ln {vocab} = {uniforme:.3f}; com notas de "
                                          f"desvio {s:.3f}, o esperado é {esperado:.3f}) | desvio da via residual por "
                                          f"camada: {', '.join(f'{d:.3f}' for d in desvios)}")


# ------------------------------------------------------------------ gradientes
def _perda_de_referencia(modelo: GPT, ids, alvos):
    """O mesmo GPT, escrito só com funções prontas do PyTorch, usando os mesmos tensores de peso."""
    c = modelo.cfg
    T = ids.shape[1]
    x = F.embedding(ids, modelo.emb_token) + modelo.emb_posicao[:T]
    for b in modelo.blocos:
        h = F.layer_norm(x, (c.dim,), b.norma1.ganho, b.norma1.vies, 1e-5)
        q, k, v = F.linear(h, b.atencao.qkv.peso, b.atencao.qkv.vies).split(c.dim, dim=2)
        dividir = lambda t: t.view(t.shape[0], T, c.cabecas, c.dim // c.cabecas).transpose(1, 2)   # noqa: E731
        y = F.scaled_dot_product_attention(dividir(q), dividir(k), dividir(v), is_causal=True)
        y = y.transpose(1, 2).reshape(x.shape)
        x = x + F.linear(y, b.atencao.saida.peso, b.atencao.saida.vies)
        h = F.layer_norm(x, (c.dim,), b.norma2.ganho, b.norma2.vies, 1e-5)
        h = F.gelu(F.linear(h, b.sobe.peso, b.sobe.vies), approximate="tanh")
        x = x + F.linear(h, b.desce.peso, b.desce.vies)
    x = F.layer_norm(x, (c.dim,), modelo.norma_final.ganho, modelo.norma_final.vies, 1e-5)
    logits = x @ modelo.emb_token.t()
    return F.cross_entropy(logits.reshape(-1, c.vocab), alvos.reshape(-1))


@_tempo
def gradientes() -> Resultado:
    """Os gradientes do nosso GPT contra os de um GPT de referência e contra diferenças finitas (float64)."""
    modelo = _mini_gpt()
    gerador = torch.Generator().manual_seed(5)
    ids = torch.randint(0, 97, (2, 16), generator=gerador)
    alvos_ = torch.randint(0, 97, (2, 16), generator=gerador)
    parametros = list(modelo.parameters())
    nosso = torch.autograd.grad(modelo(ids, alvos_)[1], parametros)
    referencia = torch.autograd.grad(_perda_de_referencia(modelo, ids, alvos_), parametros)
    diferenca = max(float((a - b).abs().max()) for a, b in zip(nosso, referencia))
    # diferenças finitas em 12 pesos escolhidos ao acaso (um por tensor, nos 12 primeiros tensores)
    numerico = 0.0
    with torch.no_grad():
        for p, g in list(zip(parametros, nosso))[:12]:
            indice = tuple(int(torch.randint(0, n, (1,), generator=gerador)) for n in p.shape)
            original = float(p[indice])
            p[indice] = original + 1e-6
            mais = float(modelo(ids, alvos_)[1])
            p[indice] = original - 1e-6
            menos = float(modelo(ids, alvos_)[1])
            p[indice] = original
            numerico = max(numerico, abs((mais - menos) / 2e-6 - float(g[indice])))
    ok = diferenca < 1e-10 and numerico < 1e-6
    return Resultado("gradientes", ok, f"contra o GPT de referência: {diferenca:.1e} | contra diferenças finitas: {numerico:.1e}")


# ------------------------------------------------------------------ otimizador
@_tempo
def otimizador() -> Resultado:
    """O AdamW escrito à mão contra o do PyTorch (decaimento só nas matrizes), e o corte de gradiente."""
    nosso_modelo, deles_modelo = _mini_gpt(semente=1), _mini_gpt(semente=1)
    nosso = AdamW(nosso_modelo.parameters(), decaimento=0.1)
    matrizes = [p for p in deles_modelo.parameters() if p.dim() >= 2]
    resto = [p for p in deles_modelo.parameters() if p.dim() < 2]
    deles = torch.optim.AdamW([{"params": matrizes, "weight_decay": 0.1}, {"params": resto, "weight_decay": 0.0}],
                              lr=1e-3, betas=(0.9, 0.95), eps=1e-8)
    gerador = torch.Generator().manual_seed(7)
    diferenca_corte = 0.0
    for passo in range(6):
        ids = torch.randint(0, 97, (2, 16), generator=gerador)
        taxa = 1e-3 * (passo + 1) / 6
        for g in deles.param_groups:
            g["lr"] = taxa
        for modelo in (nosso_modelo, deles_modelo):
            modelo(ids, ids.roll(-1, 1))[1].backward()
        norma_nossa = nosso.cortar_gradiente(0.5)
        norma_deles = float(torch.nn.utils.clip_grad_norm_(deles_modelo.parameters(), 0.5))
        diferenca_corte = max(diferenca_corte, abs(norma_nossa - norma_deles))
        nosso.passo(taxa)
        deles.step()
        nosso.zerar()
        deles.zero_grad(set_to_none=True)
    diferenca = max(float((a - b).abs().max()) for a, b in zip(nosso_modelo.parameters(), deles_modelo.parameters()))
    ok = diferenca < 1e-9 and diferenca_corte < 1e-9
    return Resultado("otimizador", ok, f"pesos depois de 6 passos, contra torch.optim.AdamW: {diferenca:.1e} | "
                                       f"norma do corte contra clip_grad_norm_: {diferenca_corte:.1e}")


# ------------------------------------------------------------------ checkpoint
@_tempo
def checkpoint() -> Resultado:
    """Salvar e restaurar: o modelo e o otimizador voltam idênticos, e o treino continua igual."""
    from .treinar import CHECKPOINT, carregar_checkpoint, confere, salvar_checkpoint

    torch.manual_seed(2)
    modelo = GPT(ConfigGPT(vocab=97, contexto=16, camadas=2, cabecas=2, dim=24))
    otim = AdamW(modelo.parameters())
    gerador = torch.Generator().manual_seed(9)
    lotes = [torch.randint(0, 97, (4, 17), generator=gerador) for _ in range(5)]

    def passo(m, o, lote):
        m(lote[:, :-1], lote[:, 1:])[1].backward()
        o.cortar_gradiente(1.0)
        o.passo(1e-3)
        o.zerar()

    for lote in lotes[:3]:
        passo(modelo, otim, lote)
    with tempfile.TemporaryDirectory() as pasta:
        salvar_checkpoint(Path(pasta) / CHECKPOINT, modelo, otim, passo=3, melhor=4.2, segundos=1.5)
        integro = confere(Path(pasta) / CHECKPOINT)
        salvo = carregar_checkpoint(Path(pasta), avisar=lambda _: None)
    copia = GPT(ConfigGPT(**salvo["config"]))
    copia.load_state_dict(salvo["modelo"])
    otim_copia = AdamW(copia.parameters())
    otim_copia.carregar_estado(salvo["otimizador"])
    for lote in lotes[3:]:
        passo(modelo, otim, lote)
        passo(copia, otim_copia, lote)
    diferenca = max(float((a - b).abs().max()) for a, b in zip(modelo.parameters(), copia.parameters()))
    campos = salvo["passo"] == 3 and salvo["melhor"] == 4.2 and salvo["segundos"] == 1.5
    ok = integro is True and campos and diferenca == 0.0
    return Resultado("checkpoint", ok, f"impressão confere: {integro} | passo, melhor e segundos voltam: {campos} | "
                                       f"pesos 2 passos depois de restaurar, contra o treino sem parar: {diferenca:.1e}")


# ------------------------------------------------------------------ inferência
@_tempo
def inferencia_numpy(arquivo_modelo: Path, tok: Tokenizador, ids: np.ndarray) -> Resultado:
    """Os pesos de verdade: as notas do NumPy (o serviço) contra as do PyTorch, e o atalho de um pedaço por vez."""
    from .pesos import gpt_de_npz, ler_npz

    cfg, pesos = ler_npz(arquivo_modelo)
    cerebro = inferencia.CerebroNumpy(pesos, cfg, tok)
    modelo = gpt_de_npz(arquivo_modelo)
    janela = [int(i) for i in ids[:cfg["contexto"]]]
    with torch.no_grad():
        deles = modelo(torch.tensor([janela]))[0][0].numpy()
    nosso = cerebro.logits(janela)
    diferenca = float(np.abs(nosso - deles).max())
    memoria = cerebro._memoria_nova()
    atalho = max(float(np.abs(cerebro._avancar(t, i, memoria) - nosso[i]).max()) for i, t in enumerate(janela[:64]))
    mesma_escolha = float(np.mean(nosso.argmax(-1) == deles.argmax(-1)))
    ok = diferenca < 1e-3 and atalho < 1e-3 and mesma_escolha >= 0.99   # (um quase empate pode virar por arredondamento)
    return Resultado("inferencia", ok, f"NumPy contra PyTorch: {diferenca:.1e} (mesmo token mais provável em "
                                       f"{mesma_escolha:.0%} das posições) | um pedaço por vez contra a conta inteira: {atalho:.1e}")


# ------------------------------------------------------------------ memorizar
def memorizar(ids: np.ndarray, tamanho: str = "nano", vocab: int = 4096, passos: int = 300, taxa: float = 1e-3,
              dispositivo="cpu", semente: int = 0, avisar=None) -> Resultado:
    """O teste de sobreajuste: aprender de cor um texto pequeno e depois repeti-lo sozinho.

    Treina só nesse texto e, no fim, exporta os pesos e pede à inferência em NumPy (a do
    serviço) que continue o começo do texto escolhendo sempre o token mais provável. Um
    pipeline certo decora: a perda vai quase a zero e a continuação sai igual ao original.
    """
    inicio = time.time()
    torch.manual_seed(semente)
    cfg = ConfigGPT(vocab=vocab, **TAMANHOS[tamanho])
    modelo = GPT(cfg).to(dispositivo)
    otim = AdamW(modelo.parameters(), decaimento=0.0)
    T = min(cfg.contexto, len(ids) - 1)
    dados = torch.from_numpy(np.asarray(ids, dtype=np.int64))
    sorteio = np.random.default_rng(semente)
    perda = float("nan")
    for passo in range(passos):
        comecos = sorteio.integers(0, len(ids) - T, size=8)
        lote = torch.stack([dados[c:c + T + 1] for c in comecos]).to(dispositivo)
        _, perda_t = modelo(lote[:, :-1], lote[:, 1:])
        perda_t.backward()
        otim.cortar_gradiente(1.0)
        otim.passo(taxa * min(1.0, (passo + 1) / 20))
        otim.zerar()
        if (passo + 1) % 50 == 0:
            perda = float(perda_t)
            if avisar:
                avisar(f"  memorizar: passo {passo + 1} | perda {perda:.4f}")
    perda = float(perda_t)
    with tempfile.TemporaryDirectory() as pasta:
        arquivo = Path(pasta) / inferencia.MODELO
        inferencia.exportar(modelo.cpu(), arquivo)
        from .pesos import ler_npz
        cfg_npz, pesos = ler_npz(arquivo)
    cerebro = inferencia.CerebroNumpy(pesos, cfg_npz, None)
    comeco = [int(i) for i in ids[:8]]
    quantos = min(T, len(ids)) - 8
    memoria, notas, gerados = cerebro._memoria_nova(), None, list(comeco)
    for posicao, token in enumerate(comeco):
        notas = cerebro._avancar(token, posicao, memoria)
    while len(gerados) < 8 + quantos:
        proximo = int(np.argmax(notas))
        gerados.append(proximo)
        notas = cerebro._avancar(proximo, len(gerados) - 1, memoria)
    acerto = float(np.mean(np.array(gerados[8:]) == np.asarray(ids[8:8 + quantos])))
    ok = perda < 0.1 and acerto >= 0.95
    return Resultado("memorizar", ok, f"{tamanho} em {dispositivo}: perda final {perda:.4f} depois de {passos} passos | "
                                      f"repetiu sozinho {acerto:.1%} dos {quantos} tokens seguintes", time.time() - inicio)


def verificar(pasta: Path, arquivo_modelo: Path | None = None, tamanho_memorizar: str = "nano",
              dispositivo_memorizar="cpu", passos_memorizar: int = 300, avisar=print) -> list[Resultado]:
    """Todas as checagens. ``pasta`` é a do cérebro (tokenizador, val.bin)."""
    pasta = Path(pasta)
    tok = Tokenizador.carregar(pasta / inferencia.TOKENIZADOR)
    val = np.asarray(np.memmap(pasta / "val.bin", dtype=np.uint16, mode="r")[:200_000]).astype(np.int64)
    # o texto de prova: documentos inteiros da validação (o primeiro está cortado: começa no meio de um artigo)
    fins = np.flatnonzero(val == tok.id_fim)
    texto = tok.decodificar(val[fins[0] + 1:fins[40] + 1].tolist())
    resultados = []
    for checagem in (lambda: tokenizador(tok, texto, val[fins[0] + 1:fins[40] + 1]), alvos, mascara, camadas,
                     lambda: inicializacao(tok.tamanho, "mini", val), gradientes, otimizador, checkpoint):
        resultados.append(checagem())
        if avisar:
            r = resultados[-1]
            avisar(f"{'ok   ' if r.ok else 'FALHA'} {r.nome:<14} {r.detalhe}")
    arquivo_modelo = Path(arquivo_modelo or pasta / inferencia.MODELO)
    if arquivo_modelo.exists():
        resultados.append(inferencia_numpy(arquivo_modelo, tok, val[fins[0] + 1:]))
        if avisar:
            r = resultados[-1]
            avisar(f"{'ok   ' if r.ok else 'FALHA'} {r.nome:<14} {r.detalhe}")
    # o texto para decorar: os dois primeiros documentos inteiros da validação, cortados no contexto do modelo
    contexto = TAMANHOS[tamanho_memorizar]["contexto"]
    pequeno = val[fins[0] + 1:fins[0] + 1 + contexto + 1]
    resultados.append(memorizar(pequeno, tamanho_memorizar, tok.tamanho, passos_memorizar,
                                dispositivo=dispositivo_memorizar, avisar=avisar))
    if avisar:
        r = resultados[-1]
        avisar(f"{'ok   ' if r.ok else 'FALHA'} {r.nome:<14} {r.detalhe}")
    return resultados
