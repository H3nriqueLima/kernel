"""O laço de treino do mini GPT.

Cada passo: pegar um lote, calcular a perda, retropropagar, cortar o gradiente,
dar um passo do AdamW. A cada ``avaliar_cada`` passos ele mede a perda na
validação, escreve uma amostra, salva o checkpoint e, se melhorou, exporta os
pesos para o serviço usar.

O treino pode ser interrompido (Ctrl+C) e retomado: o checkpoint guarda o
modelo, o otimizador e o passo. ``--horas`` limita uma sessão; ``--passos`` é
a meta total, que pode levar várias madrugadas.

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
    passos: int = 20_000           # meta total de passos
    horas: float | None = None     # limite desta sessão
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


def taxa_no_passo(cfg: ConfigTreino, passo: int) -> float:
    """Sobe em linha reta no aquecimento, depois desce em cosseno até 10% da taxa."""
    if passo < cfg.aquecimento:
        return cfg.taxa * (passo + 1) / cfg.aquecimento
    progresso = min(1.0, (passo - cfg.aquecimento) / max(1, cfg.passos - cfg.aquecimento))
    return cfg.taxa * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * progresso)))


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
    if passo:
        avisar(f"continuando do passo {passo} (melhor perda de validação até aqui: {melhor:.3f})")
    if passo >= cfg.passos:
        avisar(f"a meta de {cfg.passos} passos já foi atingida; aumente --passos para continuar.")

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
                                    f"{taxa_no_passo(cfg, passo):.6f}", f"{tokens_por_segundo:.0f}", f"{segundos:.0f}"])
        if quadro:
            quadro.add_scalar("perda/validacao", perda_val, passo)
            quadro.add_text("amostra", amostra, passo)
        avisar(f"  validação {perda_val:.3f} (melhor {melhor:.3f}) | amostra: {amostra!r}")

    inicio = time.time()
    limite = inicio + cfg.horas * 3600 if cfg.horas else None
    media, marca, passo_da_marca = None, inicio, passo
    tokens_por_segundo = 0.0
    modelo.train()
    pedido_de_parada = pasta / "PARAR"  # o serviço cria este arquivo quando você diz "para o treino"
    try:
        while passo < cfg.passos and (limite is None or time.time() < limite):
            if pedido_de_parada.exists():
                pedido_de_parada.unlink(missing_ok=True)
                avisar("parando a pedido: salvando o checkpoint...")
                break
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
                faltam = (cfg.passos - passo) * cfg.acumular * cfg.lote * contexto / tokens_por_segundo
                avisar(f"passo {passo:6d}/{cfg.passos} | perda {media:.3f} | taxa {taxa:.2e} | "
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
