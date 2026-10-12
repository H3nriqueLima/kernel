import shutil

import pytest

from kernel.registro import Registro
from kernel.seguranca import ErroSeguranca, Nivel, Seguranca, integridade


@pytest.fixture
def seguranca(cfg):
    tempo = [1000.0]
    s = Seguranca(cfg, Registro(cfg.pasta("registro")), relogio=lambda: tempo[0])
    s.tempo = tempo
    return s


def test_tudo_pede_confirmacao_na_v01(seguranca):
    for nivel in Nivel:
        assert seguranca.precisa_confirmar(nivel, "usuario")


def test_nivel_sistema_confirma_mesmo_com_a_configuracao_frouxa(seguranca):
    seguranca.cfg.seguranca.confirmar_a_partir_de = 99
    assert not seguranca.precisa_confirmar(Nivel.LEITURA, "usuario")
    assert seguranca.precisa_confirmar(Nivel.SISTEMA, "usuario")
    assert seguranca.precisa_confirmar(Nivel.LEITURA, "autonomia")  # iniciativa própria sempre pergunta


def test_pedido_aprovado_negado_e_repetido(seguranca):
    pedido = seguranca.abrir_pedido("abrir_programa", {}, "Abrir X", Nivel.SISTEMA, "usuario")
    assert pedido.estado == "pendente" and seguranca.pendentes() == [pedido]
    assert seguranca.responder(pedido.id, True).estado == "aprovado"
    with pytest.raises(ErroSeguranca):
        seguranca.responder(pedido.id, True)  # não dá para aprovar duas vezes
    outro = seguranca.abrir_pedido("abrir_programa", {}, "Abrir Y", Nivel.SISTEMA, "usuario")
    assert seguranca.responder(outro.id, False).estado == "negado"
    with pytest.raises(ErroSeguranca):
        seguranca.responder("inexistente", True)


def test_pedido_expira_sem_resposta(seguranca):
    pedido = seguranca.abrir_pedido("abrir_programa", {}, "Abrir X", Nivel.SISTEMA, "usuario")
    seguranca.tempo[0] += seguranca.cfg.seguranca.validade_pedido + 1
    with pytest.raises(ErroSeguranca):
        seguranca.responder(pedido.id, True)
    assert pedido.estado == "expirado"


def test_pasta_permitida_nao_deixa_escapar(seguranca, tmp_path):
    liberada = tmp_path / "liberada"
    assert seguranca.pasta_permitida(liberada)
    assert seguranca.pasta_permitida(liberada / "fotos")
    assert not seguranca.pasta_permitida(tmp_path)
    assert not seguranca.pasta_permitida(liberada / ".." / "dados")  # o ".." é resolvido antes


def test_modo_seguro_desliga_as_maos(seguranca):
    seguranca.entrar_em_modo_seguro("teste")
    with pytest.raises(ErroSeguranca):
        seguranca.abrir_pedido("listar_pasta", {}, "Listar", Nivel.LEITURA, "usuario")


def test_pode_explorar_so_dentro_das_regras(seguranca, tmp_path):
    liberada = tmp_path / "liberada"
    assert not seguranca.pode_explorar(liberada)                 # a exploração vem desligada nos testes
    seguranca.cfg.exploracao.ligada = True
    assert seguranca.pode_explorar(liberada) and seguranca.pode_ler(liberada / "relatorio.txt")
    assert not seguranca.pode_explorar(tmp_path)                 # fora das pastas liberadas
    assert not seguranca.pode_explorar(liberada / "minhas senhas" / "banco.txt")   # nome proibido
    assert not seguranca.pode_explorar(liberada / ".ssh")
    assert not seguranca.pode_explorar(seguranca.cfg.dados)      # a própria memória não é assunto
    seguranca.cfg.exploracao.ler_arquivos = False
    assert seguranca.pode_explorar(liberada) and not seguranca.pode_ler(liberada / "relatorio.txt")
    seguranca.cfg.exploracao.ler_arquivos = True
    seguranca.pausado = True                                     # você disse "para"
    assert not seguranca.pode_explorar(liberada)
    seguranca.pausado = False
    seguranca.entrar_em_modo_seguro("teste")
    assert not seguranca.pode_explorar(liberada)


