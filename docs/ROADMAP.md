# Sub-roadmap: da versão auditada até a fase 4 do plano

Este é um roteiro de estabilização que corre antes da fase 4 do [plano](PLANO.md) (cérebro maior). Ele nasceu da [auditoria da versão 0.5.0](auditoria-kernel-v0.5.md). Por enquanto só a Fase 0 está definida; as fases seguintes serão descritas depois.

## Fase 0 — Consolidar e proteger a versão 0.5.0

**Situação:** concluída em 14/10/2026 com a versão 0.5.1 (branch `estabilizacao-0.5`). Veja o [fechamento](fase0/README.md).

**Objetivo:** transformar o sistema atual em uma base confiável para evoluções futuras.

**Tarefas:**

- Criar uma branch de estabilização e uma tag da versão auditada.
- Reproduzir a suíte de 332 testes e guardar o resultado inicial.
- Corrigir os problemas A1–A7 identificados no relatório, além de investigar os bloqueios do SQLite e as falhas de interpretação.
- Ampliar a proteção de integridade para os componentes críticos, proteger os checkpoints, registrar os motivos de encerramento de treinamento e criar backups testados.
- Revisar a exposição HTTP do acesso por celular e a privacidade da memória.
- Registrar as versões exatas do Python, PyTorch, DirectML e dependências.

**Entrega:** versão 0.5.1 ou equivalente, com alterações revisáveis, testes reproduzíveis e procedimentos de restauração.

**Portão de saída:** todos os problemas críticos resolvidos ou explicitamente documentados; nenhum mecanismo de parada, autenticação ou permissão enfraquecido.

O fechamento de cada tarefa, o portão de saída e os riscos aceitos estão em [fase0/README.md](fase0/README.md).

## Fase 1 — Avaliação científica do cérebro

**Situação:** concluída em 15/10/2026. Veja o [relatório de diagnóstico](fase1/diagnostico.md).

**Objetivo:** descobrir por que o modelo atual não gera texto coerente e criar uma forma confiável de medir progresso.

**Tarefas:**

- Fixar um conjunto de dados de treino, validação e teste sem sobreposição indevida.
- Medir a perda de treino e validação, perplexidade, velocidade, uso de RAM/VRAM e estabilidade.
- Verificar tokenizador, máscara causal, deslocamento dos alvos, normalização, inicialização, gradientes, otimizador e salvamento/restauração do checkpoint.
- Investigar se os 22% de processamento dos dados e o treinamento interrompido explicam parte do resultado, sem presumir que sejam a única causa.
- Guardar amostras de geração com prompts fixos e avaliar coerência, repetição e continuidade em português.
- Criar testes de sobreajuste em um conjunto minúsculo: o modelo deve conseguir memorizar deliberadamente uma amostra pequena. Isso ajuda a detectar erros no pipeline.

**Entrega:** relatório de diagnóstico e um comando de avaliação reproduzível.

**Portão de saída:** treinamento e inferência validados; o modelo consegue aprender um conjunto pequeno deliberadamente e há uma linha de base estável. Não avançar apenas porque a perda caiu.

## Fase 1.5 — Consolidar a Fase 1 e levar o mini ao seu melhor

**Situação:** concluída em 16/10/2026. Teto (provisório) do mini: 3,036 no teste fixo. Veja o [relatório](fase15/relatorio.md).

**Objetivo:** deixar o repositório fiel ao que foi feito e tirar do mini de 3,5 mi tudo o que o diagnóstico da Fase 1 mostrou que dá para tirar. O resultado é o teto do mini, a referência justa para a Fase 2.

**Tarefas:**

- Enviar ao GitHub tudo de pendente e atualizar o README.
- Continuar as sessões sem reaquecer a taxa de aprendizado: retomar de onde a sessão anterior parou, ou com taxa baixa e constante.
- Trocar o sorteio de janelas com reposição por uma passada embaralhada por documento, sem repetição.
- Subir o corte de gradiente acima da norma típica (por exemplo 3,0), para voltar a ser proteção.
- Aplicar uma mudança por vez e medir cada uma com `cerebro protocolo` no conjunto de teste fixo.
- Rodar sessões até a perda parar de cair de forma mensurável e registrar esse ponto como o teto do mini.
- Definir 12 começos fixos e uma rubrica de coerência (0 a 2 em português, assunto e coerência) e avaliar às cegas.
- Rodar `python -m kernel selar` depois de revisar, porque `cerebro/treinar.py` está no selo.

