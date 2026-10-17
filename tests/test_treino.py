"""Fase 1.5: o treino continua sem reaquecer, lê sem repetir e para quando a validação estabiliza."""
import numpy as np
import pytest

FIM = 65535


@pytest.fixture(scope="module")
def torch():
    return pytest.importorskip("torch")


def _arquivo_de_documentos(pasta, n_documentos=60, semente=0):
    """Documentos de tamanhos variados; cada token vale um número único (para saber onde ele estava)."""
    sorteio, partes, proximo = np.random.default_rng(semente), [], 0
    for tamanho in sorteio.integers(10, 120, size=n_documentos):
        partes.append(np.arange(proximo, proximo + tamanho))
        partes.append([FIM])
        proximo += tamanho
    dados = np.concatenate(partes).astype(np.uint16)
    dados.tofile(pasta / "treino.bin")
    return dados


def test_passada_le_cada_token_uma_vez_por_epoca(torch, tmp_path):
    from kernel.cerebro.dados import Passada

    dados = _arquivo_de_documentos(tmp_path)
    passada = Passada(tmp_path / "treino.bin", contexto=8, lote=4, id_fim=FIM, semente=3)
    alvos, primeiras = [], []
    for _ in range(passada.janelas_por_faixa):
        x, y = passada.pegar("cpu")
        assert (y[:, :-1] == x[:, 1:]).all()                      # o alvo é a entrada deslocada de um token
        alvos.extend(int(v) for v in y.flatten() if int(v) != FIM)
        primeiras.append([int(v) for v in x[:, 0]])
    assert len(alvos) == len(set(alvos))                            # nada repetido na época
    assert len(alvos) / int((dados != FIM).sum()) > 0.9             # e quase tudo lido (sobram pontas das faixas)
    # as linhas de um lote vêm de partes distantes do fluxo: começos bem diferentes entre si
    assert np.mean([len(set(np.array(p) // 100)) for p in primeiras]) > 3
    assert passada.epoca == 0 and passada.lido() == 1.0
    passada.pegar("cpu")                                            # a época acabou: embaralha de novo
    assert passada.epoca == 1 and passada.posicao == 1


def test_passada_continua_de_onde_parou(torch, tmp_path):
    from kernel.cerebro.dados import Passada

    _arquivo_de_documentos(tmp_path)
    uma = Passada(tmp_path / "treino.bin", contexto=8, lote=4, id_fim=FIM, semente=5)
    for _ in range(7):
        uma.pegar("cpu")
    estado = uma.estado()
    outra = Passada(tmp_path / "treino.bin", contexto=8, lote=4, id_fim=FIM, semente=5,
                    epoca=estado["epoca"], posicao=estado["posicao"])
    for _ in range(3):
        assert (uma.pegar("cpu")[0] == outra.pegar("cpu")[0]).all()


def _cerebro_pequeno(tmp_path):
    from kernel.cerebro import dados, inferencia, tokenizador

    texto = ("O Brasil é o maior país da América do Sul. A capital do Brasil é Brasília. O Sol é a estrela do "
             "sistema solar. A água é formada por hidrogênio e oxigênio. ")
    tok = tokenizador.treinar([texto], tamanho=300)
    tok.salvar(tmp_path / inferencia.TOKENIZADOR)
    frases = texto.split(". ")
    sorteio = np.random.default_rng(0)
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("".join(f"Artigo {i}\n\n" + ". ".join(sorteio.permutation(frases)) + "\n<|fim|>\n"
                              for i in range(300)), encoding="utf-8")
    dados.preparar(corpus, tok, tmp_path)


def test_continuar_sem_reaquecer_e_lendo_sem_repetir(torch, tmp_path):
    from kernel.cerebro.treinar import CHECKPOINT, ConfigTreino, treinar

    _cerebro_pequeno(tmp_path)
    cfg = ConfigTreino(tamanho="nano", passos=20, lote=4, aquecimento=5, avaliar_cada=10, lotes_de_avaliacao=1,
                       dispositivo="cpu", taxa=3e-3, amostragem="sorteio")   # um checkpoint do jeito antigo
    treinar(tmp_path, cfg, avisar=lambda _: None)
    sessao = ConfigTreino(tamanho="nano", lote=4, aquecimento=5, avaliar_cada=10, lotes_de_avaliacao=1,
                          dispositivo="cpu", taxa=3e-3, sessao_passos=10, ao_continuar="retomar", amostragem="passada")
    avisos = []
    resumo = treinar(tmp_path, sessao, avisar=avisos.append)
    assert resumo["passo"] == 30 and resumo["motivo"] == "meta"
    assert any("continuando sem reaquecer: taxa constante de 1.5e-04" in a for a in avisos)
    assert any("passada sem repetição: começando uma época nova" in a for a in avisos)
    salvo = torch.load(tmp_path / CHECKPOINT, weights_only=True)
    assert abs(salvo["taxa"] - sessao.taxa_ao_retomar) < 1e-12
    assert salvo["amostrador"]["posicao"] == 10 * sessao.acumular   # dois lotes por passo

    avisos.clear()
    treinar(tmp_path, sessao, avisar=avisos.append)                  # a sessão seguinte continua a passada
    assert any("passada sem repetição: época 0," in a for a in avisos)
    assert torch.load(tmp_path / CHECKPOINT, weights_only=True)["amostrador"]["posicao"] == 20 * sessao.acumular


def test_reaquecer_por_passos_termina_baixo(torch, tmp_path):
    from kernel.cerebro.treinar import CHECKPOINT, ConfigTreino, treinar

    _cerebro_pequeno(tmp_path)
    treinar(tmp_path, ConfigTreino(tamanho="nano", passos=10, lote=4, aquecimento=2, avaliar_cada=10,
                                   lotes_de_avaliacao=1, dispositivo="cpu", taxa=3e-3), avisar=lambda _: None)
    sessao = ConfigTreino(tamanho="nano", lote=4, aquecimento=2, avaliar_cada=10, lotes_de_avaliacao=1,
                          dispositivo="cpu", taxa=3e-3, sessao_passos=20, ao_continuar="reaquecer")
    treinar(tmp_path, sessao, avisar=lambda _: None)
    taxa_final = torch.load(tmp_path / CHECKPOINT, weights_only=True)["taxa"]
    pico = 3e-3 * sessao.taxa_ao_continuar
    assert 0.1 * pico <= taxa_final < 0.12 * pico                  # o cosseno da sessão desceu até perto de 10%


def test_para_quando_a_validacao_estabiliza(torch, tmp_path):
    from kernel.cerebro.treinar import ConfigTreino, treinar

    _cerebro_pequeno(tmp_path)
    cfg = ConfigTreino(tamanho="nano", lote=4, aquecimento=2, avaliar_cada=5, lotes_de_avaliacao=1, dispositivo="cpu",
                       sessao_passos=50, parar_se_estagnar=1, melhora_minima=10.0)   # nenhuma melhora conta
    avisos = []
    resumo = treinar(tmp_path, cfg, avisar=avisos.append)
    assert resumo["motivo"] == "estabilizou" and resumo["passo"] == 10    # a 1ª medida vira a régua; a 2ª não melhora
    assert any("parando" in a and "medidas seguidas" in a for a in avisos)


def test_marcos_guardam_os_pesos_e_a_hora(torch, tmp_path):
    import json

    from kernel.cerebro import inferencia
    from kernel.cerebro.treinar import ConfigTreino, confere, treinar

    _cerebro_pequeno(tmp_path)
    cfg = ConfigTreino(tamanho="nano", lote=4, aquecimento=2, avaliar_cada=10, lotes_de_avaliacao=1, dispositivo="cpu",
                       sessao_passos=12, marcos=(5, 12))
    treinar(tmp_path, cfg, avisar=lambda _: None)
    for passo in (5, 12):
        assert confere(tmp_path / "marcos" / f"passo-{passo}.npz") is True
        assert inferencia.CerebroNumpy is not None
    linhas = [json.loads(l) for l in (tmp_path / "marcos" / "marcos.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [l["passo"] for l in linhas] == [5, 12]
    assert linhas[1]["tokens"] == 12 * cfg.acumular * cfg.lote * 64 and linhas[1]["segundos"] >= linhas[0]["segundos"]


def test_sessao_interrompida_continua_igual(torch, tmp_path):
    """Fase 2: uma sessão parada no meio e continuada com --sessao-desde termina igual à que não parou."""
    import shutil

    from kernel.cerebro.treinar import CHECKPOINT, ConfigTreino, treinar

    def sessao(**extra):
        return ConfigTreino(tamanho="nano", lote=4, aquecimento=2, avaliar_cada=7, lotes_de_avaliacao=1,
                            dispositivo="cpu", taxa=3e-3, sessao_passos=12, **extra)

    inteira, partida = tmp_path / "inteira", tmp_path / "partida"
    inteira.mkdir()
    _cerebro_pequeno(inteira)
    shutil.copytree(inteira, partida)
    treinar(inteira, sessao(), avisar=lambda _: None)

    def parar_no_passo_7(texto):   # o ponto de controle do passo 7 avisa; o pedido de parada vale no passo seguinte
        if texto.lstrip().startswith("validação"):
            (partida / "PARAR").touch()

    assert treinar(partida, sessao(), avisar=parar_no_passo_7)["passo"] == 7
    avisos = []
    resumo = treinar(partida, sessao(sessao_desde=0), avisar=avisos.append)
    assert resumo["passo"] == 12 and resumo["motivo"] == "meta"
    assert any("continuando a sessão que começou no passo 0" in a for a in avisos)
    assert not any("sem reaquecer" in a for a in avisos)
    a = torch.load(inteira / CHECKPOINT, weights_only=True)
    b = torch.load(partida / CHECKPOINT, weights_only=True)
    assert a["taxa"] == b["taxa"] and b["sessao"] == {"desde": 0, "passos": 12}
    assert a["amostrador"] == b["amostrador"]
    assert max(float((a["modelo"][n] - b["modelo"][n]).abs().max()) for n in a["modelo"]) < 1e-6

    with pytest.raises(ValueError):   # passou do fim da sessão: não há o que continuar
        treinar(partida, sessao(sessao_desde=0), avisar=lambda _: None)
