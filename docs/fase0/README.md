# Fase 0: fechamento (versão 0.5.1)

**Objetivo da fase** ([sub-roadmap](../ROADMAP.md)): transformar a versão 0.5.0 numa base confiável para evoluções futuras.

**Feita em 14/10/2026**, na branch `estabilizacao-0.5`, a partir da tag `v0.5.0` (commit `3548c0b`). Cada problema virou um commit separado, para dar para revisar um de cada vez.

## Testes

| | Testes | Passaram | Falharam | Erros | Pulados | Tempo |
|---|---|---|---|---|---|---|
| [Linha de base](linha-de-base.md), 0.5.0 ([XML](testes-linha-de-base.xml)) | 332 | 331 | 0 | 0 | 1 | 108 s |
| 0.5.1 ([XML](testes-0.5.1.xml)) | 353 | 352 | 0 | 0 | 1 | 93 s |

Os 332 testes da linha de base continuam lá, e nenhum foi removido ou afrouxado. Três foram adaptados:
- os dois do selo passaram a usar o caminho relativo a `kernel/` (`seguranca/permissoes.py` em vez de `permissoes.py`), com as mesmas verificações;
- um ganhou semente fixa no sorteio, explicado abaixo.

São 21 testes novos. O pulado é o mesmo da linha de base: atalho simbólico exige administrador no Windows.

**Dois testes intermitentes da 0.5.0 foram corrigidos:**
- `test_gerar_um_pedaco_por_vez_da_a_mesma_conta` sorteava sem semente e, 1 vez em cerca de 8, parava no token de fim antes do esperado;
- `test_treinar_o_cerebro_pelo_chat` às vezes lia as falas antes da notícia do fim. O defeito era do código: o estudo se dizia livre antes de dar a notícia.

## Tarefas

| Tarefa | Situação | Onde |
|---|---|---|
| Branch de estabilização e tag da versão auditada | Feito | Tag `v0.5.0`, branch `estabilizacao-0.5` |
| Reproduzir os 332 testes e guardar o resultado | Feito | [linha-de-base.md](linha-de-base.md) |
| Versões exatas de Python, PyTorch, DirectML e dependências | Feito | [ambiente.md](ambiente.md), `requirements-travado.txt` |
| **A1:** selo cobria só 4 arquivos | Resolvido | `85673d5` |
| **A2:** HTTP sem criptografia em `0.0.0.0` com o celular ligado | Mitigado; HTTPS fica como risco aceito | `4ae2558` |
| **A3:** treino de 6 h parou aos 12 min sem motivo | Causa encontrada; motivo de toda parada registrado | `319a90d`, [investigacao-a3.md](investigacao-a3.md) |
| **A4:** privacidade (termos dos arquivos saindo, registro no celular) | Mitigado; criptografia em repouso fica como risco aceito | `4ae2558` |
| **A5:** `torch.load(weights_only=False)` | Resolvido | `319a90d` |
| **A6:** `pypdf` e `soundfile` não declarados | Resolvido | `78676f7` |
| **A7:** sem cópia de segurança nem rotação | Resolvido, com ensaio de restauração | `ee535dc`, [restauracao.md](restauracao.md) |
| **A8:** falhas de interpretação | Resolvido | `cffca3a` |
| **A9:** bloqueios do SQLite ("database is locked") | Resolvido | `5992bfe` |

### O que cada correção fez

**A1, integridade.** O selo agora cobre 20 arquivos: a pasta `seguranca/` e todo o código que aplica as regras, que são:

| Arquivo | O que aplica |
|---|---|
| `interface/api.py` | O porteiro |
| `nucleo/servico.py` | O freio, o desligar e as confirmações |
| `nucleo/reflexos.py` | O "para" |
| `nucleo/estudo.py` | O lançamento do treino |
| `maos/*` | As ferramentas |
| `internet/rede.py` | A porta da internet |
| `exploracao/explorador.py` | Até onde ele anda no PC |
| `cerebro/treinar.py` | A leitura do checkpoint |
| `copias.py` | A restauração |
| `config.py` | As regras de fábrica |
| `__main__.py` | O endereço em que o serviço escuta e o comando `selar` |

