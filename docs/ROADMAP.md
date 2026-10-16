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

## Fases seguintes

A definir.
