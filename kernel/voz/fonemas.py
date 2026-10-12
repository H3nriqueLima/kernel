"""Do texto aos fonemas: as regras de pronúncia do português do Brasil.

O português se lê quase como se escreve, então dá para converter letra em som
com regras (sem dicionário). O caminho de uma frase:

1. ``preparar``: números viram palavras ("15%" -> "quinze por cento"), caminhos
   de arquivo e símbolos somem, a pontuação vira pausa.
2. Em cada palavra, achar a sílaba tônica (acento gráfico, ou a regra das
   terminações: "casa" é paroxítona, "Brasil" é oxítona).
3. ``palavra_para_fonemas``: letra a letra, olhando os vizinhos ("c" antes de
   "e" é /s/; "s" entre vogais é /z/; "ti" vira "tchi"; "l" no fim vira "u").

Os símbolos dos fonemas:

    vogais   a  A(a fraco)  E(é)  e(ê)  i  O(ó)  o(ô)  u    nasais: an en in on un
    semiv.   j (i curto)   w (u curto)
    consoa.  p b t d k g   f v s z   S(ch) Z(j)   tS dZ   m n N(nh)   l L(lh)   r(tepe) R(rr)
             mc nc (nasal curtinha que fecha uma vogal nasal: caMpo, aNtes)
    pausas   ,  .  ?

Uma vogal tônica vem marcada com um apóstrofo na frente: ``'a``.
"""
from __future__ import annotations

import re

VOGAIS = "aáàâãeéêiíoóôõuúü"
# O "r" que fecha a sílaba (porta, falar): "R" = aspirado, à carioca; "r" = tepe, à paulista.
# No teste contra a voz de referência o aspirado foi reconhecido melhor (50 de 61 palavras, contra 47).
R_NO_FIM_DA_SILABA = "R"
_AGUDAS = {"á": "a", "é": "E", "í": "i", "ó": "O", "ú": "u", "â": "a", "ê": "e", "ô": "o", "à": "a"}
_SEM_ACENTO = {"á": "a", "à": "a", "â": "a", "ã": "a", "é": "e", "ê": "e", "í": "i", "ó": "o", "ô": "o",
               "õ": "o", "ú": "u", "ü": "u"}
_NASAL = {"a": "an", "e": "en", "i": "in", "o": "on", "u": "un"}
_OCLUSIVAS = {"p", "b", "t", "d", "k", "g", "f"}
_SONORAS = set("bdgvzjmnlr")

# Palavrinhas sem acento próprio: grudam na palavra seguinte e têm vogal fraca.
_ATONAS = {
    "o": "u", "a": "A", "os": "u s", "as": "A s", "e": "i", "de": "dZ i", "do": "d u", "da": "d A",
    "dos": "d u s", "das": "d A s", "em": "en jn", "no": "n u", "na": "n A", "nos": "n u s", "nas": "n A s",
    "que": "k i", "se": "s i", "me": "m i", "te": "tS i", "lhe": "L i", "por": "p u r", "com": "k on",
    "para": "p a r A", "pra": "p r A", "pro": "p r u", "um": "un", "ao": "a w", "ou": "o w", "mas": "m a s",
}
# Palavras que fogem das regras (estrangeiras ou irregulares). ' marca a tônica.
_EXCECOES = {
    "kernel": "k 'E r n e w", "muito": "m 'un jn t u", "muita": "m 'un jn t A", "muitos": "m 'un jn t u s",
    "wikipedia": "w i k i p 'E dZ i A", "wikipédia": "w i k i p 'E dZ i A", "internet": "in t e r n 'E tS i",
    "windows": "w 'in d o w s", "download": "d a w n l 'o w dZ i", "downloads": "d a w n l 'o w dZ i s",
    "backup": "b E k 'a p i", "software": "s O f tS i w 'E r", "hardware": "R a r dZ i w 'E r",
    "pc": "p e s 'e", "pdf": "p e d e 'E f i", "ok": "o k 'e j", "wifi": "w a j f 'a j",
    "ela": "'E l A", "elas": "'E l A s", "esta": "'E s t A", "essa": "'E s A", "é": "'E", "nós": "n 'O s",
    "ele": "'e l i", "eles": "'e l i s", "quer": "k 'E r", "mulher": "m u L 'E r", "dez": "d 'E j s",
    "sete": "s 'E tS i", "certo": "s 'E r t u", "perto": "p 'E r t u", "aberto": "a b 'E r t u",
    "hoje": "'o Z i", "você": "v o s 'e", "não": "n 'an wn", "sim": "s 'in", "são": "s 'an wn",
    "seu": "s 'e w", "meu": "m 'e w", "eu": "'e w", "sou": "s 'o w", "vou": "v 'o w", "tem": "t 'en jn",
    "bem": "b 'en jn", "sem": "s 'en jn", "quem": "k 'en jn", "nem": "n 'en jn",
    "gb": "Z 'i g A s", "mb": "m 'E g A s", "kb": "k 'i l o s", "ram": "R 'an", "hd": "a g a d 'e",
}
_X_COMO_KS = ("taxi", "táxi", "fixo", "fixa", "sexo", "toxic", "tóxic", "boxe", "complex", "anex", "oxig",
              "nexo", "reflex", "fluxo", "torax", "tórax", "index", "latex", "látex")
