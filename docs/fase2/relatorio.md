# Fase 2 — Estudo de escala e cérebro candidato

K.E.R.N.E.L 0.5.1 · treinos de 16 a 18/10/2026, avaliação às cegas revelada em 24/10 · branch `estabilizacao-0.5`

**Resultado:** o tamanho **grande** (40,1 milhões de parâmetros, 12 camadas × 512) é o melhor cérebro já treinado no projeto pela perda: **2,969 nats por token no teste fixo** (1,323 bits por byte), contra 3,036 do teto do mini medido na mesma rodada. **Mas ele não passou no portão da fase: a coerência não melhorou de um jeito que um leitor note.**

| Critério | Exigência | Candidato | Situação |
|---|---|---|---|
| Perda no teste fixo | ≤ 2,986 | 2,969 | **Cumprido** (folga de 0,017; −0,067 contra o mini) |
| Repetição numa segunda semente | o ganho em 60 mi se repete | — | **Não verificado** (cancelada pelo Henrique para dar horas à continuação) |
| Coerência (nota 1 ou 2) | ≥ 25% nos dois avaliadores | Henrique 2%, Claude 29% | **Não cumprido** |
| Assunto (nota 1 ou 2) | ≥ 50% nos dois | Henrique 60%, Claude 65% | Cumprido, mas o mini também cumpre (63% nos dois) |
| Português (nota 1 ou 2) | no máximo 10 pontos abaixo do mini | 96% nos dois, contra 98% e 96% do mini | Cumprido |
| Portão técnico (serviço, NumPy contra PyTorch, ≥ 20 tokens/s, testes) | — | 49 tokens/s, 2·10⁻⁵, 375 testes | **Cumprido** |

**A pergunta da fase:** quanto de capacidade a mais compra de coerência?
- **Resposta:** nesta escala, quase nada que um leitor note. São 3,5 contra 40 milhões de parâmetros e ~111 milhões de tokens.
- **O que melhorou:** a perda caiu 0,067 e o português melhorou um pouco (a média das notas subiu nos dois avaliadores).
- **O que não mudou:**
  - o assunto ficou igual;
  - nos textos do candidato, o Henrique viu coerência em 1 de 48; nos do mini, em nenhum.
- **A Fase 1.5 já tinha mostrado o mesmo no mini:** a perda cai e o texto não ganha sentido.

O plano foi registrado num commit antes do primeiro treino ([plano.md](plano.md)). Tudo o que mudou depois está na seção "Alterações depois do registro" de lá, com data.

## A comparação de escala (60 milhões de tokens)

Os quatro tamanhos treinaram do zero do mesmo jeito:
- **dados:** o mesmo corpus, na mesma ordem (passada sem repetição, semente 1337);
- **taxa:** a mesma (sobe por 200 passos até 6e-4 e desce em cosseno até 6e-5);
- **passo:** 8.192 tokens, por 7.325 passos.

Os pesos foram guardados a cada 10 milhões de tokens e medidos depois, pelo protocolo, no teste fixo. Cada medida rodou num processo à parte.

| Tamanho | Parâmetros | Camadas × dimensão | Teste em 60 mi | Bits por byte | Contra o mini | Horas de treino |
|---|---|---|---|---|---|---|
| mini | 3,5 mi | 6 × 192 | 3,501 | 1,560 | — | 2,4 |
| medio | 11,3 mi | 8 × 320 | 3,224 | 1,437 | −0,276 | 4,9 |
| pequeno | 15,9 mi | 8 × 384 | 3,168 | 1,412 | −0,332 | 5,7 |
| **grande** | 40,1 mi | 12 × 512 | **3,052** | **1,361** | **−0,448** | 14,2 |
| *trigrama contado* | | | *3,719* | *1,658* | | |
| *teto do mini (Fase 1.5)* | 3,5 mi | 6 × 192 | *3,036* | *1,353* | | *~21 h, 524 mi de tokens* |

Todos os números de perda foram **medidos**.

![Perda no teste fixo por tokens de treino](escala/perda-por-tokens.svg)

