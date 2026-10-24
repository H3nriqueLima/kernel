# Fase 2.5, Etapa 2: o corpus simples (proposta para aprovação)

Escrito em 24/10/2026. Nada foi baixado nem treinado, e a placa não foi usada. As fontes foram consultadas na web nesse dia.

## Os candidatos

| | A. TinyStories traduzido aqui | B. Histórias infantis de licença aberta | C. Literatura infantil em domínio público | D. Ririro | E. Histórias geradas por um modelo em português |
|---|---|---|---|---|---|
| **Fonte** | [TinyStories](https://huggingface.co/datasets/roneneldan/TinyStories): histórias em inglês geradas pelo GPT-3.5 e pelo GPT-4 com o vocabulário de uma criança de 3 a 4 anos. A versão V2 tem só as do GPT-4. A tradução seria feita aqui com o [Opus-MT tc-big en→pt](https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-en-pt) | [StoryWeaver](https://storyweaver.org.in), [African Storybook](https://www.africanstorybook.org), [Storybooks Brasil](https://global-asp.github.io/storybooks-brasil/) e o [GlotStoryBook](https://huggingface.co/datasets/cis-lmu/GlotStoryBook), que reúne essas coleções | Monteiro Lobato (obra infantil), Júlia Lopes de Almeida (*Era uma vez...*), Guerra Junqueiro, traduções antigas de Grimm, *Através do Brasil*; no [Wikisource](https://pt.wikisource.org/wiki/Categoria:Literatura_infantil) e no [Projeto Gutenberg](https://www.gutenberg.org) | [ririro.com](https://www.ririro.com) | O Claude (ou outro modelo) escrevendo histórias simples direto em português |
| **Licença, e se permite treinar** | Dados: CDLA-Sharing 1.0, que permite usar e treinar; se o corpus traduzido for publicado, ele vai sob a mesma licença. Tradutor: CC BY 4.0, que pede atribuição | CC BY 4.0 na maior parte, que permite; **algumas histórias são CC BY-NC**, e é preciso filtrar história por história | Domínio público. Lobato entrou em 1º/1/2019 no Brasil (70 anos após a morte, em 1948). Só o texto original: as adaptações recentes das editoras têm direitos próprios | **Sem licença clara.** O site é "grátis para ler", e não há permissão escrita para reproduzir ou treinar | Depende dos termos do provedor sobre usar as respostas para treinar modelos; **precisa ser verificado** antes |
| **Tamanho** | 2,1 a 2,7 milhões de histórias em inglês, muito mais do que o necessário. Proposta: traduzir ~250 mil, o que dá **~60 a 75 mi de tokens** em português (estimativa) | Pequeno. Na parte em português do [BabyBabelLM](https://arxiv.org/html/2510.10159v1), as histórias e a wiki infantil somam **~0,38 mi de tokens**; o Storybooks Brasil tem 40 histórias | Pequeno: cerca de **1 a 2 mi de tokens** (estimativa; não contei) | — | O quanto se pagar |
| **Qualidade da língua** | **Tradução automática**: o tradutor faz BLEU ~50 no FLORES en→pt, bom mas com erros. Os nomes ficam em inglês (Lily, Tom), e há risco de "traduzês" e de erro de gênero nos pronomes | Texto original ou traduzido por pessoas (cada história traz "Texto de" e "Tradução de"), português de Moçambique, Angola e Brasil | Português original, mas antigo (grafia de 1900 em parte: "Paschoa", "Perolas") e com vocabulário mais difícil | — | Português nativo, vocabulário controlável |
| **Riscos** | Traduzês. Histórias geradas pelo GPT (zona cinzenta dos termos da OpenAI para quem gerou). Variante do português incerta (o tradutor tem `>>por<<` e `>>pob<<`). Precisa da placa para traduzir (ver o orçamento) | Pequeno demais para treinar; licenças misturadas | Pequeno demais; trechos racistas conhecidos em Lobato; grafia antiga | Sem licença: **não serve** | Gasto, que pede a sua aprovação; termos de uso |

**Leitura:** nenhum corpus simples de **texto original em português** com licença aberta tem tamanho para treinar sozinho (B e C ficam abaixo de 2 milhões de tokens). O único com volume é o A, que é tradução automática. Não achei um TinyStories em português pronto: a busca no Hugging Face trouxe versões em vietnamita, alemão, francês, turco, coreano e outras línguas, mas nenhuma em português.

## A proposta

**Treinar com o A** e usar o B como um teste de histórias reais escritas ou traduzidas por pessoas. Assim dá para ver se o que o modelo aprendeu na tradução vale para o português de verdade.

- **O C fica para depois.** Ele serve como um segundo teste, ou para um ajuste fino.
- **O D está descartado** por falta de licença.
- **O E só entra se você quiser gastar**, e depois de conferir os termos de uso.

## O tokenizador

**Proposta: manter o BPE atual, de 4.096 tokens, treinado na Wikipédia.**

- **A medida:** num trecho de história simples que eu escrevi (112 palavras), ele usou **1,81 tokens por palavra**, contra 1,91 no teste fixo da Wikipédia. Em bytes por token, a história dá 2,77 contra 3,38, mas a diferença vem só de as palavras serem mais curtas. **É uma indicação, não uma medida firme**: a amostra é pequena e foi escrita por mim. Vou medir de novo no corpus traduzido.
- **Por que não treinar um tokenizador novo:** um tokenizador novo comprimiria melhor as histórias, mas mudaria duas coisas ao mesmo tempo (o corpus e o tokenizador). Também deixaria a perda na Wikipédia sem comparação direta em nats por token. Fica como uma variação para depois, se o resultado pedir.
- **As comparações saem em bits por byte** em todos os conjuntos de qualquer jeito, como você pediu.

## O desenho

- **Modelo:** o **mini** de 3,5 mi, do zero, com o padrão da Fase 1.5 (passada sem repetição, corte em 3,0), por **60 mi de tokens** (7.325 passos, como na comparação da Fase 2).
  - **A comparação por tokens:** o mini da Wikipédia com os mesmos 60 mi de tokens já está medido (3,501 no teste fixo).
  - **O médio** (11,3 mi) entra só se sobrar orçamento.
- **Corpus:** ~250 mil histórias do TinyStories V2 (só as do GPT-4), traduzidas.
  - **De onde vêm:** os primeiros ~300 MB do arquivo de treino, baixados por pedido parcial, sem baixar os 2,23 GB inteiros.
  - **Conjuntos fixos:** teste (~2 mi de tokens) e validação (~1 mi) com histórias que o treino nunca lê, separadas por documento, com a mesma regra dos conjuntos fixos da Fase 1.
- **O que se mede** (perda e bits por byte em cada um):
  1. o teste próprio, de histórias traduzidas;
  2. o teste de histórias reais (B), se você aprovar o download, que é pequeno;
  3. **o teste fixo da Wikipédia**, que é o custo da troca de corpus.
- **Avaliação às cegas:**
  - **Começos:** 12 começos novos, de histórias (abaixo). São diferentes dos da Wikipédia porque "O Brasil é..." não é começo de história, e um corpus de histórias não aprende a continuar verbetes.
  - **Comparação com o mini da Wikipédia:** o mini das histórias e o teto do mini respondem aos 12 começos novos, 48 textos cada.
  - **Os 12 começos antigos:** o mini das histórias também responde a eles (48 textos), para comparar com a linha de base que já existe.
  - **Total:** 144 textos por avaliador.
  - **O critério de coerência interna** (nota 2, ≥ 25% nos dois avaliadores) é medido nos 48 textos do mini das histórias com os começos de história.
- **Os 12 começos de história (proposta):** "Era uma vez uma menina chamada Lia", "Era uma vez um cachorro", "O menino Pedro foi ao parque", "Um dia, a mãe de Ana", "O gato estava com fome", "Tom e Sara acharam uma caixa", "A pequena tartaruga", "No aniversário de Ben", "O passarinho azul queria voar", "Lucas tinha medo do escuro", "A vovó fez um bolo", "Era uma vez um trem". Metade dos nomes é em português e metade é dos que o TinyStories usa.
- **Os treinos pela linha de comando** já vão para o histórico do serviço desde a Fase 2 (evento `treino_acabou`, com origem "linha de comando").

## O orçamento (estimativas)

As velocidades medidas: o mini faz ~25 mi de tokens por hora (2,4 h para 60 mi) e o médio, ~12 mi por hora (4,9 h).

| Etapa | Horas de placa | De onde vem a conta |
|---|---|---|
| Piloto da tradução (1.000 histórias): mede a velocidade e a qualidade | ~0,5 | estimativa |
| Tradução de ~250 mil histórias | **4 a 10** | **estimativa; o piloto decide.** Na CPU (i5-2400) seriam centenas de horas. Se o piloto indicar mais de 12 h, eu volto antes de seguir |
| Mini, 60 mi de tokens, com as medidas | ~3 | medido na Fase 2 |
| Geração dos textos e protocolos | ~0,5 | medido na Fase 2 |
| **Total sem o médio** | **~8 a 14** | |
| Médio, 60 mi de tokens, com as medidas (opcional) | ~5,5 | medido na Fase 2 |
| **Total com o médio** | **~13,5 a 19,5** | |

**Peço um teto de 15 h** sem o médio, ou de 20 h com o médio.

## O que precisa da sua aprovação antes de baixar

1. **Os primeiros ~300 MB** de `TinyStoriesV2-GPT4-train.txt`, por pedido parcial do arquivo, e o `TinyStoriesV2-GPT4-valid.txt` (22,5 MB).
2. **O tradutor** `Helsinki-NLP/opus-mt-tc-big-en-pt` (~0,2 bilhão de parâmetros, de 0,5 a 0,9 GB).
3. **Bibliotecas novas** (`transformers` e `sentencepiece`), num ambiente Python **separado**, em `dados/fase25/`, para não entrarem no K.E.R.N.E.L. O tradutor é uma ferramenta de preparo dos dados: o cérebro continua escrito à mão.
4. **As histórias reais em português** (B), com só as de licença CC BY: poucos MB.

## Como a rubrica se aplica a histórias

Numa história inventada, a factualidade perde o sentido: um gato que fala não é um erro. **Proposta:** nos textos com começo de história, a factualidade dá lugar à **consistência**. Nos textos com os 12 começos da Wikipédia, a factualidade continua, para comparar com a linha de base. Português, assunto e coerência interna ficam como estão.

**Consistência:** os nomes, os personagens, os lugares e as coisas se mantêm ao longo do texto.

| Nota | Consistência |
|---|---|
| **2** | Quem aparece continua o mesmo do começo ao fim: o nome não muda, a mãe continua mãe, o gato continua gato, os pronomes apontam para o personagem certo, e nenhum detalhe contradiz o que foi dito antes. Um texto com um personagem só, que não muda, também é 2 |
| **1** | Um deslize: um nome troca uma vez, um pronome aponta para o personagem errado, ou um detalhe contradiz o que foi dito (o gato branco vira preto) |
| **0** | Nada se mantém: cada frase traz outro personagem, os nomes trocam o tempo todo, ou não há nenhum personagem nem lugar que dure (só repetição ou letras soltas também é 0) |

**Exemplos.** Ainda não há histórias geradas pelos nossos modelos, então **estes exemplos foram escritos por mim, para ilustrar a regra**. Na Etapa 3, antes da avaliação às cegas, troco por 3 a 5 exemplos reais de cada nota. Eles virão de textos gerados com outras sementes, fora dos 144 avaliados, para que nenhum texto pontuado sirva de exemplo.

- **Nota 2:**
  - "Era uma vez uma menina chamada Lia. Ela tinha um gato branco. Um dia, o gato subiu na árvore. Lia chamou a mãe, e a mãe trouxe uma escada."
  - "O menino Pedro foi ao parque com o pai. Pedro chutou a bola, e o pai pegou. Os dois riram e voltaram para casa."
  - "Tom era um cachorro grande. Ele gostava de correr no quintal. Um dia, Tom achou um osso e o enterrou perto da árvore."
- **Nota 1:**
  - "Era uma vez uma menina chamada Lia. Ela tinha um gato branco. Um dia, **Ana** subiu na árvore para pegar o gato." (o nome troca)
  - "O menino Pedro foi ao parque com o pai. **Ela** chutou a bola, e o pai pegou." (o pronome aponta errado)
  - "Tom tinha um balão vermelho. Ele brincou com o balão **azul** o dia todo." (o detalhe contradiz)
- **Nota 0:**
  - "Lia tinha um gato. O cachorro de Pedro foi à escola. A mãe de Ben comprou um bolo. Sara dormiu no carro." (cada frase com outro personagem)
  - "O gato era a menina. A menina era o parque. O parque foi para casa com o gato." (nada se mantém)
  - "Era uma vez um. Um um um um." (só repetição)

**Como fica com a coerência interna:** as duas são independentes. "Lia chamou a mãe. **Ana** trouxe uma escada e pegou o gato." tem coerência interna 2, porque as frases seguem uma linha, e consistência 1, porque o nome troca.

## O que este experimento pode e não pode dizer

- **O que pode:** se um mini treinado em histórias simples escreve textos com coerência interna que o Henrique nota, comparado ao mini da Wikipédia com os mesmos começos.
- **O que não pode:** dizer que isso melhora a Wikipédia. **Ganho num corpus simples não prova ganho na Wikipédia**, e o relatório não vai dizer o contrário. O custo na Wikipédia é medido e relatado.
- **Limite da tradução:** se o corpus for o traduzido, um bom resultado pode ser em parte "traduzês". O teste com histórias reais (B) existe para medir isso.
