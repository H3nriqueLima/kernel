# Fase 2.5, Etapa 3: o piloto de tradução (24/10/2026)

**Resultado:** o piloto parou antes da tradução de verdade, por dois motivos.
1. **Velocidade.** Na RX 570, o tradutor faz no máximo ~1,3 histórias por segundo. As 250 mil histórias levariam **~53 h**, acima das 12 h combinadas. Ficaria acima mesmo com menos histórias: 100 mil seriam ~21 h.
2. **Qualidade.** Traduzida inteira de uma vez, como foi pedido, **a história perde metade do texto**. A mediana do português tem 53% das palavras do inglês, e o que sobra vem com erros.

Pelas regras combinadas, a decisão volta para o Henrique.

## O que foi preparado (aprovado na Etapa 2)

- **Ambiente separado:** `dados/fase25/venv-traducao`.
  - `transformers` 4.46.3, `sentencepiece` 0.2.0 e dependências, com versões fixas em `dados/fase25/requisitos-traducao.txt`. Foram instalados com `--no-deps --only-binary=:all:`.
  - O `torch` e o `torch-directml` vêm do ambiente do projeto, só para leitura, por um arquivo `.pth`.
  - **O ambiente do projeto não mudou:** a lista de pacotes tem a mesma impressão MD5 antes e depois, igual à do `requirements-travado.txt`. Nenhum arquivo selado foi tocado.
- **Tradutor:** `Helsinki-NLP/opus-mt-tc-big-en-pt`, no commit `9f2863d`, licença CC BY 4.0, 291 mi de parâmetros.
  - Foram baixados só os arquivos de configuração, os `.spm`, o `vocab.json` e o `model.safetensors` (465 MB). O `pytorch_model.bin` (pickle) e o `tf_model.h5` não foram baixados.
  - Carregado com `use_safetensors=True`, sem `trust_remote_code`.
- **Dados:** TinyStories no commit `f54c09f`.
  - Os primeiros 300.000.000 bytes de `TinyStoriesV2-GPT4-train.txt`, por download parcial: **366.395 histórias inteiras**, com média de 160 palavras (mediana 144, máximo 902).
  - O `TinyStoriesV2-GPT4-valid.txt` (22,5 MB).

## As medidas

Todas são de testes curtos com as primeiras histórias do arquivo. São **medidas**; as projeções em horas são **estimativas** feitas a partir delas.

| Onde | Busca | Lote | Histórias/s | Tokens de saída/s | Observação |
|---|---|---|---|---|---|
| Placa (DirectML) | feixe de 4 | 8 | 0,14 | 2 | **saídas vazias**: a busca em feixe não funciona no DirectML |
| Placa | gulosa | 1 | 0,17 | 17 | certo |
| Placa | gulosa | 4 | 0,49 | 50 | certo |
| Placa | gulosa | 8 | 0,84 | 85 | certo |
| Placa | gulosa | 16 | 1,04 a 1,09 | 114 | certo |
| Placa | gulosa | 24 | **1,29** | 135 | o melhor |
| Placa | gulosa | 32 | — | — | faltou memória de vídeo nas histórias mais longas |
| Placa, meia precisão (fp16) | gulosa | 16 | 0,69 | — | **mais lenta** que fp32 |
| CPU (i5-2400, 4 threads) | gulosa | 8 | 0,31 | 31 | certo |

**A omissão** (lote 16 na placa, 64 histórias):
- **Palavras:** a razão entre as palavras em português e em inglês tem mediana **0,53** e mínimo 0,21; 59 das 64 histórias ficam abaixo de 0,8.
- **Frases:** são **593 em português contra 1.212 em inglês**.
- **Feixe de 4 na CPU** (3 histórias): razões de 0,52, 0,46 e 0,78. A omissão não depende da busca nem do lugar.
- **Causa provável:** o tradutor foi treinado com frases e pares curtos, e numa entrada longa ele encerra cedo.

Exemplo (o começo de uma história):

> **EN:** Sam and Ben were brothers who liked to play outside. One day, they saw a big mill near the river. The mill had a big wheel that turned with the water. Sam and Ben wanted to see the mill up close. "Let's go to the mill," Sam said. "Maybe we can find something fun inside." ...
>
> **PT:** Sam e Ben eram irmãos que gostavam de brincar lá fora. Um dia, eles queriam um moinho grande perto do rio. O moinho tinha uma roda grande que girava com a água. Eles Ben e Ben queriam ver o moinho perto. "Vamos para o moinho", Sam disse. "Talvez não possamos encontrar algo divertido dentro." ... (e depois para no meio da história)

**As etiquetas `>>por<<` e `>>pob<<`** dão o mesmo resultado nas frases de teste, ambas em português do Brasil ("O ônibus estava atrasado, então a equipe foi para casa.").

## As projeções (estimativas)

| Histórias | Tokens do K.E.R.N.E.L (estimativa: ~317 por história) | Horas na placa a 1,3 histórias/s |
|---|---|---|
| 250 mil | ~79 mi | ~53 |
| 100 mil | ~32 mi | ~21 |
| 40 mil | ~13 mi | ~8,5 |

E isso com a tradução da história inteira, que perde metade do texto. **Do jeito pedido, nenhum tamanho de corpus é ao mesmo tempo viável no tempo e bom na qualidade.**

## Tempo de placa usado

~0,25 h das 15 h aprovadas (cinco testes curtos entre 14:31 e 14:51 de 24/10). O registro está em [placa.md](placa.md).

## As saídas (para o Henrique decidir)

1. **Traduzir por trechos de frases inteiras**, sem separar frase por frase: grupos de 2 a 4 frases (até ~50 palavras), sem quebrar nenhuma frase e respeitando os parágrafos. O contexto curto (quem é "ele", o gênero) fica dentro do trecho.
   - **A medir num segundo piloto** (~0,25 h): a omissão (meta: mediana ≥ 0,9 nas palavras e o mesmo número de frases) e a velocidade. Trechos curtos fazem lotes maiores caberem na placa, então deve ser mais rápido (estimativa).
   - **Volume:** junto com isso, reduzir o corpus para ~100 mil histórias (~32 mi de tokens) e treinar os 60 mi de tokens em duas passadas.
2. **Traduzir com um modelo de linguagem grande por API**, que traduz a história inteira sem perder texto. A qualidade seria a melhor, mas **tem custo**, e os termos de uso precisam ser verificados.
3. **Gerar as histórias direto em português** com um modelo por API (a opção E da Etapa 2). Mesmo custo e mesma ressalva.
4. **Desistir do corpus traduzido** e treinar o mini só com as histórias reais e as de domínio público (~1,5 a 2,5 mi de tokens) por muitas passadas. Tem risco alto de o modelo decorar.

**Recomendação:** a saída 1, com o segundo piloto antes de qualquer tradução grande. As saídas 2 e 3 só fazem sentido se o Henrique quiser gastar.

## Licenças NC (pergunta da aprovação)

**Confirmado:** a CC BY-NC 4.0 permite copiar e adaptar para fins não comerciais, com atribuição. Usar essas histórias como teste privado do projeto cabe nisso.
- **Onde ficam:** só em `dados/`, fora do Git.
- **O que nunca acontece:** elas não entram no repositório público, não vão para o treino e não entram em nenhum uso comercial.
- **Atribuição:** o relatório vai citar as fontes.
- **Verificação:** a licença de cada história é conferida no próprio arquivo de origem antes de usar.