- **Com os mesmos tokens, tamanho compra muito.** O grande em 60 milhões de tokens quase empata com o teto do mini, que leu 524 milhões. Ou seja: o mesmo resultado com ~9 vezes menos texto.
- **Não há sinal de saturação até 40 mi.** Cada aumento de tamanho ganhou em todos os marcos, desde os 10 milhões de tokens.
- **O medio e o pequeno ficam perto um do outro** (0,056 de diferença): os dois têm 8 camadas e só a largura muda. O grande é mais largo e mais fundo ao mesmo tempo, então esta comparação não separa uma coisa da outra. As variações de largura, profundidade e contexto ficaram de fora por falta de orçamento, como previsto no plano.

### A mesma conta em horas de placa

Aqui a ordem se inverte. Os números são **estimativas** (uma reta entre dois marcos medidos), com duas ressalvas:

- **Os marcos intermediários não são o fim de um treino.** Eles estão no meio do cosseno, com a taxa ainda alta; só o de 60 milhões terminou de descer a taxa. Comparar em horas iguais favorece o mini, o único que chega ao fim do cosseno nesse tempo.
- **O grande rodou com lote 2.** Com lote 4 faltou memória de vídeo (ver "O que deu errado"), e com lote 2 ele faz ~1.180 tokens/s em vez de ~1.770.

| Tamanho | Teste em 2,4 h (o tempo do mini inteiro) | Horas até a perda final do mini (3,501) |
|---|---|---|
| mini | 3,501 (medido) | 2,4 (medido) |
| medio | ~3,55 | ~2,6 |
| pequeno | ~3,63 | ~2,8 |
| grande | ~4,22 | ~6,1 |

![Perda no teste fixo por horas de placa](escala/perda-por-horas.svg)

**Leitura:** nesta placa, cada hora rende menos num modelo maior, mas o teto de um modelo maior é mais baixo. O mini precisou de ~21 h para chegar a 3,036. O grande chegou a 2,969 com ~26 h, contando a continuação. Para quem quer o melhor cérebro e não o mais barato, o maior que cabe é o certo.

### Uma lei de potência (estimativa)

Com os quatro tamanhos em 60 milhões de tokens, o ajuste é L(N) ≈ 2,835 + 1,184 · N^−0,46, com N em milhões de parâmetros. São quatro pontos para três números, então o ajuste quase não é testado. Fica como ordem de grandeza:
- um modelo de 80 milhões faria ~2,99 com os mesmos 60 milhões de tokens;
- um de 120 milhões faria ~2,97.

Nenhum dos dois cabe na RX 570: o grande já é o limite (ver a seção de memória de vídeo).

## O finalista e a continuação

- **Escolha do finalista:** a regra do plano (a menor perda em 60 milhões de tokens; um empate a menos de 0,01 iria para o menor) escolheu o grande, com 0,116 à frente do pequeno.
- **Ponto de partida:** a continuação partiu do marco de 60 milhões, do jeito registrado no plano: sem reaquecer, com taxa constante de 3e-5 e a passada seguindo de onde estava.
- **Duração:** 12,1 h, em dois trechos (5,7 h e 6,4 h), com uma pausa no meio a pedido do Henrique. Ela parou pelo fim do tempo, não por estagnação.

![O finalista do começo ao fim](escala/continuacao.svg)

| | Marco de 60 mi | Candidato |
|---|---|---|
| Passo | 7.325 | 13.500 |
| Tokens lidos | 60,0 mi | 110,6 mi |
| Teste fixo (protocolo) | 3,052 | **2,969** |
| Validação interna do treino (40 janelas) | 3,118 | 3,028 |

- **Medido e não medido:** no gráfico, a linha amarela liga medidas do protocolo. Entre 60 e 110 milhões de tokens não houve medida, só os dois pontos das pontas.
- **Validação interna:** a linha cinza é a do treino (40 janelas, porque o número de janelas acompanha o lote). Ela é a régua de bolso do treino, não a da fase.
- **O candidato** é o modelo de melhor validação interna, o passo 13.500. A continuação acabou no 13.544.
- **Tendência no fim:** a validação interna ainda caía ~0,007 por hora. O teto do grande não foi atingido (estimativa).

## O candidato contra o teto do mini

Os dois foram medidos pelo protocolo v2 na mesma rodada (`candidato/` e `teto-mini/`).

