# K.E.R.N.E.L

**Kinetic Extended Resolution Network and Evolutionary Logic** — um Jarvis pessoal construído do zero, 100% local, no seu PC.

Versão **0.5.1**: a Fase 0 do [sub-roadmap](docs/ROADMAP.md), a 0.5 consolidada e protegida:
- cópias de segurança diárias, com restauração testada;
- o selo de integridade cobre todo o código que aplica as regras;
- cada fim de treino diz por quê;
- os bancos não travam com leituras de fora;
- o celular só é atendido da rede local.

O que mudou, e o que ficou documentado como risco aceito, está em [docs/fase0/README.md](docs/fase0/README.md).

Depois veio a Fase 1, o diagnóstico do cérebro ([relatório](docs/fase1/diagnostico.md)). O pipeline de treino e de inferência foi conferido peça por peça, e passou. O texto sem sentido vem do tamanho do modelo: 3,5 milhões de parâmetros. A medida de progresso agora é reprodutível: `python -m kernel cerebro protocolo`, num conjunto de teste fixo de texto que ele nunca leu.

A 0.5 foi uma rodada de ajustes antes do cérebro maior. A conversa ficou mais esperta (perguntas que ele não conhecia, "fale mais", perguntas sobre ele mesmo), ele explora com critério (sem perder tempo com o Windows), não fala sozinho quando você não está e conta o que aprendeu. Da 0.4 vem a pesquisa na internet; da 0.3, a voz de difones; da 0.2, a autonomia, o celular e a orbe. O plano completo está em [docs/PLANO.md](docs/PLANO.md).

## Ligar e desligar

- **Ligar:** dois cliques em `iniciar.bat`. A janela abre em `http://127.0.0.1:8765/`.
- **Desligar:** menu ≡ → Desligar (dois toques), ou `desligar.bat`.
- **Parar só a autonomia:** diga `para` no chat, ou toque no botão de pausa. Para voltar: `pode continuar`.

Pelo terminal: `.venv\Scripts\python.exe -m kernel iniciar --janela`, `... estado`, `... desligar`.

**Ligue sempre pelo `iniciar.bat`.** Ligado de dentro de outro programa (o app do Claude, um editor), ele é fechado junto quando esse programa fecha ou se atualiza. Foi o que interrompeu o treino de 13/10 ([investigação](docs/fase0/investigacao-a3.md)).

## Autonomia: ele explora o PC sozinho

Quando você não está falando com ele, a curiosidade sobe. Ao passar do limiar, ele sai explorando em fôlegos: visita uma pasta, anota os arquivos, lê os que consegue (texto, Word, Excel, PowerPoint, PDF) e guarda trechos na memória. Depois:

- **responde sobre os seus arquivos:** `onde está o contrato?`, `o que você lembra sobre a padaria?`
- **conta o que achou**, por conta própria ou quando você pergunta `o que você descobriu?`
- **pergunta o que não conhece:** se um nome aparece em vários arquivos, ele pergunta quem é e guarda a resposta.

**Ele trabalha calado quando você não está.** Depois de 15 minutos sem você falar, ele continua explorando e estudando, mas não puxa assunto nem faz perguntas. Quando você volta, conta de uma vez: "Enquanto você esteve fora (3 h), li 12 arquivos seus e estudei 18 assuntos na internet". O tempo é `minutos_de_presenca`, em `[mente]`.

**Ele explora com critério.** Mesmo que você libere um disco inteiro, ele pula o Windows, os programas instalados, as pastas que os programas montam (`obj`, `bin`, `node_modules`) e o que começa com ponto (`.claude`, `.aws`: configuração de programas, onde costumam ficar chaves de acesso). Lê só documentos (texto, Word, Excel, PowerPoint, PDF); código e configuração entram no mapa pelo nome. De um arquivo de texto ele só guarda o que for prosa em português ou inglês. Quando essas regras mudam, na partida seguinte ele esquece o que tinha lido fora do alcance novo. Tudo se religa em `[exploracao]`: `pastas_de_sistema`, `ocultos`, `ler_codigo`.

### O que ele pode e o que não pode

Tudo em `kernel.toml`, nas duas primeiras seções. Esse arquivo é a sua configuração e fica só no seu PC, fora do Git; o repositório traz o modelo [kernel.exemplo.toml](kernel.exemplo.toml), que o `instalar.ps1` copia para `kernel.toml`:

