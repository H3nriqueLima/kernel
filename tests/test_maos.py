import pytest

from kernel.maos import AbrirPrograma, AnotarLembrete, ErroFerramenta, ListarPasta, Maos
from kernel.memoria import Memoria
from kernel.registro import Registro
from kernel.seguranca import Seguranca


@pytest.fixture
def maos(cfg):
    registro = Registro(cfg.pasta("registro"))
    seguranca = Seguranca(cfg, registro)
    memoria = Memoria(cfg.dados / "kernel.db")
    abertos = []
    m = Maos(seguranca, registro, [AbrirPrograma(cfg, abertos.append), ListarPasta(cfg, seguranca),
                                   AnotarLembrete(memoria)])
    m.abertos, m.memoria = abertos, memoria
    return m


def test_abrir_programa_so_depois_de_permitir(maos):
    pedido = maos.propor("abrir_programa", {"programa": "calculadora"})
    assert pedido.estado == "pendente" and maos.abertos == []
    assert "calc.exe" in pedido.descricao
    maos.concluir(pedido.id, True)
    assert pedido.estado == "executado" and maos.abertos == ["calc.exe"]


def test_negar_nao_abre_nada(maos):
    pedido = maos.propor("abrir_programa", {"programa": "bloco de notas"})
    maos.concluir(pedido.id, False)
    assert pedido.estado == "negado" and maos.abertos == []


def test_acha_programa_por_parte_do_nome_e_recusa_desconhecido(maos):
    assert maos.propor("abrir_programa", {"programa": "o gerenciador"}).argumentos["alvo"] == "taskmgr.exe"
    with pytest.raises(ErroFerramenta):
        maos.propor("abrir_programa", {"programa": "formatador de disco"})
    with pytest.raises(ErroFerramenta):
        maos.propor("abrir_programa", {"programa": ""})


def test_alvo_fora_da_lista_nunca_e_lancado(maos):
    """Mesmo que alguém troque o alvo de um pedido já aberto, a ferramenta confere de novo."""
    pedido = maos.propor("abrir_programa", {"programa": "calculadora"})
    pedido.argumentos["alvo"] = r"C:\Windows\System32\format.com"
    maos.concluir(pedido.id, True)
    assert pedido.estado == "falhou" and maos.abertos == []


def test_listar_pasta_liberada(maos, tmp_path):
    pedido = maos.propor("listar_pasta", {"pasta": str(tmp_path / "liberada")})
    maos.concluir(pedido.id, True)
    assert "[pasta] fotos" in pedido.resultado and "relatorio.txt" in pedido.resultado
    assert pedido.resultado.index("fotos") < pedido.resultado.index("relatorio.txt")  # pastas primeiro


def test_listar_pasta_fora_das_liberadas_e_recusada(maos, tmp_path):
    with pytest.raises(ErroFerramenta, match="fora das pastas liberadas"):
        maos.propor("listar_pasta", {"pasta": str(tmp_path)})
    with pytest.raises(ErroFerramenta):
        maos.propor("listar_pasta", {"pasta": str(tmp_path / "nao-existe")})


def test_anotar_lembrete_vai_para_a_memoria(maos):
    pedido = maos.propor("anotar_lembrete", {"texto": "pagar o boleto", "quando": "2026-10-13T10:00:00"})
    assert "13/10/2026 às 10:00" in pedido.descricao
    assert maos.memoria.lembretes() == []  # ainda não confirmou
    maos.concluir(pedido.id, True)
    (lembrete,) = maos.memoria.lembretes()
    assert lembrete.texto == "pagar o boleto" and lembrete.quando == "2026-10-13T10:00:00"


def test_ferramenta_inexistente(maos):
    with pytest.raises(ErroFerramenta):
        maos.propor("apagar_tudo", {})