| Conjunto | Teto do mini | Candidato | Diferença |
|---|---|---|---|
| Teste fixo | 3,0360 (1,353 bits/byte) | **2,9686 (1,323)** | −0,067 |
| Validação fixa | 3,0598 | 2,9941 | −0,066 |
| Amostra já lida no treino | 3,0397 | 2,9840 | −0,056 |
| Validação antiga | 3,0481 | 2,9955 | −0,053 |

- **Ele não decorou o que leu:** no texto já lido ele faz 2,984, quase o mesmo que no nunca lido (2,969).
- **Reprodutibilidade da régua:** o teto do mini, medido de novo, deu os mesmos 3,0360 da Fase 1.5.

Perda por posição na janela:

| Posições | 1 | 2–4 | 5–16 | 17–64 | 65–128 | 129–256 |
|---|---|---|---|---|---|---|
| Teto do mini | 5,135 | 3,920 | 3,394 | 3,139 | 3,011 | 2,939 |
| Candidato | **4,935** | **3,797** | **3,339** | **3,076** | **2,948** | **2,869** |

**Ele ganha em todas as faixas, e mais no contexto curto** (−0,20 com um token só). Na Fase 1.5, mais treino no mini só melhorava o contexto longo; aqui a capacidade a mais aparece onde o mini não alcançava. Mesmo assim, com um token de contexto ele ainda perde para um bigrama contado (4,60).

**O preço:**

| | Teto do mini | Candidato |
|---|---|---|
| Geração na CPU (NumPy, um token por vez) | ~250 tokens/s | **~49 tokens/s** |
| Pesos | 13,4 MB | 152,8 MB |
| RAM de pico (protocolo) | 388 MB | 796 MB |

No serviço, o "completa: ..." do candidato levou 1,9 s, contra 0,8 s do mini.

## A segunda semente

O plano previa repetir o treino de comparação do finalista com a semente 2026 até os 60 milhões de tokens.

- **O cancelamento:** em 18/10, o Henrique decidiu cancelar essa repetição para a continuação ficar com o resto das 48 h. Ela parou no passo 1.704 de 7.325, com o checkpoint salvo (`dados/fase2/escala/grande-s2026`).
- **O único marco medido** (10 milhões de tokens):

  | Semente | Teste em 10 mi | Vantagem sobre o mini no mesmo ponto |
  |---|---|---|
  | 1337 | 4,221 | 0,299 |
  | 2026 | 4,255 | 0,265 |

- **Leitura:** nas duas sementes, o grande está bem à frente do mini. A diferença entre elas (0,034) é grande perto da margem do critério (0,05). Mas isso foi medido cedo, quando a perda ainda cai rápido, e não diz o tamanho do ruído em 60 milhões. Na Fase 1.5, no mini, sementes diferentes deram 0,002 de diferença.
- **Conclusão:** **o critério 1 está cumprido sem a repetição combinada.** Para fechá-lo, falta terminar a segunda semente: ~10,8 h de treino e ~1,5 h de medidas, retomando do checkpoint com `escala.py --tamanhos grande --semente 2026 --continuar`.

## A avaliação às cegas

- **Textos:** 96, os 12 começos fixos × 4 jeitos de gerar (o do serviço e o sorteio cru, duas sementes cada) × 2 modelos (o candidato e o teto do mini).
- **Embaralhamento:** os textos foram embaralhados com códigos em [`cegas/cegas.md`](cegas/cegas.md).
- **Rubrica:** [a da Fase 1.5](../fase15/rubrica.md).
- **Notas do Claude:** gravadas em `cegas/notas-claude.json` e num commit (`0c0e419`) antes de qualquer pessoa abrir `cegas/chave.json`. O Claude também não abriu os relatórios do candidato e do teto, onde os textos aparecem com o nome do modelo.
- **Uma ressalva:** 24 dos 48 textos do teto são idênticos aos que o Claude pontuou na Fase 1.5 (mesmo modelo, mesmos começos, mesmas sementes). Ele contou isso depois de gravar as notas. Na hora de pontuar não reconheceu nenhum com segurança, mas para ele a avaliação é às cegas só em parte.
- **Notas do Henrique:** gravadas em `cegas/notas-henrique.json` e num commit (`75f2454`) antes de abrir a chave.
- **A chave** foi aberta depois, por `cegas.py --revelar` ([resultado.json](cegas/resultado.json)).

### O resultado

