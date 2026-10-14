# A3: o treino de 6 horas que parou aos 12 minutos

**Achado da auditoria:** em 13/10/2026, um treino de 6 horas aprovado às 23:32 terminou às 23:44, sem erro e sem motivo registrado. A saída do processo de treino não era gravada em lugar nenhum.

**Conclusão:** o treino não falhou. O serviço tinha sido iniciado de dentro do app do Claude. Quando o app se atualizou, às 23:44, o Windows fechou os processos que nasceram dele, inclusive o serviço e o treino. O treino recebeu o sinal de interrupção, salvou o checkpoint e saiu pelo caminho normal: por isso não houve erro. O defeito do K.E.R.N.E.L era não registrar por que ele parou.

## Linha do tempo

Montada a partir do registro do K.E.R.N.E.L, do `treino.csv`, dos logs do Windows e do histórico da sessão de desenvolvimento. Do registro foram lidos só o tipo e a hora de cada evento, não o conteúdo das conversas.

| Hora (13/10) | Fonte | Evento |
|---|---|---|
| 23:19:54 | registro | Serviço desligado pelo arquivo `DESLIGAR` (reinício depois das mudanças da v0.5) |
| 23:20:06 | sessão de desenvolvimento | O Claude Code inicia o serviço: `Start-Process pythonw -m kernel iniciar`, de dentro do app do Claude |
| 23:20:37 | registro | Serviço começa |
| 23:32:39 | registro | Pedido `treinar_cerebro` com `horas = 6.0` |
| 23:32:42 | registro | Confirmação; o estudo começa |
| 23:35 a 23:44:19 | registro | O laço segue normal (pesquisas, pulso) |
| 23:44:24 | registro, `treino.csv` | Fim do estudo: "Treino encerrado. parou no passo 20573". O `treino.csv` tem a linha do passo 20.573, que o treino só grava quando sai pelo caminho normal |
| 23:44:25 | registro | O serviço anuncia o fim do treino. **Depois disso, nenhuma linha até 05:30:10 de 14/10**, que é uma partida nova |
| 23:44:49 | Windows, Aplicativos | "O programa pythonw.exe parou de interagir com o Windows e foi fechado" (Application Hang, evento 1002), com o caminho do K.E.R.N.E.L |
| 23:44:49 | Windows, Aplicativos e Sistema | No mesmo segundo, o serviço do app do Claude (`CoworkVMService`) para e é reinstalado: o app do Claude estava se atualizando |
| 23:30 a 05:35 | Windows, Sistema | Nenhum desligamento, suspensão ou reinício do PC |

## Como se chega à conclusão

**1. O treino saiu pelo caminho normal.** O processo terminou com código 0 e imprimiu a frase final. Nesse caso, o laço do treino só termina de quatro jeitos:
- o tempo acabou (não: faltavam 5 h 48 min);
- a meta de passos (não: a sessão era por horas);
- o arquivo `PARAR` (não: só o serviço o cria, ao ouvir "para" ou ao desligar, e nenhum dos dois ficou registrado);
- uma interrupção de teclado (Ctrl+C) — só sobra esta.

**2. Alguém de fora fechou o serviço.** Não há linha de "desligar" no registro. O freio, o botão, o arquivo `DESLIGAR` e o encerramento normal do servidor ("servidor encerrado") sempre deixam essa linha. O Windows registrou o serviço como travado e fechado à força 25 segundos depois do fim do treino.

**3. Foi a atualização do app do Claude.** O serviço era filho do app do Claude: tinha sido iniciado por ele às 23:20. O fechamento coincide, no mesmo segundo, com a atualização do app.

Conferido em 14/10, com `IsProcessInJob` do Windows:
- o shell que o Claude Code usa para rodar comandos está dentro de um *job* do app, um grupo de processos que o Windows fecha junto;
- o serviço ligado pelo `iniciar.bat` não está, e o Explorer também não.

Um serviço lançado por aquele shell nasce dentro do job, e por isso morreu com a atualização.

Quando o Windows fecha um app para atualizá-lo, fecha junto os processos que nasceram dele:
- os programas de console, como o treino, recebem um sinal de interrupção;
- os outros, como o serviço (`pythonw`), recebem um pedido de fechamento e, se não respondem, são fechados à força.

**Grau de certeza:** alto para "fechado pelo Windows junto com o app do Claude", porque registro, eventos e horários batem ao segundo.

O sinal exato que o treino recebeu não ficou gravado: era justamente o que faltava. Mas é o único compatível com o código, e o comportamento foi reproduzido no ensaio abaixo com o sinal equivalente.

## O que mudou na 0.5.1

- **Motivo de toda parada.** O motivo (`tempo`, `meta`, `pedido` ou `interrupcao`) vai para:
  - o resumo do treino;
  - uma linha `RESUMO {...}` no fim da saída, para o serviço ler;
  - o registro (evento `treino_acabou`, com passos, segundos e horas pedidas).
- **`dados/cerebro/treino.log`.** Tudo o que o treino diz, com a hora: início (processo, horas, dispositivo), progresso, avaliações e fim, com o motivo.
- **Aviso no chat.** Ele avisa quando o treino para:
  - antes de 90% do tempo pedido, sem ninguém pedir;
  - por interrupção;
  - por um motivo desconhecido.
- **Fechar o console, sair da conta ou o sistema fechando o programa** (sinal `SIGBREAK`) agora contam como interrupção, e o checkpoint é salvo. Antes, esse sinal matava o treino na hora.
- **Na interrupção, salva antes de avaliar**, porque quem está sendo fechado tem poucos segundos.
- **Queda da partida anterior.** A partida seguinte registra que a anterior caiu sem desligar (evento `queda_anterior`, pelo `kernel.pid` que ficou para trás).
- **Regra de uso.** Inicie o serviço pelo atalho (ou pelo `iniciar.ps1`), nunca de dentro de outro programa (um terminal, o app do Claude). Ele morre junto quando esse programa fecha ou se atualiza.

## Ensaio (14/10/2026)

Rodado numa cópia dos dados, na pasta de rascunho: checkpoint real do passo 20.573, tokenizador, `val.bin` e 20 mi de tokens do `treino.bin`. O comando foi o mesmo que o serviço usa (`python -m kernel cerebro treinar --horas N`), na RX 570 pelo DirectML.

| Sessão | Como terminou | Resultado |
|---|---|---|
| 0,03 h | Pelo tempo | Motivo `tempo`; do passo 20.573 ao 20.664 em 1,9 min. O checkpoint real carregou com `weights_only=True`; a impressão `.sha256` foi gravada e o `checkpoint-anterior.pt` guardado; a linha `RESUMO` saiu certa |
| 1 h | Sinal de fechamento (`CTRL_BREAK`) depois do passo 50 | Motivo `interrupcao`; salvou o checkpoint e saiu em 1,0 s, com código 0 |
