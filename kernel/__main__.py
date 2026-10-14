"""Linha de comando do K.E.R.N.E.L.

    python -m kernel iniciar            liga o serviço e abre a janela de chat
    python -m kernel desligar           o freio de mão
    python -m kernel estado             ele está rodando?
    python -m kernel selar              sela o código de segurança depois de você revisar
    python -m kernel comandos ...       classificador de comandos
    python -m kernel memoria ...        buscar e guardar direto na memória
    python -m kernel cerebro ...        micrograd, bigramas, tokenizador, treino
    python -m kernel ouvidos ...        gravar e treinar a palavra de ativação
    python -m kernel diario             escreve o diário de hoje agora
    python -m kernel falar "texto"      grava a voz dele dizendo o texto (falar.wav)
    python -m kernel voz ...            banco de difones: baixar gravações e construir
    python -m kernel internet ...       pesquisar um assunto, ler uma página, ver o que já pesquisou
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from datetime import date
from pathlib import Path

from . import NOME, NOME_COMPLETO, VERSAO
from .config import carregar


# ================================================================== serviço
def _saude(porta: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/saude", timeout=2) as resposta:
            return json.load(resposta)
    except OSError:
        return None


def _abrir_janela(endereco: str) -> None:
    """Abre o chat numa janela própria (Edge em modo aplicativo) ou no navegador padrão."""
    candidatos = [shutil.which("msedge"),
                  r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                  r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
    for edge in candidatos:
        if edge and Path(edge).exists():
            subprocess.Popen([edge, f"--app={endereco}", "--window-size=1180,760"])
            return
    webbrowser.open(endereco)


def _interromper(_sinal, _quadro):
    raise KeyboardInterrupt


def iniciar(args) -> int:
    cfg = carregar()
    endereco = f"http://127.0.0.1:{cfg.nucleo.porta}/"
    if _saude(cfg.nucleo.porta):
        print(f"{NOME} já está rodando em {endereco}")
        if args.janela:
            _abrir_janela(endereco)
        return 0

    if sys.stdout is None or sys.stderr is None:  # pythonw: sem console, então escrevemos num arquivo
        diario_do_servico = cfg.dados / "servico.log"
        if diario_do_servico.exists() and diario_do_servico.stat().st_size > 5_000_000:
            diario_do_servico.replace(cfg.dados / "servico.log.1")   # guarda o anterior; não cresce sem fim
        sys.stdout = sys.stderr = open(diario_do_servico, "a", encoding="utf-8", buffering=1)

    import uvicorn

    from .interface.api import criar_app
    from .nucleo import Kernel

    kernel = Kernel(cfg)
    app = criar_app(kernel, secrets.token_urlsafe(24))
    # Só a sua máquina enxerga o serviço, a não ser que você tenha ligado o acesso pelo celular.
    anfitriao = "0.0.0.0" if cfg.celular.ligado else "127.0.0.1"
    servidor = uvicorn.Server(uvicorn.Config(app, host=anfitriao, port=cfg.nucleo.porta,
                                             log_level="warning", access_log=False))
    kernel.ao_desligar = lambda: setattr(servidor, "should_exit", True)
    arquivo_pid = cfg.dados / "kernel.pid"
    if arquivo_pid.exists():
        # O arquivo só fica para trás quando o processo anterior morreu sem desligar (fechado à força,
        # travou, faltou luz). Fica anotado, para não ser um mistério depois.
        kernel.registro.anotar("servico", evento="queda_anterior",
                               pid=arquivo_pid.read_text(encoding="utf-8", errors="replace").strip()[:12],
                               desde=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(arquivo_pid.stat().st_mtime)))
    arquivo_pid.write_text(str(os.getpid()))
    print(f"{NOME} {VERSAO} — {NOME_COMPLETO}")
    print(f"janela de chat: {endereco}   (Ctrl+C ou o botão Desligar para parar)")
    if cfg.celular.ligado:
        from .interface.api import enderecos_na_rede

        for ip in enderecos_na_rede():
            print(f"no celular (mesma rede): http://{ip}:{cfg.nucleo.porta}/")
        print("ATENÇÃO: o acesso pelo celular é HTTP, sem criptografia. Use só no Wi-Fi de casa; "
              "quem não for da rede local é recusado.")
    if kernel.seguranca.modo_seguro:
        print(f"ATENÇÃO: modo seguro — {kernel.seguranca.motivo_modo_seguro}")
    if args.janela:
        threading.Timer(1.5, _abrir_janela, [endereco]).start()
    try:
        servidor.run()
    finally:
        arquivo_pid.unlink(missing_ok=True)
    return 0


def desligar(_args) -> int:
    cfg = carregar()
    if not _saude(cfg.nucleo.porta):
        print(f"{NOME} não está rodando.")
        return 0
    (cfg.dados / "DESLIGAR").write_text("desligar\n")  # o laço vê este arquivo na próxima volta
    for _ in range(40):
        time.sleep(0.5)
        if not _saude(cfg.nucleo.porta):
            print(f"{NOME} desligado.")
            return 0
    print("Ele não respondeu ao pedido. Para forçar, encerre o processo do arquivo dados/kernel.pid.")
    return 1


def estado(_args) -> int:
    cfg = carregar()
    saude = _saude(cfg.nucleo.porta)
    if saude:
        print(f"{saude['nome']} {saude['versao']} rodando em http://127.0.0.1:{cfg.nucleo.porta}/")
    else:
        print(f"{NOME} não está rodando. Ligue com: python -m kernel iniciar")
    return 0


def selar(_args) -> int:
    from .seguranca import integridade

    integro, mudancas = integridade.verificar()
    if integro:
        print("O código de segurança já está selado e íntegro.")
        return 0
    print("Mudanças desde o último selo:")
    for mudanca in mudancas:
        print("  -", mudanca)
    for nome, digital in integridade.selar().items():
        print(f"  selado {nome}  {digital[:16]}…")
    print("Selado. Reinicie o serviço para sair do modo seguro.")
    return 0


def diario(_args) -> int:
    from .memoria import Memoria
    from .mente import Diario
    from .registro import Registro

    cfg = carregar()
    escritor = Diario(cfg, Registro(cfg.pasta("registro")), Memoria(cfg.dados / "kernel.db"))
    print(escritor.escrever(date.today()))
    return 0


def falar(args) -> int:
    from . import voz as v
    from .voz.fonemas import texto_para_fonemas

    cfg = carregar()
    if args.motor:
        cfg.voz.motor = args.motor
    if args.estilo:
        cfg.voz.estilo = args.estilo
    print("fonemas:", " ".join(texto_para_fonemas(args.texto)))
    onda, taxa, motor = v.onda_com(cfg, args.texto)
    destino = Path(args.saida)
    destino.write_bytes(v._wav(onda, taxa))
    print(f"motor: {motor} | {len(onda) / taxa:.1f} s de fala | gravado em {destino.resolve()}")
    if args.tocar:
        import winsound

        winsound.PlaySound(str(destino), winsound.SND_FILENAME)
    return 0


def voz(args) -> int:
    from .voz import corpus, difones

    cfg = carregar()
    pasta = cfg.pasta("voz", "corpus")
    if args.acao == "baixar":
        lista = corpus.baixar_lista(pasta, args.frases)
        minutos = sum(f["fim"] - f["inicio"] for f in lista) / 60
        print(f"{len(lista)} frases, {minutos:.0f} minutos de fala")
        arquivos = corpus.baixar_mp3(lista, pasta / "mp3")
        print(f"{len(arquivos)} arquivos MP3, {sum(a.stat().st_size for a in arquivos) / 1e6:.0f} MB em {pasta / 'mp3'}")
    elif args.acao == "construir":
        meta = difones.construir(pasta, cfg.pasta("voz", "banco"), frases=args.frases, minutos=args.minutos)
        print(f"banco pronto: {meta['frases']} frases ({meta['minutos']} min), {meta['metades']} metades de fonema, "
              f"{meta['fonemas']} fonemas e {meta['difones']} difones diferentes; tom mediano {meta['tom']:.0f} Hz")
        print("Reinicie o serviço para ele falar com a voz nova.")
    else:
        from .voz import falante_de

        falante = falante_de(cfg)
        if falante is None:
            print("Ainda não há banco de difones. Rode: python -m kernel voz baixar  e depois  voz construir")
            return 1
        m = falante.meta
        print(f"{m['frases']} frases ({m['minutos']} min) | {m['metades']} metades | {m['fonemas']} fonemas | "
              f"{m['difones']} difones | tom {m['tom']:.0f} Hz\nfonte: {m['fonte']}")
    return 0


def internet(args) -> int:
    """Pesquisa pela linha de comando (com o serviço desligado ou ligado: a memória é a mesma)."""
    from .internet import Pesquisador
    from .memoria import Memoria
    from .registro import Registro
    from .seguranca import Seguranca

    cfg = carregar()
    registro = Registro(cfg.pasta("registro"))
    pesquisador = Pesquisador(cfg, Seguranca(cfg, registro), Memoria(cfg.dados / "kernel.db"), registro)
    if args.acao == "estado":
        n = pesquisador.numeros()
        ligada = "ligada" if cfg.internet.ligada else "DESLIGADA (kernel.toml, [internet] ligada = true)"
        print(f"internet {ligada} | sozinho: {'sim' if cfg.internet.pesquisar_sozinho else 'não'} | "
              f"buscador: {'sim' if cfg.internet.buscador else 'não'}")
        print(f"{n['pesquisados']} assuntos pesquisados, {n['paginas']} páginas lidas, {n['na_fila']} na fila")
        print(pesquisador.relato())
        return 0
    if not cfg.internet.ligada:
        print("A internet está desligada. Ligue em kernel.toml: [internet] ligada = true")
        return 1
    resultado = (pesquisador.ler_pagina(args.alvo) if args.acao == "ler"
                 else pesquisador.pesquisar(args.alvo, por_conta_propria=False))
    print(resultado.resposta or "(nada)")
    for fonte in resultado.fontes:
        print(f"  [{fonte.fonte}] {fonte.titulo}  —  {fonte.url}  ({fonte.letras} letras)")
    print(f"  {resultado.trechos} trechos guardados na memória")
    for aviso in resultado.avisos:
        print("  aviso:", aviso)
    return 0 if resultado.fontes else 1


# ================================================================= comandos
def comandos(args) -> int:
    from . import comandos as c
    from .comandos.classificador import arquivos_de_exemplos

    cfg = carregar()
    do_projeto, extras = arquivos_de_exemplos(cfg)
    if args.acao == "treinar":
        exemplos = c.carregar_exemplos(do_projeto, extras)
        print(f"{len(exemplos)} exemplos, {len(c.INTENCOES)} intenções")
        modelo = c.treinar(exemplos, ao_progredir=lambda e, p, a: print(f"  época {e:3d}  perda {p:.3f}  acerto {a:.0%}"))
        modelo.salvar(cfg.pasta("comandos") / "modelo.npz")
        print("classificador salvo em dados/comandos/modelo.npz")
    elif args.acao == "testar":
        modelo = c.garantir(cfg)
        for nome, p in sorted(modelo.probabilidades(args.frase).items(), key=lambda par: -par[1]):
            print(f"  {p:6.1%}  {nome}")
    elif args.acao == "ensinar":
        if args.intencao not in c.INTENCOES:
            print("intenções:", ", ".join(c.INTENCOES))
            return 2
        with open(extras, "a", encoding="utf-8") as f:
            f.write(f"[{args.intencao}]\n{args.frase}\n")
        print(f'aprendi o exemplo "{args.frase}" -> {args.intencao}. Rode: python -m kernel comandos treinar')
    return 0


# ================================================================== memória
def memoria(args) -> int:
    from .memoria import Memoria

    cfg = carregar()
    banco = Memoria(cfg.dados / "kernel.db")
    if args.acao == "buscar":
        achados = banco.buscar(args.texto, k=10)
        for a in achados:
            print(f"  {a.pontos:5.2f}  [{a.tipo}] {a.texto}")
        if not achados:
            print("nada encontrado.")
    elif args.acao == "guardar":
        print("guardado com id", banco.guardar(args.texto, tipo="fato", origem="usuario"))
    else:
        for tipo, n in banco.contar().items():
            print(f"  {n:6d}  {tipo}")
    return 0


# ================================================================== cérebro
def _barra(feito: float, total: float, extra: str = "") -> None:
    fracao = min(1.0, feito / total) if total else 0.0
    print(f"\r  [{'#' * int(30 * fracao):30}] {fracao:5.1%} {extra}", end="", flush=True)


def cerebro(args) -> int:
    cfg = carregar()
    pasta = cfg.pasta("cerebro")
    corpus = Path(getattr(args, "corpus", None) or pasta / "corpus.txt")

    if args.acao == "micrograd":
        from .cerebro import micrograd
        micrograd.demonstrar()
    elif args.acao == "bigrama":
        from .cerebro import bigrama
        bigrama.demonstrar()

    elif args.acao == "wikipedia":
        from .cerebro import wikipedia
        partes = wikipedia.listar_partes()
        if not partes:
            print("Não achei as partes do dump em", wikipedia.INDICE)
            return 1
        total = sum(tamanho for _, tamanho in partes)
        print(f"O dump tem {len(partes)} partes ({total / 1e9:.1f} GB compactado).")
        escolhidas = partes[:args.partes]
        (pasta / "wiki").mkdir(exist_ok=True)
        arquivos = []
        for nome, tamanho in escolhidas:
            print(f"baixando {nome} ({tamanho / 1e6:.0f} MB)" + (f", só os primeiros {args.max_mb} MB" if args.max_mb else ""))
            arquivos.append(wikipedia.baixar(nome, pasta / "wiki", args.max_mb,
                                             lambda feito, tudo: _barra(feito, tudo, f"{feito / 1e6:.0f} MB")))
            print()
        print("limpando o wikitexto...")
        resumo = wikipedia.extrair(arquivos, corpus, args.artigos,
                                   ao_progredir=lambda n, c: print(f"\r  {n} artigos, {c / 1e6:.0f} MB de texto", end=""))
        print(f"\ncorpus pronto: {resumo['artigos']} artigos, {resumo['caracteres'] / 1e6:.1f} MB em {corpus}")

    elif args.acao == "tokenizador":
        from .cerebro import tokenizador
        if not corpus.exists():
            print(f"Não achei o corpus em {corpus}. Rode antes: python -m kernel cerebro wikipedia")
            return 1
        with open(corpus, encoding="utf-8") as f:
            amostra = f.read(int(args.amostra_mb * 1024 * 1024))
        print(f"treinando BPE de {args.vocab} tokens em {len(amostra) / 1e6:.1f} MB de texto...")
        inicio = time.time()
        tok = tokenizador.treinar([amostra], args.vocab, lambda feito, tudo: _barra(feito, tudo))
        tok.salvar(pasta / "tokenizador.json")
        ids = tok.codificar(amostra[:200_000])
        print(f"\npronto em {time.time() - inicio:.0f} s: {tok.tamanho} tokens, "
              f"{len(amostra[:200_000]) / len(ids):.2f} caracteres por token")
        print("exemplo:", [tok.decodificar([i]) for i in tok.codificar("O Brasil é um país da América do Sul.")])

    elif args.acao == "preparar":
        from .cerebro import dados, tokenizador
        tok = tokenizador.Tokenizador.carregar(pasta / "tokenizador.json")
        resumo = dados.preparar(corpus, tok, pasta, lambda lido, tudo, n: _barra(lido, tudo, f"{n / 1e6:.1f} mi tokens"))
        print(f"\ntreino.bin: {resumo['treino'] / 1e6:.2f} mi de tokens | val.bin: {resumo['val'] / 1e6:.2f} mi")

    elif args.acao == "treinar":
        from .cerebro.gpt import LOTES
        from .cerebro.treinar import ConfigTreino, treinar
        tamanho = args.tamanho or cfg.cerebro.tamanho
        lote, acumular = LOTES[tamanho]
        treino = ConfigTreino(tamanho=tamanho, passos=args.passos, horas=args.horas,
                              lote=args.lote or lote, acumular=args.acumular or acumular, taxa=args.taxa,
                              avaliar_cada=args.avaliar_cada, dispositivo=args.dispositivo or cfg.cerebro.dispositivo)
        from .cerebro.treinar import MOTIVOS
        if hasattr(signal, "SIGBREAK"):
            # No Windows, fechar o console, sair da conta ou o sistema fechando o programa chegam como SIGBREAK,
            # que por padrão mata o processo na hora. Assim eles viram uma interrupção: o checkpoint é salvo.
            signal.signal(signal.SIGBREAK, _interromper)
        resumo = treinar(pasta, treino)
        print(f"parou no passo {resumo['passo']} ({MOTIVOS[resumo['motivo']]}) com perda de validação "
              f"{resumo['melhor_validacao']:.3f}. Reinicie o serviço para ele usar o cérebro novo.")
        # a última linha é para o serviço: ele lê daqui por que o treino parou
        print("RESUMO " + json.dumps({chave: resumo[chave] for chave in
                                      ("motivo", "passo", "passo_inicial", "melhor_validacao", "segundos", "horas_pedidas")}))

    elif args.acao == "medir":
        from .cerebro.gpt import LOTES
        if not (args.tamanho and args.dispositivo):
            # Uma medida por processo: o DirectML não devolve a VRAM de um modelo para o seguinte.
            for tamanho in ([args.tamanho] if args.tamanho else list(LOTES)):
                for dispositivo in ([args.dispositivo] if args.dispositivo else ["directml", "cpu"]):
                    subprocess.run([sys.executable, "-m", "kernel", "cerebro", "medir",
                                    "--tamanho", tamanho, "--dispositivo", dispositivo])
            return 0
        from .cerebro.treinar import medir
        lote = LOTES[args.tamanho][0]
        try:
            m = medir(args.tamanho, 8192 if args.tamanho == "pequeno" else 4096, lote, args.dispositivo)
        except RuntimeError as erro:  # normalmente falta de VRAM
            print(f"  {args.tamanho:8} lote {lote:2} em {args.dispositivo}: não coube ({str(erro)[:60]})")
            return 1
        print(f"  {args.tamanho:8} {m['parametros'] / 1e6:5.1f} mi | lote {lote:2} | {m['dispositivo']:32} | "
              f"{m['tokens_por_segundo']:6,.0f} tokens/s | {m['tokens_por_segundo'] * 3.6 / 1000:5.1f} mi de tokens por hora")

    elif args.acao == "gerar":
        from .cerebro import inferencia
        modelo = inferencia.carregar(cfg)
        if modelo is None:
            print("Ainda não há cérebro treinado em dados/cerebro.")
            return 1
        print(args.texto + modelo.continuar(args.texto, args.tokens, args.temperatura, cfg.cerebro.top_k))

    elif args.acao == "avaliar":
        import math

        from .cerebro import inferencia
        modelo = inferencia.carregar(cfg)
        if modelo is None:
            print("Ainda não há cérebro treinado em dados/cerebro.")
            return 1
        print(modelo.descricao)
        historia = inferencia.historico(pasta)
        if historia:
            print(f"treino: {historia['passos']} passos, {historia['horas']:.1f} h, {historia['tokens'] / 1e6:.0f} mi de tokens lidos | "
                  f"perda de validação {historia['primeira']:.2f} -> {historia['perda']:.2f} (melhor {historia['melhor']:.2f})")
        medida = inferencia.avaliar(modelo, pasta, args.janelas)
        if medida:
            print(f"medido agora em {medida['tokens']} tokens que ele nunca viu: perda {medida['perda']:.3f}, "
                  f"perplexidade {medida['perplexidade']:.1f} (em dúvida entre ~{medida['perplexidade']:.0f} pedaços a cada passo; "
                  f"um chute às cegas seria {modelo.cfg['vocab']}, e log dele {math.log(modelo.cfg['vocab']):.2f})")
        inicio = time.time()
        for comeco in ("O Brasil é", "A inteligência artificial é", "Em 1500,"):
            print(f"  {comeco} {modelo.responder(comeco, 50, cfg.cerebro.temperatura, cfg.cerebro.top_k)}")
        print(f"(3 amostras em {time.time() - inicio:.1f} s)")
    return 0


# ================================================================== cópias
def copia(args) -> int:
    from . import copias

    cfg = carregar()
    if args.acao == "fazer":
        pasta = copias.fazer(cfg, motivo="manual", manter=cfg.copias.manter)
        print(f"cópia feita: {pasta}")
    elif args.acao == "listar":
        lista = copias.listar(cfg)
        if not lista:
            print("Nenhuma cópia ainda. Faça uma com: python -m kernel copia fazer")
        for c in lista:
            print(f"{c['nome']:<40} {c['bytes'] / 1e6:8.1f} MB  {c['arquivos']:4d} arquivos  cérebro: {c['cerebro']}")
    elif args.acao == "conferir":
        nomes = [args.nome] if args.nome else [c["nome"] for c in copias.listar(cfg)]
        ruins = 0
        for nome in nomes:
            problemas = copias.conferir(copias.pasta_das_copias(cfg) / nome)
            ruins += bool(problemas)
            print(f"{nome}: {'inteira' if not problemas else '; '.join(problemas)}")
        return 1 if ruins else 0
    elif args.acao in ("restaurar", "compactar"):
        if _saude(cfg.nucleo.porta):
            print(f"Desligue o {NOME} antes (python -m kernel desligar): ele não pode estar usando os bancos.")
            return 1
        if args.acao == "compactar":
            for banco, (antes, depois) in copias.compactar(cfg).items():
                print(f"{banco}: {antes / 1e6:.1f} MB -> {depois / 1e6:.1f} MB")
            return 0
        try:
            resultado = copias.restaurar(cfg, args.nome)
        except copias.ErroCopia as erro:
            print(f"Não restaurei nada: {erro}")
            return 1
        print(f"restaurado: {', '.join(resultado['restaurados'])}")
        print(f"O estado de antes ficou na cópia {resultado['seguranca']} (para desfazer, restaure ela).")
    return 0


# ================================================================== ouvidos
def ouvidos(args) -> int:
    cfg = carregar()
    pasta = cfg.pasta("ouvidos")
    microfone = None if cfg.ouvidos.microfone < 0 else cfg.ouvidos.microfone

    if args.acao == "microfones":
        from .ouvidos import gravar
        for linha in gravar.microfones() or ["nenhum microfone encontrado"]:
            print(" ", linha)
    elif args.acao == "gravar":
        from .ouvidos import gravar
        if args.tipo == "ruido":
            print("gravado:", gravar.gravar_ruido(pasta / "gravacoes", args.segundos, microfone))
        else:
            feitas = gravar.gravar(pasta / "gravacoes", args.tipo, args.quantidade, cfg.ouvidos.palavra, microfone)
            print(f"{feitas} gravações salvas em {pasta / 'gravacoes' / args.tipo}")
    elif args.acao == "treinar":
        from .ouvidos import treinar as t
        gravacoes = t.carregar_gravacoes(pasta / "gravacoes")
        rede, medidas = t.treinar(gravacoes, ao_progredir=lambda e, p: print(f"  época {e:2d}  perda {p:.4f}"))
        rede.limiar = cfg.ouvidos.limiar
        rede.salvar(pasta / t.MODELO)
        print(f"acerto {medidas['acerto']:.1%} | não ouviu {medidas['nao_ouviu']:.1%} | "
              f"alarme falso {medidas['alarme_falso']:.1%}  (em gravações que ficaram fora do treino)")
        print("modelo salvo. Reinicie o serviço para ele começar a escutar.")
    elif args.acao == "escutar":
        from .ouvidos import escutar
        ouvidos_, motivo = escutar.iniciar(cfg, lambda p: print(f"  ouvi! (certeza {p:.0%})"))
        if ouvidos_ is None:
            print("Não liguei os ouvidos:", motivo)
            return 1
        print(f'Escutando. Diga "{cfg.ouvidos.palavra}". Ctrl+C para sair.')
        try:
            while True:
                time.sleep(0.2)
        except KeyboardInterrupt:
            ouvidos_.parar()
    return 0


# ================================================================== entrada
def main(argv: list[str] | None = None) -> int:
    for saida in (sys.stdout, sys.stderr):  # o console do Windows nem sempre vem em UTF-8
        if saida is not None and hasattr(saida, "reconfigure"):
            # linha a linha: um treino de horas redirecionado para arquivo mostra o progresso na hora
            saida.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

    analisador = argparse.ArgumentParser(prog="python -m kernel", description=f"{NOME} — {NOME_COMPLETO}")
    sub = analisador.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("iniciar", help="liga o serviço")
    p.add_argument("--janela", action="store_true", help="abre a janela de chat")
    p.set_defaults(funcao=iniciar)
    sub.add_parser("desligar", help="o freio de mão").set_defaults(funcao=desligar)
    sub.add_parser("estado", help="ele está rodando?").set_defaults(funcao=estado)
    sub.add_parser("selar", help="sela o código de segurança").set_defaults(funcao=selar)
    sub.add_parser("diario", help="escreve o diário de hoje").set_defaults(funcao=diario)

    p = sub.add_parser("falar", help="grava a voz dele dizendo um texto")
    p.add_argument("texto")
    p.add_argument("--saida", default="falar.wav")
    p.add_argument("--tocar", action="store_true", help="toca no alto-falante depois de gravar")
    p.add_argument("--motor", choices=["difones", "formantes"], help="padrão: o do kernel.toml")
    p.add_argument("--estilo", choices=["natural", "robotica"])
    p.set_defaults(funcao=falar)

    p = sub.add_parser("voz", help="banco de difones: baixar gravações e construir")
    acoes = p.add_subparsers(dest="acao", required=True)
    a = acoes.add_parser("baixar", help="baixa a lista de frases e os MP3 do LibriVox")
    a.add_argument("--frases", type=int, default=400)
    a = acoes.add_parser("construir", help="alinha as gravações e corta os difones")
    a.add_argument("--frases", type=int, default=None)
    a.add_argument("--minutos", type=float, default=45.0)
    acoes.add_parser("estado", help="mostra o banco atual")
    p.set_defaults(funcao=voz)

    p = sub.add_parser("internet", help="pesquisar na internet, ler uma página, ver o que já pesquisou")
    acoes = p.add_subparsers(dest="acao", required=True)
    acoes.add_parser("pesquisar", help="pesquisa um assunto agora e guarda na memória").add_argument("alvo")
    acoes.add_parser("ler", help="lê um endereço e guarda o texto na memória").add_argument("alvo")
    acoes.add_parser("estado", help="o que já pesquisou e o que está na fila")
    p.set_defaults(funcao=internet)

    p = sub.add_parser("comandos", help="classificador de comandos")
    acoes = p.add_subparsers(dest="acao", required=True)
    acoes.add_parser("treinar")
    acoes.add_parser("testar").add_argument("frase")
    a = acoes.add_parser("ensinar")
    a.add_argument("frase")
    a.add_argument("intencao")
    p.set_defaults(funcao=comandos)

    p = sub.add_parser("memoria", help="memória longa")
    acoes = p.add_subparsers(dest="acao", required=True)
    acoes.add_parser("buscar").add_argument("texto")
    acoes.add_parser("guardar").add_argument("texto")
    acoes.add_parser("contar")
    p.set_defaults(funcao=memoria)

    p = sub.add_parser("cerebro", help="do micrograd ao mini GPT")
    acoes = p.add_subparsers(dest="acao", required=True)
    acoes.add_parser("micrograd", help="backpropagation à mão aprendendo o XOR")
    acoes.add_parser("bigrama", help="modelo de bigramas inventando nomes")
    a = acoes.add_parser("wikipedia", help="baixa e limpa a Wikipédia PT")
    a.add_argument("--partes", type=int, default=1, help="quantas partes do dump baixar")
    a.add_argument("--max-mb", type=float, default=None, help="baixa só o começo de cada parte (amostra)")
    a.add_argument("--artigos", type=int, default=None, help="para depois de N artigos")
    a.add_argument("--corpus")
    a = acoes.add_parser("tokenizador", help="treina o BPE")
    a.add_argument("--vocab", type=int, default=4096)
    a.add_argument("--amostra-mb", type=float, default=20.0)
    a.add_argument("--corpus")
    acoes.add_parser("preparar", help="tokeniza o corpus em treino.bin e val.bin").add_argument("--corpus")
    a = acoes.add_parser("treinar", help="treina (ou continua treinando) o mini GPT")
    a.add_argument("--tamanho", choices=["nano", "mini", "pequeno"])
    a.add_argument("--passos", type=int, default=None, help="meta total de passos (sem isso e sem --horas: 20000)")
    a.add_argument("--horas", type=float, default=None, help="uma sessão de N horas, continuando de onde parou")
    a.add_argument("--lote", type=int, default=None, help="padrão: o que cabe na RX 570 para o tamanho")
    a.add_argument("--acumular", type=int, default=None)
    a.add_argument("--taxa", type=float, default=6e-4)
    a.add_argument("--avaliar-cada", type=int, default=500)
    a.add_argument("--dispositivo", choices=["auto", "directml", "cuda", "cpu"])
    a = acoes.add_parser("medir", help="mede a velocidade de treino neste PC")
    a.add_argument("--tamanho", choices=["nano", "mini", "pequeno"])
    a.add_argument("--dispositivo", choices=["auto", "directml", "cuda", "cpu"])
    a = acoes.add_parser("avaliar", help="mede o cérebro treinado e mostra amostras")
    a.add_argument("--janelas", type=int, default=24)
    a = acoes.add_parser("gerar", help="pede um texto ao cérebro treinado")
    a.add_argument("texto")
    a.add_argument("--tokens", type=int, default=80)
    a.add_argument("--temperatura", type=float, default=0.8)
    p.set_defaults(funcao=cerebro)

    p = sub.add_parser("ouvidos", help="palavra de ativação")
    acoes = p.add_subparsers(dest="acao", required=True)
    acoes.add_parser("microfones")
    a = acoes.add_parser("gravar")
    a.add_argument("tipo", choices=["positivo", "negativo", "ruido"])
    a.add_argument("--quantidade", type=int, default=100)
    a.add_argument("--segundos", type=int, default=120)
    acoes.add_parser("treinar")
    acoes.add_parser("escutar")
    p.set_defaults(funcao=ouvidos)

    p = sub.add_parser("copia", help="cópias de segurança: fazer, listar, conferir, restaurar, compactar")
    acoes = p.add_subparsers(dest="acao", required=True)
    acoes.add_parser("fazer", help="faz uma cópia agora (pode ser com o serviço ligado)")
    acoes.add_parser("listar", help="as cópias guardadas, da mais nova para a mais antiga")
    acoes.add_parser("conferir", help="confere as impressões digitais e os bancos").add_argument("nome", nargs="?")
    acoes.add_parser("restaurar", help="volta os dados para os de uma cópia (serviço desligado)").add_argument("nome")
    acoes.add_parser("compactar", help="VACUUM nos bancos (serviço desligado)")
    p.set_defaults(funcao=copia)

    args = analisador.parse_args(argv)
    return args.funcao(args)


if __name__ == "__main__":
    sys.exit(main())