Fração dos 48 textos de cada modelo com nota 1 ou 2, que é a medida dos critérios:

| Critério | Henrique: candidato | Henrique: mini | Claude: candidato | Claude: mini |
|---|---|---|---|---|
| Português | 95,8% | 97,9% | 95,8% | 95,8% |
| Assunto | 60,4% | 62,5% | 64,6% | 62,5% |
| Coerência | **2,1%** | 0% | **29,2%** | 12,5% |

O critério de coerência pedia 25% nos dois avaliadores, e o Henrique deu nota 1 a um texto só do candidato:

> **T065** · *A cidade de São Paulo*, em Portugal, é uma das mais importantes áreas da região. O município conta com as principais áreas do transporte público. É o principal centro de produção agrícola do estado. O Centro de Saúde Metropolitana de Lisboa.

O Claude deu a mesma nota a esse texto: frases que se aguentam uma a uma, com um fato errado na primeira.

### Candidato contra mini, texto por texto

Cada texto do candidato tem um par do mini com o mesmo começo, o mesmo jeito de gerar e a mesma semente. Contando em quantos pares cada um teve a nota maior:

| Critério | Henrique: candidato melhor / pior / empate | Claude: candidato melhor / pior / empate |
|---|---|---|
| Português | 15 / 9 / 24 (p = 0,31) | 15 / 6 / 27 (p = 0,08) |
| Assunto | 9 / 12 / 27 (p = 0,66) | 12 / 13 / 23 (p = 1,0) |
| Coerência | 1 / 0 / 47 (p = 1,0) | 11 / 3 / 34 (p = 0,06) |

O p é do teste do sinal, bilateral.

- **Português:** o candidato escreve um pouco melhor nos dois avaliadores, mas sem significância com 48 pares.
- **Assunto:** não muda.
- **Coerência:** para o Claude, o ganho está quase todo no jeito do serviço (46% contra 12% do mini); no sorteio cru, os dois ficam em 12%. Para o Henrique, não há ganho.

### Por que os avaliadores discordam na coerência

A concordância é boa no assunto (kappa de Cohen 0,73 em "nota 1 ou 2") e quase nula na coerência (0,08). As 19 discordâncias de coerência são todas do mesmo tipo: o Claude deu 1 e o Henrique, 0. Um exemplo é "Albert Einstein foi um dos líderes mais influentes da história da Somália...".

- **A rubrica permite as duas leituras.** Ela dá 1 a "fatos claramente errados" e 0 a "afirmações absurdas", e um fato errado desse tamanho é as duas coisas.
- **O Claude** leu como fato errado em frases plausíveis.
- **O Henrique** leu como absurdo, e só um texto em 96 escapou disso.

**Para a próxima rodada,** a rubrica precisa de exemplos combinados de cada nota antes de pontuar. A leitura que importa é a do Henrique, porque é ele quem conversa com o cérebro.

### Duas notas sobre a medida

- **O Claude mudou pouco entre as rodadas.** Ele pontuou de novo 24 textos do teto que já tinham passado por ele na Fase 1.5, sem saber quais eram. Os resultados:
  - coerência: igual em 92% dos textos (kappa 0,70);
  - assunto: igual em 88% (kappa 0,80);
  - português: igual em só 67%, e ficou mais severo (média 1,17 antes, 1,00 agora).
- **A conta da Fase 1.5 era outra.** Lá a porcentagem era de pontos: a soma das notas sobre o máximo. Os números de partida do ROADMAP vêm dela ("o mini fica em torno de 10%", "assunto 35%", "português 71% para 58%"). Os critérios desta fase pedem a fração de textos com nota 1 ou 2, e foram aplicados assim.
  - **Na conta de pontos, o resultado seria este:**

    | Critério | Henrique: candidato | Henrique: mini | Claude: candidato | Claude: mini |
    |---|---|---|---|---|
    | Português | 69,8% | 64,6% | 61,5% | 52,1% |
    | Assunto | 40,6% | 43,8% | 42,7% | 44,8% |
    | Coerência | 1,0% | 0% | 14,6% | 6,2% |

  - **A conclusão não muda.** Nas duas contas a coerência fica longe do pedido, o assunto fica igual ao do mini e o português não cai. O assunto, que passa na conta dos critérios, não passaria na de pontos; mas o mini também passa na primeira, então esse critério, do jeito que ficou escrito, não separa os dois.

