"""Cópias de segurança: fazer, conferir, restaurar (e recusar uma cópia estragada)."""
import json
from datetime import datetime, timedelta

import pytest

from kernel import copias
from kernel.memoria import Memoria


def preparar(cfg):
    memoria = Memoria(cfg.dados / "kernel.db")
    memoria.guardar("A reunião com o cliente é na sexta.")
    memoria.fechar()
    (cfg.dados / "estado.json").write_text('{"impulsos": {"curiosidade": 0.5}}', encoding="utf-8")
    (cfg.pasta("diario") / "2026-10-14.md").write_text("Hoje estudei.", encoding="utf-8")
    cerebro = cfg.pasta("cerebro")
    (cerebro / "modelo.npz").write_bytes(b"pesos de mentira")
    (cerebro / "tokenizador.json").write_text("{}", encoding="utf-8")


def contar(cfg):
    memoria = Memoria(cfg.dados / "kernel.db")
    try:
        return memoria._bd.execute("SELECT COUNT(*) FROM memorias").fetchone()[0]
    finally:
        memoria.fechar()


def test_fazer_conferir_e_restaurar(cfg):
    preparar(cfg)
    pasta = copias.fazer(cfg)
    manifesto = json.loads((pasta / copias.MANIFESTO).read_text(encoding="utf-8"))
    assert manifesto["bancos"]["kernel.db"] == "ok" and manifesto["cerebro"] == "copiado"
    caminhos = {a["caminho"] for a in manifesto["arquivos"]}
    assert {"kernel.db", "estado.json", "diario/2026-10-14.md", "cerebro/modelo.npz"} <= caminhos
    assert copias.conferir(pasta) == []
    assert [c["nome"] for c in copias.listar(cfg)] == [pasta.name]

    # depois da cópia: uma memória nova, o estado mudou e o modelo foi trocado
    memoria = Memoria(cfg.dados / "kernel.db")
    memoria.guardar("O relatório sai na segunda.")
    memoria.fechar()
    (cfg.dados / "estado.json").write_text("{}", encoding="utf-8")
    (cfg.pasta("cerebro") / "modelo.npz").write_bytes(b"pesos piores")
    assert contar(cfg) == 2

    resultado = copias.restaurar(cfg, pasta.name)
    assert contar(cfg) == 1
    assert "curiosidade" in (cfg.dados / "estado.json").read_text(encoding="utf-8")
    assert (cfg.pasta("cerebro") / "modelo.npz").read_bytes() == b"pesos de mentira"
    assert "kernel.db" in resultado["restaurados"]

    # o estado de antes de restaurar ficou guardado: dá para desfazer
    seguranca = copias.pasta_das_copias(cfg) / resultado["seguranca"]
    assert resultado["seguranca"].endswith("antes-de-restaurar") and copias.conferir(seguranca) == []
    copias.restaurar(cfg, resultado["seguranca"])
    assert contar(cfg) == 2