_X_COMO_S = ("proxim", "próxim", "maxim", "máxim", "auxil", "trouxe", "sintax", "experi", "expli", "extra",
             "exte", "expo", "expr", "exce", "text", "sext", "context")
_QU_COM_U = ("cinquenta", "tranquil", "frequen", "consequen", "eloquen", "delinquen", "sequestr", "aguent",
             "linguic", "linguiç", "pinguim", "bilingue", "equestre")

# ------------------------------------------------------------- números por extenso
_UNIDADES = "zero um dois três quatro cinco seis sete oito nove dez onze doze treze quatorze quinze " \
            "dezesseis dezessete dezoito dezenove".split()
_DEZENAS = ", , vinte trinta quarenta cinquenta sessenta setenta oitenta noventa".split()
_CENTENAS = ", cento duzentos trezentos quatrocentos quinhentos seiscentos setecentos oitocentos novecentos".split()


def por_extenso(n: int) -> str:
    """ 1249 -> "mil duzentos e quarenta e nove" """
    if n < 0:
        return "menos " + por_extenso(-n)
    if n < 20:
        return _UNIDADES[n]
    if n < 100:
        dezena, resto = divmod(n, 10)
        return _DEZENAS[dezena] + (f" e {_UNIDADES[resto]}" if resto else "")
    if n == 100:
        return "cem"
    if n < 1000:
        centena, resto = divmod(n, 100)
        return _CENTENAS[centena] + (f" e {por_extenso(resto)}" if resto else "")
    if n < 1_000_000:
        milhar, resto = divmod(n, 1000)
        comeco = "mil" if milhar == 1 else f"{por_extenso(milhar)} mil"
        if not resto:
            return comeco
        liga = " e " if resto < 100 or resto % 100 == 0 else " "
        return comeco + liga + por_extenso(resto)
    if n < 1_000_000_000_000:
        milhoes, resto = divmod(n, 1_000_000)
        if milhoes >= 1000:
            bilhoes, milhoes = divmod(milhoes, 1000)
            comeco = ("um bilhão" if bilhoes == 1 else f"{por_extenso(bilhoes)} bilhões")
            comeco += f" {por_extenso(milhoes)} milhões" if milhoes else ""
        else:
            comeco = "um milhão" if milhoes == 1 else f"{por_extenso(milhoes)} milhões"
        return comeco + (f" {por_extenso(resto)}" if resto else "")
    return " ".join(_UNIDADES[int(d)] for d in str(n))


def _numero(achado: re.Match) -> str:
    inteiro = achado.group(1).replace(".", "")
    decimal = achado.group(2)
    texto = por_extenso(int(inteiro))
    if decimal:
        texto += " vírgula " + (por_extenso(int(decimal)) if len(decimal) <= 2 and decimal[0] != "0"
                                else " ".join(_UNIDADES[int(d)] for d in decimal))
    return f" {texto} "


