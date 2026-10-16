"""Fase 2: a interface estável do cérebro (carregar por configuração, gerar, pontuar)."""
import numpy as np
import pytest

from kernel.cerebro import inferencia, interface, tokenizador

TEXTO = ("O Brasil é o maior país da América do Sul. A capital do Brasil é Brasília. O Sol é a estrela do sistema "
         "solar. A água é uma substância formada por hidrogênio e oxigênio. ")


@pytest.fixture(scope="module")
def torch():
    return pytest.importorskip("torch")


@pytest.fixture
def pasta(torch, tmp_path):
    from kernel.cerebro.gpt import GPT, ConfigGPT

    tok = tokenizador.treinar([TEXTO], tamanho=300)
    tok.salvar(tmp_path / inferencia.TOKENIZADOR)
    torch.manual_seed(0)
    inferencia.exportar(GPT(ConfigGPT(vocab=tok.tamanho, contexto=32, camadas=2, cabecas=2, dim=32)),
                        tmp_path / inferencia.MODELO)
    return tmp_path


def test_os_dois_motores_dao_a_mesma_perda(pasta):
    tok = tokenizador.Tokenizador.carregar(pasta / inferencia.TOKENIZADOR)
    ids = np.array(tok.codificar(TEXTO * 3), dtype=np.int64)
    pelo_numpy = interface.carregar(interface.Especificacao.da_pasta(pasta))
    pelo_torch = interface.carregar(interface.Especificacao.da_pasta(pasta, motor="torch", dispositivo="cpu"))
    a, b = pelo_numpy.pontuar(ids), pelo_torch.pontuar(ids)
    assert a.shape == b.shape == ((len(ids) - 1) // 32, 32)
    assert np.abs(a - b).max() < 1e-4
    assert pelo_numpy.info["sha256"] == (pasta / (inferencia.MODELO + ".sha256")).read_text().strip()
    assert pelo_numpy.info["parametros"] == pelo_torch.info["parametros"] > 0


def test_gerar_com_semente_se_repete(pasta):
    cerebro = interface.carregar(interface.Especificacao.da_pasta(pasta))
    um = cerebro.gerar("O Brasil", 20, semente=7)
    assert um == cerebro.gerar("O Brasil", 20, semente=7) and isinstance(um, str)
    assert cerebro.velocidade_de_geracao(tokens=20) > 0
    assert isinstance(cerebro.responder("O Brasil", 20), str)


def test_carregar_pela_configuracao_e_recusar_adulterado(pasta, tmp_path_factory):
    import shutil

    outra = tmp_path_factory.mktemp("candidato")
    shutil.copy(pasta / inferencia.MODELO, outra / "candidato.npz")
    shutil.copy(pasta / (inferencia.MODELO + ".sha256"), outra / "candidato.npz.sha256")

    class Cfg:
        class cerebro:
            pesos = str(outra / "candidato.npz")

        def pasta(self, nome):
            return pasta
    especificacao = interface.Especificacao.da_configuracao(Cfg())
    assert especificacao.pesos.name == "candidato.npz" and especificacao.existe()
    servico = inferencia.carregar(Cfg())                           # o serviço carrega pela interface
    assert isinstance(servico, interface.Cerebro) and servico.info["pesos"] == "candidato.npz"

    dados = bytearray((outra / "candidato.npz").read_bytes())
    dados[-300] ^= 0xFF
    (outra / "candidato.npz").write_bytes(bytes(dados))
    with pytest.raises(inferencia.ModeloEstragado):
        interface.carregar(especificacao)
    avisos = []
    assert inferencia.carregar(Cfg(), avisar=avisos.append) is None and avisos
