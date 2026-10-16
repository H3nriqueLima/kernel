# Fase 1.5 — O mini no seu melhor

K.E.R.N.E.L 0.5.1 · 15 e 16/10/2026 · branch `estabilizacao-0.5`

**Resultado:** o teto (provisório) do mini de 3,5 milhões de parâmetros mede **3,036 nats por token no teste fixo** (1,353 bits por byte). O modelo que o serviço usava media 3,094.

- **Ganho:** 0,058. A variação entre rodadas é 0,002, então o ganho é cerca de 26 vezes maior que ela.
- **Reprodutível:** duas medidas do mesmo modelo deram relatórios idênticos.
- **A leitura não melhorou.** Avaliados às cegas, os textos do teto e do modelo antigo empatam no assunto (35%) e na coerência (6% contra 8%). A perda caiu; a coerência, não.

O teto já é o cérebro do serviço; o anterior está na cópia de segurança `2026-10-16_064006-manual`.

## O ganho de cada ajuste

Todos os braços partem do mesmo checkpoint: o passo 49.039, assentado com a taxa baixa, que mede 3,110 no teste.

Cada braço é uma sessão de treino de verdade (`cerebro treinar`) de 1.100 passos, ou ~9 milhões de tokens. No fim, os pesos do último passo são medidos pelo protocolo no teste fixo.

Cada braço muda uma coisa em relação ao anterior:

| Braço | O que muda | Teste | Validação | Ganho |
|---|---|---|---|---|
| A0 | O jeito antigo: cada sessão reaquece a taxa até 3e-4 | 3,1012 | 3,1269 | — |
| A1 | **Retomar sem reaquecer** (taxa constante de 3e-5) | 3,0809 | 3,1058 | **−0,0203** contra A0 |
| R | A1 com outra semente de dados | 3,0830 | 3,1076 | Variação entre rodadas: **0,0022** |
| A2 | + **passada sem repetição** | 3,0752 | 3,0992 | **−0,0057** contra A1 (~2,6 vezes a variação) |
| A3 | + **corte de gradiente em 3,0** | 3,0752 | 3,0993 | 0,0000 contra A2 |

Os três ajustes viraram o padrão do treino, cada um no seu commit, com o ganho na mensagem:

- **Retomar** é o ganho grande. Reaquecer custava ~0,02 a cada sessão nova, e sessões curtas saíam no prejuízo.
- **A passada** dá um ganho pequeno, mas mensurável. Ela lê o corpus inteiro sem repetir, guarda a posição no checkpoint e custa 1,5 GB de RAM durante o treino. Com a mesma quantidade de passos, o que mais conta é a taxa: o mini quase não decora o que lê (ver a Fase 1), então reler custa pouco.
- **O corte em 3,0** não muda a perda, como era de esperar com o Adam, que já normaliza a escala. Ele fica pelo motivo pedido: a norma típica é ~1,85. Com o corte em 1,0, 100% dos passos eram cortados; em 3,0, 0% dos passos normais são cortados, e só um pico seria.

## A corrida até o teto

A corrida partiu do fim do A3 (passo 50.139), com os três ajustes:
- duração: 4,8 h, 14.684 passos (~120 milhões de tokens);
- critério de parada: se a validação não melhorasse 0,002 em 6 medidas seguidas (~1 h).

| Hora | 01:48 | 02:47 | 03:46 | 04:45 | 05:43 | 06:13 | 06:29 (fim) |
|---|---|---|---|---|---|---|---|
| Validação fixa | 3,120 | 3,106 | 3,096 | 3,093 | 3,087 | **3,085** | 3,087 |

**O critério de parada não disparou.** Na última hora a validação ainda caía ~0,003 por hora (24 milhões de tokens), e o tempo combinado acabou antes. Por isso é um **teto provisório**: a perda ainda cai, mas a passos cada vez menores, e a leitura dos textos não acompanha (seção abaixo). A passada leu 16,8% da época; o checkpoint guarda a posição, e os próximos treinos do serviço continuam dali.

O modelo do teto é o de melhor validação (passo 64.000), medido pelo protocolo:

| | Modelo antigo (passo 46.000) | **Teto** |
|---|---|---|
| Teste | 3,0939 | **3,0360** |
| Bits por byte (teste) | 1,3792 | **1,3533** |
| Validação | 3,1156 | 3,0598 |
| Amostra já lida | 3,0866 | 3,0397 |

O ganho veio do contexto longo. Perda por posição na janela:

