"""Como todo banco SQLite do K.E.R.N.E.L é aberto.

O modo WAL ("write-ahead log") deixa ler e gravar ao mesmo tempo: quem lê o banco
(a tela de estado, um script de análise, uma cópia de segurança) não tranca o
serviço na hora de gravar. Sem ele, uma leitura longa de fora fazia o serviço
esperar 5 s e desistir com "database is locked".

Com WAL, o banco fica em três arquivos (``x.db``, ``x.db-wal`` e ``x.db-shm``). Para
copiar um banco com segurança use ``python -m kernel copia fazer``, que usa a cópia
do próprio SQLite, em vez de copiar o arquivo ``.db`` sozinho.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ESPERA = 5.0   # segundos que uma gravação espera outra terminar antes de desistir


def abrir(arquivo: Path | str) -> sqlite3.Connection:
    bd = sqlite3.connect(str(arquivo), check_same_thread=False, timeout=ESPERA)
    try:
        bd.execute("PRAGMA journal_mode = WAL")
        # NORMAL no WAL: uma queda de luz pode perder a última gravação, nunca estragar o banco.
        bd.execute("PRAGMA synchronous = NORMAL")
    except sqlite3.OperationalError:
        pass   # outro processo segurando o banco agora: segue no modo em que ele já está
    return bd
