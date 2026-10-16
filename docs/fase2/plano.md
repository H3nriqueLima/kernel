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
