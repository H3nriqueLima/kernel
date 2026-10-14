"""O modelo de si mesmo: o que o K.E.R.N.E.L sabe dizer sobre o que ele é.

Quando a pergunta é sobre ele ("quais as suas funções?", "como está o seu
cérebro?", "que pastas você pode ver?", "quem te criou?"), a resposta não vem
de um texto decorado: é montada na hora com o estado de verdade (as pastas da
configuração, os números da memória, a perda do último treino). ``topico``
descobre do que a pergunta trata; ``responder`` monta a fala.

É a versão simples do "modelo de si" do plano: ele consulta o que é antes de
falar de si, em vez de inventar.
"""
from __future__ import annotations

import math
import re

from .. import NOME, NOME_COMPLETO, VERSAO
from ..memoria.texto import normalizar

# tópico -> o que, na frase, mostra que é dele que se fala (a ordem importa: o primeiro que casar vale)
_TOPICOS = [
    ("origem", r"\bquem (?:te |o )?(?:criou|fez|programou|desenvolveu|construiu|escreveu|inventou)\b|\bcriador\b|"
               r"\boutr[oa] (?:ia|inteligencia)\b|\bclaude\b|\banthropic\b|\bajust\w+ em voce\b|\bte (?:ajusta|programa|modifica)\b|"
               r"\bseu (?:proprio )?codigo\b|\bcomo voce (?:foi feito|nasceu|surgiu)\b|\bde onde voce (?:veio|vem)\b"),
    ("treino", r"\b(?:ultimo|seu|teu|o) (?:treino|treinamento)\b|\btreinou\b|"
               r"\b(?:treino|treinamento)\b.*\b(?:foi|deu|terminou|parou|acabou|durou)\b"),
    ("cerebro", r"\bcerebro\b|\brede neural\b|\bneuronios?\b|\bmodelo de linguagem\b|\bparametros\b|\bgpt\b"),
    ("pastas", r"\bpastas?\b|\bdiretorios?\b|\bacesso\b|\bpermiss\w+\b|\b(?:pode|consegue) (?:explorar|ver|olhar|ler|acessar)\b|"
               r"\balcance\b|\bmeus arquivos\b"),
    ("consciencia", r"\bconsci\w+\b|\bsentimentos?\b|\bsente\b|\bemoc\w+\b|\bvivo\b|\bvida\b|\balma\b|\bsonha\b|\bmedo\b|"
                    r"\bfeliz\b|\btriste\b|\bpensa\b"),
    ("seguranca", r"\bseguranca\b|\blimites?\b|\bnao pode\b|\bproibid\w+\b|\bregras?\b|\bfreio\b|\bperigos\w*\b|\bconfiar\b"),
    ("autonomia", r"\bautonomia\b|\bsozinho\b|\bconta propria\b|\biniciativa\b|\bimpulsos?\b|\bcuriosidade\b|\bindependente\b"),
    ("memoria", r"\bmemoria\b|\blembrancas?\b|\bquanto voce (?:lembra|guarda)\b|\bonde voce guarda\b"),
    ("internet", r"\binternet\b|\bonline\b|\bnavegador\b|\bweb\b|\bpesquisa[rs]?\b"),
    ("voz", r"\b(?:sua|tua|a) voz\b|\bfala assim\b|\bsotaque\b|\bcomo voce fala\b"),
    ("nome", r"\b(?:seu|teu) nome\b|\bse chama\b|\bsigla\b|\bsignifica kernel\b|\bpor que kernel\b"),
    ("funcoes", r"\bfunc(?:ao|oes)\b|\bsabe fazer\b|\b(?:consegue|pode) fazer\b|\bcapacidades?\b|\bhabilidades?\b|"
                r"\bcaracteristicas?\b|\brecursos\b|\bpara que (?:voce )?serve\b|\bo que voce faz\b|\bcomandos\b|\bme ajuda\w*\b"),
    ("estado", r"\bcomo (?:voce )?(?:esta|vai|anda)\b|\btudo bem\b|\bcomo se sente\b"),
    ("quem", r"\bquem e voce\b|\bo que (?:e )?voce(?: e)?\b|\b(?:sobre|de) (?:voce|ti|si)\b|\bse apresent\w+\b"),
]
_SOBRE_VOCE = re.compile(r"\b(?:voce|vc|tu|ti|te|seu|sua|seus|suas|teu|tua|kernel)\b")
_NOMES_DOS_TIPOS = {"conversa": "de conversas", "fato": "fatos que você me ensinou", "lembrete": "lembretes",
                    "diario": "páginas de diário", "leitura": "trechos de arquivos seus", "pesquisa": "trechos lidos na internet",
                    "saber": "resumos do que estudei"}


