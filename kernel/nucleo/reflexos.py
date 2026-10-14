"""Reflexos: respostas que não precisam nem do classificador nem do cérebro.

São regras curtas e previsíveis, conferidas antes de tudo. A mais importante é
o freio: "para" tem de funcionar sempre, do mesmo jeito, sem depender de um
modelo acertar a intenção.
"""
from __future__ import annotations

import re
from datetime import datetime

from ..memoria.texto import normalizar

_DIAS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")
_MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
          "setembro", "outubro", "novembro", "dezembro")

_ENFEITE = r"(?: agora| ai| um pouco| por favor| por enquanto| ja)*"
_O_QUE = r"(?: de explorar| de fucar| de mexer| de olhar(?: (?:meus arquivos|o pc|as pastas))?| com isso| tudo)?"
_PAUSAR = re.compile(
    rf"^(?:pode )?(?:para|pare|parar|pausa|pause|pausar|chega|quieto|fica quieto|fique quieto|stop){_O_QUE}{_ENFEITE}$"
    rf"|^(?:para|pare|pausa|pause|desliga|desligue)(?: a| sua)? (?:exploracao|autonomia){_ENFEITE}$"
    rf"|^nao explor\w+(?: mais| nada)?{_ENFEITE}$")
_RETOMAR = re.compile(
    rf"^(?:pode )?(?:continuar|continua|continue|voltar|volta|volte|retoma|retome|retomar|seguir|segue)"
    rf"(?: a explorar| explorando| a exploracao| com a exploracao| de onde parou)?{_ENFEITE}$"
    rf"|^pode (?:explorar|voltar a explorar)(?: de novo| o pc)?{_ENFEITE}$"
    rf"|^(?:liga|ligue|ativa|ative)(?: a| sua)? (?:exploracao|autonomia){_ENFEITE}$")


def _limpo(texto: str) -> str:
    plano = re.sub(r"[^\w\s]", " ", normalizar(texto))
    return re.sub(r"^kernel\s+", "", " ".join(plano.split()))


def controle(texto: str) -> str | None:
    """ "pausar", "retomar" ou None. É o freio da autonomia, dito em palavras."""
    plano = _limpo(texto)
    if _PAUSAR.match(plano):
        return "pausar"
    if _RETOMAR.match(plano):
        return "retomar"
    return None


def hora_ou_data(texto: str, agora: datetime) -> str | None:
    plano = _limpo(texto)
    if re.search(r"\bque horas?\b|\bhoras sao\b|\bme diz a hora\b|\bqual a hora\b", plano):
        return f"São {agora:%H:%M}."
    if re.search(r"\bque dia e hoje\b|\bqual (?:e )?a data\b|\bdata de hoje\b|\bque dia da semana\b|"
                 r"\bem que dia estamos\b|\bhoje e que dia\b", plano):
        return f"Hoje é {_DIAS[agora.weekday()]}, {agora.day} de {_MESES[agora.month - 1]} de {agora.year}."
    return None


_CUMPRIMENTOS = {"oi", "ola", "opa", "e ai", "oi kernel", "ola kernel", "fala", "fala kernel", "eai", "salve",
                 "oie", "hello", "hi", "hey", "alo", "e ae", "eae", "hello kernel", "hi kernel", "oi oi", "ei"}
_COMO_VAI = {"tudo bem", "tudo bom", "tudo certo", "como vai", "como vai voce", "beleza", "tudo bem com voce",
             "e ai tudo bem", "oi tudo bem", "ola tudo bem", "tudo joia", "como voce esta", "tudo bem kernel"}
_PERIODOS = {"bom dia": "Bom dia", "boa tarde": "Boa tarde", "boa noite": "Boa noite"}
_AGRADECIMENTOS = {"obrigado", "obrigada", "muito obrigado", "valeu", "brigado", "obrigado kernel", "vlw", "valeu kernel"}
_DESPEDIDAS = {"tchau", "ate mais", "ate amanha", "ate logo", "ate depois", "fui", "tchau kernel"}


def saudacao(texto: str, usuario: str, lembretes_pendentes: int) -> str | None:
    plano = re.sub(r"(\w)\1+\b", r"\1", _limpo(texto))   # "oiii" e "olaaa" são "oi" e "ola"
    if plano in _COMO_VAI:
        return f"Tudo certo por aqui, {usuario}. E com você?"
    lembrete = ""
    if lembretes_pendentes:
        plural = "lembrete pendente" if lembretes_pendentes == 1 else "lembretes pendentes"
        lembrete = f" Você tem {lembretes_pendentes} {plural}."
    for dito, resposta in _PERIODOS.items():
        if plano in (dito, f"{dito} kernel"):
            return f"{resposta}, {usuario}.{lembrete}"
    if plano in _CUMPRIMENTOS:
        return f"Olá, {usuario}.{lembrete}"
    if plano in _AGRADECIMENTOS:
        return "De nada."
    if plano in _DESPEDIDAS:
        return f"Até mais, {usuario}."
    return None


