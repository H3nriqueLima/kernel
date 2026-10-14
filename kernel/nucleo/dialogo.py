"""Diálogo: entender o jeito de falar quando o classificador não sabe o que fazer.

O classificador de comandos conhece dez intenções. O que não se parece com
nenhuma cai em "conversa", e antes isso queria dizer "guardei na memória",
mesmo para "fale mais", "quais as suas funções?" ou uma pergunta que ele nunca
viu. As funções daqui olham a frase com regras curtas e dizem o que ela é:

- uma pergunta (aí ele procura no que estudou e na internet);
- um pedido para continuar o assunto ("fale mais", "explica melhor");
- uma pergunta sobre ele mesmo (ver ``sobre_si.py``);
- um pedido para explorar agora;
- um texto para o cérebro completar ("completa: era uma vez");
- a resposta a uma pergunta que ele fez.

Nada aqui usa modelo: são expressões regulares que dá para ler e consertar.
"""
from __future__ import annotations

import re

from ..memoria.texto import normalizar

DESISTENCIAS = {"nao sei", "deixa", "deixa pra la", "esquece", "nada", "depois", "nao importa", "pula", "sei la"}
_INTERROGA = re.compile(
    r"^(?:e |mas |entao |kernel |me diz |me diga |me fala |me explica |explica |explique |sabe |voce sabe |sabe me dizer |"
    r"sabe dizer )*(?:qual|quais|quanto|quanta|quantos|quantas|quando|onde|aonde|como|por que|porque|pra que|para que|"
    r"quem|o que|oque|que|cade|existe|existem|tem como|da para|da pra|e possivel|sera que|defina|significado)\b")
_MAIS = re.compile(
    r"^(?:pode |por favor |entao |e |me )*(?:(?:fal[ae]|cont[ae]|dig[ao]|explic\w+|detalh\w+|desenvolv\w+|aprofund\w+|"
    r"continu\w+|prossig\w+|segu[ei]\w*)(?: um pouco| ai| me| pra mim)*(?: mais| melhor| direito| algo| alguma coisa)*"
    r"(?: longo| longa| detalhes| detalhado| a fundo)?|mais detalhes|e o que mais|que mais|mais|e ai|o que mais)"
    r"(?: (?:sobre|d[aeo]s?|acerca de|a respeito de) (?P<assunto>.+))?$")
_LONGO = re.compile(r"\b(?:long[oa]|detalh\w+|a fundo|complet[oa]|tudo)\b")
_EXPLORAR = re.compile(
    r"^(?:pode |por favor |vai |va |comeca a |comece a )*(?:explor\w+|vasculh\w+|fu[cç]\w+|olh[ae]\w*|varr\w+|mape\w+)"
    r"(?: agora| ja| ai)?(?: (?:o|a|os|as|meu|minha|meus|minhas|esse|este|todo o|toda a))?"
    r"(?: (?:pc|computador|maquina|disco|hd|pastas?|arquivos?|documentos|tudo))?(?: agora| ja| inteiro| todo| tod[oa]s)?$")
_COMPLETAR = re.compile(
    r"^\s*(?:kernel[,:]?\s+)?(?:complet[ae]r?|continu[ae]r?(?: a frase| o texto)?|cerebro)\s*[:,]\s*(?P<texto>.+)$", re.I | re.S)
_O_QUE_ACHA = re.compile(
    r"^(?:o que |oque )?(?:o )?(?:seu |teu )?cerebro (?:diz|acha|pensa|fala|escreve|sabe)(?: (?:sobre|de|do|da|a respeito de))? (?P<texto>.+)$")
_APRENDEU_SOBRE = re.compile(
    r"^(?:e )?o que (?:e que )?(?:voce )?(?:ja )?(?:aprendeu|estudou|pesquisou|leu|descobriu)(?: na internet)? "
    r"(?:sobre|de|a respeito de|acerca de) (?:o |a |os |as )?(?P<assunto>.+)$")
_ABRE_RESPOSTA = re.compile(r"^(?:e|sao|foi|era|eram|trata|significa|quer dizer|um|uma|o|a|os|as|meu|minha|nosso|nossa|"
                            r"ele|ela|isso|esse|essa|sim|nao|ninguem|nenhum)\b")


def _limpo(texto: str) -> str:
    plano = re.sub(r"[^\w\s]", " ", normalizar(texto))
    return re.sub(r"^kernel\s+", "", " ".join(plano.split()))


def eh_pergunta(texto: str) -> bool:
    """A frase pergunta alguma coisa? (Termina em "?" ou começa como pergunta.)"""
    return texto.rstrip().endswith("?") or bool(_INTERROGA.match(_limpo(texto)))


def pede_mais(texto: str) -> tuple[int, str] | None:
    """ "fale mais" -> (3, ""); "explica em detalhes" -> (6, ""); "fale mais sobre o sol" -> (3, "sol")."""
    plano = _limpo(texto)
    achado = _MAIS.match(plano)
    if not achado:
        return None
    assunto = re.sub(r"^(?:o|a|os|as|um|uma|isso|isto|esse assunto|ele|ela)\b ?", "", achado.group("assunto") or "").strip()
    return (6 if _LONGO.search(plano) else 3), assunto


def explorar_agora(texto: str) -> bool:
    """ "explore o computador", "vasculha as pastas", "explora agora"."""
    return bool(_EXPLORAR.match(_limpo(texto)))


def para_o_cerebro(texto: str) -> str | None:
    """O texto que você quer que o cérebro complete: "completa: era uma vez" -> "era uma vez"."""
    achado = _COMPLETAR.match(texto)
    if achado:
        return achado.group("texto").strip()
    achado = _O_QUE_ACHA.match(_limpo(texto))
    if achado:   # "o que seu cérebro diz sobre o Brasil" -> ele completa "O Brasil é"
        assunto = achado.group("texto").strip()
        return assunto[:1].upper() + assunto[1:] + " é"
    return None


def aprendeu_sobre(texto: str) -> str | None:
    """ "o que você aprendeu sobre redes neurais?" -> "redes neurais"."""
    achado = _APRENDEU_SOBRE.match(_limpo(texto))
    return achado.group("assunto").strip() if achado else None


def parece_resposta(texto: str, termo: str) -> bool:
    """Ele perguntou "o que é ``termo``?". Esta fala responde, ou você mudou de assunto?

    Vale como resposta se cita o termo, se começa como quem define ("é a contadora...",
    "uma cliente antiga") ou se é uma desistência ("não sei", "deixa"). Uma pergunta sua
    ou um pedido qualquer não é resposta, e a dúvida dele continua aberta.
    """
    plano = _limpo(texto)
    if plano in DESISTENCIAS:
        return True
    if texto.rstrip().endswith("?"):
        return False
    return _limpo(termo) in plano or bool(_ABRE_RESPOSTA.match(plano))


def sem_letra_repetida(plano: str) -> str:
    """ "oiii" -> "oi", "olaaa" -> "ola", "bom diaaa" -> "bom dia" (só no fim das palavras)."""
    return re.sub(r"(\w)\1+\b", r"\1", plano)