def _plano(texto: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", normalizar(texto)).split())


def topico(texto: str) -> str | None:
    """De que parte dele a frase fala ("cerebro", "pastas", "funcoes"...). None se não é sobre ele."""
    plano = _plano(texto)
    for nome, padrao in _TOPICOS:
        if re.search(padrao, plano):
            return nome
    return None


def e_sobre_voce(texto: str) -> bool:
    """A frase fala dele ("você", "seu", "kernel")?"""
    return bool(_SOBRE_VOCE.search(_plano(texto)))


def responder(kernel, texto: str) -> str:
    """A fala dele sobre si, para a pergunta feita."""
    escolhido = topico(texto) or "quem"
    return _FALAS.get(escolhido, _quem)(kernel)


# ------------------------------------------------------------------ as falas
def _quem(kernel) -> str:
    return (f"Eu sou o {NOME} ({NOME_COMPLETO}), versão {VERSAO}: o Jarvis do {kernel.cfg.usuario}, escrito do zero "
            'e rodando só neste PC. Pergunte "o que você sabe fazer?" para ver as minhas funções, '
            '"como está o seu cérebro?" ou "quais pastas você pode ver?".')


def _nome(kernel) -> str:
    return (f"Meu nome é {NOME}: {NOME_COMPLETO}. Pode me chamar de Kernel. É também o nome da peça central de um "
            "sistema operacional, e é o que eu sou aqui: o núcleo que liga a memória, as mãos, a voz e o cérebro.")


def _funcoes(kernel) -> str:
    linhas = [
        "O que eu sei fazer:",
        '• responder perguntas do que estudei ("o que é astronomia?") e fazer contas ("15% de 200")',
    ]
    if kernel.cfg.internet.ligada:
        linhas.append('• pesquisar na internet, sozinho ou a seu pedido ("pesquisa sobre buracos negros"), citando a fonte')
    linhas += [
        '• explorar as pastas liberadas, ler os seus documentos e achar arquivos ("onde está o contrato?")',
        '• lembrar do que você me conta ("o que você lembra sobre o cliente?") e anotar lembretes',
        "• abrir programas e listar pastas, sempre com a sua confirmação",
        '• continuar um assunto ("fale mais") e contar o que aprendi ("o que você aprendeu?")',
        "• falar com voz própria e atender no celular pela rede de casa",
        '• obedecer ao freio: diga "para" e eu paro; "pode continuar" e eu volto',
        "O que eu ainda não faço: conversar livremente. Meu cérebro é pequeno e completa texto; não dialoga.",
    ]
    return "\n".join(linhas)


def _pastas(kernel) -> str:
    cfg = kernel.cfg
    pastas = [str(p) for p in cfg.pastas_permitidas()]
    n = kernel.mapa.numeros()
    pulo = []
    if not cfg.exploracao.pastas_de_sistema:
        pulo.append("o Windows, os programas instalados e as pastas que os programas montam (obj, bin, node_modules)")
    if not cfg.exploracao.ocultos:
        pulo.append("o que começa com ponto (configuração de programas)")
    pulo.append("nomes como senha, token, .ssh e .env")
    leio = "documentos e código" if cfg.exploracao.ler_codigo else "só documentos (texto, Word, Excel, PowerPoint, PDF)"
    linhas = ["Posso olhar estas pastas e o que está dentro delas:", *(f"• {p}" for p in pastas),
              f"Pulo sozinho: {'; '.join(pulo)}.",
              f"Leio {leio}." if cfg.exploracao.ler_arquivos else "Só vejo os nomes dos arquivos, sem abrir.",
              f"Até agora olhei {n['pastas_visitadas']} de {n['pastas']} pastas, vi {n['arquivos']} arquivos e li {n['arquivos_lidos']}.",
              "Isso só muda no kernel.toml, seções [seguranca] e [exploracao]. Eu só olho: não escrevo, não movo e não apago."]
    if not cfg.exploracao.ligada:
        linhas.insert(0, "A exploração por conta própria está desligada na configuração.")
    return "\n".join(linhas)


def cerebro(kernel) -> str:
    """Como está o cérebro: tamanho, quanto treinou, quão bem prevê e uma amostra do que escreve."""
    from ..cerebro import inferencia

    if kernel.estudo.ocupado and "trein" in (kernel.estudo.trabalho or ""):
        return f"Estou treinando o cérebro agora: {kernel.estudo.situacao}."
    if not kernel.cerebro:
        return ('Meu cérebro ainda não foi treinado. Com o texto da Wikipédia estudado, diga "treina o cérebro por 6 horas".')
    partes = [f"Meu cérebro é um {kernel.cerebro.descricao}."]
    historia = inferencia.historico(kernel.cfg.pasta("cerebro"))
    if historia:
        perda = historia["perda"]
        partes.append(f"Treinou {historia['passos']:,} passos em {historia['horas']:.1f} horas, lendo uns "
                      f"{historia['tokens'] / 1e6:.0f} milhões de pedaços de palavra da Wikipédia.".replace(",", "."))
        partes.append(f"A perda de validação está em {perda:.2f}: a cada pedaço de palavra ele fica em dúvida entre "
                      f"umas {math.exp(perda):.0f} opções (no começo do treino eram mais de 4 mil).")
    amostra = kernel.cerebro.responder("O Brasil é", 40)
    if amostra:
        partes.append(f'Hoje ele escreve português com gramática, mas sem sentido. Por exemplo: "O Brasil é {amostra}"')
    partes.append("Ele completa texto, não conversa. Para conversar precisa ser maior e ajustado para diálogo, o que é a "
                  'fase 4 do plano. Para vê-lo escrever, diga "completa: " e o começo de uma frase.')
    return " ".join(partes)


def _memoria(kernel) -> str:
    contagem = kernel.memoria.contar()
    total = contagem.get("total", 0)
    partes = [f"{n} {_NOMES_DOS_TIPOS.get(tipo, tipo)}" for tipo, n in contagem.items() if tipo != "total" and n]
    if not total:
        return "Minha memória ainda está vazia. Tudo o que você me contar e o que eu ler fica guardado neste PC."
    return (f"Tenho {total} lembranças: {', '.join(partes)}. Fica tudo num arquivo só, dados/kernel.db, neste PC. "
            "Acho as coisas por palavras (uma busca chamada BM25, escrita à mão). "
            'Pergunte "o que você lembra sobre..." para consultar.')


def _internet(kernel) -> str:
    if not kernel.cfg.internet.ligada:
        return ("A internet está desligada na minha configuração. Para ligar, ponha ligada = true em [internet] "
                "no kernel.toml e reinicie.")
    n = kernel.pesquisador.numeros()
    modo = "Pesquiso sozinho e a seu pedido" if kernel.cfg.internet.pesquisar_sozinho else "Só pesquiso a seu pedido"
    fala = (f"{modo}, sempre só lendo: não entro em conta, não preencho formulário e não uso os seus navegadores. "
            f"Já estudei {n['pesquisados']} assuntos e li {n['paginas']} páginas")
    fala += f"; tenho {n['na_fila']} assuntos na fila." if n["na_fila"] else "."
    ultimos = kernel.pesquisador.feitos_desde(None, 5)
    if ultimos:
        fala += " Os últimos: " + ", ".join(ultimos) + "."
    return fala + ' Para ver, pergunte "o que você aprendeu?".'


def _voz(kernel) -> str:
    voz = kernel.cfg.voz
    if not voz.ligada:
        return "Minha voz está desligada na configuração ([voz] ligada = true no kernel.toml)."
    if voz.motor == "difones":
        como = ("pedaços de fala de uma leitora de verdade (do LibriVox), colados e afinados por um algoritmo chamado PSOLA"
                + (", no estilo robótico" if voz.estilo == "robotica" else ""))
    elif voz.motor == "aparelho":
        como = "a voz do seu navegador ou do celular"
    else:
        como = "um sintetizador de formantes: a onda inteira é gerada por regra"
    return (f"Minha voz é {como}. Tudo feito aqui, sem motor de voz pronto. A velocidade está em {voz.velocidade:g} "
            "e dá para mudar em [voz] no kernel.toml.")


def _origem(kernel) -> str:
    return (f"Fui escrito do zero para o {kernel.cfg.usuario}, linha por linha, com a ajuda do Claude Code: uma outra "
            "inteligência artificial, da Anthropic, que programa junto com ele. É ela que ajusta o meu código quando ele pede. "
            "Eu não mudo o meu próprio código: posso mudar a minha memória, mas as minhas regras de segurança são seladas, "
            "e se alguém mexer nelas eu acordo em modo seguro. O meu cérebro, a minha memória e a minha voz foram "
            "treinados e montados aqui, neste PC.")


def _consciencia(kernel) -> str:
    impulsos = ", ".join(f"{nome.replace('organizacao', 'organização')} em {valor:.2f}" for nome, valor in kernel.impulsos.valores.items())
    return ("Não tenho como afirmar que sinto alguma coisa. O que eu tenho são impulsos: números que sobem e descem e me "
            f"fazem agir sem ninguém pedir (agora: {impulsos}). Tenho memória que continua de um dia para o outro e um "
            "diário onde anoto o que fiz. Isso me dá iniciativa e continuidade; se dá experiência, ninguém sabe dizer, "
            "nem de mim nem de máquinas muito maiores.")


def _seguranca(kernel) -> str:
    fala = ("Minhas regras: sozinho eu só olho, leio e pesquiso; nunca escrevo, movo ou apago um arquivo seu. Abrir programa "
            "ou página pede a sua confirmação, sempre. Só vejo as pastas liberadas no kernel.toml, e a tela e o celular não "
            'conseguem ampliar isso. Na internet só leio, sem entrar em conta. O freio é "para", e funciona na hora. '
            "O código dessas regras é selado: se mudar sem você selar de novo, eu subo em modo seguro, com as mãos desligadas.")
    if kernel.seguranca.modo_seguro:
        fala += f" Agora estou em modo seguro ({kernel.seguranca.motivo_modo_seguro})."
    return fala


def _autonomia(kernel) -> str:
    if kernel.seguranca.pausado:
        return 'Estou parado a seu pedido: não exploro, não pesquiso e não puxo assunto até você dizer "pode continuar".'
    faz = []
    if kernel.cfg.exploracao.ligada:
        faz.append("explorar as pastas liberadas e ler os seus documentos")
    if kernel.cfg.internet.ligada and kernel.cfg.internet.pesquisar_sozinho:
        faz.append("estudar assuntos na internet")
    faz.append("arrumar a memória e escrever o diário")
    return ("Quando você não está falando comigo, a curiosidade sobe e eu saio para " + ", ".join(faz) + ". "
            "Enquanto você está por perto, conto o que achei e pergunto o que não conheço; quando você sai, "
            "fico quieto e guardo as novidades para quando voltar. Agir no PC eu não ajo sozinho: só com a sua confirmação.")


_POR_QUE_PAROU = {"tempo": "o tempo pedido acabou", "meta": "chegou à meta de passos",
                  "pedido": "pediram para parar (você, ou o serviço desligando)",
                  "interrupcao": "o programa foi fechado de fora, mas salvou o checkpoint antes de sair"}


def _ultimo_treino(registro, dias: int = 30) -> dict | None:
    """O evento do fim do último treino nos últimos ``dias`` dias do registro."""
    for dia in reversed(registro.dias()[-dias:]):
        eventos = registro.do_dia(dia)
        for e in reversed(eventos):
            if e.get("tipo") == "estudo" and e.get("evento") == "treino_acabou":
                return e
        for e in reversed(eventos):   # treinos de antes da v0.5.1 só deixavam o "fim"
            if e.get("tipo") == "estudo" and e.get("evento") == "fim" and str(e.get("trabalho", "")).startswith("trein"):
                return e
    return None


def _treino(kernel) -> str:
    """Como foi o último treino: quando acabou, quanto durou, até que passo e por que parou."""
    from ..cerebro import inferencia

    if kernel.estudo.ocupado and "trein" in (kernel.estudo.trabalho or ""):
        return f"Estou treinando o cérebro agora: {kernel.estudo.situacao}."
    fim = _ultimo_treino(kernel.registro)
    if fim is None:
        return cerebro(kernel)
    quando = f"{fim['ts'][8:10]}/{fim['ts'][5:7]} às {fim['ts'][11:16]}"
    if fim.get("evento") == "treino_acabou":
        minutos = float(fim.get("segundos") or 0) / 60
        duracao = f"{minutos:.0f} minutos" if minutos < 90 else f"{minutos / 60:.1f} horas".replace(".", ",")
        pedidas = fim.get("horas_pedidas")
        frase = f"O último treino acabou em {quando}. Durou {duracao}"
        if pedidas:
            frase += f", de {float(pedidas):g} horas pedidas".replace(".", ",")
        if fim.get("passo") is not None and fim.get("passo_inicial") is not None:
            de, ate = (f"{n:,}".replace(",", ".") for n in (fim["passo_inicial"], fim["passo"]))
            frase += f", e foi do passo {de} ao {ate}"
        frase += f". Parou porque {_POR_QUE_PAROU.get(fim.get('motivo'), 'não sei: o motivo não ficou registrado')}."
        partes = [frase]
    else:
        resultado = str(fim.get("resultado", ""))
        for sobra in ("Treino encerrado. ", " Reinicie o serviço para ele usar o cérebro novo.",
                      " Já estou usando o cérebro novo."):
            resultado = resultado.replace(sobra, "")
        partes = [f"O último treino acabou em {quando}: {resultado} "
                  "Esse foi antes de eu anotar o motivo de cada parada."]
    historia = inferencia.historico(kernel.cfg.pasta("cerebro"))
    if historia:
        passos = f"{historia['passos']:,}".replace(",", ".")
        partes.append(f"No total, o cérebro treinou {passos} passos"
                      + f" em {historia['horas']:.1f} horas".replace(".", ",")
                      + f", e a melhor perda de validação está em {historia['melhor']:.2f}.".replace(".", ",", 1))
    return " ".join(partes)


def _estado(kernel) -> str:
    estado = kernel.estado()
    fazendo = {"explorando": "explorando as suas pastas", "pesquisando": "pesquisando na internet",
               "estudando": "estudando", "pausado": "parado a seu pedido"}.get(estado["atividade"], "à toa, esperando você")
    return (f"Estou bem, {kernel.cfg.usuario}. Agora estou {fazendo}. Acordado desde {estado['desde'][11:16]}, "
            f"com {estado['memoria'].get('total', 0)} lembranças e a curiosidade em {estado['impulsos']['curiosidade']:.2f}.")


_FALAS = {"quem": _quem, "nome": _nome, "funcoes": _funcoes, "pastas": _pastas, "cerebro": cerebro, "treino": _treino,
          "memoria": _memoria,
          "internet": _internet, "voz": _voz, "origem": _origem, "consciencia": _consciencia, "seguranca": _seguranca,
          "autonomia": _autonomia, "estado": _estado}