_ESTUDAR_WIKI = re.compile(r"\b(?:estud\w+|aprend\w+|baix\w+|lei?a?)\b.*\bwikipedia\b")
_TREINAR = re.compile(r"\btrein\w+\b.*\bcerebro\b")
# "treine por 6 horas" / "treina mais 2 horas": o único treino que dura horas é o do cérebro. Precisa do verbo
# (não "o treino de ontem") e de uma duração; a palavra de ativação treina de outro jeito e fica de fora.
_TREINAR_POR_TEMPO = re.compile(r"\btrein(?:a|e|ar)\b(?:\s+\w+){0,3}?\s+(?:por|durante|mais)\b")
_NAO_E_O_CEREBRO = re.compile(r"\b(?:ativacao|palavra|ouvidos?|voz|comandos?)\b")
_PARAR_ESTUDO = re.compile(r"\b(?:par[ae]\w*|cancel\w+|interromp\w+)\b.*\b(?:treino|treinamento|estudo|download)\b")
_ANDAMENTO = re.compile(r"\b(?:como (?:esta|vai|anda)|andamento|progresso|quanto falta)\b.*\b(?:treino|treinamento|estudo|download)\b")


_PALAVRAS_DE_ESTUDO = ("estudo", "treino", "treinamento", "cerebro", "wikipedia", "download")


def _consertar(plano: str) -> str:
    """Um erro de dedo numa palavra de comando não pode mudar o que você pediu: "etudo" é "estudo"."""
    import difflib

    palavras = []
    for palavra in plano.split():
        if len(palavra) >= 5 and palavra not in _PALAVRAS_DE_ESTUDO:
            parecida = difflib.get_close_matches(palavra, _PALAVRAS_DE_ESTUDO, n=1, cutoff=0.88)
            palavra = parecida[0] if parecida else palavra
        palavras.append(palavra)
    return " ".join(palavras)


def estudo(texto: str) -> tuple[str, dict] | None:
    """Pedidos de estudo longo: ("wikipedia", {...}), ("treinar", {...}), ("parar", {}) ou ("andamento", {})."""
    plano = _consertar(_limpo(texto))
    if _PARAR_ESTUDO.search(plano):
        return "parar", {}
    if _ANDAMENTO.search(plano):
        return "andamento", {}
    if _ESTUDAR_WIKI.search(plano):
        partes = re.search(r"(\d+) partes?", plano)
        tudo = re.search(r"\b(?:toda|inteira|completa|tudo)\b", plano)
        return "wikipedia", {"partes": 99 if tudo else int(partes.group(1)) if partes else 1}
    if _TREINAR.search(plano):
        return "treinar", {"horas": _duracao_em_horas(normalizar(texto)) or 8.0}
    if _TREINAR_POR_TEMPO.search(plano) and not _NAO_E_O_CEREBRO.search(plano):
        horas = _duracao_em_horas(normalizar(texto))
        if horas:
            return "treinar", {"horas": horas}
    return None


def _duracao_em_horas(plano: str) -> float | None:
    """ "2 horas", "20 minutos", "1 hora e 30 minutos", "1h30", "meia hora" -> horas. None se a frase não diz."""
    numero = r"(\d+(?:[.,]\d+)?)"
    horas = re.search(numero + r"\s*(?:horas?\b|h(?![a-z]))", plano)
    minutos = re.search(numero + r"\s*(?:min\b|minutos?\b)", plano) or re.search(r"\dh(\d{1,2})\b", plano)
    total = 0.0
    if horas:
        total += float(horas.group(1).replace(",", "."))
        if re.search(r"horas? e meia\b", plano):
            total += 0.5
    elif re.search(r"\bmeia hora\b", plano):
        total += 0.5
    if minutos:
        total += float(minutos.group(1).replace(",", ".")) / 60
    return total or None



# ----------------------------------------------------------------- internet
_ENDERECO = re.compile(
    r"https?://[^\s<>\"']+"
    r"|(?<![@\w.\-])(?:[a-z0-9][a-z0-9\-]*\.)+(?:com|org|net|gov|edu|br|pt|io|dev|info|app|tv|wiki)(?:\.[a-z]{2})?(?:/[^\s<>\"']*)?(?![\w\-])",
    re.I)