```toml
[seguranca]
pastas_permitidas = ["{area de trabalho}", "{documentos}", "{downloads}", "{projeto}"]

[exploracao]
ligada = true          # false = ele nunca olha nada sozinho
ler_arquivos = true    # false = só vê os nomes
ritmo = "normal"       # calmo | normal | intenso
nunca = []             # nomes que ele sempre pula, além dos de fábrica
```

- **Só olha.** O explorador não tem nenhuma função que escreva, mova ou apague arquivos. Abrir programas e anotar lembretes continuam pedindo a sua confirmação, sempre.
- **Só nas pastas da lista.** Atalhos e junções que levam para fora são ignorados.
- **Nunca abre** arquivos ou pastas com nomes como `senha`, `password`, `token`, `.ssh`, `.env`, `.kdbx`, `appdata` (a lista completa está em `kernel/config.py`; a sua lista `nunca` soma a ela).
- **Não baixa nada do OneDrive.** Arquivos que estão só na nuvem entram no mapa pelo nome, mas não são abertos.
- **Tudo fica no registro** (`dados/registro/`, linhas do tipo `explorar`) e o que ele leu fica só em `dados/kernel.db`, no seu HD.
- **Tirou uma pasta da lista?** Na próxima partida ele esquece o que viu lá.
- **O freio vale no meio de uma pasta.** Numa pasta com milhares de arquivos (liberar `C:\` inteiro inclui as do Windows), ele confere a cada 64 itens se você falou, mandou parar ou pediu para desligar, e larga a pasta ali; na volta, recomeça por ela.
- A interface e o celular **não conseguem ampliar o acesso**: as pastas só mudam editando o `kernel.toml` no PC.

## Internet: ele pesquisa e aprende sozinho

Com a internet ligada, ele faz três coisas:

- **Responde o que não sabia.** Você pergunta `o que é o pré-sal?`; se não está no que ele estudou, ele vai à internet, lê, responde em duas frases e mostra a fonte (um link, que abre no seu navegador).
- **Pesquisa quando você pede:** `pesquisa sobre buracos negros`, `procura na internet quem foi Santos Dumont`, `lê a página https://...`. Depois: `o que você pesquisou?` e `abre a fonte`.
- **Pesquisa por conta própria** quando está ocioso, alternando com a exploração do PC: um fôlego nas pastas, um assunto na internet. A fila de assuntos vem do que você perguntou ou pediu, da lista `interesses` e dos assuntos vizinhos do que ele acabou de ler (até dois passos de distância).

O que ele lê vira memória do tipo `pesquisa`, em pedaços, cada um com o endereço de onde veio. De cada assunto ele também guarda um resumo de três frases (tipo `saber`), escolhidas do que leu, sem inventar nada (`kernel/conhecimento/resumo.py`). É com isso que ele responde na segunda vez, sem voltar à rede, e conta o que aprendeu: `o que você aprendeu?`, `o que você aprendeu sobre redes neurais?`.

Os `interesses` do `kernel.toml` entram na fila assim que você reinicia o serviço e passam na frente dos assuntos vizinhos. São uns 10 assuntos por hora (o teto por hora protege os sites; a API da Wikipédia não entra na conta), então uma lista de 400 interesses leva uns dois dias de PC ligado.

### Onde ele procura

- **Wikipédia e Wikcionário**, pela API que a Wikimedia oferece a programas.
- **Um buscador** (DuckDuckGo, na versão em HTML puro) para achar páginas do resto da web; ele lê até duas por assunto.

### O que ele pode e o que não pode na internet

Em `kernel.toml` (no modelo ela vem desligada):

```toml
[internet]
ligada = true             # false = nunca sai do PC, nem quando você pede
pesquisar_sozinho = true  # false = só quando você pede
buscador = true           # false = só Wikipédia e Wikcionário
interesses = []           # assuntos para ele estudar sozinho: ["astronomia", "finanças pessoais"]
assuntos_dos_arquivos = false
sites_proibidos = []      # sites que ele nunca abre
paginas_por_hora = 30     # teto de pedidos por hora quando pesquisa sozinho
```

- **Só lê.** Ele usa um leitor de páginas próprio (`kernel/internet/rede.py`), que só sabe fazer pedidos de leitura. Não entra em conta, não preenche formulário, não guarda cookie e não baixa arquivo: só aceita texto.
- **Não usa os seus navegadores.** No Chrome, no Edge e no Firefox estão as suas contas abertas (e-mail, banco, redes sociais); um programa que anda sozinho pela internet não deve carregar isso. O único contato com o seu navegador é `abre a fonte` ou `abre o site ...`: ele pede confirmação e o Windows abre a página para **você** ver.
- **Só a internet pública.** A sua máquina e a sua rede local (roteador, impressora, o próprio serviço dele) ficam de fora, mesmo quando um site tenta redirecionar para lá ou usa um nome que aponta para dentro.
- **O que sai do PC são as palavras da pesquisa**, nunca o conteúdo dos seus arquivos. E os assuntos dos seus arquivos só viram pesquisa se você ligar `assuntos_dos_arquivos`: vem desligado porque o que está nos arquivos pode ser de outras pessoas (clientes, por exemplo). Mesmo ligado, nunca saem:
  - nomes próprios vistos nos arquivos;
  - palavras com número;
  - o seu nome;
  - o que você puser em `nunca_pesquisar`.
- **Respeita os sites.** Lê o `robots.txt` de cada um, espera entre dois pedidos ao mesmo site, tem teto por hora e, se um site pede prova de que não é robô, desiste e o deixa em paz. Não tenta contornar.
- **O freio é o mesmo.** `para` segura a pesquisa por conta própria na hora (um pedido seu ele continua atendendo). `ligada = false` segura tudo.
- **O que vem da internet é texto, não ordem.** Nenhuma frase lida numa página vira comando para as mãos dele.
- **Tudo fica no registro:** cada endereço aberto (tipo `internet`, inclusive os barrados e o motivo) e cada assunto pesquisado (tipo `pesquisar`).

O limite honesto: sem o cérebro treinado, ele não "entende" o que leu. Ele acha o artigo ou a página que trata do assunto, mostra as primeiras frases e guarda o resto para consulta. Numa pergunta muito específica ("qual a temperatura agora em tal bairro?") isso pode não responder.

```
python -m kernel internet pesquisar "fotossíntese"
python -m kernel internet ler https://pt.wikipedia.org/wiki/Astronomia
python -m kernel internet estado
```

## A conversa

Ele ainda não conversa livremente: quem entende as frases são um classificador pequeno e regras, não o cérebro. O que já funciona:

- **Perguntas**, mesmo as que o classificador nunca viu: vão para o que ele estudou, para o que já pesquisou e, por fim, para a internet.
- **Continuar o assunto:** `fale mais`, `explica melhor`, `e o que mais?`, `fale mais sobre buracos negros`.
- **Perguntas sobre ele** (`kernel/nucleo/sobre_si.py`): `o que você sabe fazer?`, `quais pastas você pode ver?`, `como está o seu cérebro?`, `quem te criou?`, `você tem sentimentos?`. A resposta é montada com o estado de verdade (as pastas da configuração, a perda do último treino), não com um texto decorado.
- **Pedidos diretos:** `explore o computador`, `para`, `pode continuar`, `pesquisa sobre...`, `treina o cérebro por 6 horas`.
- **O cérebro, quando você chama:** `completa: Era uma vez` mostra o que ele escreve. Na conversa normal ele fica de fora (`[cerebro] na_conversa = false`), porque um cérebro deste tamanho escreve português com gramática e sem sentido.

Quando ele pergunta algo ("vi 'Padaria Estrela' em 4 arquivos; quem é?"), só vale como resposta uma fala que pareça resposta; se você mudar de assunto, a dúvida continua aberta em vez de ele guardar a sua frase como se fosse a explicação.

## A interface

Uma orbe no centro e a conversa embaixo. A orbe muda com o que ele está fazendo: respira quando ocioso, fica verde com satélites quando explora, acelera quando pensa, apaga quando você manda parar e, quando fala, se estica com o volume e o espectro da própria voz.

Os três botões no canto: voz ligada/muda, parar/continuar a autonomia, e o menu ≡ (o que ele está fazendo, pastas liberadas, impulsos, órgãos, celular, registro, diário e desligar).

## A voz dele

São dois sintetizadores, os dois escritos aqui, sem motor de voz pronto (`kernel/voz/`).

**Difones com PSOLA (o padrão).** A voz é de uma pessoa: pedacinhos de gravações, cada um indo do meio de um fonema ao meio do seguinte, colados e ajustados em duração e tom pelo algoritmo PSOLA (sobrepor e somar em sincronia com o tom). O caminho inteiro:

1. `corpus.py` baixa gravações com transcrição (ver "De onde vem a voz", abaixo).
2. `alinhador.py` descobre onde cada fonema começa e acaba. Primeiro compara cada frase com a mesma frase dita pelo sintetizador de formantes (cujos tempos são conhecidos); depois treina um modelo de cada fonema *nesta voz* e realinha pelo caminho mais provável (Viterbi), algumas vezes.
3. `marcas.py` mede o tom e marca cada vibração das cordas vocais.
4. `difones.py` corta cada fonema em duas metades, guarda as pontas (timbre, tom, volume) e, na hora de falar, escolhe a sequência de metades que soma menos custo. Pedaços que já eram vizinhos na gravação emendam de graça.
5. `psola.py` cola os pedaços, dando a cada um a duração e o tom pedidos.

**Formantes (a reserva).** Gera a onda inteira por regra (`sintetizador.py`): voz de máquina, mas não depende de gravação. É o molde do passo 2 e entra sozinho quando o banco não existe ou não tem um som pedido. Por isso o sistema é híbrido.

```
python -m kernel voz baixar --frases 400       lista de frases e MP3 dos capítulos (~120 MB)
python -m kernel voz construir                 alinha e corta (uns 30 minutos)
python -m kernel voz estado                    o que há no banco
python -m kernel falar "Olá, Henrique." --tocar
python -m kernel falar "Olá, Henrique." --estilo robotica --tocar
python -m kernel falar "Olá, Henrique." --motor formantes --tocar
```

Em `kernel.toml`, seção `[voz]`:

- `motor`: `difones`, `formantes` ou `aparelho` (a voz do navegador ou do celular);
- `estilo`: `natural` (a frase desce aos poucos, a pergunta sobe na última sílaba tônica) ou `robotica` (cada vogal presa numa nota fixa, sem deslizar, como uma voz afinada à força: o efeito das IAs de ficção);
- `altura` (1.0 = o tom da gravação) e `velocidade` (1.0 = o ritmo da leitora; 0.7 = bem mais devagar).

Ele fala com **um motor só**, o que estiver em `motor`. Mudou o `kernel.toml`? Reinicie o serviço. Cada fala fica no registro (linhas do tipo `voz`) com o motor que a disse: se a voz parecer errada, é lá que se confere. O navegador não guarda os áudios, e a página recarrega sozinha quando o serviço reinicia; com duas janelas abertas no mesmo navegador, fala só aquela em que você mexeu por último.

### Como foi medida

Não dá para um programa "ouvir" se a voz ficou boa, então há duas medidas objetivas, e as duas dizem coisas diferentes:

| Medida | Difones (natural) | Difones (robótica) | Formantes |
|---|---|---|---|
| Distância até a leitora de verdade, em 20 frases que **não** entraram no banco (menor é melhor; outra frase qualquer dela dá 4,99) | **4,05** | — | 5,81 |
| 61 palavras soltas reconhecidas contra a voz "Maria" do Windows (na primeira / entre as três) | 42 / 53 | 45 / 53 | **48** / 58 |
| Tempo para gerar 1 s de fala (depois de carregar o banco, 114 MB) | 0,03 a 0,07 s | 0,03 a 0,07 s | 0,10 s |

Em frases, a voz de difones fica uns 30% mais perto de uma pessoa falando. Em palavras soltas ela **não** é mais inteligível que a de formantes: uma palavra isolada sai de pedaços de frases diferentes, e o corte automático dos fonemas erra em parte deles. O banco atual tem 178 frases (45 minutos), 697 difones diferentes e 56 mil metades de fonema; 70 a 75% das emendas de uma frase comum são entre pedaços que já eram vizinhos na gravação.

Limites conhecidos: a entonação é por regra (não aprendida da leitora); as gravações têm um chiado de fundo que vem junto; e a pronúncia erra o timbre de algumas vogais ("quero" sai com "e" fechado). Amostras das três vozes em `docs/amostras/`.

### De onde vem a voz

A leitora é a voluntária "Leni", brasileira, lendo *Senhora*, de José de Alencar, no [LibriVox](https://librivox.org/reader/2961). As gravações do LibriVox são de **domínio público**. Os cortes em frases e as transcrições vêm do conjunto *Multilingual LibriSpeech* (Pratap et al., 2020), de licença **CC BY 4.0**. Os MP3 e o banco ficam em `dados/voz/`, fora do Git.

Não usei falas de jogos ou de dubladores: são material protegido e, no caso de uma voz em inglês, nem serviriam, porque faltam ao inglês sons do português (vogais nasais, "lh", "nh"). O efeito de voz de IA vem do `estilo = "robotica"`, aplicado a uma voz brasileira.

Para trocar de voz: qualquer conjunto de gravações de uma pessoa só, com o texto de cada trecho, serve. `difones.construir_de` recebe uma lista de pares (som a 22.050 Hz, texto).

## No celular

1. Em `kernel.toml`, `[celular] ligado = true` e reinicie.
2. Na primeira vez, o Windows pergunta se o Python pode receber conexões: **permita**. Sua rede está marcada como "Pública"; marque essa opção na pergunta, ou mude a rede para "Particular" nas configurações do Windows.
3. No PC: menu ≡ → **Parear um celular**. Aparece um código de 6 dígitos (vale 5 minutos, um aparelho).
4. No celular, no mesmo Wi-Fi, abra o endereço que o menu mostra (algo como `http://192.168.x.x:8765/`), digite o código e pronto. "Adicionar à tela inicial" deixa com cara de aplicativo.

Para **falar** com ele pelo celular, toque no campo de texto e use o microfone do teclado (o ditado do próprio celular, que funciona sem internet se o idioma estiver baixado). Ele responde com a voz dele e a orbe.

O que saber:

- A conversa pela rede local vai **sem criptografia** (HTTP). Use só no Wi-Fi de casa.
- Ele só atende aparelhos da rede local (endereços como `192.168.x.x`). Mesmo que o roteador abra a porta para a internet, quem vier de fora é recusado, até com a chave de um celular pareado.
- O registro e o diário só aparecem no PC: o registro mostra caminhos e trechos dos seus arquivos.
- Um aparelho pareado pode conversar e confirmar ações. Para cortar o acesso: menu ≡ → Celular → esquecer.
- Reconhecimento de fala **dele** (sem depender do teclado do celular) ainda não existe: precisa de um modelo treinado, que é uma fase à frente no plano.

## Mais sabido

| Você diz | O que acontece |
|---|---|
| `quanto é 15% de 200?` `raiz de 144` | Faz a conta (analisador próprio, sem `eval`) |
| `que horas são?` `que dia é hoje?` | Responde na hora |
| `como está o pc?` `quanto espaço tem no disco?` | Processador, memória, placa de vídeo e discos |
| `onde está a planilha de custos?` | Procura no mapa do que explorou |
| `o que é astronomia?` `quem foi Santos Dumont?` | Responde da enciclopédia local, **depois de estudar** |
| `estuda a wikipédia` | Pede confirmação, baixa ~210 MB, limpa e monta a enciclopédia (use `estuda 3 partes da wikipédia` ou `a wikipédia inteira` para mais) |
| `treina o cérebro por 8 horas` | Pede confirmação e treina o mini GPT na placa de vídeo |
| `como está o estudo?` `para o treino` | Acompanha ou interrompe (o treino salva o ponto e retoma depois) |

O limite honesto continua o mesmo: o **cérebro** é um GPT de 3,5 milhões de parâmetros que ainda não foi treinado, e mesmo treinado ele completa texto, não conversa. O que deixa o K.E.R.N.E.L mais sabido nesta versão é busca e regra: memória, mapa de arquivos, enciclopédia e reflexos. As respostas da enciclopédia vêm marcadas com a fonte.

## Os órgãos

| Órgão | Onde está | O que é |
|---|---|---|
| Núcleo | `kernel/nucleo/servico.py` | Liga os órgãos, trata as mensagens e roda o laço perceber → lembrar → avaliar → decidir → agir → refletir |
| Reflexos | `kernel/nucleo/reflexos.py` | O freio ("para"), hora, cumprimentos e pedidos de estudo, por regra |
| Exploração | `kernel/exploracao/` | Mapa do que viu, leitores de arquivo, o explorador passo a passo e o que sabe da máquina |
| Segurança | `kernel/seguranca/` | Níveis de permissão, confirmações, o que pode ser explorado, aparelhos pareados e o selo do próprio código |
| Mãos | `kernel/maos/` | Abrir programa, listar pasta, anotar lembrete, abrir uma página no seu navegador |
| Comandos | `kernel/comandos/` | Classificador de intenções (softmax em NumPy), extração de argumentos e a calculadora |
| Memória | `kernel/memoria/` | SQLite + índice invertido + BM25 escritos à mão |
| Conhecimento | `kernel/conhecimento/` | Enciclopédia local montada da Wikipédia |
| Internet | `kernel/internet/` | Leitor de páginas próprio (só leitura, só internet pública), HTML para texto, fontes (Wikipédia, Wikcionário, buscador) e o pesquisador com a fila de assuntos |
| Estudo | `kernel/nucleo/estudo.py` | Os trabalhos longos: estudar a Wikipédia e treinar o cérebro |
| Cérebro | `kernel/cerebro/` | micrograd, bigramas, BPE, mini GPT com camadas à mão, treino com DirectML, inferência em NumPy |
| Voz | `kernel/voz/` | Pronúncia do português, banco de difones com PSOLA (corpus, alinhador, marcas de tom) e sintetizador de formantes de reserva |
| Ouvidos | `kernel/ouvidos/` | Palavra de ativação (precisa de microfone no PC e das suas gravações) |
| Mente | `kernel/mente/` | Três impulsos (curiosidade, organização, social) e o diário |
| Interface | `kernel/interface/` | API local em FastAPI e a página (HTML, CSS e JavaScript puros) |

Tudo o que ele aprende e guarda fica em `dados/` (fora do Git).

## Segurança, em resumo

- Toda ação das mãos pede confirmação; abrir programa, baixar e treinar pedem sempre (está no código, a configuração não afrouxa).
- Sozinho, ele só olha, dentro das regras da seção de autonomia.
- No PC, a API exige um código que só a página recebe. Pela rede, só entra aparelho pareado e da rede local. Parear e desparear, ler o registro e ler o diário, só no PC.
- **O selo.** `kernel/seguranca/selo.json` guarda a impressão digital de todo o código que aplica as regras: a pasta `seguranca/`, a API, o freio, os reflexos, as ferramentas, a porta da internet, o explorador, o treino, as cópias, a configuração e o `__main__`. A lista está em `integridade.CRITICOS`.
- Ele confere o selo na partida e de 10 em 10 minutos. Se algo mudar, entra em **modo seguro** (sem mãos e sem autonomia) e avisa. Quando *você* editar um desses arquivos, revise e rode `python -m kernel selar`.
- O checkpoint do treino é lido só como números (`weights_only=True`). Cada checkpoint e o `modelo.npz` saem com a impressão digital ao lado, e um arquivo que não confere não é usado.

## Cópias de segurança

Uma por dia, feita pelo próprio serviço em `dados/copias/`. Ele guarda as 7 mais novas. Cada cópia leva:
- a memória, o mapa e a fila da internet;
- o estado, os aparelhos pareados, os comandos ensinados e o diário;
- o cérebro do dia a dia e o checkpoint.

Cada arquivo vai com a impressão digital, e cada banco é conferido na hora da cópia.

```
python -m kernel copia fazer | listar | conferir [NOME] | restaurar NOME | compactar
```

Restaurar só com o serviço desligado. Antes de trocar qualquer coisa, ele confere a cópia e guarda o estado atual, para dar para desfazer. O passo a passo, os cuidados e o ensaio feito com os dados reais estão em [docs/fase0/restauracao.md](docs/fase0/restauracao.md).

## Treinar o cérebro e a palavra de ativação

Pelo chat: `estuda a wikipédia` e depois `treina o cérebro por 8 horas`. Pelo terminal, passo a passo:

```
python -m kernel cerebro micrograd                 backpropagation à mão aprendendo o XOR
python -m kernel cerebro bigrama                   o modelo de linguagem mais simples
python -m kernel cerebro wikipedia --partes 1      baixa e limpa a Wikipédia PT
python -m kernel cerebro tokenizador               treina o BPE de 4096 tokens
python -m kernel cerebro preparar                  tokeniza o corpus
python -m kernel cerebro treinar --horas 8         treina o mini GPT na RX 570 (cada sessão continua de onde a outra parou)
python -m kernel cerebro avaliar                   perda, perplexidade e amostras do cérebro treinado (rápido)
python -m kernel cerebro gerar "O Brasil é"        pede um texto ao cérebro
python -m kernel cerebro verificar                 confere cada peça do pipeline e o teste de memorizar
python -m kernel cerebro protocolo                 a medida reprodutível: perda nos conjuntos fixos, n-gramas, textos, desempenho
```

**Como medir progresso de verdade.** Use o `protocolo`, não a perda que aparece no treino. Ele mede o cérebro em conjuntos fixos (`dados/cerebro/avaliacao/`) de texto que ele nunca leu, sempre do mesmo jeito: o mesmo modelo dá os mesmos números. A régua de hoje é **3,094 nats por token no teste** (1,379 bits por byte), o modelo do passo 46.000. Uma perda menor não garante texto com sentido: o protocolo guarda os textos gerados para conferir. O diagnóstico completo está em [docs/fase1/diagnostico.md](docs/fase1/diagnostico.md).

Velocidade medida neste PC (i5-2400, 12 GB, RX 570 4 GB): o `mini` (3,5 mi de parâmetros) treina a ~21 milhões de tokens por hora na placa, cerca de 7 a 8 horas para a meta padrão; o `pequeno` (17 mi) a ~5,5 milhões por hora, cerca de 8 madrugadas.

A palavra de ativação (`python -m kernel ouvidos gravar ...`) precisa de um microfone no PC.

## Ler, rodar, mudar

| Órgão | Leia | Rode | Mude e veja o que acontece |
|---|---|---|---|
| Voz | `voz/psola.py` | `pytest tests/test_psola.py` | Mude `PESO_MINIMO`, ou tire a inversão dos grãos sem voz, e ouça o chiado virar zumbido |
| Voz | `voz/difones.py` | `python -m kernel falar "bom dia" --tocar` | Zere o custo de emenda em `_custo_de_emenda` e ouça os trancos |
| Voz | `voz/sintetizador.py` | `python -m kernel falar "bom dia" --motor formantes --tocar` | Troque os formantes do "a" em `VOGAIS` |
| Voz | `voz/fonemas.py` | `pytest tests/test_voz.py -k pronuncia` | Ponha `R_NO_FIM_DA_SILABA = "r"` e ouça o sotaque mudar |
| Exploração | `exploracao/explorador.py` | observe o registro no menu ≡ | Ponha `ritmo = "intenso"` no `kernel.toml` |
| Reflexos | `nucleo/reflexos.py` | `pytest tests/test_reflexos.py` | Acrescente um jeito seu de mandar parar |
| Calculadora | `comandos/calculo.py` | `pytest tests/test_reflexos.py -k contas` | Ensine "o triplo de" |
| Enciclopédia | `conhecimento/enciclopedia.py` | `pytest tests/test_reflexos.py -k responde` | Mude `PESO_DO_TITULO` |
| Orbe | `interface/web/orbe.js` | abra a página | Crie um estado novo em `ESTADOS` |
| Cérebro | `cerebro/micrograd.py`, `gpt.py` | `python -m kernel cerebro micrograd` | Tire a máscara causal da `Atencao` |
| Comandos | `comandos/classificador.py` | `python -m kernel comandos treinar` | Ensine frases novas em `exemplos.txt` |
| Memória | `memoria/bm25.py` | `python -m kernel memoria buscar "wifi"` | Zere o `B` |
| Segurança | `seguranca/permissoes.py` | `pytest tests/test_seguranca.py` | Edite uma linha: ele sobe em modo seguro até você selar |
| Internet | `internet/rede.py` | `python -m kernel internet pesquisar "astronomia"` | Ponha um site em `sites_proibidos` e veja o registro barrar |

## Testes

```
.venv\Scripts\python.exe -m pytest
```

Mais de 350 testes: exploração (o que olha e o que nunca olha), o freio, a internet (numa internet de mentira: nenhum teste sai para a rede), contas, enciclopédia, a voz de ponta a ponta (PSOLA, alinhador e um banco de difones montado na hora), pareamento do celular, a API por HTTP de verdade, memória, segurança, mãos, o núcleo de ponta a ponta e o cérebro.

## O que ainda não existe

- **Ouvir de verdade.** Sem microfone no PC e sem modelo de reconhecimento de fala próprio. No celular, a entrada por voz é o ditado do teclado.
- **Conversar de verdade.** O cérebro não está treinado; treinado, completa texto.
- **Conexão cifrada com o celular** (HTTPS) e, com ela, captar o microfone do celular pela página.
- **Agir sozinho.** Por decisão de projeto, a iniciativa dele é olhar, perguntar e contar. Qualquer ação no PC continua passando pela sua confirmação.
- Espaço de trabalho global, estados emocionais, busca vetorial e aprendizado noturno automático: próximas rodadas do plano.
