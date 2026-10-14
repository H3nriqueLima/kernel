"""A API de verdade: um servidor numa porta livre, falando por HTTP como a janela de chat fala."""
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest
import uvicorn

from kernel.interface.api import criar_app, ip_da_rede_local
from kernel.nucleo import Kernel

CODIGO = "codigo-de-teste"


@pytest.fixture
def servidor(cfg):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    abertos = []
    cfg.mente.hora_do_diario = 25   # estes testes usam o relógio de verdade: às 23h o diário não pode entrar na conversa
    kernel = Kernel(cfg, lancar=abertos.append)
    servidor = uvicorn.Server(uvicorn.Config(criar_app(kernel, CODIGO, eh_local=lambda p: p.headers.get("x-teste-remoto") != "1",
                                                       da_rede_local=lambda p: p.headers.get("x-teste-internet") != "1"), host="127.0.0.1", port=porta,
                                             log_level="error"))
    kernel.ao_desligar = lambda: setattr(servidor, "should_exit", True)
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    for _ in range(100):
        if servidor.started:
            break
        time.sleep(0.05)
    servidor.base, servidor.kernel, servidor.abertos, servidor.thread = f"http://127.0.0.1:{porta}", kernel, abertos, thread
    yield servidor
    servidor.should_exit = True
    thread.join(timeout=10)
    kernel.fechar()


