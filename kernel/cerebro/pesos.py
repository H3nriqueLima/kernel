"""Os pesos exportados (``modelo.npz``) de volta para o GPT do PyTorch.

O serviço usa os pesos em NumPy (``inferencia.py``). Para medir um modelo com o
PyTorch (na placa de vídeo, em lotes), as mesmas matrizes voltam para um ``GPT``.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from .gpt import GPT, ConfigGPT


def ler_npz(arquivo: Path) -> tuple[dict, dict[str, np.ndarray]]:
    """(configuração, pesos) de um ``modelo.npz``."""
    with np.load(arquivo) as dados:
        cfg = json.loads(str(dados["_config"]))
        pesos = {nome: dados[nome] for nome in dados.files if nome != "_config"}
    return cfg, pesos


def gpt_de_npz(arquivo: Path, dispositivo="cpu", dtype=torch.float32) -> GPT:
    cfg, pesos = ler_npz(arquivo)
    modelo = GPT(ConfigGPT(**cfg))
    modelo.load_state_dict({nome: torch.from_numpy(valor) for nome, valor in pesos.items()})
    return modelo.to(dtype).to(dispositivo).eval()