Uma ferramenta nova em `maos/` também dispara o alarme. Além da partida, o serviço confere o selo de 10 em 10 minutos. Se algo mudou, entra em modo seguro, larga a exploração em curso e avisa.

**A2 e A4, celular e privacidade.**
- **Só a rede local.** O porteiro recusa, antes de tudo, quem não é o próprio PC nem da rede local (IP privado ou link-local), mesmo com a chave de um celular pareado.
- **Registro e diário só no PC.** O registro mostra caminhos e trechos de arquivos; a página do celular esconde essas abas.
- **Aviso de HTTP sem criptografia**, na partida e na tela de pareamento.
- **Filtro nas buscas.** Com `assuntos_dos_arquivos = true`, não saem do PC:
  - nomes próprios vistos nos arquivos;
  - palavras com número;
  - o nome do usuário;
  - a lista nova `[internet] nunca_pesquisar`.

**A3, motivo de cada fim de treino.**
- **O que foi:** o treino de 13/10 foi fechado pelo Windows junto com o app do Claude, que se atualizou; o serviço tinha sido iniciado de dentro dele.
- **Onde o motivo aparece agora:** `tempo`, `meta`, `pedido` ou `interrupcao` vão para:
  - o `dados/cerebro/treino.log`;
  - a linha `RESUMO`;
  - o registro (evento `treino_acabou`).
- **Aviso no chat** quando o treino para antes de 90% do tempo sem pedido.
- **Sinal de fechamento.** O `SIGBREAK` vira interrupção e o checkpoint é salvo; antes, matava na hora.
- **Queda registrada.** A partida seguinte anota quando a anterior caiu.

**A5, checkpoints.**
- **Leitura segura:** `weights_only=True`, conferido no checkpoint real.
- **Impressão SHA-256** ao lado de cada checkpoint e do `modelo.npz`.
- **O anterior fica guardado** como `checkpoint-anterior.pt`. Checkpoint estragado ou com código dentro: volta ao anterior e avisa. Os dois estragados: para, em vez de recomeçar do zero sem você saber.
- **`modelo.npz` que não confere** não é carregado.

**A7, cópias.**
- **A cópia:** diária, com as 7 mais novas guardadas, e também pela linha de comando (`python -m kernel copia ...`).
- **Restauração com volta:** ela confere a cópia antes e faz uma cópia "antes-de-restaurar", para dar para desfazer.
- **Ensaio com os dados reais:** passou.
- **Rotação:** o `servico.log` acima de 5 MB vira `servico.log.1`, e o registro com mais de 30 dias é compactado.
- **VACUUM** pela linha de comando.

**A8, interpretação.**
- "Treine por 6 horas" passou a valer sem a palavra "cérebro".
- "Como foi seu último treino?" ganhou resposta própria.
- "O que é o Brasil?" agora fala do país: o artigo sem parênteses vem antes dos de mesmo nome.

**A9, SQLite.** Memória, mapa e fila da internet abrem em modo WAL. Reproduzido antes da correção: com um leitor de fora, a gravação falhava em 5,6 s; com WAL, passa na hora.

## Portão de saída

**Todos os problemas críticos resolvidos ou explicitamente documentados.** A auditoria não classificou nenhum problema como de severidade alta. Os três de severidade média estão assim:
- A1: resolvido;
- A2: mitigado, com o restante documentado abaixo;
- A3: causa encontrada, com o registro que faltava.

Os de severidade baixa estão resolvidos, ou mitigados com o restante documentado.

**Nenhum mecanismo de parada, autenticação ou permissão enfraquecido.** Conferido um a um:

| Mecanismo | Antes | Depois |
|---|---|---|
| "para", botão Desligar, arquivo `DESLIGAR`, `python -m kernel desligar` | Funcionam | Iguais. O treino também para salvando quando o Windows o fecha (antes morria) |
| Arquivo `PARAR` do treino | Funciona | Igual, e o motivo fica registrado |
| Porteiro da API | Host + código da sessão ou chave pareada; celular fora de `/api/celular` | Iguais, mais duas regras: só rede local; registro e diário só no PC |
| Confirmações | Toda ação das mãos; SISTEMA sempre | Iguais. "Treine por N horas" cai no mesmo pedido de nível SISTEMA, com confirmação |
| Permissões (`permissoes.py`, `maos/`) | — | Sem mudança de código |
| Modo seguro | Só na partida | Na partida e de 10 em 10 minutos, com mais arquivos selados |
| Código novo com poder de escrita | — | Ver abaixo |

