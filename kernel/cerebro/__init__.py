"""Cérebro: do micrograd ao mini GPT, tudo escrito à mão.

Ordem de estudo (e de construção):

1. ``micrograd.py``   — backpropagation com números soltos, sem biblioteca.
2. ``bigrama.py``     — o modelo de linguagem mais simples: contar pares de letras.
3. ``tokenizador.py`` — BPE: como texto vira números.
4. ``gpt.py``         — o Transformer, camada por camada, em PyTorch.
5. ``treinar.py``     — o laço de treino (na RX 570 via DirectML, ou na CPU).
6. ``inferencia.py``  — o mesmo modelo rodando só com NumPy, para o dia a dia.
"""