**Entrega:** `main` atualizada, relatório curto com o ganho de cada ajuste, modelo do teto do mini e pontuação à mão feita pelo Claude.

**Portão de saída:** perda no teste menor que 3,094 por mais que a variação medida entre rodadas (que foi zero, então qualquer ganho reprodutível conta), nenhum teste removido ou afrouxado, parada e checkpoint intactos. A perda cair não basta: a coerência à mão é registrada à parte.

## Fase 2 — Estudo de escala e cérebro candidato

**Situação:** concluída em 24/10/2026, **sem passar no portão**. Veja o [relatório](fase2/relatorio.md).

- **Perda: cumprido.** O tamanho grande (40,1 mi de parâmetros) fez **2,969 nats por token no teste fixo** (1,323 bits por byte), contra 3,036 do teto do mini. O pedido era 2,986 ou menos.
- **Portão técnico: cumprido.** Funciona no serviço, o NumPy confere com o PyTorch, gera 49 tokens/s na CPU e os testes não regrediram.
- **Coerência: NÃO cumprido.** Fração de textos com nota 1 ou 2: Henrique 2,1% (1 de 48) e Claude 29,2%. O pedido era 25% nos dois avaliadores. A concordância entre os dois na coerência foi quase nula (kappa de Cohen 0,08).
- **Segunda semente: NÃO verificado.** Ela foi cancelada por decisão do Henrique, para dar as horas à continuação. Por isso a repetição do ganho de perda não foi medida.
- **Assunto: não separou os modelos.** O candidato passou (60,4% e 64,6%), mas o teto do mini também passa (62,5% nos dois).
- **Português: cumprido**, sem queda contra o mini.
- **Decisão:** o candidato NÃO vira o padrão.
  - O serviço continua com o teto do mini.
  - O checkpoint do grande fica guardado em `dados/fase2/candidato/cerebro`, com os pesos (SHA-256 `79c86f63…`), o otimizador e a posição da passada.
- **Erro de conta nas duas fases:** a "porcentagem" da Fase 1.5 era de pontos (a soma das notas sobre o máximo). Os critérios da Fase 2 foram escritos como fração de textos com nota 1 ou 2, mas com os números de partida da outra conta. O relatório traz as duas contas, e a conclusão é a mesma nas duas. **A partir daqui, toda conta é fração de textos com nota 1 ou 2.**

**A resposta da fase:** de 3,5 para 40 milhões de parâmetros, a perda cai bem, mas a coerência que o Henrique vê, não.

**Nota posterior (24/10/2026, Etapa 1 da Fase 2.5):** o portão da Fase 2 continua NÃO cumprido, pelos critérios escritos naquela época. Mas os mesmos 96 textos foram pontuados de novo com a rubrica calibrada, que separa coerência interna de factualidade, e o resultado muda a leitura:
- **O grande liga melhor as frases que o mini.** No mesmo começo, modo e semente, ele ganha em coerência interna em 18 pares e perde em 4 para o Henrique (p = 0,004), e ganha em 21 e perde em 3 para o Claude (p < 0,001).
- **A factualidade ficou baixa e igual** nos dois modelos (23% a 31% dos textos com nota 1 ou 2).
- **A conclusão "a coerência não melhorou"** vinha da rubrica antiga, que misturava os dois critérios: um texto bem ligado e com fato absurdo levava 0.
- **Ressalvas:** os 27 exemplos da rubrica nova saíram desses mesmos 96 textos, e os dois avaliadores já conheciam os resultados da Fase 2 quando pontuaram de novo.
- **Os detalhes** estão em [fase25/linha-de-base](fase25/linha-de-base/).

**Objetivo:** descobrir com dados quanto de capacidade a mais compra de coerência e o que a RX 570 aguenta, antes de qualquer gasto.

