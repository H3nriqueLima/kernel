"""Fase 1: as ferramentas de avaliação do cérebro (cobertura, conjuntos fixos, checagens, protocolo)."""
import numpy as np
import pytest

from kernel.cerebro import cobertura


@pytest.fixture(scope="module")
def torch():
    return pytest.importorskip("torch")


def test_cobertura_refaz_o_sorteio_de_verdade(torch, tmp_path):
    """O sorteio refeito tem de bater, janela por janela, com o da classe Lotes que o treino usa."""
    from kernel.cerebro.dados import Lotes

    arquivo = tmp_path / "treino.bin"
    np.arange(50_000, dtype=np.uint16).tofile(arquivo)   # cada token vale a própria posição
    sessao = cobertura.Sessao(inicio=37, fim=37 + 60, lote=4, acumular=2, contexto=16, pedaco=3000)
    lotes = Lotes(arquivo, sessao.contexto, sessao.lote, pedaco=sessao.pedaco, semente=sessao.semente)
    reais = []
    for _ in range(sessao.chamadas):
        x, y = lotes.pegar("cpu")
        assert (y[:, :-1] == x[:, 1:]).all()               # o alvo é a entrada deslocada de um token
        reais.extend(int(v) for v in x[:, 0])
    refeitos = cobertura.inicios_da_sessao(50_000, sessao)
    assert refeitos.tolist() == reais                      # inclusive nas trocas de pedaço (a cada 46 chamadas)
    assert sessao.chamadas > sessao.pedaco // (sessao.lote * sessao.contexto)


def test_tokens_distintos_e_documentos_tocados():
    inicios = np.array([0, 5, 30, 100])
    assert cobertura.tokens_distintos(inicios, 10) == 15 + 10 + 10   # [0,15) [30,40) [100,110)
    comecos, fins = np.array([0, 15, 40, 60, 105]), np.array([15, 40, 60, 100, 200])
    tocados = cobertura.janelas_por_documento(inicios, 10, comecos, fins)
    assert tocados.tolist() == [2, 1, 0, 0, 1]   # [30,40) não toca o documento que começa em 40


def test_ngramas_somam_um_e_aprendem_o_padrao():
    from kernel.cerebro.ngramas import Ngramas

    sorteio = np.random.default_rng(0)
    padrao = np.tile([1, 2, 3, 4, 5, 6, 7], 300)            # uma sequência que o trigrama acerta sempre
    ruido = sorteio.integers(0, 20, size=2000)
    modelo = Ngramas(np.concatenate([padrao, ruido]), vocab=20)
    for u, v in [(1, 2), (3, 9), (19, 19)]:                  # visto, meio visto, nunca visto
        total = modelo._trigrama(np.full(20, u), np.full(20, v), np.arange(20)).sum()
        assert abs(total - 1.0) < 1e-9, (u, v, total)        # é uma distribuição de verdade
    for v in (1, 19):
        assert abs(modelo._bigrama(np.full(20, v), np.arange(20)).sum() - 1.0) < 1e-9
    perdas = modelo.perdas(np.tile([1, 2, 3, 4, 5, 6, 7], 20))
    assert perdas["trigrama"] < perdas["bigrama"] <= perdas["unigrama"]
    assert perdas["trigrama"] < 0.2


