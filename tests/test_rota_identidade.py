"""Testes da identidade de rota por id (config, banco, migracao, painel e API)."""
from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from busca_voos.config import (
    adicionar_rota_config,
    atualizar_rota_config,
    carregar_config,
    listar_rotas_dict,
)
from busca_voos.db import Banco
from busca_voos.models import Oferta, Rota


@pytest.fixture()
def pasta():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        shutil.copyfile(RAIZ / "config.example.yaml", p / "config.yaml")
        yield p


def _rotas_sao(pasta: Path):
    """Duas FLN-SAO: uma so ida (teto 300) e uma ida+volta (teto 500)."""
    atualizar_rota_config(pasta / "config.yaml", 0, {
        "origem": "FLN", "destino": "SAO",
        "janela_ida": {"de": "2026-11-01", "ate": "2026-11-04"},
        "preco_maximo": 300.0, "nome": "IDA SP",
    })
    adicionar_rota_config(pasta / "config.yaml", {
        "origem": "FLN", "destino": "SAO",
        "janela_ida": {"de": "2026-11-01", "ate": "2026-11-04"},
        "janela_volta": {"de": "2026-11-05", "ate": "2026-11-06"},
        "preco_maximo": 500.0, "nome": "Sao Paulo",
    })


def test_ids_de_rotas_duplicadas_sao_unicos(pasta: Path):
    _rotas_sao(pasta)
    rotas = listar_rotas_dict(pasta / "config.yaml")
    assert [r["id"] for r in rotas] == ["FLN-SAO", "FLN-SAO-2"]


def test_carregar_config_traz_os_mesmos_ids(pasta: Path):
    _rotas_sao(pasta)
    cfg = carregar_config(pasta / "config.yaml")
    assert [r.id for r in cfg.rotas] == ["FLN-SAO", "FLN-SAO-2"]
    assert cfg.rotas[0].datas_volta == []
    assert cfg.rotas[1].datas_volta == [date(2026, 11, 5), date(2026, 11, 6)]


def test_id_preservado_ao_editar_datas_teto_e_nome(pasta: Path):
    _rotas_sao(pasta)
    rotas = atualizar_rota_config(pasta / "config.yaml", 0, {
        "origem": "FLN", "destino": "SAO",
        "janela_ida": {"de": "2026-12-01", "ate": "2026-12-03"},
        "preco_maximo": 250.0, "nome": "IDA SP nova",
    })
    assert rotas[0]["id"] == "FLN-SAO"


def test_id_acompanha_o_par_ao_editar_origem_destino(pasta: Path):
    _rotas_sao(pasta)
    rotas = atualizar_rota_config(pasta / "config.yaml", 0, {
        "origem": "FLN", "destino": "BSB",
        "janela_ida": {"de": "2026-11-01", "ate": "2026-11-04"},
        "preco_maximo": 300.0,
    })
    assert rotas[0]["id"] == "FLN-BSB"
    assert rotas[1]["id"] == "FLN-SAO-2"


def test_nova_rota_recebe_id_livre(pasta: Path):
    _rotas_sao(pasta)
    rotas = adicionar_rota_config(pasta / "config.yaml", {
        "origem": "FLN", "destino": "SAO",
        "janela_ida": {"de": "2026-11-01", "ate": "2026-11-04"},
        "preco_maximo": 700.0,
    })
    assert rotas[-1]["id"] == "FLN-SAO-3"


def test_id_explicito_duplicado_no_yaml_nao_quebra(pasta: Path):
    (pasta / "config.yaml").write_text(
        "fontes: {google_flights: {ativo: true}}\n"
        "rotas:\n"
        "  - id: X\n    origem: FLN\n    destino: SAO\n"
        "    janela_ida: { de: 2026-11-01, ate: 2026-11-02 }\n    preco_maximo: 100\n"
        "  - id: X\n    origem: FLN\n    destino: SAO\n"
        "    janela_ida: { de: 2026-11-01, ate: 2026-11-02 }\n    preco_maximo: 200\n",
        encoding="utf-8",
    )
    rotas = listar_rotas_dict(pasta / "config.yaml")
    assert [r["id"] for r in rotas] == ["X", "FLN-SAO-2"]
    assert len({r.id for r in carregar_config(pasta / "config.yaml").rotas}) == 2


