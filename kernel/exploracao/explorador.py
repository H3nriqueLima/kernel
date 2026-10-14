"""O explorador: um passo de cada vez, sempre só olhando.

Cada passo é uma de duas coisas:

- **visitar uma pasta**: anotar no mapa os arquivos e as subpastas que há nela;
- **ler um arquivo**: tirar o texto, guardar trechos na memória (tipo ``leitura``)
  e anotar de que assunto ele trata.

Antes de qualquer passo ele pergunta à segurança (``pode_explorar`` e
``pode_ler``), e todo passo vai para o registro. Não existe aqui nenhuma função
que escreva, mova ou apague arquivos seus.

Ele explora com critério. Mesmo que você libere um disco inteiro, ele não perde
tempo com o que não é seu: pula o Windows, os programas instalados e as pastas
que os programas montam; só lê documentos (código e configuração entram no mapa
pelo nome); e só guarda na memória o que é prosa em português ou inglês. Tudo
isso se muda em ``[exploracao]`` no kernel.toml.
"""
from __future__ import annotations

import os
import re
import stat
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from ..memoria.texto import PARADAS, normalizar, termos
from . import leitores

ITENS_POR_PASTA = 3000
ITENS_ENTRE_OLHADAS = 64   # no meio de uma pasta grande, de quantos em quantos itens ele confere se é para largar
# Muda quando mudam as regras do que vale ler e guardar: aí ele esquece as leituras antigas e relê
# o que continua ao alcance (o mapa de arquivos fica; só o que foi tirado de dentro deles é refeito).
REGRAS_DE_LEITURA = 2
# Arquivos que estão só na nuvem (OneDrive e parecidos): abrir um deles faria o Windows baixá-lo.
# offline | baixar ao abrir | baixar ao ler
_SO_NA_NUVEM = 0x1000 | 0x40000 | 0x400000
_PALAVRA = re.compile(r"[^\W\d_]{4,}")
_COM_NOMES = {".txt", ".md", ".docx", ".pdf", ".pptx", ".xlsx", ".csv"}   # onde procurar nomes de gente e empresas
_MAIUSCULA = r"[A-ZÁÉÍÓÚÂÊÔÃÕÀÇ][a-záéíóúâêôãõàç]+"
_NOME = re.compile(rf"{_MAIUSCULA}(?:\s+(?:d[aeo]s?\s+)?{_MAIUSCULA})*")
# Palavras que se repetem em qualquer arquivo de programa e não são assunto de ninguém.
_SEM_ASSUNTO = frozenset("""function return true false null none self this class import const var let void public private
    static string value name type file files data system window error result object array index item list default
    using namespace include define param params args license copyright software without warranty permission
    version microsoft windows http https html body style script span width height color font size table
    with from that which will have been were their there other such only also into than then they your about
    para como mais esta este isso essa pelo pela pelos pelas seus suas quando onde cada pode""".split())


def _escondido(entrada: os.DirEntry) -> bool:
    try:
        atributos = entrada.stat(follow_symlinks=False).st_file_attributes
    except (OSError, AttributeError):
        return entrada.name.startswith(".")
    return bool(atributos & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM))


def assunto_de(texto: str, n: int = 5) -> str:
    """As palavras de conteúdo que mais se repetem: um resumo bem cru do assunto."""
    contagem = Counter(t for t in termos(texto) if len(t) > 3 and not t.isdigit() and t not in _SEM_ASSUNTO)
    return ", ".join(palavra for palavra, vezes in contagem.most_common(n) if vezes > 1)


def nomes_proprios(texto: str) -> dict[str, tuple[str, int, int]]:
    """nome -> (como aparece, vezes com maiúsculas no meio da frase, vezes em minúsculas).

    Palavras seguidas com inicial maiúscula contam como um nome só ("Padaria Estrela",
    "João da Silva"). O começo de frase não conta: ali toda palavra tem maiúscula.
    """
    proprias, formas = Counter(), {}
    for achado in _NOME.finditer(texto):
        nome = achado.group(0)
        antes = texto[:achado.start()].rstrip()
        if not antes or antes[-1] in ".!?:\n" or len(nome) < 4:
            continue
        termo = normalizar(nome)
        if termo in PARADAS or termo in _SEM_ASSUNTO:
            continue
        proprias[termo] += 1
        formas.setdefault(termo, nome)
    minusculas = Counter(normalizar(p) for p in _PALAVRA.findall(texto) if p.islower())
    return {termo: (formas[termo], vezes, minusculas[termo]) for termo, vezes in proprias.items()}


