# Cópias de segurança e restauração

A partir da 0.5.1, o próprio serviço faz uma cópia de segurança por dia em `dados/copias/` e guarda as 7 mais novas. Este documento diz:
- o que entra na cópia;
- como conferir uma cópia;
- como voltar a ela;
- como foi o ensaio de restauração.

## O que entra e o que fica de fora

| Entra | Por quê |
|---|---|
| `kernel.db` (memória), `mapa.db` (o que ele viu no PC) e `internet.db` (fila de pesquisa) | Copiados pelo próprio SQLite. A cópia sai inteira mesmo com o serviço gravando, e cada banco copiado é conferido (`PRAGMA integrity_check`) |
| `estado.json`, `aparelhos.json`, `comandos/` e `diario/` | O estado da mente, os celulares pareados, os comandos ensinados e o diário |
| `cerebro/modelo.npz`, `tokenizador.json`, `checkpoint.pt` e as impressões `.sha256` | O cérebro do dia a dia e o ponto de onde o treino continua |
| `lembranca/kernel.toml` | Só como lembrança da configuração daquele dia. **Restaurar nunca sobrescreve o seu `kernel.toml`** |
| `manifesto.json` | Cada arquivo com tamanho e impressão digital (SHA-256), e o resultado da conferência dos bancos |

| Fica de fora | Como refazer |
|---|---|
| `conhecimento.db` (a enciclopédia, 2,1 GB) | Diga "estude a Wikipédia" (leva horas) |
| `cerebro/corpus.txt`, `treino.bin`, `val.bin` e `wiki/` | `python -m kernel cerebro preparar` (a partir do corpus) ou "estude a Wikipédia" |
| `voz/` (banco de difones) | `python -m kernel voz baixar` e `python -m kernel voz construir` |
| `registro/` | De propósito: o registro só cresce e nunca volta no tempo. Os dias com mais de 30 dias são compactados (`.jsonl.gz`) e continuam legíveis |

Uma cópia com cérebro ocupa cerca de 146 MB. As 7 juntas, cerca de 1 GB.

## Quando as cópias são feitas

- **Diária:** na primeira volta do laço depois de 24 h da última cópia. Durante um treino, o cérebro fica de fora (o checkpoint é regravado a toda hora) e entra na cópia do dia seguinte. Para desligar a cópia diária: `[copias] diaria = false` no `kernel.toml`. Para guardar mais ou menos cópias: `manter = N`.
- **Na hora:** `python -m kernel copia fazer`, que pode rodar com o serviço ligado.
- **Antes de restaurar:** o estado atual vira uma cópia "antes-de-restaurar", para dar para desfazer.

Uma cópia só aparece na lista quando terminou inteira: ela é montada numa pasta temporária (`.NOME.parcial`) e só ganha o nome final no fim. Uma sobra de cópia interrompida é apagada na cópia seguinte.

## Comandos

```
python -m kernel copia fazer              faz uma cópia agora
python -m kernel copia listar             as cópias, da mais nova para a mais antiga
python -m kernel copia conferir [NOME]    confere as impressões e os bancos (todas, se não der o nome)
python -m kernel copia restaurar NOME     volta os dados para os da cópia (serviço desligado)
python -m kernel copia compactar          VACUUM nos bancos (serviço desligado)
```

## Restaurar, passo a passo

1. Desligue o serviço: `python -m kernel desligar` (ou o botão Desligar). A restauração se recusa a rodar com ele ligado.
2. Veja as cópias: `python -m kernel copia listar`.
3. Confira a escolhida: `python -m kernel copia conferir NOME`. Precisa dizer "inteira".
4. Restaure: `python -m kernel copia restaurar NOME`. Ele confere de novo, faz a cópia "antes-de-restaurar" e só então troca os arquivos.
5. Ligue o serviço **pelo atalho**.

**Para desfazer:** restaure a cópia "antes-de-restaurar" que o passo 4 indicou.

Se a cópia não confere (um arquivo mudou ou um banco está estragado), nada é mexido e ele diz o que está errado. Escolha outra cópia.

## Cuidados

- **Restaure com o mesmo `kernel.toml`.** Na partida, a faxina esquece o que ficou fora das pastas liberadas. Se você restaurar com uma configuração mais fechada que a da cópia, as leituras dos arquivos que ficaram de fora saem da memória. Isso aconteceu no ensaio, de propósito: 29 leituras. A configuração do dia está em `lembranca/kernel.toml`, dentro da cópia, para comparar.
- **Não copie só o arquivo `.db` com o serviço ligado.** Os bancos estão em modo WAL: as últimas gravações podem estar no `.db-wal` ao lado. Use `copia fazer`.
- **As cópias ficam no mesmo disco.** Elas protegem de banco estragado, arquivo apagado sem querer e treino que piorou o cérebro, mas não de perder o HD. De vez em quando, copie a pasta `dados/copias` (ou só a cópia mais nova) para outro disco ou pendrive.
- **Arquivos que surgiram depois da cópia** (um dia novo do diário, por exemplo) ficam onde estão: a restauração sobrescreve, não apaga.

## Só o cérebro

- **Checkpoint estragado:** o treino percebe sozinho. A impressão `.sha256` não confere, ou o arquivo não é só números. Ele volta para o `checkpoint-anterior.pt` e avisa no `treino.log`. Se os dois estiverem estragados, ele para em vez de começar do zero sem você saber.
- **`modelo.npz` estragado:** o serviço não carrega um modelo cuja impressão não confere. Fica sem cérebro e anota o problema no registro, em vez de usar pesos adulterados. Para voltar ao de uma cópia: desligue o serviço e copie `dados/copias/NOME/cerebro/modelo.npz` e o `.sha256` dele para `dados/cerebro/`, ou restaure a cópia inteira.
- **Um treino piorou o cérebro:** o serviço só troca o `modelo.npz` quando a perda de validação melhora. Mesmo assim, as cópias guardam o cérebro de cada dia.

## Ensaio de restauração (14/10/2026)

Feito com os dados reais e o serviço 0.5.0 ligado. A restauração foi feita numa pasta de rascunho, com outra porta, sem tocar nos dados reais. Do conteúdo, só foram contadas linhas: nada foi lido.

| Passo | Resultado |
|---|---|
| `copia fazer` (serviço ligado, gravando) | 4,4 s, 145,9 MB, 12 arquivos; os três bancos com `integrity_check` = ok |
| `copia conferir` | "inteira" (1,1 s) |
| `copia restaurar` na pasta de rascunho | 3,3 s; restaurou os bancos, o estado, os aparelhos, os comandos, o diário e o cérebro; fez a cópia "antes-de-restaurar" |
| Contagens depois de restaurar | `kernel.db` 1.982 memórias, `mapa.db` 6.612 arquivos, `internet.db` 440 assuntos, as mesmas da cópia; `integrity_check` = ok nos três |
| O K.E.R.N.E.L abrindo os dados restaurados | Abriu: bancos em modo WAL, cérebro carregado, fora do modo seguro. A faxina de partida esqueceu 29 leituras, porque a configuração do ensaio não tinha as suas pastas liberadas (veja os cuidados) |

Os testes automáticos (`tests/test_copias.py`) repetem o ciclo a cada execução da suíte:
- fazer, conferir e restaurar;
- desfazer pela cópia "antes-de-restaurar";
- recusar uma cópia adulterada sem mexer em nada;
- guardar só as mais novas e limpar sobras;
- nunca sobrescrever a configuração;
- a cópia diária pelo laço;
- a linha de comando recusando restaurar com o serviço ligado;
- a compactação do registro antigo.