def test_oferta_tem_rota_id_default_vazio():
    o = Oferta(fonte="f", rota="FLN-SAO", origem="FLN", destino="SAO",
              data_ida=date(2026, 11, 1), data_volta=None, preco=1.0,
              moeda="BRL", link="http://x")
    assert o.rota_id == ""


def _temp_db(tmp_path: Path) -> Banco:
    return Banco(tmp_path / "d.sqlite3")


def test_schema_tem_rota_id(tmp_path: Path):
    b = _temp_db(tmp_path)
    try:
        for tabela in ("ofertas", "alertas"):
            cols = {r[1] for r in b.con.execute(f"PRAGMA table_info({tabela})")}
            assert "rota_id" in cols
    finally:
        b.fechar()


def test_coluna_rota_id_adicionada_em_banco_antigo(tmp_path: Path):
    caminho = tmp_path / "velho.sqlite3"
    con = sqlite3.connect(caminho)
    con.executescript(
        "CREATE TABLE ofertas (id INTEGER PRIMARY KEY, ts TEXT, ciclo INTEGER,"
        " fonte TEXT, rota TEXT, data_ida TEXT, data_volta TEXT, preco REAL,"
        " moeda TEXT, cia TEXT, escalas TEXT, link TEXT);"
        "CREATE TABLE alertas (id INTEGER PRIMARY KEY, ts TEXT, fonte TEXT, rota TEXT,"
        " data_ida TEXT, data_volta TEXT, preco REAL, link TEXT);"
        "CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT);"
    )
    con.commit()
    con.close()
    b = Banco(caminho)   # __init__ deve ALTERar as tabelas
    try:
        for tabela in ("ofertas", "alertas"):
            cols = {r[1] for r in b.con.execute(f"PRAGMA table_info({tabela})")}
            assert "rota_id" in cols
    finally:
        b.fechar()


def test_salvar_ofertas_grava_rota_id(tmp_path: Path):
    b = _temp_db(tmp_path)
    try:
        o = Oferta(fonte="f", rota="FLN-SAO", origem="FLN", destino="SAO",
                   data_ida=date(2026, 11, 1), data_volta=None, preco=250.0,
                   moeda="BRL", link="http://x", rota_id="FLN-SAO-2")
        b.salvar_ofertas([o], ciclo=1)
        rid = b.con.execute("SELECT rota_id FROM ofertas").fetchone()[0]
        assert rid == "FLN-SAO-2"
    finally:
        b.fechar()


def test_dedupe_separa_rotas_do_mesmo_par(tmp_path: Path):
    b = _temp_db(tmp_path)
    try:
        d = date(2026, 11, 1)
        b.registrar_alerta("f", "FLN-SAO", d, None, 250.0, "http://x", rota_id="FLN-SAO")
        # outra rota do mesmo par, outra janela de dedupe: ainda deve alertar
        alertar, _ = b.deve_alertar("f", "FLN-SAO-2", d, None, 250.0, dedupe_horas=24)
        assert alertar is True
        # a mesma rota (id) com o mesmo preco: suprimido
        alertar2, motivo = b.deve_alertar("f", "FLN-SAO", d, None, 250.0, dedupe_horas=24)
        assert alertar2 is False and motivo == "repetido"
    finally:
        b.fechar()


def test_registrar_alerta_posicional_ainda_funciona(tmp_path: Path):
    b = _temp_db(tmp_path)
    try:
        d = date(2026, 11, 1)
        b.registrar_alerta("f", "FLN-RIO", d, None, 100.0, "http://x")   # sem rota_id
        n = b.con.execute("SELECT COUNT(*) FROM alertas").fetchone()[0]
        assert n == 1
    finally:
        b.fechar()
