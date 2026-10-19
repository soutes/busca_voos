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
