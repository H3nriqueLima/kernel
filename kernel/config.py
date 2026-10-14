"""Configuração do K.E.R.N.E.L.

Os valores padrão moram aqui; o arquivo ``kernel.toml`` na raiz do projeto
sobrescreve o que você quiser mudar. É o painel de botões do sistema.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path

from .caminhos import pastas_conhecidas

RAIZ = Path(__file__).resolve().parent.parent


@dataclass
class ConfigNucleo:
    porta: int = 8765             # o serviço só atende em 127.0.0.1 (a sua máquina)
    intervalo_laco: float = 5.0   # segundos entre uma volta e outra do laço de autonomia
    autonomia: bool = True        # False = ele só responde, nunca toma iniciativa


@dataclass
class ConfigSeguranca:
    # Nível a partir do qual uma ação sua pede confirmação. 0 = tudo pede (v0.1).
    # O nível SISTEMA (abrir programa) pede sempre: isso está no código, não aqui.
    confirmar_a_partir_de: int = 0
    validade_pedido: float = 300.0  # segundos até um pedido sem resposta expirar
    # Tudo o que ele pode ver: é aqui que as mãos listam e que ele explora sozinho.
    # Aceita caminhos ou {area de trabalho}, {documentos}, {downloads}, {imagens},
    # {musicas}, {videos} e {projeto}.
    pastas_permitidas: list[str] = field(
        default_factory=lambda: ["{area de trabalho}", "{documentos}", "{downloads}", "{projeto}"]
    )


@dataclass
class ConfigExploracao:
    """Até onde ele pode ir sozinho. As pastas são as de [seguranca] pastas_permitidas."""
    ligada: bool = True         # pode olhar as pastas liberadas por conta própria (só leitura)
    ler_arquivos: bool = True   # pode ler o texto dos arquivos (False = só os nomes)
    ritmo: str = "normal"       # calmo | normal | intenso
    # False = pula o Windows, os programas instalados e as pastas que os programas montam (obj, bin,
    # node_modules...). Lá não há documento seu: são dezenas de milhares de arquivos de sistema.
    pastas_de_sistema: bool = False
    # False = pula o que começa com ponto (.claude, .aws, .config...): é configuração de programa,
    # e é onde programas costumam guardar chaves de acesso.
    ocultos: bool = False
    # False = código e arquivos de configuração entram no mapa pelo nome, mas ele não lê o conteúdo.
    ler_codigo: bool = False
    # Pedaços de nome de pasta ou arquivo que ele sempre pula, em qualquer lugar.
    nunca: list[str] = field(
        default_factory=lambda: [
            "senha", "password", "passwd", "segredo", "secret", "token", "credencia", "credential",
            "wallet", "id_rsa", "id_ed25519", ".ssh", ".gnupg", ".env", ".pem", ".key", ".pfx", ".kdbx",
            "cookies", "login data", "keychain", ".netrc", ".npmrc", ".pypirc",
            "appdata", "node_modules", ".git", ".venv", "__pycache__", "$recycle.bin",
        ]
    )
    profundidade: int = 6               # quantas pastas para dentro ele desce
    tamanho_maximo_kb: int = 2048       # arquivos maiores que isso ele não abre
    caracteres_por_arquivo: int = 6000  # quanto de cada arquivo ele guarda na memória
    horas_para_revisitar: float = 24.0  # depois disso ele volta a olhar uma pasta já vista


@dataclass
class ConfigInternet:
    """Até onde ele pode ir na internet. Sempre só leitura: não entra em conta, não envia formulário, não baixa arquivo."""
    ligada: bool = False            # False = ele nunca sai para a internet, nem quando você pede
    pesquisar_sozinho: bool = True  # com a internet ligada: pesquisa por conta própria quando está ocioso
    buscador: bool = True           # além da Wikipédia, usa um buscador e lê as páginas que achar
    # True = também pesquisa os assuntos que viu nos seus arquivos. As palavras pesquisadas saem do PC.
    assuntos_dos_arquivos: bool = False
    interesses: list[str] = field(default_factory=list)       # assuntos que você quer que ele estude sozinho
    sites_proibidos: list[str] = field(default_factory=list)  # sites que ele nunca abre ("exemplo.com")
    paginas_por_hora: int = 30          # teto de pedidos por hora quando ele pesquisa por conta própria
    paginas_por_assunto: int = 2        # quantas páginas (fora a Wikipédia) ele lê para cada assunto
    caracteres_por_pagina: int = 4000   # quanto de cada página ele guarda na memória
    segundos_entre_pedidos: float = 2.0  # intervalo entre dois pedidos ao mesmo site
    trechos_maximos: int = 20000        # teto de trechos de pesquisa na memória (os mais antigos saem)


@dataclass
class ConfigCelular:
    ligado: bool = False        # True = atende também na rede local, para o celular parear


@dataclass
class ConfigVoz:
    ligada: bool = True
    # difones   = voz gravada, colada por difones com PSOLA (usa formantes se o banco não existir)
    # formantes = voz de máquina gerada por regra ("propria" é o nome antigo e continua valendo)
    # aparelho  = a voz do seu navegador ou celular
    motor: str = "difones"
    estilo: str = "natural"     # natural | robotica (cada vogal numa nota fixa, sem deslizar). Só nos difones
    altura: float = 1.0         # difones: 1.0 = o tom da gravação; 1.1 = mais aguda; 0.9 = mais grave
    tom: float = 112.0          # formantes: altura da voz em Hz (mais baixo = mais grave)
    velocidade: float = 1.0     # 1.0 = normal; 1.2 = mais rápido


@dataclass
class ConfigMaos:
    # nome falado -> o que abrir (executável ou caminho completo)
    programas: dict[str, str] = field(
        default_factory=lambda: {
            "calculadora": "calc.exe",
            "bloco de notas": "notepad.exe",
            "paint": "mspaint.exe",
            "explorador de arquivos": "explorer.exe",
            "gerenciador de tarefas": "taskmgr.exe",
        }
    )
    atalhos_menu_iniciar: bool = True  # também acha programas pelos atalhos do Menu Iniciar


@dataclass
class ConfigCerebro:
    dispositivo: str = "auto"   # auto | directml | cuda | cpu (só para treinar)
    tamanho: str = "mini"       # nano | mini | pequeno (ver kernel/cerebro/gpt.py)
    temperatura: float = 0.8
    top_k: int = 40
    max_tokens: int = 60
    # True = numa conversa, o cérebro acrescenta uma fala dele. Vem desligado porque o cérebro pequeno
    # completa texto sem sentido; ele entra na conversa quando for ajustado para diálogo (fase 4).
    # Para vê-lo escrever a qualquer hora, diga "completa: " e o começo de uma frase.
    na_conversa: bool = False


@dataclass
class ConfigOuvidos:
    ativo: bool = True          # liga sozinho quando existe um modelo treinado
    palavra: str = "kernel"     # a palavra que você grava para chamar por ele
    limiar: float = 0.85        # certeza mínima para considerar que ouviu a palavra
    microfone: int = -1         # -1 = microfone padrão do Windows


@dataclass
class ConfigMente:
    limiar_impulso: float = 0.6          # acima disso o impulso vira ação
    curiosidade_por_minuto: float = 0.04 # quanto a curiosidade sobe por minuto de ócio
    organizacao_por_memoria: float = 0.05  # quanto sobe por memória ainda não arrumada
    minutos_entre_perguntas: float = 20.0
    social_por_novidade: float = 0.02      # vontade de contar o que descobriu, por descoberta
    minutos_entre_relatos: float = 30.0
    # Depois deste tempo sem você falar, ele entende que você saiu: continua explorando e estudando,
    # mas não puxa assunto nem pergunta nada. Quando você volta, conta de uma vez o que fez.
    minutos_de_presenca: float = 15.0
    hora_do_diario: int = 23
    termos_para_lembrar: int = 2         # termos em comum para ele citar uma memória na conversa


@dataclass
class Config:
    raiz: Path = RAIZ
    dados: Path = RAIZ / "dados"
    usuario: str = "Henrique"
    nucleo: ConfigNucleo = field(default_factory=ConfigNucleo)
    seguranca: ConfigSeguranca = field(default_factory=ConfigSeguranca)
    exploracao: ConfigExploracao = field(default_factory=ConfigExploracao)
    internet: ConfigInternet = field(default_factory=ConfigInternet)
    celular: ConfigCelular = field(default_factory=ConfigCelular)
    voz: ConfigVoz = field(default_factory=ConfigVoz)
    maos: ConfigMaos = field(default_factory=ConfigMaos)
    cerebro: ConfigCerebro = field(default_factory=ConfigCerebro)
    ouvidos: ConfigOuvidos = field(default_factory=ConfigOuvidos)
    mente: ConfigMente = field(default_factory=ConfigMente)

    def pasta(self, *partes: str) -> Path:
        """Subpasta de ``dados`` (criada se não existir)."""
        caminho = self.dados.joinpath(*partes)
        caminho.mkdir(parents=True, exist_ok=True)
        return caminho

    def pastas_permitidas(self) -> list[Path]:
        conhecidas = {**pastas_conhecidas(), "projeto": self.raiz}
        saida = []
        for item in self.seguranca.pastas_permitidas:
            chave = item.strip().strip("{}").lower()
            if item.strip().startswith("{") and chave in conhecidas:
                saida.append(conhecidas[chave])
            else:
                saida.append(Path(os.path.expandvars(item)).expanduser())
        return saida


def _aplicar(alvo, valores: dict, onde: str) -> None:
    conhecidos = {f.name for f in fields(alvo)} - {"raiz"}
    for chave, valor in valores.items():
        if chave not in conhecidos:
            raise ValueError(f"{onde}: opção desconhecida '{chave}'")
        atual = getattr(alvo, chave)
        if is_dataclass(atual):
            _aplicar(atual, valor, f"{onde} [{chave}]")
        elif isinstance(atual, dict):
            atual.update(valor)
        elif chave == "nunca":  # a sua lista soma aos nomes proibidos de fábrica, não substitui
            atual.extend(str(v).lower() for v in valor if str(v).lower() not in atual)
        elif isinstance(atual, Path):
            setattr(alvo, chave, Path(valor))
        else:
            setattr(alvo, chave, valor)


def carregar(arquivo: Path | None = None, dados: Path | None = None) -> Config:
    """Lê ``kernel.toml`` por cima dos padrões. ``KERNEL_DADOS`` troca a pasta de dados."""
    arquivo = Path(arquivo or os.environ.get("KERNEL_CONFIG") or RAIZ / "kernel.toml")
    cfg = Config()
    if arquivo.exists():
        with open(arquivo, "rb") as f:
            _aplicar(cfg, tomllib.load(f), arquivo.name)
    dados = dados or os.environ.get("KERNEL_DADOS")
    if dados:
        cfg.dados = Path(dados)
    if not cfg.dados.is_absolute():
        cfg.dados = RAIZ / cfg.dados
    cfg.dados.mkdir(parents=True, exist_ok=True)
    return cfg
