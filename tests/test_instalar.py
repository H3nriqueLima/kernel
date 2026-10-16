"""Fase 2: instalar um cérebro de outra pasta, e os treinos da linha de comando no histórico do serviço."""
import asyncio
import shutil

import pytest

from conftest import falas
from kernel.cerebro import inferencia, tokenizador

TEXTO = "O Brasil é o maior país da América do Sul. A capital do Brasil é Brasília. "


@pytest.fixture(scope="module")
def torch():
    return pytest.importorskip("torch")


def _cerebro_em(pasta, torch, semente):
    from kernel.cerebro.gpt import GPT, ConfigGPT
    from kernel.cerebro.otimizador import AdamW
    from kernel.cerebro.treinar import CHECKPOINT, salvar_checkpoint

    pasta.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(semente)
    modelo = GPT(ConfigGPT(vocab=300, contexto=16, camadas=1, cabecas=2, dim=16))
    inferencia.exportar(modelo, pasta / inferencia.MODELO)
    salvar_checkpoint(pasta / CHECKPOINT, modelo, AdamW(modelo.parameters()), passo=1000 + semente, melhor=3.0,
                      segundos=1.0)
    (pasta / "treino.csv").write_text(f"passo,perda_treino,perda_val,taxa,tokens_por_segundo,segundos\n{1000 + semente},3,3,0.0001,100,1\n",
                                      encoding="utf-8")
    (pasta / "treino.log").write_text(f"treino da semente {semente}\n", encoding="utf-8")


@pytest.fixture
def duas_pastas(torch, tmp_path):
    tok = tokenizador.treinar([TEXTO], tamanho=300)
    servico, novo = tmp_path / "servico", tmp_path / "novo"
    for pasta, semente in ((servico, 1), (novo, 2)):
        _cerebro_em(pasta, torch, semente)
        tok.salvar(pasta / inferencia.TOKENIZADOR)
    return servico, novo


def test_instalar_troca_arquiva_e_anota(duas_pastas, tmp_path):
    from kernel.cerebro import instalar
    from kernel.registro import Registro

    servico, novo = duas_pastas
    registro = Registro(tmp_path / "registro")
    evento = instalar.instalar(novo, servico, registro, teste=2.95)
    assert (servico / inferencia.MODELO).read_bytes() == (novo / inferencia.MODELO).read_bytes()
    assert evento["passo"] == 1002 and evento["teste"] == 2.95
    assert "semente 2" in (servico / "treino.log").read_text(encoding="utf-8")       # o histórico do cérebro novo
    (arquivado,) = (servico / "historico").iterdir()
    assert "semente 1" in (arquivado / "treino.log").read_text(encoding="utf-8")       # e o do anterior, guardado
    assert registro.ultimos(1)[0]["tipo"] == "cerebro" and registro.ultimos(1)[0]["evento"] == "instalado"
    assert inferencia.carregar_de(servico) is not None


def test_instalar_recusa_tokenizador_diferente_ou_impressao_errada(duas_pastas):
    from kernel.cerebro import instalar

    servico, novo = duas_pastas
    antes = (servico / inferencia.MODELO).read_bytes()
    tokenizador.treinar([TEXTO + " Outro texto qualquer."], tamanho=280).salvar(novo / inferencia.TOKENIZADOR)
    with pytest.raises(instalar.ErroInstalar, match="tokenizador"):
        instalar.instalar(novo, servico)
    shutil.copy(servico / inferencia.TOKENIZADOR, novo / inferencia.TOKENIZADOR)
    (novo / (inferencia.MODELO + ".sha256")).write_text("0" * 64 + "\n")
    with pytest.raises(instalar.ErroInstalar, match="não confere"):
        instalar.instalar(novo, servico)
    assert (servico / inferencia.MODELO).read_bytes() == antes                         # nada foi mexido


def test_como_foi_o_ultimo_treino_ve_a_instalacao(kernel):
    kernel.registro.anotar("cerebro", evento="instalado", descricao="GPT de 16.0 milhões de parâmetros", passo=40000,
                           teste=2.98, quando="2026-10-18T07:30:00")
    asyncio.run(kernel.receber("como foi seu último treino?"))
    resposta = falas(kernel)[-1]
    assert "foi instalado em 18/10 às 07:30" in resposta and "passo 40.000" in resposta and "2,980" in resposta


def test_treino_pela_linha_de_comando_entra_no_registro(cfg, monkeypatch):
    from kernel import __main__ as cli
    from kernel.cerebro import treinar
    from kernel.registro import Registro

    resumo = {"motivo": "tempo", "passo": 120, "passo_inicial": 100, "melhor_validacao": 3.2, "segundos": 60.0,
              "horas_pedidas": 0.02}
    monkeypatch.setattr(cli, "carregar", lambda: cfg)
    monkeypatch.setattr(treinar, "treinar", lambda pasta, config: resumo)
    monkeypatch.delenv("KERNEL_PELO_SERVICO", raising=False)
    cli.main(["cerebro", "treinar", "--horas", "0.02"])
    hoje = __import__("datetime").date.today()
    eventos = [e for e in Registro(cfg.pasta("registro")).do_dia(hoje) if e.get("evento") == "treino_acabou"]
    assert len(eventos) == 1 and eventos[0]["origem"] == "linha de comando" and eventos[0]["passo"] == 120

    monkeypatch.setenv("KERNEL_PELO_SERVICO", "1")                   # lançado pelo serviço: quem anota é ele
    cli.main(["cerebro", "treinar", "--horas", "0.02"])
    eventos = [e for e in Registro(cfg.pasta("registro")).do_dia(__import__("datetime").date.today())
               if e.get("evento") == "treino_acabou"]
    assert len(eventos) == 1