A análise completa está em [analise_cegas.py](analise_cegas.py) e [cegas/analise.txt](cegas/analise.txt).

## Portão de saída

| Exigência | Situação |
|---|---|
| Perda no teste ≤ 2,986 | **Sim:** 2,969 |
| O ganho se repete numa segunda semente | **Não verificado:** cancelada por decisão do Henrique. No único ponto medido, as duas sementes ficam à frente do mini |
| Coerência ≥ 25% nos dois avaliadores | **Não:** Henrique 2,1%, Claude 29,2% |
| Assunto ≥ 50% nos dois | **Sim:** 60,4% e 64,6% (o mini também: 62,5% nos dois) |
| Português no máximo 10 pontos abaixo do mini | **Sim:** 95,8% nos dois avaliadores, contra 97,9% e 95,8% do mini |
| Sem regressão nos testes | **Sim:** 375 testes, 374 passam e 1 é pulado (o mesmo de antes: o Windows não deixa criar atalho simbólico sem ser administrador). Linhas de teste trocadas: 3, todas mais exigentes que as antigas (a contagem de textos do protocolo v2, e um teste de retomada que ficou determinístico) |
| Carrega e responde no serviço pela inferência NumPy | **Sim:** um serviço de verdade, numa porta à parte, com uma cópia do candidato. Subiu em 12,6 s e respondeu ao "completa: ..." em 1,9 s ([portao.json](portao.json)) |
| NumPy conferido contra o PyTorch | **Sim:** 1,5 a 2,4·10⁻⁵ em quatro janelas do teste fixo, o mesmo token mais provável em todas as posições |
| ≥ 20 tokens por segundo na CPU | **Sim:** 49,2 (mediana de 5 medidas de 200 tokens) |

## O cérebro candidato

- **Pesos:** `dados/fase2/candidato/cerebro/modelo.npz`, 152,8 MB, fora do Git.
- **Impressão SHA-256:** `79c86f632b9f326d9c926a78888fdf5fd7db733e0a6b80f7d485c898a5fdcad3` (também em `modelo.npz.sha256`).
- **Para continuar treinando:** o checkpoint fica na mesma pasta, com o otimizador e a posição da passada.
- **O serviço continua com o teto do mini, e recomendo que fique assim.**
  - **O que o candidato daria:** perda menor e um português um pouco melhor.
  - **O que custaria:** respostas ~5 vezes mais lentas e pesos 11 vezes maiores.
  - **O que não daria:** coerência que o Henrique note.
- **Se quiser trocar mesmo assim:** com o serviço desligado, `python -m kernel cerebro instalar --de dados\fase2\candidato\cerebro`. O comando faz uma cópia de segurança antes.

## Tempo de placa

O orçamento era de 48 h de placa, contadas desde 16/10 às 19:30. As duas pausas pedidas pelo Henrique (15 min em 17/10 e 3,5 h em 18/10) não contam. O último uso da placa acabou às 22:59 de 18/10, com ~47,7 h.

| Etapa | Horas | Previsto |
|---|---|---|
| Medidas do limite da placa e comparação dos quatro tamanhos, com as medidas | 31,5 | ~23,5 |
| Segunda semente (cancelada no passo 1.704) | 3,3 | 5 a 9 |
| Continuação do grande | 12,1 | ~15 |
| Medidas finais (os protocolos do candidato e do teto, e o marco da segunda semente) | 0,8 | ~1 |

A comparação levou 8 h a mais que o previsto. Desse total, 4,8 h vieram do grande com lote 2. O resto foi das medidas, mais lentas que o previsto (cada marco do grande leva ~13 min, e o protocolo completo dele ~27 min), e do pequeno com lote 4.

## O que deu errado

- **A conta das notas mudou de uma fase para a outra, por erro do Claude.**
  - **Na Fase 1.5:** o relatório chamou de "porcentagem" uma conta de pontos (a soma das notas sobre o máximo).
  - **Nos critérios desta fase:** eles foram escritos como fração de textos com nota 1 ou 2, com os números de partida da outra conta.
  - **Consequência:** isso só apareceu ao abrir a chave. As duas contas estão acima; a conclusão é a mesma nas duas.

