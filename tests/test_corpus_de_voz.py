"""O corpus de voz, sem internet: a lista de frases, o corte dos capítulos e a troca de taxa."""
import json

import numpy as np

from kernel.voz import corpus


def test_reamostrar_muda_o_tamanho_e_mantem_o_tom():
    t = np.arange(22050) / 22050
    som = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    para_16k = corpus.reamostrar(som, 22050, 16000)
    assert abs(len(para_16k) - 16000) <= 1 and para_16k.dtype == np.float32
    espectro = np.abs(np.fft.rfft(para_16k))
    assert abs(np.argmax(espectro) * 16000 / len(para_16k) - 440) < 2
    assert corpus.reamostrar(som, 22050, 22050) is not None and len(corpus.reamostrar(som, 22050, 22050)) == len(som)
    # um agudo acima do que a taxa nova comporta não pode voltar como um som falso mais grave
    agudo = np.sin(2 * np.pi * 9000 * t).astype(np.float32)
    assert np.abs(corpus.reamostrar(agudo, 22050, 16000)).max() < 0.5


def test_lista_de_frases_e_baixada_aos_poucos_e_fica_em_disco(tmp_path, monkeypatch):
    pedidos = []

    def linhas_de_mentira(inicio, quantas, tentativas=6):
        pedidos.append((inicio, quantas))
        return [{"id": f"2961_3118_{inicio + i:06d}", "speaker_id": "2961", "chapter_id": "3118",
                 "original_path": f"http://www.archive.org/download/senhora/senhora_{(inicio + i) // 150:02d}.mp3",
                 "begin_time": 10.0 * i, "end_time": 10.0 * i + 12.5, "transcript": f"frase número {inicio + i}"}
                for i in range(quantas)]

    monkeypatch.setattr(corpus, "_linhas", linhas_de_mentira)
    lista = corpus.baixar_lista(tmp_path, 150, avisar=lambda _: None)
    assert len(lista) == 150 and pedidos == [(corpus.PRIMEIRA_LINHA, 100), (corpus.PRIMEIRA_LINHA + 100, 50)]
    assert lista[0]["mp3"].startswith("https://archive.org/") and lista[0]["fim"] - lista[0]["inicio"] == 12.5
    assert json.loads((tmp_path / "frases.jsonl").read_text(encoding="utf-8").splitlines()[149])["texto"].startswith("frase")
    pedidos.clear()
    assert len(corpus.baixar_lista(tmp_path, 120, avisar=lambda _: None)) == 120 and pedidos == []   # já estava em disco
    assert len(corpus.carregar_lista(tmp_path)) == 150


def test_frases_de_outro_leitor_ou_livro_ficam_de_fora(tmp_path, monkeypatch):
    def linhas_misturadas(inicio, quantas, tentativas=6):
        dona = [{"id": "a", "speaker_id": "2961", "chapter_id": "3118", "original_path": "http://www.archive.org/x.mp3",
                 "begin_time": 0.0, "end_time": 11.0, "transcript": "da leitora"}]
        outro = [{"id": "b", "speaker_id": "9351", "chapter_id": "9280", "original_path": "http://www.archive.org/y.mp3",
                  "begin_time": 0.0, "end_time": 11.0, "transcript": "de outro leitor"}]
        return dona + outro if inicio == corpus.PRIMEIRA_LINHA else outro

    monkeypatch.setattr(corpus, "_linhas", linhas_misturadas)
    lista = corpus.baixar_lista(tmp_path, 10, avisar=lambda _: None)
    assert [f["texto"] for f in lista] == ["da leitora"]


def test_corta_a_frase_do_capitulo(tmp_path):
    import soundfile as sf

    taxa = 22050
    som = np.zeros(taxa * 4, dtype=np.float32)
    som[taxa:2 * taxa] = 0.5                                    # o segundo 1 a 2 é "a frase"
    sf.write(str(tmp_path / "capitulo_01.mp3"), np.stack([som, som], axis=1), taxa, format="WAV")   # estéreo
    capitulos = corpus.Capitulos(tmp_path)
    trecho, taxa_lida = capitulos.frase({"mp3": "https://archive.org/download/x/capitulo_01.mp3", "inicio": 1.0, "fim": 2.0})
    assert taxa_lida == taxa and len(trecho) == taxa and trecho.ndim == 1
    assert abs(float(trecho.mean()) - 0.5) < 1e-3              # mono, e o trecho certo
