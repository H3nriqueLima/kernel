"""A API local (FastAPI) que a janela de chat e o celular usam para falar com o núcleo.

O porteiro tem três regras:

- o cabeçalho ``Host`` tem de ser desta máquina (o próprio PC ou o IP dele na rede);
- no próprio PC, toda chamada a ``/api`` tem de trazer o código que a página
  recebeu ao abrir. Sem isso, qualquer site aberto no seu navegador poderia
  mandar pedidos para ``127.0.0.1`` e clicar em "Permitir" no seu lugar;
- de outro aparelho (o celular na rede local), só entra quem foi pareado e
  manda a chave que recebeu no pareamento. Parear, ver os aparelhos e
  esquecê-los só se faz no próprio PC.

Por padrão o serviço só atende em 127.0.0.1. Ele só aparece na rede local se
você ligar ``[celular] ligado = true`` no kernel.toml.
"""
from __future__ import annotations

import asyncio
import secrets
import socket
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import NOME, VERSAO

WEB = Path(__file__).with_name("web")
_NESTE_PC = {"127.0.0.1", "::1", "localhost"}
_FALA_MAXIMA = 420   # caracteres: ele lê o começo de respostas compridas, não a lista inteira


class Fala(BaseModel):
    texto: str = Field(min_length=1, max_length=2000)


class Resposta(BaseModel):
    aprovar: bool


class Pareamento(BaseModel):
    codigo: str = Field(min_length=6, max_length=6)
    nome: str = Field(default="celular", max_length=40)


class Autonomia(BaseModel):
    pausar: bool