def preparar(texto: str) -> str:
    """Deixa o texto do jeito que se fala: sem caminhos, com números e símbolos por extenso."""
    t = texto
    t = re.sub(r"[A-Za-z]:\\[^\s\"]*(?: [^\s\"\\]+\\[^\s\"]*)*", " ", t)      # C:\caminhos\de arquivo
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"\((?:[^()]{0,60})\)", " ", t)                                 # (apartes curtos)
    t = t.replace("K.E.R.N.E.L", "Kernel").replace("•", ". ").replace("—", ", ").replace("\n", ". ")
    t = re.sub(r"(\d{1,2}):(\d{2})\b", lambda m: f" {por_extenso(int(m.group(1)))} e "
                                                 f"{por_extenso(int(m.group(2)))} " if int(m.group(2))
               else f" {por_extenso(int(m.group(1)))} horas ", t)              # 14:32
    t = re.sub(r"(\d{1,2})/(\d{1,2})/(\d{4})", lambda m: f" {por_extenso(int(m.group(1)))} do "
                                                         f"{por_extenso(int(m.group(2)))} de "
                                                         f"{por_extenso(int(m.group(3)))} ", t)
    t = re.sub(r"(\d{1,2})/(\d{1,2})\b", lambda m: f" {por_extenso(int(m.group(1)))} do "
                                                   f"{por_extenso(int(m.group(2)))} ", t)
    t = t.replace("%", " por cento ").replace("R$", " reais ").replace("&", " e ").replace("+", " mais ")
    t = t.replace("=", " igual a ").replace("×", " vezes ").replace("_", " ").replace("/", " ")
    t = re.sub(r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?", _numero, t)
    t = re.sub(r"[\"'“”‘’()\[\]{}<>*#|\\]", " ", t)
    t = re.sub(r"\s*[;:]\s*", ", ", t)
    t = re.sub(r"\s*\.\.\.+\s*|…", ". ", t)
    return " ".join(t.split())


# ------------------------------------------------------------------ uma palavra
def _nucleos(p: str) -> list[int]:
    """As posições das letras que são núcleo de sílaba (vogais que não são semivogal nem mudas)."""
    nucleos = []
    for i, letra in enumerate(p):
        if letra not in VOGAIS:
            continue
        antes = p[i - 1] if i else ""
        depois = p[i + 1] if i + 1 < len(p) else ""
        if letra in "uü" and antes in "qg" and depois in VOGAIS and depois:
            continue  # o "u" de "que", "gui", "quando"
        if letra in "oe" and antes in "ãõ" and antes:
            continue  # ditongos nasais: pão, mãe, põe
        if letra in "iu" and antes in VOGAIS and antes and not (antes in "uü" and i >= 2 and p[i - 2] in "qg"):
            # depois de vogal, "i" e "u" são semivogais (pai, céu)... menos em hiatos: ra-i-nha, ju-iz, sa-ir
            resto = p[i + 1:]
            hiato = resto.startswith("nh") or (resto != "" and resto[0] in "lrzmn" and not resto.startswith("rr")
                                               and (len(resto) == 1 or resto[1] not in VOGAIS))
            if not hiato:
                continue
        nucleos.append(i)
    return nucleos


def _tonica(p: str, nucleos: list[int]) -> int:
    """A posição (na palavra) da vogal tônica."""
    for i in nucleos:
        if p[i] in "áéíóúâêô":
            return i
    for i in reversed(nucleos):
        if p[i] in "ãõ":
            return i
    if len(nucleos) == 1:
        return nucleos[0]
    base = p[:-1] if p.endswith("s") else p
    paroxitona = base.endswith(("a", "e", "o", "am", "em", "en"))
    return nucleos[-2] if paroxitona else nucleos[-1]


def palavra_para_fonemas(palavra: str) -> list[str]:
    p = palavra.lower()
    if p in _EXCECOES:
        return _EXCECOES[p].split()
    if p in _ATONAS:
        return _ATONAS[p].split()
    nucleos = _nucleos(p)
    if not nucleos:  # sigla ou consoante solta: soletra
        return [f for letra in p for f in _SOLETRAR.get(letra, "").split()]
    tonica = _tonica(p, nucleos)
    ultimo_nucleo = nucleos[-1]
    saida: list[str] = []
    n = len(p)
    i = 0

    def letra(k: int) -> str:
        return p[k] if 0 <= k < n else ""

    def eh_vogal(k: int) -> bool:
        return letra(k) in VOGAIS and letra(k) != ""

    def som_de_i(k: int) -> bool:
        """A letra na posição k soa como /i/? (i, ou "e" final átono: leite -> leitchi)"""
        if letra(k) in "ií":
            return True
        final = k == n - 1 or (k == n - 2 and letra(n - 1) == "s")
        return letra(k) == "e" and final and k != tonica

    while i < n:
        c, prox, ant = p[i], letra(i + 1), letra(i - 1)
        # ------------------------------------------------------------ vogais
        if c in VOGAIS:
            if c in "uü" and ant in "qg" and eh_vogal(i + 1):
                if c == "ü" or prox in "aáãoóô" or any(r in p for r in _QU_COM_U):
                    saida.append("w")
                i += 1
                continue
            base = _SEM_ACENTO.get(c, c)
            if i not in nucleos:  # semivogal
                nasal = bool(saida) and saida[-1].lstrip("'") in _NASAL.values()
                saida.append(("jn" if nasal else "j") if base in "ie" else ("wn" if nasal else "w"))
                i += 1
                continue
            acentuada = i == tonica
            final = i == ultimo_nucleo and (i == n - 1 or (i == n - 2 and letra(n - 1) == "s"))
            # nasal: til, ou vogal + m/n no fim da sílaba (campo, bom, antes)
            fecha_com_nasal = prox in "mn" and prox and not eh_vogal(i + 2) and not (prox == "n" and letra(i + 2) == "h")
            if c in "ãõ" or fecha_com_nasal:
                som = _NASAL[base]
                saida.append(("'" if acentuada else "") + som)
                if fecha_com_nasal:
                    i += 1  # o m/n só nasaliza; não é pronunciado
                    if i == n - 1 or (i == n - 2 and letra(n - 1) == "s"):  # falam, bem, homens
                        if base == "a":
                            saida.append("wn")
                        elif base == "e":
                            saida.append("jn")
                i += 1
                continue
            if c in _AGUDAS:
                som = _AGUDAS[c]
            elif base == "a":
                som = "A" if (final and not acentuada) or (prox in "mn" and prox and acentuada) else "a"
            elif base == "e":
                if final and not acentuada:
                    som = "i"
                elif acentuada and prox == "l" and not eh_vogal(i + 2):
                    som = "E"  # papel, hotel, mel
                else:
                    som = "e"
            elif base == "o":
                if final and not acentuada:
                    som = "u"
                elif acentuada and prox == "l" and not eh_vogal(i + 2):
                    som = "O"  # sol, futebol
                else:
                    som = "o"
            else:
                som = base
            saida.append(("'" if acentuada else "") + som)
            i += 1
            continue
        # --------------------------------------------------------- consoantes
        dois = c + prox
        if dois == "ch":
            saida.append("S"); i += 2
        elif dois == "lh":
            saida.append("L"); i += 2
        elif dois == "nh":
            saida.append("N"); i += 2
        elif dois == "rr":
            saida.append("R"); i += 2
        elif dois == "ss":
            saida.append("s"); i += 2
        elif dois in ("sc", "xc") and letra(i + 2) in "eéêií":
            saida.append("s"); i += 2
        elif dois == "sç":
            saida.append("s"); i += 2
        elif c == "ç":
            saida.append("s"); i += 1
        elif c == "c":
            saida.append("s" if prox in "eéêií" and prox else "k"); i += 1
        elif c == "g":
            saida.append("Z" if prox in "eéêií" and prox else "g"); i += 1
        elif c == "q":
            saida.append("k"); i += 1
        elif c == "h":
            i += 1
        elif c == "j":
            saida.append("Z"); i += 1
        elif c == "t":
            saida.append("tS" if som_de_i(i + 1) else "t"); i += 1
        elif c == "d":
            saida.append("dZ" if som_de_i(i + 1) else "d"); i += 1
        elif c == "s":
            if eh_vogal(i - 1) and eh_vogal(i + 1):
                saida.append("z")
            elif prox in _SONORAS and prox:
                saida.append("z")
            else:
                saida.append("s")
            i += 1
        elif c == "z":
            saida.append("s" if i == n - 1 else "z"); i += 1
        elif c == "x":
            if i == 0:
                saida.append("S")
            elif any(r in p for r in _X_COMO_KS) or i == n - 1:
                saida += ["k", "s"]
            elif any(r in p for r in _X_COMO_S) or not eh_vogal(i + 1):
                saida.append("s")
            elif p.startswith("ex") and i == 1:
                saida.append("z")  # exame, exemplo, existir
            else:
                saida.append("S")  # caixa, lixo, peixe
            i += 1
        elif c == "r":
            if i == 0 or ant in "nls":
                saida.append("R")                      # rato, honra
            elif eh_vogal(i + 1):
                saida.append("r")                      # caro, prato
            else:
                saida.append(R_NO_FIM_DA_SILABA)       # porta, falar
            i += 1
        elif c == "l":
            saida.append("l" if eh_vogal(i + 1) else "w"); i += 1  # "l" no fim da sílaba vira "u": Brasil
        elif c == "m":
            saida.append("m"); i += 1
        elif c == "n":
            saida.append("n"); i += 1
        elif c in "bpfvk":
            saida.append(c); i += 1
        elif c == "w":
            saida.append("w"); i += 1
        elif c == "y":
            saida.append("j" if eh_vogal(i - 1) or eh_vogal(i + 1) else "i"); i += 1
        else:
            i += 1  # hífen, apóstrofo e o que mais aparecer

    # No Brasil, consoante "muda" ganha um i: advogado -> adjivogado, ritmo -> ritchimo, internet -> internétchi
    completa: list[str] = []
    for k, som in enumerate(saida):
        completa.append(som)
        seguinte = saida[k + 1].lstrip("'") if k + 1 < len(saida) else ""
        if som.lstrip("'") in _NASAL.values() and seguinte in _PEDE_NASAL:
            completa.append(_PEDE_NASAL[seguinte])  # campo, antes: a vogal nasal fecha numa nasal curtinha
        if som in _OCLUSIVAS and (seguinte == "" or (seguinte not in _VOCALICOS and seguinte not in ("r", "l"))):
            if som == "t":
                completa[-1] = "tS"
            elif som == "d":
                completa[-1] = "dZ"
            completa.append("i")
    return completa


# antes de uma oclusiva, a vogal nasal termina numa consoante nasal breve feita no mesmo lugar da boca
_PEDE_NASAL = {"p": "mc", "b": "mc", "t": "nc", "d": "nc", "tS": "nc", "dZ": "nc", "k": "nc", "g": "nc"}
_VOCALICOS = {"a", "A", "E", "e", "i", "O", "o", "u", "an", "en", "in", "on", "un", "j", "w", "jn", "wn"}
_SOLETRAR = {
    "a": "'a", "b": "b 'e", "c": "s 'e", "d": "d 'e", "e": "'e", "f": "'E f i", "g": "Z 'e", "h": "a g 'a",
    "i": "'i", "j": "Z 'O t A", "k": "k 'a", "l": "'E l i", "m": "'e m i", "n": "'e n i", "o": "'O",
    "p": "p 'e", "q": "k 'e", "r": "'E R i", "s": "'E s i", "t": "t 'e", "u": "'u", "v": "v 'e",
    "w": "d 'a b l i w", "x": "S 'i s", "y": "'i p s i l on", "z": "z 'e",
}
_PALAVRA = re.compile(r"[a-záàâãéêíóôõúüç]+(?:-[a-záàâãéêíóôõúüç]+)*", re.I)


def texto_para_fonemas(texto: str) -> list[str]:
    """A frase inteira: fonemas das palavras, com "," "." e "?" marcando as pausas."""
    saida: list[str] = []
    for pedaco in re.findall(r"[^\s,.!?]+|[,.!?]", preparar(texto)):
        if pedaco in ",.!?":
            pausa = "," if pedaco == "," else "?" if pedaco == "?" else "."
            if saida and saida[-1] not in ",.?":
                saida.append(pausa)
            continue
        for palavra in _PALAVRA.findall(pedaco):
            for parte in palavra.split("-"):
                saida += palavra_para_fonemas(parte)
    if saida and saida[-1] not in ".?":
        saida.append(".")
    return saida