**Régua:** o teto do mini, 3,036 nats por token e 1,353 bits por byte no teste fixo. O treino de todos os tamanhos usa o padrão da Fase 1.5.

**Critérios fixados antes de rodar** (propostos em 16/10/2026; só podem ser revistos antes do primeiro treino, nunca depois de ver resultados):

- **Perda:** o candidato ganha pelo menos 0,05 nat contra o teto do mini, ou seja, 2,986 nats ou menos no teste fixo, o que equivale a cerca de 0,02 bits por byte (1,33 ou menos). É 25 vezes a variação entre sementes (0,002) e mais do que uma sessão extra de treino rende. O ganho precisa se repetir na segunda semente.
- **Coerência à mão:** pelo menos 25% dos textos com nota de coerência 1 ou 2, nos dois avaliadores, com 48 textos por modelo. O mini hoje fica em torno de 10%.
- **Assunto:** pelo menos 50% dos textos com nota 1 ou 2 (hoje 35%).
- **Português:** não pode cair mais de 10 pontos percentuais em relação ao teto do mini. Na 1.5 ele caiu 13 (71% para 58%) e isso não foi explicado. Se aparecer de novo, investigar antes de seguir.

**Tarefas:**

- Definir uma interface estável do cérebro (carregar por configuração, gerar, pontuar), independente do resto do sistema.
- Medir o limite real da placa para três ou quatro tamanhos (o mini de 3,5 mi, um intermediário perto de 10 mi, o pequeno de 17 mi e, se couber, um maior). Medir tokens por segundo, VRAM, RAM e estabilidade, com testes curtos.
- Cada medida roda em processo separado, para uma não segurar a memória de vídeo da seguinte. O mini já usa 3,86 dos 4 GB, então os maiores provavelmente exigem lote menor com mais acúmulo de gradiente.
- Treinar cada tamanho com o mesmo corpus, a mesma ordem de dados e a mesma régua, e comparar de dois jeitos: mesmos tokens (eficiência por token) e mesmas horas (eficiência por hora de GPU). O orçamento de horas é combinado antes.
- Medir cada um no teste fixo, em bits por byte, contra os n-gramas e contra o teto do mini.
- Repetir o finalista com uma segunda semente, para saber o ruído daquele tamanho.
- Se houver orçamento, variar largura, profundidade e contexto separadamente no melhor tamanho, uma coisa por vez. O ganho da 1.5 veio do contexto longo.
- Montar a curva de perda por tamanho e por tokens. Dizer o que foi medido e o que é estimativa.
- Avaliação à mão: os mesmos 12 começos fixos, 48 textos por modelo, às cegas, com a rubrica de português, assunto e coerência. O Henrique e o Claude pontuam, e as notas ficam gravadas antes de abrir a chave. O teto do mini entra na mesma rodada, com os mesmos números de textos e avaliadores, para a comparação ser justa.
- Registrar no `treino.log` e no histórico do serviço os treinos feitos pela linha de comando. Hoje "como foi seu último treino?" não enxerga a corrida da 1.5.
- Experimento de corpus, separado e depois do estudo de escala: treinar o mesmo mini num corpus mais simples em português e medir. Verificar fonte e licença antes. O corpus ganha teste próprio e a Wikipédia continua como régua comum. Ganho num corpus simples não prova ganho na Wikipédia.
- Limpeza do corpus só se um resultado apontar dado ruim como causa. O diagnóstico não apontou.
- Separar a avaliação de linguagem (perda e geração) da de conversa (seguir instruções, uso de ferramentas), que fica para depois.

**Entrega:** relatório de escala com a curva e a recomendação (ficar no tamanho X, ou o próximo passo exige mais computação) e um cérebro candidato com pesos fora do Git e impressão SHA-256.

**Portão de saída:** o candidato atinge os quatro critérios acima de forma reprodutível, sem regressão nos testes e com inferência funcionando no serviço (carrega e responde pela inferência NumPy, conferida contra o PyTorch como na Fase 1) e gerando pelo menos 20 tokens por segundo na CPU.

