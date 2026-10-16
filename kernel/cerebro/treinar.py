"""O laço de treino do mini GPT.

Cada passo: pegar um lote, calcular a perda, retropropagar, cortar o gradiente,
dar um passo do AdamW. A cada ``avaliar_cada`` passos ele mede a perda na
validação, escreve uma amostra, salva o checkpoint e, se melhorou, exporta os
pesos para o serviço usar.

O treino pode ser interrompido (Ctrl+C) e retomado: o checkpoint guarda o
modelo, o otimizador e o passo. Cada checkpoint sai com a impressão digital
(SHA-256) ao lado, e o anterior fica guardado: se o novo vier estragado, o
treino volta para o anterior. Tudo o que o treino diz vai também para
``treino.log``, inclusive o motivo de ter parado. Há dois jeitos de dizer quanto treinar:

- ``--horas 6``: uma sessão de seis horas, que continua de onde a anterior
  parou. Na primeira, a taxa de aprendizado sobe no começo e desce em cosseno
  até o fim; as seguintes continuam com a taxa baixa e constante em que a
  primeira terminou (reaquecer a cada sessão custava ~0,02 no teste: ver
  docs/fase15/relatorio.md). Dá para repetir quantas madrugadas quiser;
- ``--passos 20000``: uma meta total de passos (o jeito antigo).

    python -m kernel cerebro treinar --horas 6
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import pickle
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch

from . import inferencia
from .dados import Lotes, Passada
from .dispositivo import escolher
from .gpt import GPT, TAMANHOS, ConfigGPT, criar
from .otimizador import AdamW
from .tokenizador import Tokenizador

CHECKPOINT = "checkpoint.pt"
ANTERIOR = "checkpoint-anterior.pt"
DIARIO = "treino.log"
# Por que uma sessão de treino acabou (vai para o registro e para a fala do fim do treino).
MOTIVOS = {"tempo": "o tempo da sessão acabou", "meta": "chegou à meta de passos", "pedido": "parou a pedido",
           "interrupcao": "foi interrompido (Ctrl+C ou sinal do sistema)",
           "estabilizou": "a validação parou de melhorar"}


def _trocar(origem: Path, destino: Path) -> None:
    """``origem.replace(destino)``, com paciência: no Windows falha se outro programa está lendo o destino."""
    for tentativa in range(10):
        try:
            Path(origem).replace(destino)
            return
        except PermissionError:
            if tentativa == 9:
                raise
            time.sleep(0.5)


def impressao(arquivo: Path) -> str:
    """SHA-256 do arquivo, lido aos pedaços (um checkpoint tem dezenas de MB)."""
    resumo = hashlib.sha256()
    with open(arquivo, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def _digital(arquivo: Path) -> Path:
    return arquivo.with_name(arquivo.name + ".sha256")


def confere(arquivo: Path) -> bool | None:
    """O arquivo ainda é o que foi gravado? None se não há impressão guardada (arquivo de antes da v0.5.1)."""
    guardada = _digital(arquivo)
    if not guardada.exists():
        return None
    return guardada.read_text(encoding="ascii").strip() == impressao(arquivo)


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
    # Ao continuar um treino numa sessão nova: "reaquecer" sobe a taxa de novo até ``taxa · taxa_ao_continuar``
    # e desce em cosseno; "retomar" segue com a taxa baixa e constante onde as sessões terminavam
    # (``taxa_ao_retomar``). Reaquecer desarruma o que o cérebro sabe: ver docs/fase1/diagnostico.md, 5.3.
    ao_continuar: str = "retomar"
    amostragem: str = "sorteio"        # "sorteio" (janelas com reposição, em pedaços) ou "passada" (sem repetição)
    sessao_passos: int | None = None   # uma sessão de N passos com o formato de uma sessão em horas (comparável)
    parar_se_estagnar: int = 0         # N > 0: para se a validação não melhorar ``melhora_minima`` em N medidas
    melhora_minima: float = 0.002

    @property
    def taxa_ao_retomar(self) -> float:
        """A taxa em que uma sessão continuada terminava: 10% do pico dela."""
        return self.taxa * self.taxa_ao_continuar * 0.1


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


def arquivo_de_validacao(pasta: Path) -> Path:
    """A validação do conjunto fixo (``conjuntos.py``), se já foi montada; senão, a antiga (o fim do corpus)."""
    from . import conjuntos

    if conjuntos.existe(pasta):
        return Path(pasta) / conjuntos.PASTA / conjuntos.ARQUIVOS["validacao"]
    return Path(pasta) / "val.bin"


def janelas_fixas(arquivo: Path, contexto: int, quantas: int) -> np.ndarray:
    """``quantas`` janelas (de contexto + 1 tokens) espalhadas por igual pelo arquivo: sempre as mesmas.

    Antes a validação sorteava janelas novas a cada medida, e a diferença entre duas medidas
    misturava "o modelo melhorou" com "caíram janelas mais fáceis". Com as mesmas janelas, a
    comparação entre dois momentos do treino é justa.
    """
    dados = np.fromfile(arquivo, dtype=np.uint16)
    possiveis = (len(dados) - 1) // contexto
    escolhidas = np.unique(np.linspace(0, possiveis - 1, min(quantas, possiveis)).astype(np.int64))
    return np.stack([dados[i * contexto:i * contexto + contexto + 1] for i in escolhidas]).astype(np.int64)


@torch.no_grad()
def avaliar(modelo: GPT, janelas: np.ndarray, dispositivo, lote: int = 16) -> float:
    """Perda média nas janelas fixas (todas pesam igual)."""
    soma = 0.0
    for i in range(0, len(janelas), lote):
        bloco = torch.from_numpy(janelas[i:i + lote]).to(dispositivo)
        soma += float(modelo(bloco[:, :-1], bloco[:, 1:])[1]) * len(bloco)
    return soma / len(janelas)


def salvar_checkpoint(arquivo: Path, modelo: GPT, otimizador: AdamW, passo: int, melhor: float,
                      segundos: float, val_digital: str = "", extra: dict | None = None) -> None:
    dados = {
        **(extra or {}),   # a taxa do último passo, o estado do amostrador...
        "config": modelo.configuracao(),
        "modelo": {nome: p.cpu() for nome, p in modelo.state_dict().items()},
        "otimizador": otimizador.estado(),
        "passo": passo,
        "melhor": melhor,             # a melhor perda de validação até aqui...
        "val_digital": val_digital,   # ...medida nestas janelas (se a validação mudar, ``melhor`` é refeita)
        "segundos": segundos,
    }
    temporario = arquivo.with_suffix(".tmp")
    torch.save(dados, temporario)
    digital = impressao(temporario)
    if arquivo.exists():   # o anterior fica guardado: se o novo vier estragado, volta-se a ele
        anterior = arquivo.with_name(ANTERIOR)
        _trocar(arquivo, anterior)
        if _digital(arquivo).exists():
            _trocar(_digital(arquivo), _digital(anterior))
        else:
            _digital(anterior).unlink(missing_ok=True)
    _trocar(temporario, arquivo)  # nunca fica um checkpoint pela metade se a luz cair
    _digital(arquivo).write_text(digital + "\n", encoding="ascii")


def carregar_checkpoint(pasta: Path, avisar=print) -> dict | None:
    """O checkpoint para continuar o treino: o atual, ou o anterior se o atual estiver estragado.

    É lido só como números (``weights_only=True``): um arquivo adulterado com código dentro é recusado
    em vez de executado.
    """
    atual, anterior = Path(pasta) / CHECKPOINT, Path(pasta) / ANTERIOR
    problemas = []
    for arquivo in (atual, anterior):
        if not arquivo.exists():
            continue
        if confere(arquivo) is False:
            problemas.append(f"{arquivo.name} não confere com a impressão digital guardada")
            continue
        try:
            dados = torch.load(arquivo, map_location="cpu", weights_only=True)
        except (pickle.UnpicklingError, RuntimeError, EOFError, ValueError) as erro:
            problemas.append(f"{arquivo.name} não pôde ser lido só como números ({type(erro).__name__})")
            continue
        if problemas:
            avisar(f"aviso: {'; '.join(problemas)}. Continuo a partir de {arquivo.name}.")
        return dados
    if problemas:
        raise SystemExit("Não há checkpoint em que dê para confiar: " + "; ".join(problemas) +
                         ". Restaure uma cópia (python -m kernel copia restaurar) ou apague os checkpoints para "
                         "começar um cérebro novo.")
    return None


def treinar(pasta: Path, cfg: ConfigTreino, avisar=print) -> dict:
    """Treina (ou continua treinando) o cérebro em ``pasta``. Devolve um resumo."""
    pasta = Path(pasta)
    diario_em_texto = pasta / DIARIO
    dizer = avisar

    def avisar(texto: str) -> None:   # noqa: F811  (o que o treino diz vai também para treino.log)
        dizer(texto)
        with open(diario_em_texto, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {texto}\n")

    avisar(f"sessão começou: processo {os.getpid()} | horas {cfg.horas} | meta de passos {cfg.passos} | "
           f"tamanho {cfg.tamanho} | dispositivo pedido {cfg.dispositivo}")
    tokenizador = Tokenizador.carregar(pasta / inferencia.TOKENIZADOR)
    torch.manual_seed(cfg.semente)
    dispositivo, descricao = escolher(cfg.dispositivo)

    arquivo = pasta / CHECKPOINT
    passo, melhor, segundos_antes = 0, float("inf"), 0.0
    salvo = carregar_checkpoint(pasta, avisar)
    if salvo is not None:
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
        modelo = criar(cfg.tamanho, tokenizador.tamanho)
    modelo.to(dispositivo)
    otimizador = AdamW(modelo.parameters(), decaimento=cfg.decaimento)
    if salvo:
        otimizador.carregar_estado(salvo["otimizador"])

    contexto = modelo.cfg.contexto
    if cfg.amostragem == "passada":
        anterior = (salvo or {}).get("amostrador") or {}
        mesmo = anterior.get("amostragem") == "passada" and anterior.get("semente") == cfg.semente
        treino = Passada(pasta / "treino.bin", contexto, cfg.lote, tokenizador.id_fim, semente=cfg.semente,
                         **({"epoca": anterior["epoca"], "posicao": anterior["posicao"]} if mesmo else {}))
        if mesmo and anterior.get("tokens") != len(treino):   # o treino.bin mudou: a posição não vale mais
            treino = Passada(pasta / "treino.bin", contexto, cfg.lote, tokenizador.id_fim, semente=cfg.semente)
            mesmo = False
        avisar(f"passada sem repetição: época {treino.epoca}, {treino.lido():.1%} lida" if mesmo
               else "passada sem repetição: começando uma época nova")
    else:
        treino = Lotes(pasta / "treino.bin", contexto, cfg.lote, semente=cfg.semente + passo)
    arquivo_val = arquivo_de_validacao(pasta)
    janelas_val = janelas_fixas(arquivo_val, contexto, cfg.lotes_de_avaliacao * cfg.lote)
    val_digital = f"{arquivo_val.name}:{hashlib.sha256(janelas_val.tobytes()).hexdigest()[:16]}"
    avisar(f"dispositivo: {descricao}")
    avisar(f"modelo: {modelo.numero_de_parametros() / 1e6:.2f} mi de parâmetros | "
           f"treino: {len(treino) / 1e6:.1f} mi de tokens | validação: {len(janelas_val)} janelas fixas de "
           f"{arquivo_val.name}")
    if salvo is not None and salvo.get("val_digital", "") != val_digital:
        # A validação mudou: a "melhor perda" guardada foi medida em outro texto e não serve de régua.
        # Passa a valer a do modelo exportado (o que o serviço usa), medida na validação de agora.
        exportado = pasta / inferencia.MODELO
        if exportado.exists():
            from .pesos import gpt_de_npz
            melhor = avaliar(gpt_de_npz(exportado, dispositivo), janelas_val, dispositivo)
        else:
            melhor = float("inf")
        avisar(f"a validação mudou para {arquivo_val.name}: a melhor perda passa a ser a do modelo exportado, "
               f"medida nela: {melhor:.4f}")
    por_passos = cfg.sessao_passos is not None               # uma sessão de N passos, no formato de uma em horas
    por_horas = (cfg.passos is None and bool(cfg.horas)) or por_passos   # sessões: a taxa segue o formato da sessão
    meta = passo + cfg.sessao_passos if por_passos else (None if por_horas else (cfg.passos or PASSOS_SEM_META))
    passo_inicial = passo
    retomar = passo_inicial > 0 and por_horas and cfg.ao_continuar == "retomar"
    if passo:
        avisar(f"continuando do passo {passo} (melhor perda de validação até aqui: {melhor:.3f})")
    if retomar:
        avisar(f"continuando sem reaquecer: taxa constante de {cfg.taxa_ao_retomar:.1e}")
    referencia, sem_melhora = melhor, 0   # para parar quando a validação estabilizar
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
        nonlocal melhor, referencia, sem_melhora
        modelo.eval()
        perda_val = avaliar(modelo, janelas_val, dispositivo)
        semente = tokenizador.codificar("O Brasil")
        amostra = tokenizador.decodificar(modelo.gerar(semente, 40, parar_em=tokenizador.id_fim))
        modelo.train()
        segundos = segundos_antes + time.time() - inicio
        salvar_checkpoint(arquivo, modelo, otimizador, passo, min(melhor, perda_val), segundos, val_digital,
                          extra=estado_extra())
        if perda_val <= referencia - cfg.melhora_minima:
            referencia, sem_melhora = perda_val, 0
        else:
            sem_melhora += 1
        if perda_val < melhor:
            melhor = perda_val
            inferencia.exportar(modelo, pasta / inferencia.MODELO)
        with open(diario_de_treino, "a", newline="") as f:
            treino_txt = "" if perda_treino is None else f"{perda_treino:.4f}"   # sem média antes do passo 10
            csv.writer(f).writerow([passo, treino_txt, f"{perda_val:.4f}",
                                    f"{taxa:.6f}", f"{tokens_por_segundo:.0f}", f"{segundos:.0f}"])
        if quadro:
            quadro.add_scalar("perda/validacao", perda_val, passo)
            quadro.add_text("amostra", amostra, passo)
        avisar(f"  validação {perda_val:.3f} (melhor {melhor:.3f}) | amostra: {amostra!r}")

    def estado_extra() -> dict:
        return {"taxa": taxa, **({"amostrador": treino.estado()} if hasattr(treino, "estado") else {})}

    inicio = time.time()
    limite = inicio + cfg.horas * 3600 if cfg.horas else None
    media, marca, passo_da_marca = None, inicio, passo
    normas: list[float] = []   # a norma do gradiente de cada passo (estabilidade do treino)
    tokens_por_segundo, taxa = 0.0, 0.0
    modelo.train()
    pedido_de_parada = pasta / "PARAR"  # o serviço cria este arquivo quando você diz "para o treino"
    motivo = None
    try:
        while (meta is None or passo < meta) and (limite is None or time.time() < limite):
            if pedido_de_parada.exists():
                pedido_de_parada.unlink(missing_ok=True)
                avisar("parando a pedido: salvando o checkpoint...")
                motivo = "pedido"
                break
            if retomar:
                taxa = cfg.taxa_ao_retomar
            elif por_horas:
                fracao = ((passo - passo_inicial) / cfg.sessao_passos if por_passos
                          else (time.time() - inicio) / (cfg.horas * 3600))
                taxa = taxa_na_sessao(cfg, passo - passo_inicial, fracao, continuando=passo_inicial > 0)
            else:
                taxa = taxa_no_passo(cfg, passo)
            for _ in range(cfg.acumular):
                x, y = treino.pegar(dispositivo)
                _, perda = modelo(x, y)
                (perda / cfg.acumular).backward()
            normas.append(otimizador.cortar_gradiente(cfg.corte_gradiente))   # a norma antes do corte
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
                gradiente = (f"gradiente {np.mean(normas):.2f} (máx {max(normas):.2f}, "
                             f"{np.mean(np.array(normas) > cfg.corte_gradiente):.0%} cortados)") if normas else ""
                normas.clear()
                tokens_por_segundo = (passo - passo_da_marca) * cfg.acumular * cfg.lote * contexto / (agora - marca)
                marca, passo_da_marca = agora, passo
                if meta is None:
                    faltam = max(limite - agora, 0.0)
                    avisar(f"passo {passo:6d} | perda {media:.3f} | taxa {taxa:.2e} | "
                           f"{tokens_por_segundo:,.0f} tok/s | faltam {faltam / 3600:.1f} h desta sessão | {gradiente}")
                else:
                    faltam = (meta - passo) * cfg.acumular * cfg.lote * contexto / tokens_por_segundo
                    avisar(f"passo {passo:6d}/{meta} | perda {media:.3f} | taxa {taxa:.2e} | "
                           f"{tokens_por_segundo:,.0f} tok/s | faltam {faltam / 3600:.1f} h para a meta | {gradiente}")
                if quadro:
                    quadro.add_scalar("perda/treino", media, passo)
                    quadro.add_scalar("taxa", taxa, passo)
            if passo % cfg.avaliar_cada == 0:
                ponto_de_controle(media, tokens_por_segundo)
                marca, passo_da_marca = time.time(), passo
                if cfg.parar_se_estagnar and sem_melhora >= cfg.parar_se_estagnar:
                    avisar(f"a validação não melhorou {cfg.melhora_minima} em {sem_melhora} medidas seguidas: parando")
                    motivo = "estabilizou"
                    break
    except KeyboardInterrupt:
        avisar("interrompido: salvando o checkpoint antes de sair...")
        motivo = "interrupcao"
    except RuntimeError as erro:
        avisar(f"erro no passo {passo}: {erro!r}")
        if "memory" not in str(erro).lower():
            raise
        raise SystemExit(f"Faltou memória de vídeo com lote {cfg.lote}. Tente a metade do lote e o dobro "
                         f"de acúmulo: --lote {max(1, cfg.lote // 2)} --acumular {cfg.acumular * 2}") from None
    if motivo is None:
        motivo = "meta" if meta is not None and passo >= meta else "tempo"
    if motivo == "interrupcao":   # quem está sendo fechado tem poucos segundos: salva já, sem avaliar
        salvar_checkpoint(arquivo, modelo, otimizador, passo, melhor, segundos_antes + time.time() - inicio,
                          val_digital, extra=estado_extra())
    elif media is not None and passo % cfg.avaliar_cada != 0:
        ponto_de_controle(media, tokens_por_segundo)
    if quadro:
        quadro.close()
    duracao = time.time() - inicio
    avisar(f"sessão acabou: {MOTIVOS[motivo]} | passo {passo} | {duracao / 60:.1f} min nesta sessão")
    return {"passo": passo, "passo_inicial": passo_inicial, "melhor_validacao": melhor, "perda_treino": media,
            "parametros": modelo.numero_de_parametros(), "dispositivo": descricao,
            "tokens_por_segundo": tokens_por_segundo, "motivo": motivo, "segundos": round(duracao, 1),
            "horas_pedidas": cfg.horas, "config": asdict(cfg)}


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
