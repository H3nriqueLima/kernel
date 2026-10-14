# Ambiente de referência

As versões exatas com que a 0.5.0 foi auditada e a Fase 0 foi feita. Elas também estão travadas em [`requirements-travado.txt`](../../requirements-travado.txt), na raiz do projeto, gerado com `pip freeze`.

## Máquina

| Item | Versão |
|---|---|
| Sistema | Windows 10 Home 22H2 (10.0.19045), 64 bits |
| Processador | Intel Core i5-2400, 4 núcleos, 3,1 GHz (sem AVX2) |
| Memória | 12 GB |
| Placa de vídeo | Radeon RX 570 (4 GB), driver 31.0.21925.1001 |
| Vídeo integrado | Intel HD Graphics, driver 9.17.10.4459 (não é usado) |

## Python e bibliotecas

| Pacote | Versão | Para quê |
|---|---|---|
| Python | 3.12.10 | O `torch-directml` só tem versão para até o 3.12 |
| pip | 26.2.1 | |
| numpy | 2.5.4 | Contas de todo o sistema |
| torch | 2.4.1 (versão para CPU) | Treino do cérebro (as derivadas) |
| torch-directml | 0.2.5.dev240914 | Treino na RX 570 pelo DirectML (dispositivo "Radeon RX 570 Series") |
| tensorboard | 2.21.0 | Gráficos do treino (opcional) |
| fastapi | 0.143.0 | API local |
| starlette | 1.7.0 | Base da FastAPI |
| pydantic | 2.14.1 | Validação das mensagens da API |
| uvicorn | 0.54.0 | Servidor HTTP |
| pypdf | 6.20.1 | Texto de PDFs |
| soundfile | 0.14.0 (libsndfile 1.2.2) | Ler os MP3 do corpus de voz |
| sounddevice | 0.5.6 | Microfone e alto-falante |
| pytest | 9.1.1 | Testes |

## Como reproduzir

```
py install 3.12
py -V:3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-travado.txt
.venv\Scripts\python.exe -m pytest
```

O `instalar.ps1` instala as versões mais novas que atendem aos `requirements*.txt`. Para ter exatamente o ambiente de referência, use o `requirements-travado.txt`.