def chamar(servidor, caminho, corpo=None, codigo=CODIGO, host=None, remoto=False, metodo=None, bruto=False,
           internet=False):
    """``remoto=True`` faz o pedido parecer vindo de outro aparelho da rede (um celular);
    ``internet=True``, de um aparelho de fora da rede de casa."""
    cabecalhos = {"Content-Type": "application/json"}
    if remoto or internet:
        cabecalhos["X-Teste-Remoto"] = "1"
    if internet:
        cabecalhos["X-Teste-Internet"] = "1"
    if codigo:
        cabecalhos["X-Kernel-Codigo"] = codigo
    if host:
        cabecalhos["Host"] = host
    dados = json.dumps(corpo).encode() if corpo is not None else None
    pedido = urllib.request.Request(servidor.base + caminho, data=dados, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(pedido, timeout=10) as resposta:
            conteudo = resposta.read()
            return resposta.status, conteudo if bruto else conteudo.decode("utf-8")
    except urllib.error.HTTPError as erro:
        return erro.code, erro.read().decode("utf-8")


def test_porteiro_exige_o_codigo_e_o_anfitriao_certo(servidor):
    assert chamar(servidor, "/api/estado", codigo=None)[0] == 401
    assert chamar(servidor, "/api/estado", codigo="errado")[0] == 401
    assert chamar(servidor, "/api/mensagem", {"texto": "abre a calculadora"}, codigo=None)[0] == 401
    assert chamar(servidor, "/api/estado", host="site-malicioso.example")[0] == 403
    assert chamar(servidor, "/api/saude", codigo=None)[0] == 200  # só nome e versão, sem código
    assert servidor.kernel.mensagens == []


def test_a_pagina_recebe_o_codigo(servidor):
    status, html = chamar(servidor, "/", codigo=None)
    assert status == 200 and "__CODIGO__" not in html
    assert re.search(r'KERNEL_CODIGO = "([^"]+)"', html).group(1) == CODIGO
    assert chamar(servidor, "/web/app.js", codigo=None)[0] == 200
    # os arquivos da página vão com uma marca no endereço: mudou o arquivo, o navegador busca de novo
    marca = re.search(r'src="/web/app\.js\?v=([\w.\-]+)"', html).group(1)
    assert "__MARCA__" not in html and marca.startswith("0.")
    assert chamar(servidor, f"/web/app.js?v={marca}", codigo=None)[0] == 200


def test_conversa_pedido_e_confirmacao_pela_api(servidor):
    assert chamar(servidor, "/api/mensagem", {"texto": "abre a calculadora"})[0] == 200
    mensagens = json.loads(chamar(servidor, "/api/mensagens?desde=0")[1])
    assert [m["autor"] for m in mensagens] == ["voce", "kernel"]
    pedido = mensagens[-1]["pedido"]
    estado = json.loads(chamar(servidor, "/api/estado")[1])
    assert estado["pedidos"] == {pedido: "pendente"} and estado["nome"] == "K.E.R.N.E.L"
    assert estado["internet"] == {"ligada": False, "sozinho": True, "buscador": True, "pesquisados": 0, "paginas": 0,
                                  "na_fila": 0, "na_ultima_hora": 0, "teto": 30}   # de fábrica, desligada

    assert chamar(servidor, f"/api/pedido/{pedido}", {"aprovar": True})[0] == 200
    assert servidor.abertos == ["calc.exe"]
    assert json.loads(chamar(servidor, "/api/estado")[1])["pedidos"] == {pedido: "executado"}
    novas = json.loads(chamar(servidor, f"/api/mensagens?desde={mensagens[-1]['id']}")[1])
    assert [m["texto"] for m in novas] == ["Abri calculadora."]

    tipos = [e["tipo"] for e in json.loads(chamar(servidor, "/api/registro")[1])]
    assert {"mensagem", "intencao", "pedido", "confirmacao", "acao"} <= set(tipos)  # tudo foi registrado


def test_mensagem_vazia_ou_gigante_e_recusada(servidor):
    assert chamar(servidor, "/api/mensagem", {"texto": ""})[0] == 422
    assert chamar(servidor, "/api/mensagem", {"texto": "a" * 5000})[0] == 422


def test_diario_pela_api(servidor):
    chamar(servidor, "/api/mensagem", {"texto": "hoje foi um bom dia"})
    texto = json.loads(chamar(servidor, "/api/diario", {})[1])["texto"]
    assert texto.startswith("# Diário") and "falou comigo 1 vez" in texto
    assert json.loads(chamar(servidor, "/api/diario")[1])["texto"] == texto


def test_botao_de_desligar_para_o_servico(servidor):
    assert chamar(servidor, "/api/desligar", {})[0] == 200
    servidor.thread.join(timeout=10)
    assert not servidor.thread.is_alive()
    eventos = [e.get("evento") for e in servidor.kernel.registro.ultimos(10) if e["tipo"] == "servico"]
    assert eventos[-2:] == ["desligar", "fim"]


# ----------------------------------------------------------------- celular
def test_celular_sem_parear_nao_entra(servidor):
    status, html = chamar(servidor, "/", codigo=None, remoto=True)
    assert status == 200 and 'KERNEL_CODIGO = ""' in html and "KERNEL_LOCAL = false" in html   # a página vem sem código
    assert chamar(servidor, "/api/estado", codigo=None, remoto=True)[0] == 401
    assert chamar(servidor, "/api/estado", codigo=CODIGO, remoto=True)[0] == 401     # o código da página só vale no PC
    assert chamar(servidor, "/api/mensagem", {"texto": "abre a calculadora"}, codigo="chute", remoto=True)[0] == 401
    assert chamar(servidor, "/api/celular/codigo", {}, codigo=CODIGO, remoto=True)[0] == 401
    assert chamar(servidor, "/api/parear", {"codigo": "123456", "nome": "x"}, codigo=None, remoto=True)[0] == 403
    assert servidor.kernel.mensagens == []


def test_pareamento_e_uso_pelo_celular(servidor):
    codigo = json.loads(chamar(servidor, "/api/celular/codigo", {})[1])["codigo"]
    errado = "000000" if codigo != "000000" else "111111"
    assert chamar(servidor, "/api/parear", {"codigo": errado, "nome": "invasor"}, codigo=None, remoto=True)[0] == 403
    status, corpo = chamar(servidor, "/api/parear", {"codigo": codigo, "nome": "Meu celular"}, codigo=None, remoto=True)
    assert status == 200
    chave = json.loads(corpo)["chave"]

    assert json.loads(chamar(servidor, "/api/estado", codigo=chave, remoto=True)[1])["celular"]["aparelhos"] == 1
    assert chamar(servidor, "/api/mensagem", {"texto": "abre a calculadora"}, codigo=chave, remoto=True)[0] == 200
    pedido = json.loads(chamar(servidor, "/api/mensagens", codigo=chave, remoto=True)[1])[-1]["pedido"]
    assert chamar(servidor, f"/api/pedido/{pedido}", {"aprovar": True}, codigo=chave, remoto=True)[0] == 200
    assert servidor.abertos == ["calc.exe"]

    # o celular não gera código, não vê a lista de aparelhos e não desfaz pareamentos
    assert chamar(servidor, "/api/celular", codigo=chave, remoto=True)[0] == 403
    assert chamar(servidor, "/api/celular/codigo", {}, codigo=chave, remoto=True)[0] == 403

    lista = json.loads(chamar(servidor, "/api/celular")[1])
    assert lista["aparelhos"][0]["nome"] == "Meu celular" and "chave" not in json.dumps(lista)
    assert chamar(servidor, f"/api/celular/{lista['aparelhos'][0]['id']}", metodo="DELETE")[0] == 200
    assert chamar(servidor, "/api/estado", codigo=chave, remoto=True)[0] == 401      # esquecido: acesso cortado na hora


def test_voz_de_uma_mensagem(servidor):
    chamar(servidor, "/api/mensagem", {"texto": "quanto é 2 + 2?"})
    mensagens = json.loads(chamar(servidor, "/api/mensagens")[1])
    status, som = chamar(servidor, f"/api/voz/{mensagens[-1]['id']}", bruto=True)
    assert status == 200 and som[:4] == b"RIFF" and som[8:12] == b"WAVE" and len(som) > 20_000
    assert chamar(servidor, f"/api/voz/{mensagens[0]['id']}", bruto=True)[0] == 404     # a sua fala não é dele
    assert chamar(servidor, "/api/voz/999", bruto=True)[0] == 404
    assert chamar(servidor, f"/api/voz/{mensagens[-1]['id']}", codigo=None, bruto=True)[0] == 401
    servidor.kernel.cfg.voz.ligada = False
    assert chamar(servidor, f"/api/voz/{mensagens[-1]['id']}", bruto=True)[0] == 204


def test_voz_nao_fica_guardada_no_navegador_e_e_da_partida_certa(servidor):
    """Os números das mensagens recomeçam a cada partida: um som guardado tocaria a fala errada."""
    chamar(servidor, "/api/mensagem", {"texto": "quanto é 2 + 2?"})
    ultima = json.loads(chamar(servidor, "/api/mensagens")[1])[-1]["id"]
    sessao = json.loads(chamar(servidor, "/api/estado")[1])["sessao"]
    assert sessao == servidor.kernel.sessao and len(sessao) >= 8
    pedido = urllib.request.Request(f"{servidor.base}/api/voz/{ultima}?s={sessao}", headers={"X-Kernel-Codigo": CODIGO})
    with urllib.request.urlopen(pedido, timeout=10) as resposta:
        assert resposta.status == 200 and resposta.headers["Cache-Control"] == "no-store"
        assert resposta.read()[:4] == b"RIFF"
    assert chamar(servidor, f"/api/voz/{ultima}?s=partida-antiga", bruto=True)[0] == 409   # página de antes do reinício
    # o registro diz qual motor falou (sem banco de difones nos testes, é o de formantes)
    vozes = [e for e in servidor.kernel.registro.ultimos(20) if e["tipo"] == "voz"]
    assert len(vozes) == 1 and vozes[0]["id"] == ultima and vozes[0]["motor"] == "formantes" and vozes[0]["segundos"] > 0.5


def test_cada_partida_tem_a_sua_marca(cfg):
    um, outro = Kernel(cfg), Kernel(cfg)
    try:
        assert um.sessao != outro.sessao and um.estado()["sessao"] == um.sessao
    finally:
        um.fechar()
        outro.fechar()


def test_botao_de_parar_e_continuar(servidor):
    assert json.loads(chamar(servidor, "/api/autonomia", {"pausar": True})[1]) == {"pausado": True}
    estado = json.loads(chamar(servidor, "/api/estado")[1])
    assert estado["pausado"] and estado["atividade"] == "pausado"
    assert json.loads(chamar(servidor, "/api/autonomia", {"pausar": False})[1]) == {"pausado": False}
    assert not json.loads(chamar(servidor, "/api/estado")[1])["pausado"]


def test_texto_para_falar_encurta_listagens():
    from kernel.interface.api import texto_para_falar

    listagem = {"classe": "resultado", "texto": "C:\\x tem 16 itens:\n[pasta] a\n[pasta] b"}
    assert texto_para_falar(listagem) == "C:\\x tem 16 itens:"
    longo = {"classe": "conhecimento", "texto": "Primeira frase. " * 60}
    assert len(texto_para_falar(longo)) <= 420 and texto_para_falar(longo).endswith(".")


def test_so_a_rede_local_e_atendida():
    for ip in ("192.168.0.5", "10.1.2.3", "172.20.0.9", "127.0.0.1", "::1", "fe80::1%12", "::ffff:192.168.0.7"):
        assert ip_da_rede_local(ip), ip
    for ip in ("8.8.8.8", "177.45.10.2", "2804:14c:1::5", "100.70.1.1", "::ffff:8.8.8.8", "lixo"):
        assert not ip_da_rede_local(ip), ip


def test_quem_vem_da_internet_e_recusado_mesmo_pareado(servidor):
    codigo = json.loads(chamar(servidor, "/api/celular/codigo", {})[1])["codigo"]
    chave = json.loads(chamar(servidor, "/api/parear", {"codigo": codigo, "nome": "celular"}, codigo=None, remoto=True)[1])["chave"]
    assert chamar(servidor, "/api/estado", codigo=chave, remoto=True)[0] == 200
    assert chamar(servidor, "/api/estado", codigo=chave, internet=True)[0] == 403   # a mesma chave, de fora: não
    assert chamar(servidor, "/", codigo=None, internet=True)[0] == 403              # nem a página
    assert chamar(servidor, "/api/parear", {"codigo": "123456", "nome": "x"}, codigo=None, internet=True)[0] == 403


def test_registro_e_diario_so_no_proprio_pc(servidor):
    codigo = json.loads(chamar(servidor, "/api/celular/codigo", {})[1])["codigo"]
    chave = json.loads(chamar(servidor, "/api/parear", {"codigo": codigo, "nome": "celular"}, codigo=None, remoto=True)[1])["chave"]
    assert chamar(servidor, "/api/registro", codigo=chave, remoto=True)[0] == 403
    assert chamar(servidor, "/api/diario", codigo=chave, remoto=True)[0] == 403
    assert chamar(servidor, "/api/diario", {}, codigo=chave, remoto=True)[0] == 403
    assert chamar(servidor, "/api/registro")[0] == 200 and chamar(servidor, "/api/diario")[0] == 200
    assert chamar(servidor, "/api/mensagens", codigo=chave, remoto=True)[0] == 200   # a conversa continua no celular
