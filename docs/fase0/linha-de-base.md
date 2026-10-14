# Linha de base dos testes (versão 0.5.0)

A suíte inteira rodada sobre o código da tag `v0.5.0` (commit `3548c0b`), antes de qualquer mudança da Fase 0. O resultado completo, teste por teste, está em [`testes-linha-de-base.xml`](testes-linha-de-base.xml) (formato JUnit).

**Comando:**

```
.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs --junitxml=docs\fase0\testes-linha-de-base.xml
```

**Quando:** 14/10/2026, 19:50, no [ambiente de referência](ambiente.md).

## Resultado

| Testes | Passaram | Falharam | Erros | Pulados | Tempo |
|---|---|---|---|---|---|
| 332 | 331 | 0 | 0 | 1 | 108 s |

O pulado é `test_nao_segue_atalho_para_fora`: o Windows só deixa criar um atalho simbólico (o que o teste usa) como administrador. A regra que ele confere (não seguir atalho para fora das pastas liberadas) está no código e é exercitada pelos outros testes de exploração.

## Por arquivo

| Arquivo | Testes |
|---|---|
| `test_reflexos` | 60 |
| `test_voz` | 43 |
| `test_internet` | 39 |
| `test_comandos` | 32 |
| `test_exploracao` | 23 |
| `test_nucleo` | 16 |
| `test_cerebro` | 14 |
| `test_dialogo` | 14 |
| `test_psola` | 14 |
| `test_seguranca` | 14 |
| `test_api` | 13 |
| `test_difones` | 8 |
| `test_maos` | 8 |
| `test_memoria` | 8 |
| `test_estudo` | 7 |
| `test_ouvidos` | 7 |
| `test_mente` | 5 |
| `test_corpus_de_voz` | 4 |
| `test_alinhador` | 3 |
| **Total** | **332** |

Os testes trabalham só em pastas temporárias: rodá-los não mexe na memória, no cérebro nem na configuração de verdade.
