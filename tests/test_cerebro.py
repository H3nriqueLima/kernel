import math
import random

import numpy as np
import pytest

from kernel.cerebro import bigrama, inferencia, tokenizador, wikipedia
from kernel.cerebro.micrograd import MLP, Valor

TEXTO = ("O Brasil é o maior país da América do Sul. A capital do Brasil é Brasília. "
         "O português é a língua oficial do Brasil. São Paulo é a maior cidade do país. ") * 40


# ---------------------------------------------------------------- micrograd
def test_gradiente_do_micrograd_bate_com_a_derivada_numerica():
    def f(a, b, c):
        return ((a * b + c).tanh() * (a - c) ** 2 + (b * c).exp() / (a + 3)).relu() + (a * a + 1).log()

    ponto = (0.7, -1.3, 0.4)
    valores = [Valor(v) for v in ponto]
    f(*valores).retropropagar()
    h = 1e-6
    for i, valor in enumerate(valores):
        mais = [v + (h if j == i else 0) for j, v in enumerate(ponto)]
        menos = [v - (h if j == i else 0) for j, v in enumerate(ponto)]
        numerica = (f(*map(Valor, mais)).dado - f(*map(Valor, menos)).dado) / (2 * h)
        assert abs(valor.grad - numerica) < 1e-5


def test_mlp_do_micrograd_aprende_o_xor():
    random.seed(7)
    entradas, alvos = [[0, 0], [0, 1], [1, 0], [1, 1]], [-1, 1, 1, -1]
    rede = MLP(2, [4, 4, 1])
    for _ in range(200):
        perda = sum(((rede(x).tanh() - a) ** 2 for x, a in zip(entradas, alvos)), Valor(0.0))
        for p in rede.parametros():
            p.grad = 0.0
        perda.retropropagar()
        for p in rede.parametros():
            p.dado -= 0.1 * p.grad
    assert perda.dado < 0.05


# ------------------------------------------------------------------ bigrama
def test_bigrama_aprende_cara_de_nome():
    nomes = bigrama.carregar_palavras()
    assert len(nomes) > 250
    modelo = bigrama.Bigrama(nomes[:-30])
    assert modelo.perda(nomes[-30:]) < math.log(len(modelo.letras)) - 0.5  # bem melhor que chutar
    sorteio = random.Random(1)
    inventados = [modelo.gerar(sorteio) for _ in range(20)]
    assert all(nome.isalpha() or nome == "" for nome in inventados) and any(inventados)


# --------------------------------------------------------------- tokenizador
def test_pedacos_cobrem_o_texto_inteiro():
    texto = "Olá, mundo!  Em 2026 o R$ subiu 12,5% _ok_\n\tfim…"
    assert "".join(tokenizador.PEDACOS.findall(texto)) == texto


def test_bpe_vai_e_volta_e_comprime():
    tok = tokenizador.treinar([TEXTO], tamanho=400)
    assert 257 < tok.tamanho <= 400
    frase = "A capital do Brasil é Brasília, não São Paulo! 123 ☃"
    ids = tok.codificar(frase)
    assert tok.decodificar(ids) == frase
    assert len(tok.codificar(TEXTO)) < len(TEXTO.encode("utf-8")) / 3
    assert max(ids) < tok.tamanho


def test_bpe_token_de_fim_e_arquivo(tmp_path):
    tok = tokenizador.treinar([TEXTO], tamanho=300)
    ids = tok.codificar(f"um{tokenizador.FIM}dois")
    assert ids.count(tok.id_fim) == 1 and tok.decodificar(ids) == f"um{tokenizador.FIM}dois"
    tok.salvar(tmp_path / "tok.json")
    outro = tokenizador.Tokenizador.carregar(tmp_path / "tok.json")
    assert outro.codificar(TEXTO[:500]) == tok.codificar(TEXTO[:500])


