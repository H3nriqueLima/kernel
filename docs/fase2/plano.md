# Fase 2: o plano, registrado antes do primeiro treino

Escrito em 16/10/2026, antes de qualquer treino da Fase 2. Os critérios e as regras abaixo não mudam depois de ver resultados. Este arquivo vai para um commit antes do primeiro treino; o histórico do Git é a prova.

## Critérios do candidato (os da fase, como combinados)

A régua é o teto do mini: **3,036 nats por token e 1,353 bits por byte** no teste fixo.

1. **Perda:** 2,986 nats ou menos no teste fixo (cerca de 1,33 bits por byte).
   - **Segunda semente (combinado em 16/10, antes do primeiro treino):** repetir a continuação longa do finalista não cabe nas 48 h. A segunda semente repete o treino de comparação do finalista, do zero até 60 milhões de tokens, com outra semente de dados e de inicialização.
   - O ganho conta como repetido se a vantagem do finalista sobre o mini, nos mesmos 60 milhões de tokens, aparecer nas duas sementes.
   - Também é preciso que a diferença entre as duas sementes seja pequena perto da margem do critério (0,05).
2. **Coerência à mão:** pelo menos 25% dos textos com nota 1 ou 2 em coerência, nos dois avaliadores (Henrique e Claude), com 48 textos por modelo.
3. **Assunto:** pelo menos 50% dos textos com nota 1 ou 2.
4. **Português:** não pode cair mais de 10 pontos percentuais em relação ao teto do mini, medido na mesma rodada.
5. **Portão:** sem regressão nos testes. O candidato funciona no serviço: carrega e responde pela inferência NumPy, conferida contra o PyTorch, e gera pelo menos 20 tokens por segundo na CPU.

## Os tamanhos e o limite da placa (medido em 16/10, `medir_placa.py`)

| Tamanho | Parâmetros | Camadas × dimensão | Lote × acúmulo | Tokens/s no treino | Geração na CPU |
|---|---|---|---|---|---|
| mini | 3,5 mi | 6 × 192 | 16 × 2 | 7.084 | 253 tokens/s |
| medio | 11,3 mi | 8 × 320 | 8 × 4 | 3.421 | 128 tokens/s |
| pequeno | 15,9 mi | 8 × 384 | 8 × 4 | 3.188 | 103 tokens/s |
| grande | 40,1 mi | 12 × 512 | 4 × 8 | 1.769 | 51 tokens/s |

Em todos: contexto de 256, vocabulário de 4.096 e 8.192 tokens por passo.

## O treino de comparação (igual para os quatro)

- **Começo:** do zero, no corpus de sempre (o `treino.bin` sem os conjuntos de teste e validação).
- **Duração:** 7.325 passos, ou **60 milhões de tokens**.
- **Sementes:** de dados 1337 (passada sem repetição, a mesma ordem para todos) e de inicialização 1337.
- **Taxa:** o padrão da Fase 1.5 numa sessão nova. Sobe por 200 passos até 6e-4 e desce em cosseno até 6e-5 no último passo, nos quatro tamanhos (a taxa não é ajustada por tamanho, para não mudar duas coisas ao mesmo tempo).
- **Resto:** decaimento 0,1 e corte em 3,0.
- **Marcos:** os pesos são guardados a cada 10 milhões de tokens (passos 1.221, 2.442, 3.663, 4.883, 6.104 e 7.325).
  - Cada marco é medido no teste fixo depois do treino, num processo separado.
  - O último (60 milhões) passa pelo protocolo completo.
  - As curvas por tokens e por horas saem desses pontos. Os pontos intermediários são do meio do cosseno, com a taxa ainda alta, e o relatório diz isso.

## O finalista e o resto do orçamento

- **Regra de escolha (registrada agora):** o finalista é o tamanho com a menor perda no teste em 60 milhões de tokens. Se dois ficarem a menos de 0,01 um do outro, vence o menor, que gera mais rápido e treina mais tokens por hora.
- **Segunda semente:** o finalista refaz o treino de comparação com semente 2026 (dados e inicialização).
- **Continuação:** o resto das 48 h vai para continuar o finalista a partir do marco de 60 milhões, com o padrão da Fase 1.5: retomar sem reaquecer, taxa baixa e constante, passada continuando de onde parou.
- **Estimativa de tempo:**

  | Etapa | Horas |
  |---|---|
  | Comparação | ~22 |
  | Segunda semente | 5 a 9 |
  | Medidas | ~1,5 |
  | Continuação | ~15 |