- **17/10, 04:30 — falta de memória de vídeo:** o pequeno e o grande falharam logo no começo.
  - **Causa:** cada um começou no mesmo segundo em que o processo anterior terminava, antes de a placa devolver a memória.
  - **Efeito em cadeia:** o pipeline do finalista começou sozinho com só dois tamanhos prontos, escolheu o medio e lançou a segunda semente dele. Interrompi em 10 minutos.
  - **Correção:** o script espera a placa liberar entre processos e tenta de novo se faltar memória no começo. O finalista passou a exigir os quatro tamanhos.
- **O grande não coube com lote 4:** em 16/10 ele coube, mas com pico de 3,2 GB numa placa de 4 GB. Depois faltou memória três vezes.
  - Com lote 2 × 16 a conta é a mesma (8.192 tokens por passo, na mesma ordem); muda só a velocidade.
  - **Ressalva:** o grande é o maior que esta placa treina, e ainda assim no limite.
- **Pausas no meio de treinos:** parar um treino de comparação no meio recomeçava a curva da taxa. A opção nova `--sessao-desde` continua a sessão como ela seria sem a parada. Um teste mostra que parar e retomar dá os mesmos pesos de quem não parou.

## Recomendação

1. **Não instalar o candidato como padrão.** O grande fica guardado, com checkpoint, como a melhor base do projeto pela perda. Ele é o maior que a RX 570 treina (lote 2, ~1.180 tokens/s); tamanhos maiores ficariam para outra placa ou para a nuvem.
2. **Mais tamanho não é o próximo passo.**
   - **O que o tamanho comprou:** de 3,5 para 40 milhões de parâmetros, a perda caiu bem e o português melhorou um pouco, mas a coerência que o Henrique vê continuou perto de zero.
   - **O que a extrapolação promete:** 80 a 120 milhões de parâmetros dariam ~0,02 a 0,04 de perda a mais (estimativa), e as duas fases mostram que perda nesse tamanho não vira sentido.
3. **O próximo passo é o que foi deixado para depois:**
   - **O experimento de corpus:** um corpus mais simples em português, com fonte e licença verificadas antes de baixar. A Wikipédia em pedaços de 256 tokens talvez seja difícil demais para um modelo deste tamanho aprender a encadear ideias.
   - **A avaliação de conversa,** separada da de linguagem.
4. **Antes da próxima avaliação à mão, calibrar a rubrica.**
   - **O problema:** a coerência teve kappa de 0,08 entre os avaliadores.
   - **O que combinar:** exemplos de cada nota, sobretudo de como tratar fatos errados, para "1" querer dizer a mesma coisa para os dois.
   - **Os critérios da próxima fase:** escrever na mesma conta da linha de base. O assunto ≥ 50%, do jeito que ficou, o mini já cumpria.
5. **A segunda semente perdeu prioridade.** Ela confirmaria o ganho de perda (~12 h de placa), mas o candidato já não passa no portão pela coerência.
6. **Mais treino no grande ainda baixa a perda.** A validação interna caía ~0,007 por hora no fim, e a passada leu 14,4% do corpus. Pelo que as duas fases mostraram, isso não deve mudar a leitura.

## Como reproduzir

```
.venv\Scripts\python.exe docs\fase2\medir_placa.py --tamanhos mini medio pequeno grande
.venv\Scripts\python.exe docs\fase2\escala.py --tamanhos mini medio pequeno grande
.venv\Scripts\python.exe docs\fase2\finalista.py --inicio "2026-10-16 19:30" --orcamento 48
.venv\Scripts\python.exe docs\fase2\curvas.py
.venv\Scripts\python.exe docs\fase2\portao.py --modelo dados\fase2\candidato\cerebro\modelo.npz --saida docs\fase2\portao.json
.venv\Scripts\python.exe docs\fase2\cegas.py --revelar
```

- **Pausas:** com pausas, `escala.py --continuar` e `finalista.py --continuar-candidato` seguem de onde pararam, e `--inicio` vai para a frente pela duração da pausa.
- **Arquivos gerados:**
  - os relatórios de cada marco estão em `escala/<tamanho>/`;
  - todos os pontos estão em `escala/curvas.json`, cada número marcado como medido ou estimado;
  - os protocolos do candidato e do teto estão em `candidato/` e `teto-mini/`.
