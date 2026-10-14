"""O laço de treino do mini GPT.

Cada passo: pegar um lote, calcular a perda, retropropagar, cortar o gradiente,
dar um passo do AdamW. A cada ``avaliar_cada`` passos ele mede a perda na
validação, escreve uma amostra, salva o checkpoint e, se melhorou, exporta os
pesos para o serviço usar.

O treino pode ser interrompido (Ctrl+C) e retomado: o checkpoint guarda o
modelo, o otimizador e o passo. Há dois jeitos de dizer quanto treinar:

- ``--horas 6``: uma sessão de seis horas, que continua de onde a anterior
  parou. A taxa de aprendizado sobe no começo da sessão e desce em cosseno até
  o fim dela. Dá para repetir quantas madrugadas quiser;
- ``--passos 20000``: uma meta total de passos (o jeito antigo).

    python -m kernel cerebro treinar --horas 6
"""
from __future__ import annotations

import csv
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import torch

from . import inferencia
from .dados import Lotes
from .dispositivo import escolher
from .gpt import GPT, TAMANHOS, ConfigGPT, criar
from .otimizador import AdamW
from .tokenizador import Tokenizador

CHECKPOINT = "checkpoint.pt"


@dataclass
class ConfigTreino:
    tamanho: str = "mini"
    passos: int | None = None      # meta total de passos (None com ``horas``: a sessão vai até o tempo acabar)
    horas: float | None = None     # limite desta sessão
    taxa_ao_continuar: float = 0.5  # numa sessão que continua um treino, o pico da taxa é esta fração de ``taxa``
    lote: int = 16                 # ver LOTES em gpt.py: o que cabe na RX 570
    acumular: int = 2              # soma o gradiente de N lotes antes do passo (efeito de lote maior)
    taxa: float = 6e-4
    aquecimento: int = 200         # passos subindo a taxa do zero
    decaimento: float = 0.1
    corte_gradiente: float = 1.0
    avaliar_cada: int = 500
    lotes_de_avaliacao: int = 20
    dispositivo: str = "auto"
    semente: int = 1337


PASSOS_SEM_META = 20_000   # sem ``--passos`` e sem ``--horas``, a meta é esta


def taxa_no_passo(cfg: ConfigTreino, passo: int) -> float:
    """Sobe em linha reta no aquecimento, depois desce em cosseno até 10% da taxa."""
    if passo < cfg.aquecimento:
        return cfg.taxa * (passo + 1) / cfg.aquecimento
    meta = cfg.passos or PASSOS_SEM_META
    progresso = min(1.0, (passo - cfg.aquecimento) / max(1, meta - cfg.aquecimento))
    return cfg.taxa * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * progresso)))


def taxa_na_sessao(cfg: ConfigTreino, passos_na_sessao: int, fracao_do_tempo: float, continuando: bool) -> float:
    """A taxa numa sessão medida em horas: aquece nos primeiros passos e desce em cosseno com o relógio.

    Numa sessão que continua um treino anterior o pico é menor (``taxa_ao_continuar``): o cérebro já
    aprendeu o grosso, e um passo grande demais desarrumaria o que ele sabe.
    """
    pico = cfg.taxa * (cfg.taxa_ao_continuar if continuando else 1.0)
    if passos_na_sessao < cfg.aquecimento:
        return pico * (passos_na_sessao + 1) / cfg.aquecimento
    progresso = min(1.0, max(0.0, fracao_do_tempo))
    return pico * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * progresso)))


@torch.no_grad()
def avaliar(modelo: GPT, lotes: Lotes, dispositivo, quantos: int) -> float:
    perdas = []
    for _ in range(quantos):
        x, y = lotes.pegar(dispositivo)
        perdas.append(float(modelo(x, y)[1]))
    return sum(perdas) / len(perdas)


def salvar_checkpoint(arquivo: Path, modelo: GPT, otimizador: AdamW, passo: int, melhor: float,
                      segundos: float) -> None:
    dados = {
        "config": modelo.configuracao(),
        "modelo": {nome: p.cpu() for nome, p in modelo.state_dict().items()},
        "otimizador": otimizador.estado(),
        "passo": passo,
        "melhor": melhor,
        "segundos": segundos,
    }
    temporario = arquivo.with_suffix(".tmp")
    torch.save(dados, temporario)
    temporario.replace(arquivo)  # nunca fica um checkpoint pela metade se a luz cair