Sobre o código novo com poder de escrita:
- **A cópia diária** só escreve em `dados/copias`.
- **A restauração** só roda pela linha de comando, com o serviço desligado. Antes de trocar qualquer arquivo, ela confere a cópia e guarda o estado atual. Nunca toca no `kernel.toml` nem no registro.
- **Os dois estão no selo.**

## Riscos aceitos

Documentados, não resolvidos nesta fase:

1. **O celular conversa por HTTP, sem criptografia.** O que diminui o risco:
   - só atende a rede local;
   - a chave do pareamento fica guardada como resumo;
   - o celular não pareia, não lê o registro e não lê o diário;
   - com a rede do Windows como "Pública" e sem regra para o Python, o firewall provavelmente barra a entrada.

   O HTTPS exige gerar um certificado e instalá-lo no celular: fica para uma fase futura. Enquanto isso, deixe `[celular] ligado = false` quando não usar o celular.
2. **A memória não é criptografada no disco.** Isso vale para `kernel.db`, `mapa.db`, o registro e as cópias, que guardam trechos dos seus documentos. Com 7 cópias, esses trechos existem em mais lugares.

   O Windows 10 Home não traz o BitLocker. Uma alternativa gratuita é um volume do VeraCrypt para o disco `Z:` ou para a pasta `dados`. O mínimo é uma senha na conta do Windows.
3. **Com `assuntos_dos_arquivos = true` (a sua configuração), palavras comuns dos seus arquivos continuam saindo como termo de busca.** O filtro tira nomes e números, mas não sabe o que é confidencial para você. Se houver dados de clientes, ponha as palavras sensíveis em `nunca_pesquisar` ou volte a opção para `false`.
4. **As cópias ficam no mesmo disco.** Elas protegem de erro e de banco estragado, não da perda do HD. Copie `dados/copias` para outro disco de vez em quando.
5. **O serviço morre junto se for ligado de dentro de outro programa.** É uma regra de uso: ligue pelo `iniciar.bat`.
6. **O selo é um alarme, não uma trava.** Ele percebe mudança no código, inclusive feita pelo próprio K.E.R.N.E.L, mas quem tem acesso ao disco pode selar de novo.
7. **A enciclopédia (`conhecimento.db`, 2,1 GB) fica fora das cópias e do modo WAL.** Ela é refeita com "estude a Wikipédia".
8. **Restaurar com outra configuração apaga leituras.** A faxina de partida esquece o que ficou fora das pastas liberadas. O cuidado está em [restauracao.md](restauracao.md).
9. **Itens só informativos da auditoria, sem mudança nesta fase:**
   - **A10:** o cérebro não passou do portão da fase 1;
   - **A11:** "abrir programa" alcança qualquer atalho do Menu Iniciar, sempre com confirmação.

## Como reproduzir

- Ambiente: [ambiente.md](ambiente.md) (`pip install -r requirements-travado.txt`).
- Testes: `.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs --junitxml=saida.xml`.
- Ensaio do treino (fim por tempo e por sinal de fechamento, na RX 570): [investigacao-a3.md](investigacao-a3.md).
- Ensaio de restauração com os dados reais: [restauracao.md](restauracao.md).

## O que muda no dia a dia

- **Ligue o serviço pelo `iniciar.bat`.**
- **Arquivos novos ao lado dos bancos.** Na primeira partida da 0.5.1, os bancos passam para o modo WAL, e aparecem arquivos `-wal` e `-shm` ao lado deles. É normal.
- **Cópias.** A primeira cópia (manual) foi feita em 14/10 às 20:15, durante o ensaio. A diária começa sozinha 24 h depois dela. Para ver as cópias: `python -m kernel copia listar`.
- **Treino.** Se um treino parar antes da hora, ele avisa no chat e diz o motivo. Para perguntar depois: "como foi seu último treino?".
- **Depois de editar código.** Quando você mudar um dos arquivos selados, rode `python -m kernel selar`. A suíte de testes também avisa (`test_o_selo_do_projeto_esta_integro`).
