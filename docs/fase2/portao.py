"""Fase 2: o portão do candidato (o que os testes automáticos não cobrem).

1. a impressão digital (SHA-256) dos pesos, que ficam fora do Git;
2. a inferência em NumPy (a do serviço) contra o PyTorch, nos pesos reais, em janelas do teste fixo
   (a mesma checagem da Fase 1, ``verificar.inferencia_numpy``);
3. a velocidade de geração na CPU, um token por vez, como o serviço gera (o portão pede 20 tokens/s);
4. o serviço de verdade: liga ``python -m kernel iniciar`` numa porta à parte, com uma pasta de dados
   temporária que só tem uma cópia do candidato, e pede "completa: ..." pela API, do jeito que a janela
   de chat pede. O cérebro instalado e o serviço de sempre não são tocados.

    python docs/fase2/portao.py --modelo dados/fase2/candidato/cerebro/modelo.npz --saida docs/fase2/portao.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
PYTHON = RAIZ / ".venv" / "Scripts" / "python.exe"
MINIMO_DE_TOKENS_POR_SEGUNDO = 20


def conferir_inferencia(modelo: Path, tokenizador: Path, janelas: int = 4) -> dict:
    """NumPy contra PyTorch em algumas janelas do teste fixo, espalhadas pelo conjunto."""
    from kernel.cerebro.tokenizador import Tokenizador
    from kernel.cerebro.verificar import inferencia_numpy

    tok = Tokenizador.carregar(tokenizador)
    teste = np.fromfile(RAIZ / "dados" / "cerebro" / "avaliacao" / "teste.bin", dtype=np.uint16)
    resultados = []
    for i in range(janelas):
        inicio = (len(teste) - 1024) * i // max(1, janelas - 1)
        resultado = inferencia_numpy(modelo, tok, teste[inicio:inicio + 1024])
        resultados.append({"inicio": int(inicio), "ok": resultado.ok, "detalhe": resultado.detalhe})
    return {"ok": all(r["ok"] for r in resultados), "janelas": resultados}


def medir_velocidade(modelo: Path, tokenizador: Path, rodadas: int = 5) -> dict:
    """Tokens por segundo gerando na CPU pela interface (a mesma conta do protocolo), mediana de algumas rodadas."""
    from kernel.cerebro.interface import Especificacao, carregar

    cerebro = carregar(Especificacao(modelo, tokenizador, motor="numpy"))
    cerebro.velocidade_de_geracao(20)   # a primeira chamada paga a preparação; não conta
    medidas = [cerebro.velocidade_de_geracao(200, semente=s) for s in range(rodadas)]
    mediana = statistics.median(medidas)
    return {"ok": mediana >= MINIMO_DE_TOKENS_POR_SEGUNDO, "tokens_por_segundo": round(mediana, 1),
            "medidas": [round(m, 1) for m in medidas], "minimo_do_portao": MINIMO_DE_TOKENS_POR_SEGUNDO,
            "descricao": cerebro.descricao, "parametros": cerebro.parametros}


def _pedir(url: str, codigo: str | None = None, corpo: dict | None = None, espera: float = 10):
    pedido = urllib.request.Request(url, data=json.dumps(corpo).encode() if corpo is not None else None,
                                    headers={"Content-Type": "application/json", **({"x-kernel-codigo": codigo} if codigo else {})})
    with urllib.request.urlopen(pedido, timeout=espera) as resposta:
        conteudo = resposta.read().decode("utf-8")
    return json.loads(conteudo) if resposta.headers.get_content_type() == "application/json" else conteudo


def no_servico(modelo: Path, tokenizador: Path, porta: int, comeco: str = "O Brasil é") -> dict:
    """Um serviço de verdade, numa pasta temporária com uma cópia do candidato, respondendo pela API."""
    pasta = Path(tempfile.mkdtemp(prefix="kernel-portao-"))
    processo = saida = None
    try:
        (pasta / "cerebro").mkdir()
        shutil.copy2(modelo, pasta / "cerebro" / "modelo.npz")
        if Path(str(modelo) + ".sha256").exists():
            shutil.copy2(str(modelo) + ".sha256", pasta / "cerebro" / "modelo.npz.sha256")
        shutil.copy2(tokenizador, pasta / "cerebro" / "tokenizador.json")
        configuracao = pasta / "kernel.toml"
        configuracao.write_text(f'[nucleo]\nporta = {porta}\n[exploracao]\nligada = false\n[voz]\nmotor = "difones"\n'
                                '[seguranca]\npastas_permitidas = ["{projeto}"]\n', encoding="utf-8")
        ambiente = {**os.environ, "PYTHONIOENCODING": "utf-8", "KERNEL_CONFIG": str(configuracao), "KERNEL_DADOS": str(pasta)}
        saida = open(pasta / "saida.txt", "w", encoding="utf-8")
        processo = subprocess.Popen([str(PYTHON), "-m", "kernel", "iniciar"], cwd=RAIZ, env=ambiente,
                                    stdout=saida, stderr=subprocess.STDOUT)
        endereco = f"http://127.0.0.1:{porta}"
        inicio = time.time()
        while True:
            try:
                _pedir(f"{endereco}/api/saude", espera=2)
                break
            except OSError:
                if processo.poll() is not None or time.time() - inicio > 90:
                    raise RuntimeError("o serviço não subiu: " + (pasta / "saida.txt").read_text(encoding="utf-8")[-500:])
                time.sleep(1)
        subiu_em = time.time() - inicio
        # a página entregue ao próprio PC traz o código que a API pede (é assim que a janela de chat fala com ele)
        codigo = re.search(r'KERNEL_CODIGO = "([^"]+)"', _pedir(f"{endereco}/")).group(1)
        estado = _pedir(f"{endereco}/api/estado", codigo)
        ultima = max((m["id"] for m in _pedir(f"{endereco}/api/mensagens", codigo)), default=0)
        pedido_em = time.time()
        _pedir(f"{endereco}/api/mensagem", codigo, {"texto": f"completa: {comeco}"})
        resposta = None
        while resposta is None and time.time() - pedido_em < 120:
            time.sleep(0.5)
            resposta = next((m for m in _pedir(f"{endereco}/api/mensagens", codigo, espera=5)
                             if m["id"] > ultima and m.get("classe") == "cerebro"), None)
        respondeu_em = time.time() - pedido_em
        try:
            _pedir(f"{endereco}/api/desligar", codigo, {})
            processo.wait(timeout=60)
        except Exception:
            pass
        cerebro = estado.get("cerebro", {})
        return {"ok": bool(resposta and cerebro.get("treinado")), "subiu_em_s": round(subiu_em, 1),
                "cerebro_no_estado": cerebro, "pedido": f"completa: {comeco}",
                "resposta": resposta["texto"] if resposta else None, "respondeu_em_s": round(respondeu_em, 1)}
    finally:
        if processo and processo.poll() is None:
            processo.terminate()
            processo.wait(timeout=30)
        if saida:
            saida.close()   # no Windows, um arquivo aberto não deixa apagar a pasta
        shutil.rmtree(pasta, ignore_errors=True)


def main() -> int:
    analisador = argparse.ArgumentParser()
    analisador.add_argument("--modelo", required=True)
    analisador.add_argument("--tokenizador", default=str(RAIZ / "dados" / "cerebro" / "tokenizador.json"))
    analisador.add_argument("--porta", type=int, default=8768)
    analisador.add_argument("--saida")
    args = analisador.parse_args()
    modelo, tokenizador = Path(args.modelo), Path(args.tokenizador)

    from kernel.cerebro.inferencia import _impressao

    resultado = {"pesos": {"arquivo": modelo.name, "sha256": _impressao(modelo),
                           "sha256_gravado": Path(str(modelo) + ".sha256").read_text(encoding="ascii").strip()
                           if Path(str(modelo) + ".sha256").exists() else None,
                           "megabytes": round(modelo.stat().st_size / 2**20, 1)}}
    resultado["pesos"]["ok"] = resultado["pesos"]["sha256"] == resultado["pesos"]["sha256_gravado"]
    for nome, etapa in (("inferencia", lambda: conferir_inferencia(modelo, tokenizador)),
                        ("velocidade", lambda: medir_velocidade(modelo, tokenizador)),
                        ("servico", lambda: no_servico(modelo, tokenizador, args.porta))):
        try:
            resultado[nome] = etapa()
        except Exception as erro:   # uma etapa que quebra reprova, mas as outras ainda são medidas
            resultado[nome] = {"ok": False, "erro": f"{type(erro).__name__}: {erro}"}
        print(f"{nome}: {'ok' if resultado[nome]['ok'] else 'FALHOU'}", flush=True)
    resultado["ok"] = all(resultado[k]["ok"] for k in ("pesos", "inferencia", "velocidade", "servico"))
    texto = json.dumps(resultado, ensure_ascii=False, indent=1)
    if args.saida:
        Path(args.saida).write_text(texto, encoding="utf-8")
    print(texto)
    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
