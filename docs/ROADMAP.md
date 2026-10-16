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

**Situação:** em andamento (desde 16/10/2026), autorizada para ir além do mini, com até 48 h de placa. Os resultados ficam em [fase2/](fase2/).

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

## Fases seguintes

A definir.