# ----------------------------------------------------------------- wikipédia
def test_limpar_wikitexto():
    wikitexto = """{{Info/País|nome=Brasil|{{aninhada|x}}}}
'''Brasil''' é o maior [[país]] da [[América do Sul|América]]<ref name="a">fonte</ref> e fica no hemisfério sul.<ref name="b" />
[[Ficheiro:Mapa.png|thumb|Mapa com [[ligação]] dentro]]
{| class="wikitable"
| tabela || que some
|}
== História ==
A história do país começou muito antes de 1500, com povos [[indígena]]s espalhados pelo território.
* item de lista que some
== Ver também ==
Este parágrafo comprido depois de Ver também não pode aparecer no texto limpo de jeito nenhum.
[[Categoria:Países]]"""
    limpo = wikipedia.limpar(wikitexto)
    assert limpo.split("\n\n") == [
        "Brasil é o maior país da América e fica no hemisfério sul.",
        "A história do país começou muito antes de 1500, com povos indígenas espalhados pelo território.",
    ]


def test_indice_do_dump_lista_todas_as_partes_em_ordem():
    linha = '<a href="{n}">{n}</a>                 02-Oct-2026 03:12           {t}\n'
    pagina = (linha.format(n="ptwiki-latest-pages-articles2.xml-p105696p513712.bz2", t=236)
              + linha.format(n="ptwiki-latest-pages-articles4.xml-p2880805p4380804.bz2", t=400)
              + linha.format(n="ptwiki-latest-pages-articles4.xml-p1629225p2880804.bz2", t=354)
              + linha.format(n="ptwiki-latest-pages-articles1.xml-p1p105695.bz2", t=209)
              + linha.format(n="ptwiki-latest-pages-articles1.xml-p1p99999.bz2", t=180)   # mesmo trecho, dump velho
              + linha.format(n="ptwiki-latest-pages-articles1.xml-p1p105695.bz2-rss.xml", t=1)
              + linha.format(n="ptwiki-latest-pages-articles-multistream.xml.bz2", t=9999))
    assert wikipedia.interpretar_indice(pagina) == [
        ("ptwiki-latest-pages-articles1.xml-p1p105695.bz2", 209),
        ("ptwiki-latest-pages-articles2.xml-p105696p513712.bz2", 236),
        ("ptwiki-latest-pages-articles4.xml-p1629225p2880804.bz2", 354),   # as duas metades da parte 4
        ("ptwiki-latest-pages-articles4.xml-p2880805p4380804.bz2", 400),
    ]


def test_ler_dump_e_montar_corpus(tmp_path):
    import bz2

    pagina = ("<page><title>{t}</title><ns>{ns}</ns>{extra}<revision><text>{x}</text></revision></page>")
    corpo = "Um parágrafo bem comprido sobre o assunto do artigo, com mais de quarenta letras. " * 8
    xml = ('<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">'
           + pagina.format(t="Artigo", ns=0, extra="", x=corpo)
           + pagina.format(t="Redireciona", ns=0, extra='<redirect title="Artigo" />', x="#REDIRECIONAMENTO [[Artigo]]")
           + pagina.format(t="Usuário:Fulano", ns=2, extra="", x=corpo)
           + pagina.format(t="Curto", ns=0, extra="", x="Pouco texto.")
           + pagina.format(t="Cópia", ns=0, extra="", x=corpo)
           + "</mediawiki>")
    arquivo = tmp_path / "dump.xml.bz2"
    arquivo.write_bytes(bz2.compress(xml.encode("utf-8")))
    assert [titulo for titulo, _ in wikipedia.artigos(arquivo)] == ["Artigo", "Curto", "Cópia"]

    saida = tmp_path / "corpus.txt"
    resumo = wikipedia.extrair([arquivo], saida)
    assert resumo["artigos"] == 1  # o curto e a cópia ficam de fora
    texto = saida.read_text(encoding="utf-8")
    assert texto.startswith("Artigo\n\nUm parágrafo") and texto.endswith(f"{tokenizador.FIM}\n")

    cortado = tmp_path / "cortado.xml.bz2"   # um download interrompido não derruba a leitura
    cortado.write_bytes(arquivo.read_bytes()[:-20])
    assert isinstance(list(wikipedia.artigos(cortado)), list)