def test_copia_estragada_nao_e_restaurada(cfg):
    preparar(cfg)
    pasta = copias.fazer(cfg)
    banco = pasta / "kernel.db"
    dados = bytearray(banco.read_bytes())
    dados[len(dados) // 2] ^= 0xFF
    banco.write_bytes(bytes(dados))
    assert any("kernel.db mudou depois da cópia" in p for p in copias.conferir(pasta))

    memoria = Memoria(cfg.dados / "kernel.db")
    memoria.guardar("Uma memória que não pode sumir.")
    memoria.fechar()
    with pytest.raises(copias.ErroCopia, match="não confere"):
        copias.restaurar(cfg, pasta.name)
    assert contar(cfg) == 2                                   # nada foi mexido
    assert len(copias.listar(cfg)) == 1                       # nem a cópia de segurança foi feita
    with pytest.raises(copias.ErroCopia, match="não existe"):
        copias.restaurar(cfg, "2020-01-01_000000-inventada")


def test_guarda_so_as_mais_novas_e_limpa_sobras(cfg):
    preparar(cfg)
    hora = datetime(2026, 10, 14, 3, 0, 0)
    nomes = []
    for dia in range(4):
        nomes.append(copias.fazer(cfg, motivo="diaria", manter=2,
                                  relogio=lambda d=dia: hora + timedelta(days=d)).name)
    assert [c["nome"] for c in copias.listar(cfg)] == nomes[:1:-1]   # as duas mais novas

    sobra = copias.pasta_das_copias(cfg) / ".2026-10-20_030000-diaria.parcial"
    sobra.mkdir()
    (sobra / "kernel.db").write_bytes(b"pela metade")
    sem_cerebro = copias.fazer(cfg, com_cerebro=False, manter=None)
    assert not sobra.exists()                                      # a cópia que caiu no meio foi limpa
    assert json.loads((sem_cerebro / copias.MANIFESTO).read_text(encoding="utf-8"))["cerebro"].startswith("pulado")
    assert not (sem_cerebro / "cerebro").exists()


def test_configuracao_vai_na_copia_mas_nunca_volta(cfg, tmp_path):
    preparar(cfg)
    configuracao = tmp_path / "kernel.toml"
    configuracao.write_text("[internet]\nligada = false\n", encoding="utf-8")
    cfg.arquivo = configuracao
    pasta = copias.fazer(cfg)
    assert (pasta / "lembranca" / "kernel.toml").read_text(encoding="utf-8") == "[internet]\nligada = false\n"
    configuracao.write_text("[internet]\nligada = true\n", encoding="utf-8")   # você mudou depois
    copias.restaurar(cfg, pasta.name)
    assert "ligada = true" in configuracao.read_text(encoding="utf-8")


def test_copia_diaria_pelo_laco(kernel):
    kernel.cfg.copias.diaria = True
    kernel.volta(1.0)
    (copia,) = copias.listar(kernel.cfg)
    assert copia["motivo"] == "diaria" and copia["cerebro"] == "copiado"
    assert any(e["tipo"] == "copia" and e["evento"] == "feita" for e in kernel.registro.ultimos(20))
    kernel.volta(1.0)
    assert len(copias.listar(kernel.cfg)) == 1                     # uma por dia, não uma por volta


def test_restaurar_pela_linha_de_comando_exige_servico_desligado(cfg, monkeypatch, capsys):
    from kernel import __main__ as cli

    preparar(cfg)
    nome = copias.fazer(cfg).name
    monkeypatch.setattr(cli, "carregar", lambda: cfg)
    monkeypatch.setattr(cli, "_saude", lambda porta: {"nome": "K.E.R.N.E.L"})
    assert cli.main(["copia", "restaurar", nome]) == 1
    assert "Desligue" in capsys.readouterr().out
    monkeypatch.setattr(cli, "_saude", lambda porta: None)
    assert cli.main(["copia", "restaurar", nome]) == 0
    assert cli.main(["copia", "conferir"]) == 0
    saida = capsys.readouterr().out
    assert "restaurado:" in saida and saida.count(": inteira") == 2


def test_registro_antigo_e_compactado_e_continua_legivel(tmp_path):
    from datetime import date

    from kernel.registro import Registro

    hoje = datetime(2026, 12, 1, 10, 0)
    registro = Registro(tmp_path / "registro", relogio=lambda: hoje)
    antigo = tmp_path / "registro" / "2026-10-13.jsonl"
    antigo.write_text('{"ts": "2026-10-13T23:44:24", "tipo": "estudo", "evento": "fim"}\n', encoding="utf-8")
    registro.anotar("servico", evento="inicio")
    assert registro.compactar_antigos() == 1
    assert not antigo.exists() and (tmp_path / "registro" / "2026-10-13.jsonl.gz").exists()
    assert registro.dias() == [date(2026, 10, 13), date(2026, 12, 1)]
    assert registro.do_dia(date(2026, 10, 13))[0]["evento"] == "fim"
    assert registro.compactar_antigos() == 0                       # hoje não é compactado