def enderecos_na_rede() -> list[str]:
    """Os endereços IPv4 deste PC na rede local."""
    ips = set()
    try:
        ips.update(info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # não envia nada: só pergunta ao sistema por onde sairia
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def texto_para_falar(mensagem: dict) -> str:
    """O que da mensagem vale a pena dizer em voz alta."""
    texto = mensagem["texto"]
    if mensagem["classe"] in ("resultado", "pesquisa") and "\n" in texto:
        texto = texto.split("\n", 1)[0]  # de uma listagem, só o título; de uma pesquisa, só a resposta
    if len(texto) > _FALA_MAXIMA:
        corte = max(texto.rfind(". ", 0, _FALA_MAXIMA), texto.rfind("\n", 0, _FALA_MAXIMA))
        texto = texto[:corte + 1] if corte > 80 else texto[:_FALA_MAXIMA]
    return texto


def criar_app(kernel, codigo: str, eh_local=None) -> FastAPI:
    """``eh_local(pedido)`` diz se o pedido veio do próprio PC (os testes trocam para simular um celular)."""
    eh_local = eh_local or (lambda pedido: pedido.client is not None and pedido.client.host in _NESTE_PC)
    porta = kernel.cfg.nucleo.porta
    falas_prontas: dict[int, asyncio.Future] = {}
    anfitrioes = {"quando": 0.0, "nomes": set(_NESTE_PC)}

    def anfitriao_valido(nome: str) -> bool:
        if time.time() - anfitrioes["quando"] > 60:  # o IP pode mudar; confere de novo a cada minuto
            maquina = socket.gethostname().lower()
            anfitrioes["nomes"] = _NESTE_PC | set(enderecos_na_rede()) | {maquina, f"{maquina}.local"}
            anfitrioes["quando"] = time.time()
        return nome.lower() in anfitrioes["nomes"]

    @asynccontextmanager
    async def vida(_app):
        tarefa = asyncio.create_task(kernel.laco())
        yield
        kernel.desligar("servidor encerrado")
        await tarefa

    app = FastAPI(title=NOME, lifespan=vida, docs_url=None, redoc_url=None, openapi_url=None)

    async def recusar(pedido: Request, status: int, erro: str) -> JSONResponse:
        # Lê o corpo antes de responder (se for pequeno): fechar a conexão com dados por ler faz
        # o Windows derrubá-la, e quem pediu nem chega a ver o motivo da recusa.
        if int(pedido.headers.get("content-length") or 0) <= 65536:
            await pedido.body()
        return JSONResponse({"erro": erro}, status_code=status)

    @app.middleware("http")
    async def porteiro(pedido: Request, seguir):
        anfitriao = pedido.headers.get("host", "")
        anfitriao = anfitriao.rsplit(":", 1)[0] if anfitriao.count(":") == 1 else anfitriao
        if not anfitriao_valido(anfitriao):
            return await recusar(pedido, 403, "anfitrião não permitido")
        caminho = pedido.url.path
        local = eh_local(pedido)
        pedido.state.local = local
        if caminho.startswith("/api/") and caminho not in ("/api/saude", "/api/parear"):
            chave = pedido.headers.get("x-kernel-codigo", "")
            do_pc = local and secrets.compare_digest(chave, codigo)
            if not (do_pc or kernel.aparelhos.reconhece(chave)):
                return await recusar(pedido, 401, "código ausente ou errado")
            if caminho.startswith("/api/celular") and not do_pc:
                return await recusar(pedido, 403, "isso só se faz no próprio PC")
        return await seguir(pedido)

    @app.get("/", response_class=HTMLResponse)
    async def pagina(pedido: Request):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        local = pedido.state.local
        html = html.replace("__CODIGO__", codigo if local else "").replace("__LOCAL__", "true" if local else "false")
        # a marca muda quando um arquivo da página muda: o navegador não fica com um app.js antigo guardado
        html = html.replace("__MARCA__", f"{VERSAO}-{int(max(a.stat().st_mtime for a in WEB.iterdir()))}")
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @app.get("/api/saude")
    async def saude():
        return {"nome": NOME, "versao": VERSAO}

    @app.get("/api/estado")
    async def estado():
        return kernel.estado()

    @app.get("/api/mensagens")
    async def mensagens(desde: int = 0):
        return [m for m in kernel.mensagens if m["id"] > desde]

    @app.post("/api/mensagem")
    async def mensagem(fala: Fala):
        await kernel.receber(fala.texto)
        return {"ok": True}

    @app.post("/api/pedido/{id_pedido}")
    async def pedido(id_pedido: str, resposta: Resposta):
        kernel.responder_pedido(id_pedido, resposta.aprovar)
        return {"ok": True}

    @app.post("/api/autonomia")
    async def autonomia(ordem: Autonomia):
        if ordem.pausar and not kernel.seguranca.pausado:
            kernel.pausar()
        elif not ordem.pausar and kernel.seguranca.pausado:
            kernel.retomar()
        return {"pausado": kernel.seguranca.pausado}

    @app.get("/api/voz/{id_mensagem}")
    async def voz(id_mensagem: int, s: str = ""):
        """A fala de uma mensagem dele, em WAV, feita pelo motor de voz da configuração.

        O navegador não pode guardar este som: os números das mensagens recomeçam a cada partida do
        serviço, e um som guardado seria tocado no lugar da fala de mesmo número da partida seguinte.
        """
        if not kernel.cfg.voz.ligada:
            return Response(status_code=204)
        if s and s != kernel.sessao:  # página aberta antes de um reinício: o número é de outra conversa
            return Response(status_code=409)
        if id_mensagem not in falas_prontas:
            achada = next((m for m in kernel.mensagens if m["id"] == id_mensagem and m["autor"] == "kernel"), None)
            if achada is None:
                return Response(status_code=404)
            from ..voz import falar_com

            def sintetizar() -> bytes:
                detalhes: dict = {}
                som = falar_com(kernel.cfg, texto_para_falar(achada), detalhes)
                kernel.registro.anotar("voz", id=id_mensagem, **detalhes)
                return som

            # guarda a tarefa, não o som: dois pedidos da mesma fala esperam a mesma síntese
            falas_prontas[id_mensagem] = asyncio.get_running_loop().run_in_executor(None, sintetizar)
            for antiga in list(falas_prontas)[:-40]:
                falas_prontas.pop(antiga)
        try:
            som = await falas_prontas[id_mensagem]
        except Exception:
            falas_prontas.pop(id_mensagem, None)   # deu errado: a próxima tentativa sintetiza de novo
            raise
        return Response(som, media_type="audio/wav", headers={"Cache-Control": "no-store"})

    @app.get("/api/registro")
    async def registro(n: int = 60):
        return kernel.registro.ultimos(min(max(n, 1), 300))

    @app.get("/api/diario")
    async def diario():
        dias = kernel.diario.dias()
        return {"dias": [d.isoformat() for d in dias],
                "texto": kernel.diario.ler(dias[-1]) if dias else None}

    @app.post("/api/diario")
    async def escrever_diario():
        return {"texto": kernel.diario.escrever(date.today())}

    @app.post("/api/desligar")
    async def desligar():
        kernel.desligar("botão de desligar")
        return {"ok": True}

    # ------------------------------------------------------------------ celular
    @app.post("/api/parear")
    async def parear(dados: Pareamento):
        chave = kernel.aparelhos.parear(dados.codigo, dados.nome)
        if chave is None:
            await asyncio.sleep(1.0)  # quem chuta código espera
            return JSONResponse({"erro": "código errado ou vencido"}, status_code=403)
        return {"chave": chave}

    @app.get("/api/celular")
    async def celular():
        return {"ligado": kernel.cfg.celular.ligado,
                "enderecos": [f"http://{ip}:{porta}/" for ip in enderecos_na_rede()],
                "aparelhos": kernel.aparelhos.lista()}

    @app.post("/api/celular/codigo")
    async def codigo_de_pareamento():
        return {"codigo": kernel.aparelhos.novo_codigo(), "minutos": 5}

    @app.delete("/api/celular/{id_aparelho}")
    async def esquecer_aparelho(id_aparelho: str):
        return {"ok": kernel.aparelhos.esquecer(id_aparelho)}

    app.mount("/web", StaticFiles(directory=WEB), name="web")
    return app
