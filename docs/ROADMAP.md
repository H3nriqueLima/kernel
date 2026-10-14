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

## Fases seguintes

A definir.