class Explorador:
    def __init__(self, cfg, seguranca, mapa, memoria, registro, relogio=datetime.now):
        self.cfg = cfg
        self.seguranca = seguranca
        self.mapa = mapa
        self.memoria = memoria
        self.registro = registro
        self._relogio = relogio
        self._vez_de_ler = False
        self.interromper = lambda: False   # o núcleo pendura aqui: você falou, ou pediram para desligar?
        self.releu_tudo = False            # nesta partida as regras de leitura mudaram e as leituras foram refeitas
        raizes = [raiz for raiz in seguranca.raizes() if raiz.is_dir()]
        self.faxina()   # o que saiu da lista de pastas, ou do alcance das regras, é esquecido aqui
        for raiz in raizes:
            self.mapa.descobrir_pasta(raiz, 0)

    # ------------------------------------------------------------------ faxina
    def faxina(self) -> dict:
        """Tira do mapa e da memória o que as regras de hoje deixam de fora.

        Roda a cada partida. Se você mudou a configuração (ou o programa mudou as regras de
        fábrica), o que ele tinha visto e lido fora do alcance novo é esquecido aqui.
        """
        raizes = [str(raiz) for raiz in self.seguranca.raizes() if raiz.is_dir()]
        dentro = [(raiz.lower().rstrip("\\") + "\\", raiz) for raiz in raizes]   # para comparar como texto

        def fora(caminho: str) -> bool:
            minusculo = caminho.lower() + "\\"
            raiz = next((original for prefixo, original in dentro if minusculo.startswith(prefixo)), None)
            return raiz is None or self.seguranca.fora_de_alcance(caminho, raiz) is not None

        mudaram = self.mapa.regras_mudaram(REGRAS_DE_LEITURA)
        pastas, lidos = self.mapa.esquecer(fora)
        relidos = 0
        if mudaram:   # as regras de leitura são outras: sai tudo o que foi lido (de uma vez) e ele relê o que ficou
            leituras = self.memoria.apagar_tipo("leitura")
            relidos = self.mapa.reler_tudo()
            self.releu_tudo = True
        else:
            leituras = self.memoria.apagar_origens("leitura", lidos) if lidos else 0
        feito = {"pastas_esquecidas": pastas, "arquivos_lidos_esquecidos": len(lidos),
                 "leituras_apagadas": leituras, "arquivos_para_reler": relidos}
        if any(feito.values()):
            self.registro.anotar("explorar", acao="faxina", **feito)
        return feito

    # ------------------------------------------------------------------- passo
    def passo(self) -> dict | None:
        """Dá um passo e devolve o que fez; None se não há nada a fazer (ou se não pode)."""
        if self.seguranca.modo_seguro or self.seguranca.pausado or not self.cfg.exploracao.ligada:
            return None
        self._vez_de_ler = not self._vez_de_ler  # alterna: uma pasta, um arquivo
        ordem = (self._ler_um, self._visitar_uma) if self._vez_de_ler else (self._visitar_uma, self._ler_um)
        for acao in ordem:
            feito = acao()
            if feito:
                self.registro.anotar("explorar", **feito)
                return feito
        return None

    def _visitar_uma(self) -> dict | None:
        alvo = self.mapa.proxima_pasta()
        if alvo is None:
            limite = self._relogio() - timedelta(hours=self.cfg.exploracao.horas_para_revisitar)
            alvo = self.mapa.pasta_para_revisitar(limite.isoformat(timespec="seconds"))
        if alvo is None:
            return None
        pasta, profundidade = alvo
        if not self.seguranca.pode_explorar(pasta):
            self.mapa.registrar_visita(pasta, 0)
            return {"acao": "pular_pasta", "pasta": str(pasta)}
        raiz = next((r for r in self.seguranca.raizes() if pasta.is_relative_to(r)), None)
        novos = pastas_novas = total = 0
        largou = False
        try:
            with os.scandir(pasta) as entradas, self.mapa.lote():
                for entrada in entradas:
                    total += 1
                    if total > ITENS_POR_PASTA:
                        break
                    # O freio vale no meio da pasta também: não se espera uma pasta de milhares de itens acabar.
                    if total % ITENS_ENTRE_OLHADAS == 0 and (self.seguranca.pausado or self.interromper()):
                        largou = True
                        break
                    caminho = Path(entrada.path)
                    if entrada.is_symlink() or entrada.is_junction() or _escondido(entrada):
                        continue  # atalhos podem levar para fora das pastas liberadas
                    # a pasta já foi conferida inteira; aqui confere-se cada item pelo nome (sem ir ao disco)
                    if raiz is not None and self.seguranca.fora_de_alcance(caminho, raiz) is not None:
                        continue
                    if entrada.is_dir(follow_symlinks=False):
                        if profundidade < self.cfg.exploracao.profundidade:
                            pastas_novas += self.mapa.descobrir_pasta(caminho, profundidade + 1)
                    elif entrada.is_file(follow_symlinks=False):
                        dados = entrada.stat(follow_symlinks=False)
                        mudou = self.mapa.registrar_arquivo(caminho, dados.st_size, dados.st_mtime) != "igual"
                        novos += mudou
                        if mudou and getattr(dados, "st_file_attributes", 0) & _SO_NA_NUVEM:
                            self.mapa.marcar(caminho, "pulado")  # entra no mapa pelo nome; ler seria baixar
        except OSError as erro:
            self.mapa.registrar_visita(pasta, 0)
            return {"acao": "pasta_fechada", "pasta": str(pasta), "erro": str(erro)}
        if largou:  # a pasta fica como não visitada: na volta ele recomeça por ela (o que já anotou não se repete)
            return {"acao": "interrompido", "pasta": str(pasta), "itens": total}
        self.mapa.registrar_visita(pasta, total)
        return {"acao": "visitar", "pasta": str(pasta), "itens": total, "arquivos_novos": novos,
                "pastas_novas": pastas_novas}

    def _o_que_ler(self) -> set[str]:
        """Os tipos de arquivo que ele abre: documentos sempre; código e configuração só se você ligar."""
        return leitores.DOCUMENTOS | (leitores.CODIGO if self.cfg.exploracao.ler_codigo else set())

    def _ler_um(self) -> dict | None:
        if not self.cfg.exploracao.ler_arquivos:
            return None
        arquivo = self.mapa.proximo_arquivo(self._o_que_ler(), self.cfg.exploracao.tamanho_maximo_kb * 1024)
        if arquivo is None:
            return None
        try:
            na_nuvem = getattr(arquivo.stat(), "st_file_attributes", 0) & _SO_NA_NUVEM
        except OSError:
            na_nuvem = True  # sumiu ou está inacessível: não insiste
        if na_nuvem or not self.seguranca.pode_ler(arquivo) or leitores.de_enfeite(arquivo):
            self.mapa.marcar(arquivo, "pulado")
            return {"acao": "pular_arquivo", "arquivo": str(arquivo)}
        texto = leitores.ler(arquivo, self.cfg.exploracao.caracteres_por_arquivo)
        self.memoria.apagar_origem("leitura", str(arquivo))  # se o arquivo mudou, sai a leitura antiga
        extensao = arquivo.suffix.lower()
        if not texto or len(texto) < 40 or (extensao in leitores.SO_SE_FOR_PROSA and not leitores.parece_leitura(texto)):
            self.mapa.marcar(arquivo, "pulado")
            return {"acao": "sem_texto", "arquivo": str(arquivo)}
        assunto = assunto_de(texto)
        trechos = [f"{arquivo.name}: {pedaco}" for pedaco in leitores.pedacos(texto)]
        self.memoria.guardar_varios(trechos, tipo="leitura", origem=str(arquivo))
        if extensao in _COM_NOMES:  # em código, "None" e "True" não são gente
            self.mapa.anotar_nomes(nomes_proprios(texto), arquivo.name)
        self.mapa.marcar(arquivo, "lido", assunto)
        return {"acao": "ler", "arquivo": str(arquivo), "caracteres": len(texto), "assunto": assunto}

    # ---------------------------------------------------------------- relatos
    def relato(self) -> str:
        """O que ele já viu, em uma fala."""
        n = self.mapa.numeros()
        if not n["pastas_visitadas"]:
            return "Ainda não explorei nada."
        faltam = n["pastas"] - n["pastas_visitadas"]
        partes = [f"Já olhei {n['pastas_visitadas']} pastas e vi {n['arquivos']} arquivos; li {n['arquivos_lidos']} deles."]
        if faltam:
            partes.append(f"Ainda tenho {faltam} pastas para olhar.")
        assuntos = self.mapa.assuntos()
        if assuntos:
            partes.append("Os assuntos que mais aparecem no que li: " + ", ".join(assuntos) + ".")
        return " ".join(partes)