def test_explorar_nao_abre_caminho_para_as_maos(seguranca):
    """Olhar sozinho é permitido; agir sozinho continua pedindo confirmação, em qualquer nível."""
    seguranca.cfg.exploracao.ligada = True
    seguranca.cfg.seguranca.confirmar_a_partir_de = 99
    for nivel in Nivel:
        assert seguranca.precisa_confirmar(nivel, "autonomia")


def test_lista_nunca_do_usuario_soma_a_de_fabrica(tmp_path):
    from kernel.config import carregar

    (tmp_path / "k.toml").write_text('[exploracao]\nnunca = ["Confidencial"]\n', encoding="utf-8")
    cfg = carregar(arquivo=tmp_path / "k.toml", dados=tmp_path / "d")
    assert "confidencial" in cfg.exploracao.nunca and "senha" in cfg.exploracao.nunca


def test_pareamento_de_aparelho(cfg):
    from kernel.seguranca.aparelhos import Aparelhos

    tempo = [0.0]
    aparelhos = Aparelhos(cfg.dados / "aparelhos.json", Registro(cfg.pasta("registro")), relogio=lambda: tempo[0])
    assert aparelhos.parear("123456", "celular") is None          # sem código gerado, nada entra
    codigo = aparelhos.novo_codigo()
    assert len(codigo) == 6 and codigo.isdigit()
    errado = "000000" if codigo != "000000" else "111111"
    assert aparelhos.parear(errado, "invasor") is None
    chave = aparelhos.parear(codigo, "  Meu Celular  ")
    assert chave and aparelhos.reconhece(chave) and not aparelhos.reconhece("outra") and not aparelhos.reconhece("")
    assert aparelhos.parear(codigo, "de novo") is None            # o código serve uma vez só
    assert chave not in (cfg.dados / "aparelhos.json").read_text(encoding="utf-8")   # só o resumo fica em disco

    outro = Aparelhos(cfg.dados / "aparelhos.json", Registro(cfg.pasta("registro")))  # sobrevive ao reinício
    assert outro.reconhece(chave) and outro.lista()[0]["nome"] == "Meu Celular"
    assert outro.esquecer(outro.lista()[0]["id"]) and not outro.reconhece(chave)


def test_codigo_de_pareamento_expira_e_trava(cfg):
    from kernel.seguranca.aparelhos import TENTATIVAS, VALIDADE_DO_CODIGO, Aparelhos

    tempo = [0.0]
    aparelhos = Aparelhos(cfg.dados / "aparelhos.json", Registro(cfg.pasta("registro")), relogio=lambda: tempo[0])
    codigo = aparelhos.novo_codigo()
    tempo[0] = VALIDADE_DO_CODIGO + 1
    assert aparelhos.parear(codigo, "atrasado") is None           # passou dos 5 minutos
    codigo = aparelhos.novo_codigo()
    errado = "000000" if codigo != "000000" else "111111"
    for _ in range(TENTATIVAS):
        assert aparelhos.parear(errado, "chute") is None
    assert aparelhos.parear(codigo, "tarde demais") is None       # errou demais: o código morreu


def test_o_selo_do_projeto_esta_integro():
    integro, mudancas = integridade.verificar()
    assert integro, f"rode 'python -m kernel selar' depois de revisar: {mudancas}"


def test_selo_percebe_alteracao(tmp_path, monkeypatch):
    copia = tmp_path / "seguranca"
    shutil.copytree(integridade.PASTA, copia)
    monkeypatch.setattr(integridade, "PASTA", copia)
    monkeypatch.setattr(integridade, "SELO", copia / "selo.json")
    integridade.selar()
    assert integridade.verificar() == (True, [])
    with open(copia / "permissoes.py", "a", encoding="utf-8") as f:
        f.write("\n# afrouxando o freio\n")
    (copia / "atalho.py").write_text("x = 1\n")
    integro, mudancas = integridade.verificar()
    assert not integro
    assert "alterado: permissoes.py" in mudancas and "novo: atalho.py" in mudancas


def test_selo_ignora_troca_de_fim_de_linha(tmp_path, monkeypatch):
    copia = tmp_path / "seguranca"
    shutil.copytree(integridade.PASTA, copia)
    monkeypatch.setattr(integridade, "PASTA", copia)
    monkeypatch.setattr(integridade, "SELO", copia / "selo.json")
    integridade.selar()
    arquivo = copia / "permissoes.py"
    arquivo.write_bytes(arquivo.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert integridade.verificar()[0]
