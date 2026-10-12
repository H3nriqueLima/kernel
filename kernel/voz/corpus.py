"""O corpus de voz: de onde vêm os difones.

A voz é de uma leitora voluntária do LibriVox ("Leni", brasileira), lendo
"Senhora", de José de Alencar. As gravações do LibriVox são de domínio público.
Os cortes em frases de 10 a 20 segundos e as transcrições vêm do conjunto
Multilingual LibriSpeech (Pratap et al., 2020, licença CC BY 4.0), consultado
pela API pública do Hugging Face.

Baixar aqui é pegar duas coisas:

- a lista de frases (texto, arquivo MP3 de origem, segundo em que começa e acaba);
- os arquivos MP3 dos capítulos citados nessa lista, direto do archive.org.

    python -m kernel voz baixar --frases 400
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

API = "https://datasets-server.huggingface.co/rows?"
CONJUNTO = {"dataset": "facebook/multilingual_librispeech", "config": "portuguese", "split": "train"}
# Onde começa, no conjunto, o livro "Senhora" lido pela Leni (leitora 2961, obra 3118).
LEITORA, OBRA, PRIMEIRA_LINHA = "2961", "3118", 10159
_AGENTE = {"User-Agent": "KERNEL-estudo/0.3 (projeto pessoal de aprendizado)"}


def _linhas(inicio: int, quantas: int, tentativas: int = 6) -> list[dict]:
    consulta = urllib.parse.urlencode({**CONJUNTO, "offset": inicio, "length": quantas})
    erro: Exception | None = None
    for tentativa in range(tentativas):
        try:
            with urllib.request.urlopen(urllib.request.Request(API + consulta, headers=_AGENTE), timeout=60) as r:
                return [linha["row"] for linha in json.load(r)["rows"]]
        except Exception as e:  # o serviço às vezes responde 500/502: espera e tenta de novo
            erro = e
            time.sleep(2 + 3 * tentativa)
    raise RuntimeError(f"não consegui ler a lista de frases: {erro}")


def baixar_lista(pasta: Path, frases: int, avisar=print) -> list[dict]:
    """Baixa (ou completa) ``frases.jsonl``: uma linha por frase da leitora."""
    arquivo = Path(pasta) / "frases.jsonl"
    lista = carregar_lista(pasta)
    while len(lista) < frases:
        novas = _linhas(PRIMEIRA_LINHA + len(lista), min(100, frases - len(lista)))
        novas = [{"id": n["id"], "mp3": n["original_path"].replace("http://www.", "https://"),
                  "inicio": n["begin_time"], "fim": n["end_time"], "texto": n["transcript"]}
                 for n in novas if n["speaker_id"] == LEITORA and n["chapter_id"] == OBRA]
        if not novas:
            break  # acabou o livro
        lista += novas
        arquivo.write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in lista) + "\n", encoding="utf-8")
        avisar(f"  lista: {len(lista)} frases")
    return lista[:frases]


def carregar_lista(pasta: Path) -> list[dict]:
    arquivo = Path(pasta) / "frases.jsonl"
    if not arquivo.exists():
        return []
    return [json.loads(linha) for linha in arquivo.read_text(encoding="utf-8").splitlines() if linha.strip()]


def baixar_mp3(lista: list[dict], pasta: Path, avisar=print) -> list[Path]:
    """Baixa os MP3 dos capítulos citados na lista (os que ainda faltam)."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivos = []
    for url in dict.fromkeys(f["mp3"] for f in lista):
        destino = pasta / url.rsplit("/", 1)[1]
        arquivos.append(destino)
        if destino.exists() and destino.stat().st_size > 100_000:
            continue
        avisar(f"  baixando {destino.name}...")
        parcial = destino.with_suffix(".parte")
        for tentativa in range(5):  # o archive.org às vezes responde 500/503: espera e tenta de novo
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=_AGENTE), timeout=120) as r, \
                        open(parcial, "wb") as saida:
                    while bloco := r.read(1 << 20):
                        saida.write(bloco)
                parcial.replace(destino)
                avisar(f"    {destino.stat().st_size / 1e6:.1f} MB")
                break
            except OSError as erro:
                avisar(f"    falhou ({erro}); tentativa {tentativa + 1} de 5")
                time.sleep(5 + 10 * tentativa)
        else:
            arquivos.pop()  # este capítulo fica de fora; as frases dele são puladas na construção
    return arquivos


class Capitulos:
    """Abre os MP3 sob demanda e devolve o som de cada frase (mono, float, na taxa do arquivo)."""

    def __init__(self, pasta: Path):
        self.pasta = Path(pasta)
        self._nome: str | None = None
        self._som: np.ndarray | None = None
        self.taxa = 0

    def frase(self, f: dict) -> tuple[np.ndarray, int]:
        import soundfile as sf

        nome = f["mp3"].rsplit("/", 1)[1]
        if nome != self._nome:  # um capítulo inteiro na RAM por vez (uns 100 MB)
            som, self.taxa = sf.read(str(self.pasta / nome), dtype="float32", always_2d=True)
            self._som, self._nome = som.mean(axis=1), nome
        return self._som[int(f["inicio"] * self.taxa):int(f["fim"] * self.taxa)], self.taxa


def reamostrar(som: np.ndarray, de: int, para: int) -> np.ndarray:
    """Muda a taxa de amostragem.

    Ao reduzir a taxa, os agudos que a taxa nova não comporta precisam ser cortados antes:
    senão eles "dobram" e reaparecem como sons graves que não existiam (aliasing). O corte é
    um filtro passa-baixas de seno cardinal com janela.
    """
    if de == para:
        return som.astype(np.float32)
    if para < de:
        pontas = 95
        n = np.arange(pontas) - (pontas - 1) / 2
        filtro = np.sinc(2 * (0.45 * para) / de * n) * np.hamming(pontas)
        som = np.convolve(som, filtro / filtro.sum(), mode="same")
    posicoes = np.arange(int(len(som) * para / de)) * (de / para)
    return np.interp(posicoes, np.arange(len(som)), som).astype(np.float32)
