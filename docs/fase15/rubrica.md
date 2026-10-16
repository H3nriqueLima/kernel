# Rubrica de coerência (Fase 1.5)

Cada texto gerado recebe uma nota de 0 a 2 em três critérios, julgados separadamente. A perda mede o quanto o modelo prevê bem o próximo token. Esta rubrica mede o que uma pessoa vê ao ler.

## Os 12 começos fixos

São os mesmos do protocolo (`kernel/cerebro/protocolo.py`, `COMECOS`):

| # | Começo | # | Começo |
|---|---|---|---|
| 1 | O Brasil é | 7 | Em 1500, Pedro Álvares Cabral |
| 2 | A fotossíntese é o processo | 8 | A água é uma substância |
| 3 | Albert Einstein foi um | 9 | O Sol é a estrela |
| 4 | A cidade de São Paulo | 10 | A língua portuguesa |
| 5 | A Segunda Guerra Mundial | 11 | Machado de Assis escreveu |
| 6 | O futebol é um esporte | 12 | Um computador é uma máquina |

Cada começo é continuado com 60 tokens, de dois jeitos, sempre com a mesma semente:
- **como o serviço faz:** temperatura 0,8, os 40 mais prováveis, top-p 0,92, penalidade de repetição 1,2;
- **sorteio cru:** temperatura 0,8, os 40 mais prováveis, semente 1.

## Os critérios

| Nota | Português | Assunto | Coerência |
|---|---|---|---|
| **0** | Palavras inventadas ou erros que atrapalham a leitura | Larga o assunto do começo já na primeira frase | Afirmações absurdas ou que se contradizem |
| **1** | Dá para ler, mas com erros de concordância ou palavras estranhas | Mantém parte do assunto (o mesmo campo, ou só a primeira frase) | Frases plausíveis uma a uma, mas que não formam um todo, ou fatos claramente errados |
| **2** | Gramática e palavras corretas | O texto inteiro trata do assunto do começo | O conjunto faz sentido e não afirma absurdos |

## Às cegas

1. **Embaralhar.** O script `docs/fase15/cegas.py` junta os textos dos modelos comparados e embaralha. Cada texto recebe um código (T01, T02, …). Os textos vão para `cegas.md`, sem dizer de que modelo vieram; a chave fica em `chave.json`.
2. **Dar as notas.** As notas são dadas lendo só `cegas.md` e gravadas em `notas.json`, antes de abrir a chave.
3. **Revelar.** Só então `cegas.py --revelar` junta as notas com a chave e calcula a média de cada modelo.

**Limite:** quem dá as notas é uma pessoa só (o Claude). Com a mesma rubrica, você pode dar as suas no mesmo `cegas.md`.
