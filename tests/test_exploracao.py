"""A exploração autônoma: o que ele olha, o que ele nunca olha, e como você manda parar."""
import asyncio
import zipfile

import pytest

from conftest import falas
from kernel.exploracao import leitores, sistema
from kernel.exploracao.explorador import assunto_de, nomes_proprios
from kernel.nucleo import Kernel

CONTRATO = ("Contrato de prestação de serviços entre a Padaria Estrela e o escritório. "
            "O contrato vale por doze meses. A Padaria Estrela paga o serviço todo dia dez. "
            "O contrato pode ser renovado pela Padaria Estrela ao fim do prazo.")


@pytest.fixture
def pasta(tmp_path):
    """A pasta liberada do teste, com arquivos de vários tipos e algumas armadilhas."""
    liberada = tmp_path / "liberada"
    (liberada / "clientes").mkdir()
    (liberada / "clientes" / "contrato padaria.txt").write_text(CONTRATO, encoding="utf-8")
    (liberada / "clientes" / "notas.md").write_text("Reunião com a Marcela sobre o fechamento do mês. " * 3,
                                                    encoding="utf-8")
    (liberada / "clientes" / "foto.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 50)
    (liberada / "senhas").mkdir()
    (liberada / "senhas" / "banco.txt").write_text("a senha do banco é 1234 e ninguém pode ler isto aqui",
                                                   encoding="utf-8")
    (liberada / "clientes" / "token de acesso.txt").write_text("um segredo que não deve entrar na memória dele",
                                                               encoding="utf-8")
    fora = tmp_path / "fora"
    fora.mkdir()
    (fora / "diario pessoal.txt").write_text("isto está fora das pastas liberadas e não pode ser lido nunca",
                                             encoding="utf-8")
    return liberada


@pytest.fixture
def explorando(cfg, relogio, pasta):
    cfg.exploracao.ligada = True
    nucleo = Kernel(cfg, relogio=relogio, lancar=lambda alvo: None)
    yield nucleo
    nucleo.fechar()


def explorar_tudo(nucleo, maximo=200):
    feitos = []
    for _ in range(maximo):
        feito = nucleo.explorador.passo()
        if feito is None:
            break
        feitos.append(feito)
    return feitos


def dizer(nucleo, texto):
    asyncio.run(nucleo.receber(texto))


# ------------------------------------------------------------------ leitores
def test_le_texto_word_e_excel(tmp_path):
    (tmp_path / "a.txt").write_text("olá, mundo\n\n\nsegunda linha", encoding="utf-8")
    assert leitores.ler(tmp_path / "a.txt") == "olá, mundo\nsegunda linha"
    (tmp_path / "latin.txt").write_bytes("ação e coração".encode("cp1252"))
    assert leitores.ler(tmp_path / "latin.txt") == "ação e coração"
    with zipfile.ZipFile(tmp_path / "d.docx", "w") as z:
        z.writestr("word/document.xml", "<w:document><w:p><w:r><w:t>Primeiro parágrafo</w:t></w:r></w:p>"
                                        "<w:p><w:r><w:t>Segundo &amp; último</w:t></w:r></w:p></w:document>")
    assert leitores.ler(tmp_path / "d.docx") == "Primeiro parágrafo\nSegundo & último"
    with zipfile.ZipFile(tmp_path / "p.xlsx", "w") as z:
        z.writestr("xl/sharedStrings.xml", "<sst><si><t>Cliente</t></si><si><t>Valor</t></si></sst>")
    assert leitores.ler(tmp_path / "p.xlsx") == "Cliente\nValor"
    (tmp_path / "bin.txt").write_bytes(b"\x00\x01\x02" * 100)
    assert leitores.ler(tmp_path / "bin.txt") is None
    (tmp_path / "foto.jpg").write_bytes(b"\xff\xd8")
    assert leitores.ler(tmp_path / "foto.jpg") is None
    assert leitores.ler(tmp_path / "nao-existe.txt") is None


def test_pedacos_respeitam_o_tamanho():
    texto = "\n".join(f"linha número {i} com algum texto para encher" for i in range(40))
    partes = leitores.pedacos(texto, tamanho=200)
    assert len(partes) > 5 and all(len(p) <= 260 for p in partes)
    assert leitores.pedacos("x" * 1300, tamanho=500)[0] == "x" * 500


def test_assunto_e_nomes_proprios():
    assert assunto_de(CONTRATO).split(", ")[:2] == ["contrato", "padaria"]
    nomes = nomes_proprios(CONTRATO)
    assert nomes == {"padaria estrela": ("Padaria Estrela", 3, 0)}   # um nome só; começo de frase não conta


# ---------------------------------------------------------------- explorador
def test_explora_so_o_que_pode(explorando, pasta):
    feitos = explorar_tudo(explorando)
    visitadas = {f["pasta"] for f in feitos if f["acao"] == "visitar"}
    lidos = {f["arquivo"] for f in feitos if f["acao"] == "ler"}
    assert str(pasta) in visitadas and str(pasta / "clientes") in visitadas
    assert str(pasta / "senhas") not in visitadas                      # nome proibido: nem entra
    assert lidos == {str(pasta / "clientes" / "contrato padaria.txt"), str(pasta / "clientes" / "notas.md")}

    tudo_que_ele_guardou = " ".join(l.texto for l in explorando.memoria.recentes(100))
    assert "Padaria Estrela" in tudo_que_ele_guardou
    for proibido in ("1234", "segredo", "fora das pastas"):
        assert proibido not in tudo_que_ele_guardou
    nomes_no_mapa = {a["nome"] for a in explorando.mapa.procurar("contrato banco token foto diario")}
    assert nomes_no_mapa == {"contrato padaria.txt", "foto.jpg"}       # viu a foto, mas não tinha o que ler

    registrados = [e for e in explorando.registro.ultimos(300) if e["tipo"] == "explorar"]
    assert len(registrados) == len(feitos)                              # todo passo ficou no registro


def test_nao_segue_atalho_para_fora(explorando, pasta, tmp_path):
    try:
        (pasta / "atalho").symlink_to(tmp_path / "fora", target_is_directory=True)
    except OSError:
        pytest.skip("este Windows não deixa criar atalhos simbólicos sem ser administrador")
    explorar_tudo(explorando)
    assert explorando.mapa.procurar("diario pessoal") == []


def test_arquivo_so_na_nuvem_entra_no_mapa_mas_nao_e_aberto(explorando, pasta):
    import ctypes

    nuvem = pasta / "clientes" / "proposta na nuvem.txt"
    nuvem.write_text("Proposta comercial que só existe no OneDrive e não deve ser baixada.", encoding="utf-8")
    if not ctypes.windll.kernel32.SetFileAttributesW(str(nuvem), 0x1000):   # marca como "offline"
        pytest.skip("não deu para marcar o arquivo como offline")
    feitos = explorar_tudo(explorando)
    assert str(nuvem) not in {f.get("arquivo") for f in feitos if f["acao"] == "ler"}
    assert explorando.mapa.procurar("proposta")[0]["nome"] == "proposta na nuvem.txt"
    assert not explorando.memoria.buscar("comercial", tipos=("leitura",))


def test_so_nomes_quando_ler_esta_desligado(cfg, relogio, pasta):
    cfg.exploracao.ligada, cfg.exploracao.ler_arquivos = True, False
    nucleo = Kernel(cfg, relogio=relogio)
    feitos = explorar_tudo(nucleo)
    assert {f["acao"] for f in feitos} == {"visitar"}
    assert nucleo.memoria.contar().get("leitura", 0) == 0
    assert nucleo.mapa.procurar("contrato")[0]["nome"] == "contrato padaria.txt"
    nucleo.fechar()


def test_arquivo_alterado_e_relido_e_pasta_removida_e_esquecida(cfg, relogio, pasta):
    cfg.exploracao.ligada = True
    nucleo = Kernel(cfg, relogio=relogio)
    explorar_tudo(nucleo)
    assert nucleo.memoria.buscar("renovado", tipos=("leitura",))
    (pasta / "clientes" / "contrato padaria.txt").write_text(
        "Distrato: o acordo com a Padaria Estrela foi encerrado em comum acordo entre as partes.", encoding="utf-8")
    relogio.avancar(hours=30)                     # passa do prazo de revisita
    explorar_tudo(nucleo)
    assert nucleo.memoria.buscar("distrato", tipos=("leitura",))
    assert not nucleo.memoria.buscar("renovado", tipos=("leitura",))   # a leitura antiga saiu
    nucleo.fechar()

    cfg.seguranca.pastas_permitidas = [str(pasta / "fotos")]           # você tirou a pasta da lista
    (pasta / "fotos").mkdir(exist_ok=True)
    outro = Kernel(cfg, relogio=relogio)
    assert outro.mapa.procurar("contrato") == [] and outro.memoria.contar().get("leitura", 0) == 0
    outro.fechar()


# ------------------------------------------------------ autonomia e o freio
def test_curiosidade_vira_folego_de_exploracao(explorando, relogio):
    explorando.impulsos.valores["curiosidade"] = 0.9
    relogio.avancar(minutes=5)
    assert explorando.volta(5) == "explorar"
    assert explorando.estado()["atividade"] == "explorando"
    decisoes = [explorando.volta(5) for _ in range(30)]
    assert "explorar" in decisoes and decisoes[-1] != "explorar"       # o fôlego acaba sozinho
    assert explorando.impulsos.valores["curiosidade"] < 0.9
    assert explorando.mapa.numeros()["arquivos_lidos"] == 2
    reflexoes = [e["reflexao"] for e in explorando.registro.ultimos(300) if e["tipo"] == "laco"]
    assert any("Neste fôlego visitei" in r for r in reflexoes)


def test_nao_explora_enquanto_voce_fala(explorando):
    explorando.impulsos.valores["curiosidade"] = 0.9
    assert explorando.volta(5) != "explorar"       # você acabou de falar (relógio parado)
    assert explorando.mapa.numeros()["pastas_visitadas"] == 0


def test_para_e_pode_continuar(explorando, relogio, cfg):
    explorando.impulsos.valores["curiosidade"] = 0.9
    relogio.avancar(minutes=5)
    explorando.volta(5)
    dizer(explorando, "para")
    assert "Parei" in falas(explorando)[-1] and explorando.estado()["pausado"]
    vistos = explorando.mapa.numeros()["pastas_visitadas"]
    relogio.avancar(minutes=30)
    explorando.impulsos.valores["curiosidade"] = 1.0
    assert [explorando.volta(5) for _ in range(5)] == ["pausado"] * 5
    assert explorando.explorador.passo() is None
    assert explorando.mapa.numeros()["pastas_visitadas"] == vistos

    explorando.fechar()                                                  # a pausa sobrevive ao reinício
    outro = Kernel(cfg, relogio=relogio)
    assert outro.estado()["pausado"] and outro.volta(5) == "pausado"
    asyncio.run(outro.receber("pode continuar"))
    assert not outro.estado()["pausado"]
    relogio.avancar(minutes=5)
    outro.impulsos.valores["curiosidade"] = 0.9
    assert outro.volta(5) == "explorar"
    outro.fechar()


def test_exploracao_desligada_na_configuracao_nao_olha_nada(kernel, relogio):
    kernel.impulsos.valores["curiosidade"] = 1.0
    relogio.avancar(minutes=5)
    assert all(kernel.volta(5) != "explorar" for _ in range(5))
    assert kernel.explorador.passo() is None and kernel.mapa.numeros()["arquivos"] == 0


def test_conta_o_que_descobriu_e_pergunta_por_um_nome(explorando, relogio, pasta):
    for i in range(3):                                                   # o mesmo nome em mais arquivos
        (pasta / f"recibo {i}.txt").write_text(f"Recibo {i}: pagamento recebido da Padaria Estrela no valor combinado.",
                                               encoding="utf-8")
    explorando.impulsos.valores["curiosidade"] = 0.9
    relogio.avancar(minutes=5)
    for _ in range(40):
        explorando.volta(5)
    iniciativas = [m["texto"] for m in explorando.mensagens if m["classe"] == "iniciativa"]
    assert any('vi "Padaria Estrela" em 4 arquivos' in t for t in iniciativas), iniciativas
    dizer(explorando, "é uma cliente antiga do escritório")
    assert 'Guardei isso sobre "Padaria Estrela"' in falas(explorando)[-1]

    explorando.novidades = 40
    relogio.avancar(minutes=5)
    explorando.volta(5)
    assert any(t.startswith("Andei explorando.") for t in
               [m["texto"] for m in explorando.mensagens if m["classe"] == "iniciativa"])
    assert explorando.novidades == 0


def test_perguntas_sobre_arquivos_e_descobertas(explorando):
    explorar_tudo(explorando)
    dizer(explorando, "onde está o arquivo do contrato")
    assert "contrato padaria.txt" in falas(explorando)[-1] and "clientes" in falas(explorando)[-1]
    dizer(explorando, "o que você descobriu")
    assert "Já visitei" in falas(explorando)[-1] and "Li 2 deles" in falas(explorando)[-1]
    dizer(explorando, "o que você lembra sobre a padaria")
    assert "Padaria Estrela" in falas(explorando)[-1] and "li em clientes" in falas(explorando)[-1]
    dizer(explorando, "cadê o arquivo de impostos")
    assert "Não vi nenhum arquivo assim" in falas(explorando)[-1]


def test_sistema_descreve_a_maquina(kernel):
    texto = sistema.descrever()
    assert "Processador:" in texto and "Memória:" in texto and "Disco" in texto
    dizer(kernel, "quanto espaço livre tem no disco")
    assert "GB livres" in falas(kernel)[-1]


# ------------------------------------------------------- pastas muito grandes
def test_pasta_grande_e_largada_no_meio_quando_mandam_parar(explorando, pasta):
    """O freio não espera uma pasta de milhares de arquivos acabar."""
    grande = pasta / "grande"
    grande.mkdir()
    for i in range(300):
        (grande / f"arquivo{i:03d}.bin").write_bytes(b"x")
    explorador = explorando.explorador
    while explorando.mapa.proxima_pasta()[0] != grande:               # anda até chegar a vez da pasta grande
        assert explorador._visitar_uma()["acao"] in ("visitar", "pular_pasta")

    def para_no_meio():                                                # o "para" chega com a pasta pela metade
        explorando.seguranca.pausado = True
        return False

    explorador.interromper = para_no_meio
    feito = explorador._visitar_uma()
    assert feito["acao"] == "interrompido" and feito["itens"] <= 128 < 300
    assert explorando.mapa.proxima_pasta()[0] == grande                # continua na fila: não foi dada como vista
    vistos = explorando.mapa.numeros()["arquivos"]
    assert explorador.passo() is None                                  # parado, ele não dá mais passo nenhum

    explorando.seguranca.pausado = False                               # "pode continuar"
    explorador.interromper = lambda: True                              # agora é você falando no meio da pasta
    assert explorador._visitar_uma()["acao"] == "interrompido"
    explorador.interromper = lambda: False
    feito = explorador._visitar_uma()
    assert feito["acao"] == "visitar" and feito["itens"] == 300
    assert explorando.mapa.numeros()["arquivos"] >= 300 > vistos       # nada repetido, nada perdido
    assert explorando.mapa.proxima_pasta() is None or explorando.mapa.proxima_pasta()[0] != grande


def test_falar_ou_pedir_para_desligar_larga_a_exploracao(explorando):
    assert not explorando._largar_a_exploracao()
    dizer(explorando, "oi")                                            # você falou: ele larga a pasta em que está
    assert explorando._largar_a_exploracao()
    explorando._largar = False
    (explorando.cfg.dados / "DESLIGAR").write_text("desligar")
    assert explorando._largar_a_exploracao()                           # o freio de mão, mesmo sem a janela aberta
    (explorando.cfg.dados / "DESLIGAR").unlink()


def test_mapa_grava_em_lote_sem_perder_nada(tmp_path):
    from kernel.exploracao import Mapa

    mapa = Mapa(tmp_path / "mapa.db")
    with mapa.lote():
        for i in range(1000):
            assert mapa.registrar_arquivo(tmp_path / f"a{i}.txt", 10, 1000.0) == "novo"
            if i == 500:
                assert mapa.numeros()["arquivos"] == 501               # quem consulta no meio do lote é atendido
    assert mapa.registrar_arquivo(tmp_path / "a0.txt", 10, 1000.0) == "igual"
    mapa.fechar()
    outro = Mapa(tmp_path / "mapa.db")                                 # está tudo em disco
    assert outro.numeros()["arquivos"] == 1000
    outro.fechar()
