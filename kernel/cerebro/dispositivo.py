"""Onde treinar: a RX 570 pelo DirectML, uma placa NVIDIA pelo CUDA, ou a CPU.

O código do cérebro é o mesmo nos três; só o dispositivo muda. Se o DirectML
falhar em alguma operação, o treino cai para a CPU em vez de parar.
"""
from __future__ import annotations

import torch


def escolher(preferencia: str = "auto"):
    """Devolve (dispositivo, descrição). ``preferencia``: auto | directml | cuda | cpu."""
    if preferencia in ("auto", "cuda") and torch.cuda.is_available():
        return torch.device("cuda"), f"{torch.cuda.get_device_name(0)} (CUDA)"
    if preferencia in ("auto", "directml"):
        try:
            import torch_directml

            nomes = [torch_directml.device_name(i).strip("\x00") for i in range(torch_directml.device_count())]
        except Exception:  # sem o pacote ou sem placa compatível com DirectX 12
            nomes = []
        if nomes:
            # prefere a placa dedicada ao vídeo integrado
            indice = next((i for i, n in enumerate(nomes) if "intel" not in n.lower() and "basic" not in n.lower()), 0)
            dispositivo = torch_directml.device(indice)
            if funciona(dispositivo):
                return dispositivo, f"{nomes[indice]} (DirectML)"
            print("aviso: o DirectML falhou no teste de treino; usando a CPU.")
    return torch.device("cpu"), f"CPU ({torch.get_num_threads()} threads)"


def funciona(dispositivo) -> bool:
    """Dois passos de treino num modelo minúsculo: o dispositivo dá conta de todas as operações?"""
    from .gpt import GPT, ConfigGPT
    from .otimizador import AdamW

    try:
        modelo = GPT(ConfigGPT(vocab=64, contexto=8, camadas=1, cabecas=2, dim=16)).to(dispositivo)
        otimizador = AdamW(modelo.parameters())
        x = torch.randint(0, 64, (2, 8)).to(dispositivo)
        for _ in range(2):
            _, perda = modelo(x, x)
            perda.backward()
            otimizador.passo(1e-3)
            otimizador.zerar()
        return bool(torch.isfinite(perda.cpu()))
    except Exception:
        return False