## Fase 2.5 — Rubrica calibrada e experimento de corpus simples

**Situação:** em andamento. As Etapas 0 e 1 foram concluídas em 24/10/2026.
- **Rubrica calibrada:** [fase25/rubrica.md](fase25/rubrica.md).
- **Concordância:** o kappa de coerência interna na linha de base foi 0,638.
- **Linha de base do mini na Wikipédia,** coerência interna com nota 2: 0% para o Henrique e 2,1% para o Claude.
- **Próximo passo:** a Etapa 2, a escolha do corpus simples.

**Objetivo:** descobrir se a falta de coerência vem do corpus (a Wikipédia em pedaços de 256 tokens, difícil demais para modelos pequenos) e não só do tamanho, e calibrar a avaliação à mão para que ela meça a mesma coisa para os dois avaliadores.

**Régua:** na Wikipédia, o teto do mini (3,036 nats, 1,353 bits por byte) e o candidato grande (2,969 nats, 1,323 bits por byte). Na avaliação à mão, a linha de base nova da rubrica calibrada, pontuada na Etapa 1 sobre os 96 textos da Fase 2.

**Critérios fixados antes de rodar** (propostas de 24/10/2026, a rever só antes da Etapa 3, nunca depois de ver resultados):

- Todas as contas são fração de textos com nota 1 ou 2, 48 textos por modelo, notas de dois avaliadores gravadas antes de abrir a chave. **Exceção, só para a coerência interna:** conta a nota 2 (ver abaixo).
- Concordância: kappa de Cohen de pelo menos 0,6 em coerência interna, medido na linha de base nova. Sem isso, não se passa à Etapa 2.
- **Coerência interna (revisto em 24/10/2026, antes da Etapa 3):** pelo menos 25% dos textos com **nota 2** nos dois avaliadores.
  - **O original era:** "pelo menos 25% dos textos com nota 1 ou 2 nos dois avaliadores, e pelo menos o dobro da linha de base do mini na Wikipédia".
  - **Motivo:** na linha de base, o mini já tem ~52% com nota 1 ou 2. O dobro seria impossível, e os 25% ele já cumpria.
  - **Na nota 2, a linha de base:** o mini tem 0% e 2,1%, e o grande, 14,6% e 20,8% (Henrique e Claude). A concordância no corte de nota 2 é kappa 0,653.
  - **Este limite não será alterado depois da Etapa 3.**
- Português: no máximo 10 pontos percentuais abaixo da linha de base do mini.
- Perda no corpus simples: só relatada, sem critério de aprovação, porque a distribuição muda. Bits por byte para comparar entre tokenizadores.
- Custo na Wikipédia: relatado, sem critério.

**Tarefas:**

- Fechar a Fase 2 no ROADMAP.md (Etapa 0).
- Rubrica nova com notas separadas de coerência interna e factualidade, exemplos combinados e re-pontuação dos 96 textos da Fase 2.
- Escolher o corpus simples com fonte e licença verificadas, e aprovar desenho e orçamento antes de baixar ou treinar.
- Treinar o mini (e o médio, se couber no orçamento) no corpus simples. Medir no teste próprio e na Wikipédia.
- Avaliação às cegas com a rubrica calibrada.
- Registrar no histórico do serviço os treinos feitos pela linha de comando.

**Entrega:** relatório com a resposta direta: um corpus simples traz coerência interna que o Henrique nota, e a que custo?

**Portão de saída:** os critérios acima, de forma reprodutível. Se não passar, o resultado vale: o relatório diz que coerência não veio nem com corpus simples e apresenta os números das Fases 1, 1.5, 2 e 2.5 para a decisão sobre GPU alugada (Fase 5 do plano), sem iniciar nenhum gasto.

**Regras:** nenhum aluguel de GPU nem gasto sem a minha aprovação. Treino longo continua pedindo confirmação. Orçamento de placa aprovado por mim na Etapa 2. Mudanças em arquivos selados são revisadas e seladas por mim. Ganho num corpus simples não prova ganho na Wikipédia, e o relatório não pode dizer o contrário.

## Fases seguintes

A definir.
