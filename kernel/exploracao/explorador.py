"""O explorador: um passo de cada vez, sempre só olhando.

Cada passo é uma de duas coisas:

- **visitar uma pasta**: anotar no mapa os arquivos e as subpastas que há nela;
- **ler um arquivo**: tirar o texto, guardar trechos na memória (tipo ``leitura``)
  e anotar de que assunto ele trata.

Antes de qualquer passo ele pergunta à segurança (``pode_explorar`` e
``pode_ler``), e todo passo vai para o registro. Não existe aqui nenhuma função
que escreva, mova ou apague arquivos seus.
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
# Arquivos que estão só na nuvem (OneDrive e parecidos): abrir um deles faria o Windows baixá-lo.
# offline | baixar ao abrir | baixar ao ler
_SO_NA_NUVEM = 0x1000 | 0x40000 | 0x400000
_PALAVRA = re.compile(r"[^\W\d_]{4,}")
_COM_NOMES = {".txt", ".md", ".docx", ".pdf", ".pptx", ".xlsx", ".csv"}   # onde procurar nomes de gente e empresas
_MAIUSCULA = r"[A-ZÁÉÍÓÚÂÊÔÃÕÀÇ][a-záéíóúâêôãõàç]+"
_NOME = re.compile(rf"{_MAIUSCULA}(?:\s+(?:d[aeo]s?\s+)?{_MAIUSCULA})*")


def _escondido(entrada: os.DirEntry) -> bool:
    try:
        atributos = entrada.stat(follow_symlinks=False).st_file_attributes
    except (OSError, AttributeError):
        return entrada.name.startswith(".")
    return bool(atributos & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM))


def assunto_de(texto: str, n: int = 5) -> str:
    """As palavras de conteúdo que mais se repetem: um resumo bem cru do assunto."""
    contagem = Counter(t for t in termos(texto) if len(t) > 3 and not t.isdigit())
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
        if termo in PARADAS:
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
        raizes = [raiz for raiz in seguranca.raizes() if raiz.is_dir()]
        for esquecido in self.mapa.esquecer_fora_de(raizes):  # pastas que você tirou da lista
            self.memoria.apagar_origem("leitura", esquecido)
        for raiz in raizes:
            self.mapa.descobrir_pasta(raiz, 0)

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
                    if self.seguranca.nome_ruim(entrada.name):
                        continue  # a pasta já foi conferida inteira; aqui basta o nome de cada item
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

    def _ler_um(self) -> dict | None:
        if not self.cfg.exploracao.ler_arquivos:
            return None
        arquivo = self.mapa.proximo_arquivo(leitores.LEGIVEIS, self.cfg.exploracao.tamanho_maximo_kb * 1024)
        if arquivo is None:
            return None
        try:
            na_nuvem = getattr(arquivo.stat(), "st_file_attributes", 0) & _SO_NA_NUVEM
        except OSError:
            na_nuvem = True  # sumiu ou está inacessível: não insiste
        if na_nuvem or not self.seguranca.pode_ler(arquivo):
            self.mapa.marcar(arquivo, "pulado")
            return {"acao": "pular_arquivo", "arquivo": str(arquivo)}
        texto = leitores.ler(arquivo, self.cfg.exploracao.caracteres_por_arquivo)
        self.memoria.apagar_origem("leitura", str(arquivo))  # se o arquivo mudou, sai a leitura antiga
        if not texto or len(texto) < 40:
            self.mapa.marcar(arquivo, "pulado")
            return {"acao": "sem_texto", "arquivo": str(arquivo)}
        assunto = assunto_de(texto)
        trechos = [f"{arquivo.name}: {pedaco}" for pedaco in leitores.pedacos(texto)]
        self.memoria.guardar_varios(trechos, tipo="leitura", origem=str(arquivo))
        if arquivo.suffix.lower() in _COM_NOMES:  # em código, "None" e "True" não são gente
            self.mapa.anotar_nomes(nomes_proprios(texto), arquivo.name)
        self.mapa.marcar(arquivo, "lido", assunto)
        return {"acao": "ler", "arquivo": str(arquivo), "caracteres": len(texto), "assunto": assunto}

    # ---------------------------------------------------------------- relatos
    def relato(self) -> str:
        """O que ele já viu, em uma fala."""
        n = self.mapa.numeros()
        if not n["pastas_visitadas"]:
            return "Ainda não explorei nada."
        tipos = ", ".join(f"{quantos} {extensao}" for extensao, quantos in n["tipos"])
        partes = [f"Já visitei {n['pastas_visitadas']} de {n['pastas']} pastas que conheço e vi "
                  f"{n['arquivos']} arquivos ({tipos}). Li {n['arquivos_lidos']} deles."]
        assuntos = self.mapa.assuntos()
        if assuntos:
            partes.append("Os assuntos que mais aparecem: " + ", ".join(assuntos) + ".")
        return " ".join(partes)