def test_conjuntos_fixos_saem_do_treino_e_nunca_foram_lidos(tmp_path):
    from kernel.cerebro import conjuntos

    fim, sorteio = 99, np.random.default_rng(1)
    documentos = [sorteio.integers(0, 99, size=int(n)) for n in sorteio.integers(40, 400, size=1500)]
    documentos[700] = documentos[100].copy()                  # uma cópia exata: não pode virar teste
    tudo = np.concatenate([np.append(d, fim) for d in documentos]).astype(np.uint16)
    tudo.tofile(tmp_path / "treino.bin")
    sessoes = [conjuntos.cobertura.Sessao(0, 30, lote=4, pedaco=20_000), conjuntos.cobertura.Sessao(30, 50, lote=4, pedaco=20_000)]
    manifesto = conjuntos.montar(tmp_path, sessoes, fim, tokens_teste=6000, tokens_validacao=3000, tokens_amostra=3000,
                                 avisar=lambda _: None)
    lidos = conjuntos.carregar(tmp_path)
    assert set(lidos) == {"teste", "validacao", "amostra_treino"}

    janelas = conjuntos.cobertura.todas_as_janelas(len(tudo), sessoes)
    origem_teste = np.array(manifesto["conjuntos"]["teste"]["origem"])
    origem_val = np.array(manifesto["conjuntos"]["validacao"]["origem"])
    for origem in (origem_teste, origem_val):
        assert (conjuntos.cobertura.janelas_por_documento(janelas, 257, origem[:, 0], origem[:, 1] + 1) == 0).all()
    assert not set(map(tuple, origem_teste)) & set(map(tuple, origem_val))
    copia = int(np.sum([len(d) + 1 for d in documentos[:100]]))
    assert copia not in origem_teste[:, 0] and copia not in origem_val[:, 0]

    # o treino novo é o original sem os documentos de teste e validação, e nada além disso
    novo = np.fromfile(tmp_path / "treino.bin", dtype=np.uint16)
    tirados = sum(b - a + 1 for a, b in np.concatenate([origem_teste, origem_val]))
    assert len(novo) == len(tudo) - tirados
    assert (np.fromfile(tmp_path / "treino-original.bin", dtype=np.uint16) == tudo).all()
    assert manifesto["conjuntos"]["teste"]["tokens"] >= 6000

    (tmp_path / "avaliacao" / "teste.bin").write_bytes(b"\x00\x01" * 10)   # trocado: tem de ser recusado
    with pytest.raises(ValueError, match="não confere"):
        conjuntos.carregar(tmp_path)
    with pytest.raises(RuntimeError, match="já foram montados"):
        conjuntos.montar(tmp_path, sessoes, fim, avisar=lambda _: None)


TEXTO = ("O Brasil é o maior país da América do Sul. A capital do Brasil é Brasília. O Sol é a estrela do sistema "
         "solar. A água é uma substância formada por hidrogênio e oxigênio. A língua portuguesa é falada no Brasil. ")


def _pasta_pequena(tmp_path, torch):
    """Um cérebro de brinquedo completo: tokenizador, treino.bin, val.bin, conjuntos fixos e um modelo exportado."""
    from kernel.cerebro import conjuntos, dados, inferencia, tokenizador
    from kernel.cerebro.gpt import GPT, ConfigGPT

    tok = tokenizador.treinar([TEXTO], tamanho=300)
    tok.salvar(tmp_path / inferencia.TOKENIZADOR)
    sorteio = np.random.default_rng(0)
    frases = TEXTO.split(". ")
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("".join(f"Artigo {i}\n\n" + ". ".join(sorteio.permutation(frases)) + "\n<|fim|>\n" for i in range(600)),
                      encoding="utf-8")
    dados.preparar(corpus, tok, tmp_path)
    conjuntos.montar(tmp_path, [conjuntos.cobertura.Sessao(0, 3, lote=2, pedaco=8_000)], tok.id_fim,
                     tokens_teste=2000, tokens_validacao=1000, tokens_amostra=1000, avisar=lambda _: None)
    torch.manual_seed(0)
    modelo = GPT(ConfigGPT(vocab=tok.tamanho, contexto=32, camadas=1, cabecas=2, dim=16))
    inferencia.exportar(modelo, tmp_path / inferencia.MODELO)
    return tmp_path / inferencia.MODELO