# -------------------------------------------------------------------- o GPT
@pytest.fixture(scope="module")
def torch():
    return pytest.importorskip("torch")


def test_inferencia_numpy_igual_ao_pytorch(torch, tmp_path):
    from kernel.cerebro.gpt import GPT, ConfigGPT

    torch.manual_seed(0)
    tok = tokenizador.treinar([TEXTO], tamanho=300)
    modelo = GPT(ConfigGPT(vocab=tok.tamanho, contexto=32, camadas=2, cabecas=4, dim=48))
    inferencia.exportar(modelo, tmp_path / inferencia.MODELO)
    tok.salvar(tmp_path / inferencia.TOKENIZADOR)
    cerebro = inferencia.carregar_de(tmp_path)

    ids = tok.codificar("O Brasil é o maior país")[:32]
    esperado = modelo(torch.tensor([ids]))[0][0].detach().numpy()
    assert np.abs(cerebro.logits(ids) - esperado).max() < 1e-4
    assert cerebro.parametros == modelo.numero_de_parametros()
    assert isinstance(cerebro.responder("O Brasil", 8), str)


def test_treino_curto_derruba_a_perda_e_retoma_do_checkpoint(torch, tmp_path):
    from kernel.cerebro import dados
    from kernel.cerebro.treinar import CHECKPOINT, ConfigTreino, treinar

    corpus = tmp_path / "corpus.txt"
    corpus.write_text(TEXTO * 5, encoding="utf-8")
    tok = tokenizador.treinar([TEXTO], tamanho=300)
    tok.salvar(tmp_path / inferencia.TOKENIZADOR)
    resumo = dados.preparar(corpus, tok, tmp_path)
    assert resumo["treino"] > 1000 and resumo["val"] >= 1
    assert (tmp_path / "treino.bin").stat().st_size == resumo["treino"] * 2

    cfg = ConfigTreino(tamanho="nano", passos=60, lote=8, taxa=3e-3, aquecimento=10, avaliar_cada=30,
                       lotes_de_avaliacao=2, dispositivo="cpu")
    avisos = []
    resumo = treinar(tmp_path, cfg, avisar=avisos.append)
    assert resumo["passo"] == 60
    assert resumo["melhor_validacao"] < 0.6 * math.log(tok.tamanho)  # texto repetitivo: cai rápido
    assert (tmp_path / CHECKPOINT).exists() and (tmp_path / inferencia.MODELO).exists()
    assert (tmp_path / "treino.csv").read_text().count("\n") == 3   # cabeçalho + 2 avaliações

    cfg.passos = 90                                                  # outra "madrugada": continua do 60
    resumo = treinar(tmp_path, cfg, avisar=avisos.append)
    assert resumo["passo"] == 90 and any("continuando do passo 60" in a for a in avisos)

    cerebro = inferencia.carregar_de(tmp_path)
    assert "Brasil" in cerebro.continuar("O Brasil é o maior país da América do Sul. A capital do", 12, temperatura=0.1)

    tokenizador.treinar([TEXTO], tamanho=280).salvar(tmp_path / inferencia.TOKENIZADOR)
    with pytest.raises(SystemExit, match="tokenizador"):   # trocar o tokenizador exige um cérebro novo
        treinar(tmp_path, cfg, avisar=avisos.append)


def test_taxa_sobe_no_aquecimento_e_desce_em_cosseno(torch):
    from kernel.cerebro.treinar import ConfigTreino, taxa_no_passo

    cfg = ConfigTreino(passos=1000, aquecimento=100, taxa=1e-3)
    assert taxa_no_passo(cfg, 0) < taxa_no_passo(cfg, 50) < taxa_no_passo(cfg, 99)
    assert abs(taxa_no_passo(cfg, 100) - 1e-3) < 1e-9
    assert taxa_no_passo(cfg, 100) > taxa_no_passo(cfg, 500) > taxa_no_passo(cfg, 999)
    assert abs(taxa_no_passo(cfg, 5000) - 1e-4) < 1e-9  # nunca abaixo de 10%