def treinar(pasta: Path, cfg: ConfigTreino, avisar=print) -> dict:
    """Treina (ou continua treinando) o cérebro em ``pasta``. Devolve um resumo."""
    pasta = Path(pasta)
    tokenizador = Tokenizador.carregar(pasta / inferencia.TOKENIZADOR)
    torch.manual_seed(cfg.semente)
    dispositivo, descricao = escolher(cfg.dispositivo)

    arquivo = pasta / CHECKPOINT
    passo, melhor, segundos_antes = 0, float("inf"), 0.0
    if arquivo.exists():
        salvo = torch.load(arquivo, map_location="cpu", weights_only=False)
        if salvo["config"]["vocab"] != tokenizador.tamanho:
            raise SystemExit(f"O checkpoint foi treinado com um tokenizador de {salvo['config']['vocab']} tokens e o "
                             f"atual tem {tokenizador.tamanho}. Apague {CHECKPOINT} e {inferencia.MODELO} em "
                             f"{pasta} para começar um cérebro novo.")
        if salvo["config"] != {"vocab": tokenizador.tamanho, **TAMANHOS[cfg.tamanho]}:
            avisar(f'aviso: o checkpoint não é do tamanho "{cfg.tamanho}"; continuo com o tamanho do checkpoint.')
        modelo = GPT(ConfigGPT(**salvo["config"]))
        modelo.load_state_dict(salvo["modelo"])
        passo, melhor, segundos_antes = salvo["passo"], salvo["melhor"], salvo["segundos"]
    else:
        salvo = None
        modelo = criar(cfg.tamanho, tokenizador.tamanho)
    modelo.to(dispositivo)
    otimizador = AdamW(modelo.parameters(), decaimento=cfg.decaimento)
    if salvo:
        otimizador.carregar_estado(salvo["otimizador"])

    contexto = modelo.cfg.contexto
    treino = Lotes(pasta / "treino.bin", contexto, cfg.lote, semente=cfg.semente + passo)
    val = Lotes(pasta / "val.bin", contexto, cfg.lote, semente=0)
    avisar(f"dispositivo: {descricao}")
    avisar(f"modelo: {modelo.numero_de_parametros() / 1e6:.2f} mi de parâmetros | "
           f"treino: {len(treino) / 1e6:.1f} mi de tokens | val: {len(val) / 1e6:.2f} mi")
    por_horas = cfg.passos is None and bool(cfg.horas)       # uma sessão que só acaba quando o tempo acaba
    meta = None if por_horas else (cfg.passos or PASSOS_SEM_META)
    passo_inicial = passo
    if passo:
        avisar(f"continuando do passo {passo} (melhor perda de validação até aqui: {melhor:.3f})")
    if meta is not None and passo >= meta:
        avisar(f"a meta de {meta} passos já foi atingida; use --horas para treinar mais uma sessão.")

    try:
        from torch.utils.tensorboard import SummaryWriter
        quadro = SummaryWriter(str(pasta / "tensorboard"))
    except Exception:  # TensorBoard é opcional; o CSV abaixo sempre é escrito
        quadro = None
    diario_de_treino = pasta / "treino.csv"
    if not diario_de_treino.exists():
        diario_de_treino.write_text("passo,perda_treino,perda_val,taxa,tokens_por_segundo,segundos\n")

    def ponto_de_controle(perda_treino: float, tokens_por_segundo: float) -> None:
        nonlocal melhor
        modelo.eval()
        perda_val = avaliar(modelo, val, dispositivo, cfg.lotes_de_avaliacao)
        semente = tokenizador.codificar("O Brasil")
        amostra = tokenizador.decodificar(modelo.gerar(semente, 40, parar_em=tokenizador.id_fim))
        modelo.train()
        segundos = segundos_antes + time.time() - inicio
        salvar_checkpoint(arquivo, modelo, otimizador, passo, min(melhor, perda_val), segundos)
        if perda_val < melhor:
            melhor = perda_val
            inferencia.exportar(modelo, pasta / inferencia.MODELO)
        with open(diario_de_treino, "a", newline="") as f:
            csv.writer(f).writerow([passo, f"{perda_treino:.4f}", f"{perda_val:.4f}",
                                    f"{taxa:.6f}", f"{tokens_por_segundo:.0f}", f"{segundos:.0f}"])
        if quadro:
            quadro.add_scalar("perda/validacao", perda_val, passo)
            quadro.add_text("amostra", amostra, passo)
        avisar(f"  validação {perda_val:.3f} (melhor {melhor:.3f}) | amostra: {amostra!r}")

    inicio = time.time()
    limite = inicio + cfg.horas * 3600 if cfg.horas else None
    media, marca, passo_da_marca = None, inicio, passo
    tokens_por_segundo, taxa = 0.0, 0.0
    modelo.train()
    pedido_de_parada = pasta / "PARAR"  # o serviço cria este arquivo quando você diz "para o treino"
    try:
        while (meta is None or passo < meta) and (limite is None or time.time() < limite):
            if pedido_de_parada.exists():
                pedido_de_parada.unlink(missing_ok=True)
                avisar("parando a pedido: salvando o checkpoint...")
                break
            if por_horas:
                taxa = taxa_na_sessao(cfg, passo - passo_inicial, (time.time() - inicio) / (cfg.horas * 3600),
                                      continuando=passo_inicial > 0)
            else:
                taxa = taxa_no_passo(cfg, passo)
            for _ in range(cfg.acumular):
                x, y = treino.pegar(dispositivo)
                _, perda = modelo(x, y)
                (perda / cfg.acumular).backward()
            otimizador.cortar_gradiente(cfg.corte_gradiente)
            otimizador.passo(taxa)
            otimizador.zerar()
            passo += 1

            if passo % 10 == 0:
                atual = float(perda)
                if not math.isfinite(atual):
                    raise RuntimeError(f"a perda virou {atual} no passo {passo}; tente uma taxa menor (--taxa)")
                media = atual if media is None else 0.9 * media + 0.1 * atual
            if passo % 50 == 0:
                agora = time.time()
                tokens_por_segundo = (passo - passo_da_marca) * cfg.acumular * cfg.lote * contexto / (agora - marca)
                marca, passo_da_marca = agora, passo
                if meta is None:
                    faltam = max(limite - agora, 0.0)
                    avisar(f"passo {passo:6d} | perda {media:.3f} | taxa {taxa:.2e} | "
                           f"{tokens_por_segundo:,.0f} tok/s | faltam {faltam / 3600:.1f} h desta sessão")
                else:
                    faltam = (meta - passo) * cfg.acumular * cfg.lote * contexto / tokens_por_segundo
                    avisar(f"passo {passo:6d}/{meta} | perda {media:.3f} | taxa {taxa:.2e} | "
                           f"{tokens_por_segundo:,.0f} tok/s | faltam {faltam / 3600:.1f} h para a meta")
                if quadro:
                    quadro.add_scalar("perda/treino", media, passo)
                    quadro.add_scalar("taxa", taxa, passo)
            if passo % cfg.avaliar_cada == 0:
                ponto_de_controle(media, tokens_por_segundo)
                marca, passo_da_marca = time.time(), passo
    except KeyboardInterrupt:
        avisar("interrompido: salvando o checkpoint antes de sair...")
    except RuntimeError as erro:
        if "memory" not in str(erro).lower():
            raise
        raise SystemExit(f"Faltou memória de vídeo com lote {cfg.lote}. Tente a metade do lote e o dobro "
                         f"de acúmulo: --lote {max(1, cfg.lote // 2)} --acumular {cfg.acumular * 2}") from None
    if media is not None and passo % cfg.avaliar_cada != 0:
        ponto_de_controle(media, tokens_por_segundo)
    if quadro:
        quadro.close()
    return {"passo": passo, "melhor_validacao": melhor, "perda_treino": media,
            "parametros": modelo.numero_de_parametros(), "dispositivo": descricao,
            "tokens_por_segundo": tokens_por_segundo, "config": asdict(cfg)}


def medir(tamanho: str, vocab: int, lote: int, dispositivo_pedido: str = "auto", passos: int = 12) -> dict:
    """Mede a velocidade de treino (tokens por segundo) de um tamanho de modelo neste PC."""
    dispositivo, descricao = escolher(dispositivo_pedido)
    modelo = criar(tamanho, vocab).to(dispositivo)
    otimizador = AdamW(modelo.parameters())
    contexto = modelo.cfg.contexto
    x = torch.randint(0, vocab, (lote, contexto)).to(dispositivo)
    for i in range(passos + 2):
        if i == 2:  # os dois primeiros passos pagam a preparação da GPU
            inicio = time.time()
        _, perda = modelo(x, x)
        perda.backward()
        otimizador.cortar_gradiente(1.0)
        otimizador.passo(1e-4)
        otimizador.zerar()
    float(perda)
    segundos = time.time() - inicio
    return {"tamanho": tamanho, "dispositivo": descricao, "parametros": modelo.numero_de_parametros(),
            "tokens_por_segundo": passos * lote * contexto / segundos, "segundos_por_passo": segundos / passos}