def test_protocolo_e_reprodutivel(torch, tmp_path):
    from kernel.cerebro import protocolo

    modelo = _pasta_pequena(tmp_path, torch)
    primeiro = protocolo.avaliar(modelo, tmp_path, "cpu", tokens_ngramas=4000, avisar=lambda _: None)
    segundo = protocolo.avaliar(modelo, tmp_path, "cpu", tokens_ngramas=4000, avisar=lambda _: None)
    assert protocolo.comparavel(primeiro) == protocolo.comparavel(segundo)      # mesmos números, duas vezes
    assert set(primeiro["perdas"]) == {"teste", "validacao", "amostra_treino", "validacao_antiga"}
    textos_por_comeco = sum(len(sementes) for *_, sementes in protocolo.MODOS.values())   # v2: guloso + 3 sorteios + 2 do serviço
    assert len(primeiro["amostras"]) == len(protocolo.COMECOS) * textos_por_comeco == len(protocolo.COMECOS) * 6
    p = primeiro["perdas"]["teste"]
    assert abs(p["perplexidade"] - np.exp(p["perda"])) < 0.01 and len(p["por_posicao"]) == 32
    assert primeiro["ngramas"]["teste"]["trigrama"] < primeiro["ngramas"]["teste"]["unigrama"]
    saida = protocolo.salvar(primeiro, tmp_path / "relatorio")
    assert "| teste |" in (saida / "relatorio.md").read_text(encoding="utf-8")


def test_treino_percebe_que_a_validacao_mudou(torch, tmp_path):
    from kernel.cerebro import conjuntos, dados, inferencia, tokenizador
    from kernel.cerebro.treinar import ConfigTreino, treinar

    tok = tokenizador.treinar([TEXTO], tamanho=300)
    tok.salvar(tmp_path / inferencia.TOKENIZADOR)
    frases = TEXTO.split(". ")
    sorteio = np.random.default_rng(0)
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("".join(f"Artigo {i}\n\n" + ". ".join(sorteio.permutation(frases)) + "\n<|fim|>\n" for i in range(400)),
                      encoding="utf-8")
    dados.preparar(corpus, tok, tmp_path)
    cfg = ConfigTreino(tamanho="nano", passos=50, lote=4, aquecimento=5, avaliar_cada=25, lotes_de_avaliacao=2,
                       dispositivo="cpu")
    avisos = []
    treinar(tmp_path, cfg, avisar=avisos.append)
    assert any("gradiente" in a and "cortados" in a for a in avisos)         # a estabilidade aparece no progresso
    assert not any("a validação mudou" in a for a in avisos)

    conjuntos.montar(tmp_path, [conjuntos.cobertura.Sessao(0, 1, lote=1, pedaco=8_000)], tok.id_fim,
                     tokens_teste=1500, tokens_validacao=1000, tokens_amostra=500, avisar=lambda _: None)
    avisos.clear()
    cfg.passos = 75
    treinar(tmp_path, cfg, avisar=avisos.append)
    mudou = [a for a in avisos if "a validação mudou para validacao.bin" in a]
    assert mudou and "medida nela" in mudou[0]
    avisos.clear()
    cfg.passos = 100
    treinar(tmp_path, cfg, avisar=avisos.append)                              # agora a régua é a mesma
    assert not any("a validação mudou" in a for a in avisos)


def test_so_a_perda_bate_com_o_protocolo_completo(torch, tmp_path):
    from kernel.cerebro import protocolo

    modelo = _pasta_pequena(tmp_path, torch)
    completo = protocolo.avaliar(modelo, tmp_path, "cpu", tokens_ngramas=4000, avisar=lambda _: None)
    so = protocolo.so_perdas(modelo, tmp_path, "cpu", ["teste", "validacao"])
    assert set(so["perdas"]) == {"teste", "validacao"}
    for nome in ("teste", "validacao"):
        assert so["perdas"][nome]["perda"] == completo["perdas"][nome]["perda"]
        assert so["perdas"][nome]["bits_por_byte"] == completo["perdas"][nome]["bits_por_byte"]