| Posições | 1 | 2–4 | 5–16 | 17–64 | 65–128 | 129–256 |
|---|---|---|---|---|---|---|
| Modelo antigo | 5,146 | 3,967 | 3,455 | 3,199 | 3,069 | 2,997 |
| Teto | 5,135 | 3,920 | 3,394 | 3,139 | 3,011 | 2,939 |

Com um token de contexto, quase nada mudou (5,15 contra 5,14), e o modelo continua pior que um bigrama contado (4,60). O limite de capacidade visto na Fase 1 continua lá.

## A coerência, à mão e às cegas

- **Rubrica:** português, assunto e coerência, de 0 a 2 cada ([rubrica.md](rubrica.md)).
- **Começos:** os 12 fixos do protocolo.
- **Textos:** dois por começo e por modelo (do jeito do serviço, e sorteio cru), 48 no total, embaralhados com códigos (`cegas/cegas.md`).
- **Ordem:** as notas foram gravadas (`cegas/notas.json`) antes de abrir a chave (`cegas/chave.json`).

| Critério | Modelo antigo | Teto |
|---|---|---|
| Português | 34/48 (71%) | 28/48 (58%) |
| Assunto | 17/48 (35%) | 17/48 (35%) |
| Coerência | 3/48 (6%) | 4/48 (8%) |

**Leitura:** nenhuma melhora visível. Com 24 textos por modelo e um avaliador só, diferenças de alguns pontos não querem dizer nada. O que dá para afirmar é que a queda de 0,058 na perda não virou texto com sentido.

**A avaliação foi às cegas só em parte:** eu já tinha lido, na Fase 1, os 24 textos do modelo antigo e reconheci alguns. Com a mesma rubrica, você pode dar as suas notas no mesmo `cegas.md`.

## Portão de saída

| Exigência | Situação |
|---|---|
| Perda no teste menor que 3,094 por mais que a variação entre rodadas | **Sim:** 3,036, ganho de 0,058. A variação medida entre sementes é 0,002; o mesmo modelo medido duas vezes dá o mesmo número |
| Nenhum teste removido ou afrouxado | **Sim:** eram 360, agora 365. As únicas mudanças em testes são um arquivo novo (`tests/test_treino.py`), sem nenhuma linha removida dos antigos |
| Parada e checkpoint intactos | **Sim.** As proteções do checkpoint não mudaram: impressão digital, cópia anterior e leitura só de números. A parada também não mudou: arquivo `PARAR`, desligar e o sinal do Windows. No uso real, em 15/10 às 22:46, "para o treino" salvou e saiu certo |
| A perda cair não basta: coerência registrada à parte | **Sim:** registrada, e não melhorou |

## Tempo de placa

Cerca de 7,6 h das 8 combinadas:

| Etapa | Tempo |
|---|---|
| Comparações (cinco braços de ~26 min, com a medida) | ~2,2 h |
| Meia hora perdida (ver abaixo) | ~0,5 h |
| Corrida até o teto | 4,8 h |
| Medidas finais | ~0,1 h |

**A meia hora perdida foi erro meu.** O primeiro script das comparações media cada braço na placa e continuava segurando a memória de vídeo. O braço seguinte treinou oito vezes mais devagar até eu perceber. Corrigido: a medida roda em outro processo.

## O que fica para a próxima fase

- **O mini está perto do teto.** Mais horas de treino ainda baixam a perda, ~0,003 por hora no fim, mas não melhoram o texto.
- **O próximo salto é um modelo maior.** Essa é a fase 4 do [plano](../PLANO.md) e depende da sua permissão. A régua para ele é o teto do mini: **3,036 no teste fixo, 1,353 bits por byte.**
- **O histórico do serviço não mostra a corrida do teto.** Como ela rodou pela linha de comando, a pergunta "como foi seu último treino?" ainda responde sobre a última sessão pelo serviço (22:46 de 15/10). O `treino.csv` e o `treino.log` do serviço receberam as linhas do A3 e do teto.

## Como reproduzir

```
.venv\Scripts\python.exe docs\fase15\ablacao.py --checkpoint dados\fase1\checkpoint-49039.pt --passos 1100 "A1=--ao-continuar retomar" ...
.venv\Scripts\python.exe docs\fase15\teto.py --braco A3 --horas 4.8
.venv\Scripts\python.exe -m kernel cerebro protocolo --modelo dados\cerebro\modelo.npz
.venv\Scripts\python.exe docs\fase15\cegas.py --montar base=... teto=...   (e depois --revelar)
```

Os relatórios do protocolo de cada braço estão em `bracos/` e o do teto em `teto/`.