_PEDE = r"(?:pode |voce pode |por favor |me )?"
_NA_REDE = r"(?:na|pela|da) (?:internet|web|rede)"
_SOBRE = r"(?: (?:sobre|por|a respeito de|acerca de))?"
_PESQUISAR = re.compile(
    rf"^{_PEDE}(?:pesquis\w+|googl\w+)(?: (?:pra|para) mim)?(?: {_NA_REDE})?{_SOBRE} (?P<fim>.+)$"
    rf"|^{_PEDE}(?:busc\w+|procur\w+|olh\w+|ve|veja|descobr\w+|aprend\w+|estud\w+)(?: (?:pra|para) mim)? {_NA_REDE}{_SOBRE} (?P<fim2>.+)$"
    rf"|^{_PEDE}(?:busc\w+|procur\w+|olh\w+|descobr\w+|aprend\w+|estud\w+){_SOBRE} (?P<meio>.+?) (?:{_NA_REDE}|no google)$")
_NAO_E_DA_REDE = re.compile(r"^(?:(?:na|nas|no|nos|da|das|do|dos|em|a|as|o|os|sua|suas|seu|seus|minha|minhas|meu|meus) )*"
                            r"(?:memoria|memorias|arquivo|arquivos|pasta|pastas|pc|computador|documento|documentos|lembrete|lembretes)\b"
                            r"|^(?:na|pela|da) (?:internet|web|rede)$")
_RELATO_DA_REDE = re.compile(
    r"\bo que (?:e que )?(?:voce )?(?:ja )?(?:andou )?(?:pesquis(?:ou|ando)|aprendeu|leu|viu|achou|descobriu)\b.*\b(?:internet|web|rede)\b"
    r"|\bo que (?:e que )?(?:voce )?(?:ja )?(?:andou )?pesquis(?:ou|ando)\b"
    r"|\b(?:quais|que) (?:assuntos|pesquisas)\b.*\bpesquis\w+")
_CABECA = re.compile(r"^(?:(?:o que (?:e|sao|foi|significa)|quem (?:e|foi|sao|foram)|sobre|a respeito de) )?(?:(?:o|a|os|as|um|uma) )?")
_CAUDA = re.compile(rf" (?:{_NA_REDE}|no google)$")
_ABRIR = re.compile(r"^(?:pode |por favor |me )?(?:abr[aei]\w*|mostr[ae]\w*)\b")
_LER = re.compile(r"^(?:pode |por favor )?(?:le|leia|ler|lei|estud\w+|aprend\w+|resum\w+|olh\w+|ve|veja|pesquis\w+|acess\w+|entr[ae]\w*|visit\w+)\b")


def _palavras(texto: str) -> list[str]:
    """As palavras do texto como você escreveu (com acento), na mesma contagem de ``_limpo``."""
    palavras = re.sub(r"[^\w\s]", " ", texto).split()
    return palavras[1:] if palavras and normalizar(palavras[0]) == "kernel" else palavras


def internet(texto: str) -> tuple[str, str] | None:
    """Pedidos para a internet: ("pesquisar", assunto), ("ler", endereço), ("abrir", endereço ou "fonte"),
    ("relato", "") ou None."""
    plano = _limpo(texto)
    endereco = _ENDERECO.search(texto)
    if endereco:
        url = endereco.group(0).rstrip(".,;:!?)\"'")
        if not url.lower().startswith("http"):
            url = "https://" + url
        resto = _limpo(texto.replace(endereco.group(0), " "))
        if _ABRIR.match(plano):
            return "abrir", url
        if _LER.match(plano) or len(resto.split()) <= 2:   # "lê esta página: ..." ou só o endereço
            return "ler", url
        return None
    if re.match(r"^(?:pode |por favor |me )?(?:abr[aei]\w*|mostr[ae]\w*) (?:a |as |essa |esta )?(?:fonte|fontes|pagina da pesquisa|pagina que voce leu)$", plano):
        return "abrir", "fonte"
    if _RELATO_DA_REDE.search(plano):
        return "relato", ""
    achado = _PESQUISAR.match(plano)
    if not achado:
        return None
    grupo = next(nome for nome in ("fim", "fim2", "meio") if achado.group(nome))
    assunto = achado.group(grupo)
    if _NAO_E_DA_REDE.match(assunto):     # "pesquisa na memória...", "procura nos arquivos...": não é com a internet
        return None
    # Do pedido fica só o assunto: saem "o que é", o artigo do começo e o "na internet" do fim.
    cabeca = len(_CABECA.match(assunto).group(0).split())
    sobra = _CAUDA.search(assunto)
    cauda = len(sobra.group(0).split()) if sobra else 0
    quantas = len(assunto.split())
    if quantas - cabeca - cauda < 1:
        return None
    comeco = len(plano[:achado.start(grupo)].split())
    originais = _palavras(texto)
    palavras = originais if len(originais) == len(plano.split()) else plano.split()   # como você escreveu, com acentos
    return "pesquisar", " ".join(palavras[comeco + cabeca:comeco + quantas - cauda])