- **Variações:** largura, profundidade e contexto ficam de fora (não sobra orçamento).

## A avaliação à mão

- **Textos:** os 12 começos fixos, com 48 textos por modelo (o jeito do serviço e o sorteio cru, duas sementes cada).
- **Modelos:** o teto do mini e o candidato.
- **Às cegas:** os textos vão embaralhados com códigos. Os dois avaliadores gravam as notas em arquivos separados antes de abrir a chave.

## O que fica para depois

- **Experimento de corpus:** um corpus mais simples em português, depois do estudo de escala, com fonte e licença verificadas antes de baixar.
- **Avaliação de conversa:** seguir instruções e usar ferramentas, separada da avaliação de linguagem, que é o que esta fase mede.

## Alterações depois do registro

- **17/10, 04:30:** o pequeno (lote 8) e o grande (lote 4) falharam por falta de memória de vídeo logo no começo. Cada um começou no mesmo segundo em que o processo anterior terminava, antes de a placa devolver a memória. Outros programas da área de trabalho também usam ~0,6 GB dela.
  - **O pipeline do finalista** começou sozinho com só mini e medio prontos, escolheu o medio e lançou a segunda semente dele. Isso fere a regra (comparar os quatro); foi interrompido em 10 minutos, e o registro dele está em `dados/fase2/finalista-abortado.log`.
  - **Correção:** o script espera a placa liberar entre processos e tenta de novo se faltar memória no começo.
  - **Lote do pequeno:** 4 × 8 em vez de 8 × 4. São os mesmos 8.192 tokens por passo, então a conta é a mesma; muda só a velocidade (2.951 contra 3.188 tokens/s). O grande segue com 4 × 8.
  - **Ordem:** pequeno e grande rodam de novo, nessa ordem, antes da escolha do finalista. O orçamento total (48 h desde 16/10 às 19:30) não muda; a continuação do finalista fica com menos horas.
- **17/10, 10:58:** o grande com lote 4 ficou sem memória de vídeo de novo nas duas primeiras tentativas, com a placa quase livre (~0,3 GB em uso por outros programas). Na medida de 16/10 ele coube, mas com pico de 3,2 GB numa placa de 4 GB: está no limite.
  - **A terceira tentativa** (automática) usa lote 2 × 16. São os mesmos 8.192 tokens por passo, na mesma ordem, então a conta é a mesma; muda a velocidade, ~1.180 tokens/s, e o treino leva **~14 h em vez de 9,4 h**.
  - **A validação interna do treino** (a que escolhe o modelo exportado e decide parar) fica com 40 janelas em vez de 80, porque o número de janelas acompanha o lote. As medidas da comparação não mudam: são do protocolo, no teste fixo.
  - **`LOTES` do grande** passa a 2 × 16, para a segunda semente e a continuação começarem com o lote que cabe.
  - **Consequência para o orçamento:** a comparação acaba por volta das 02:15 de 18/10. Se o grande for o finalista, a segunda semente leva outras ~15 h, e quase não sobra tempo de continuação dentro das 48 h.
- **17/10, 20:31:** pausa a pedido do Henrique (a placa para jogar). O grande parou pelo pedido de parada do próprio treino, no passo 4.863 de 7.325, com o checkpoint salvo (pesos, otimizador, posição da passada). Os scripts foram desligados antes das medidas.
  - **Retomada:** `escala.py --continuar` chama o treino com `--sessao-desde 0`. A taxa, a meta e a ordem dos dados seguem como seriam sem a pausa; um teste confere que uma sessão parada e retomada termina com os mesmos pesos da que não parou. As horas dos marcos contam só o tempo de treino.
  - **Orçamento:** as 48 h são de placa, e a pausa não conta. Na retomada, o começo do orçamento é empurrado pela duração da pausa.
