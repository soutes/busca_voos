"""Testes da identidade de rota por id (config, banco, migracao, painel e API)."""
from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from busca_voos.config import (
    adicionar_rota_config,
    atualizar_rota_config,
    carregar_config,
    listar_rotas_dict,
)
from busca_voos import painel
from busca_voos.db import Banco
from busca_voos.models import Oferta, Rota
from busca_voos.scheduler import ciclo
from busca_voos.web import criar_app


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
        b.con.execute("INSERT INTO ofertas (ts, fonte, rota, preco) VALUES ('t','f','X-Y',1.0)")
        b.con.execute("INSERT INTO alertas (ts, fonte, rota, preco) VALUES ('t','f','X-Y',1.0)")
        b.con.commit()
        for tabela in ("ofertas", "alertas"):
            rid = b.con.execute(f"SELECT rota_id FROM {tabela}").fetchone()[0]
            assert rid == ""
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

def _legado(b: Banco, tabela: str, rota: str, data_ida: str | None, data_volta: str | None) -> None:
    b.con.execute(
        f"INSERT INTO {tabela} (ts, fonte, rota, data_ida, data_volta, preco"
        + (", moeda" if tabela == "ofertas" else "")
        + ") VALUES (?, ?, ?, ?, ?, ?"
        + (", ?" if tabela == "ofertas" else "")
        + ")",
        (("2026-10-18T12:00:00+00:00", "f", rota, data_ida, data_volta, 100.0)
         + (("BRL",) if tabela == "ofertas" else ())),
    )
    b.con.commit()


def _rotas_migracao() -> list[Rota]:
    return [
        Rota(origem="FLN", destino="SAO",
             datas_ida=[date(2026, 11, 1), date(2026, 11, 4)], datas_volta=[],
             preco_maximo=300.0, nome="IDA SP", id="FLN-SAO"),
        Rota(origem="FLN", destino="SAO",
             datas_ida=[date(2026, 11, 1), date(2026, 11, 4)],
             datas_volta=[date(2026, 11, 5), date(2026, 11, 6)],
             preco_maximo=500.0, nome="Sao Paulo", id="FLN-SAO-2"),
    ]


def test_migracao_separa_so_ida_de_ida_volta(tmp_path: Path):
    b = _temp_db(tmp_path)
    try:
        _legado(b, "ofertas", "FLN-SAO", "2026-11-04", None)      # so ida, R$ later
        _legado(b, "ofertas", "FLN-SAO", "2026-11-03", "2026-11-05")
        _legado(b, "alertas", "FLN-SAO", "2026-11-04", None)
        n = b.migrar_rota_ids(_rotas_migracao())
        assert n == 3
        so_ida = b.con.execute(
            "SELECT rota_id FROM ofertas WHERE data_volta IS NULL"
        ).fetchone()[0]
        ida_volta = b.con.execute(
            "SELECT rota_id FROM ofertas WHERE data_volta IS NOT NULL"
        ).fetchone()[0]
        assert so_ida == "FLN-SAO"
        assert ida_volta == "FLN-SAO-2"
    finally:
        b.fechar()


def test_migracao_rota_orfa_fica_vazia(tmp_path: Path):
    b = _temp_db(tmp_path)
    try:
        _legado(b, "ofertas", "XX-YY", "2026-11-01", None)
        assert b.migrar_rota_ids(_rotas_migracao()) == 0
        rid = b.con.execute("SELECT rota_id FROM ofertas").fetchone()[0]
        assert rid == ""
    finally:
        b.fechar()


def test_migracao_e_idempotente(tmp_path: Path):
    b = _temp_db(tmp_path)
    try:
        _legado(b, "ofertas", "FLN-SAO", "2026-11-04", None)
        assert b.migrar_rota_ids(_rotas_migracao()) == 1
        assert b.migrar_rota_ids(_rotas_migracao()) == 0   # nada mais a preencher
    finally:
        b.fechar()


def test_migracao_ambigua_escolhe_a_primeira(tmp_path: Path):
    b = _temp_db(tmp_path)
    try:
        # janela/trecho da 1a rota, mas linha sem data que case em nenhuma: cai na 1a do par
        _legado(b, "ofertas", "FLN-SAO", "2027-01-01", None)
        b.migrar_rota_ids(_rotas_migracao())
        rid = b.con.execute("SELECT rota_id FROM ofertas").fetchone()[0]
        assert rid == "FLN-SAO"
    finally:
        b.fechar()

def test_ciclo_carimba_rota_id_por_rota(pasta: Path):
    _rotas_sao(pasta)
    cfg = carregar_config(pasta / "config.yaml")
    cfg.banco = pasta / "dados.sqlite3"
    cfg.agenda.pausa_entre_consultas_s = 0
    cfg.agenda.pausa_entre_fontes_s = 0
    cfg.email.senha = "x"
    cfg.email.de = "a@b.com"
    cfg.email.para = ["c@d.com"]

    class MockFonte:
        def __init__(self, _cfg): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def buscar(self, origem, destino, data_ida, data_volta=None):
            return [Oferta(fonte="fonte_teste", rota="FLN-SAO", origem="FLN",
                           destino="SAO", data_ida=data_ida, data_volta=data_volta,
                           preco=200.0, moeda="BRL", link="http://x")]

    with patch("busca_voos.scheduler.REGISTRO", {"fonte_teste": MockFonte}):
        with patch("busca_voos.scheduler.enviar"):
            ciclo(cfg, enviar_email=True, fontes=["fonte_teste"])

    b = Banco(pasta / "dados.sqlite3")
    try:
        pares = b.con.execute(
            "SELECT DISTINCT rota_id FROM ofertas ORDER BY rota_id"
        ).fetchall()
        ids = {p[0] for p in pares}
        assert ids and "" not in ids
        assert ids == {"FLN-SAO", "FLN-SAO-2"}
    finally:
        b.fechar()


def _seed_duas_rotas(caminho: Path) -> None:
    b = Banco(caminho)
    try:
        o1 = Oferta(fonte="f", rota="FLN-SAO", origem="FLN", destino="SAO",
                    data_ida=date(2026, 11, 4), data_volta=None, preco=293.0,
                    moeda="BRL", link="http://x", rota_id="FLN-SAO")
        o2 = Oferta(fonte="f", rota="FLN-SAO", origem="FLN", destino="SAO",
                    data_ida=date(2026, 11, 4), data_volta=date(2026, 11, 5),
                    preco=590.0, moeda="BRL", link="http://y", rota_id="FLN-SAO-2")
        b.salvar_ofertas([o1, o2], ciclo=1)
        b.registrar_alerta("f", "FLN-SAO", date(2026, 11, 4), None, 293.0, "http://x",
                           rota_id="FLN-SAO")
    finally:
        b.fechar()


def test_resumo_separa_rotas_do_mesmo_par(tmp_path: Path):
    db = tmp_path / "d.sqlite3"
    _seed_duas_rotas(db)
    con = painel.conectar(db)
    try:
        por_rota = {r["rota_id"]: r["preco"] for r in painel.resumo(con)["por_rota"]}
        assert por_rota == {"FLN-SAO": 293.0, "FLN-SAO-2": 590.0}
        assert all("rota" in r for r in painel.resumo(con)["por_rota"])
    finally:
        con.close()


def test_filtros_ofertas_alertas_e_historico_por_rota_id(tmp_path: Path):
    db = tmp_path / "d.sqlite3"
    _seed_duas_rotas(db)
    con = painel.conectar(db)
    try:
        assert painel.contar_ofertas(con, rota_id="FLN-SAO") == 1
        assert painel.contar_ofertas(con, rota_id="FLN-SAO-2") == 1
        ofs = painel.listar_ofertas(con, rota_id="FLN-SAO")
        assert [o["preco"] for o in ofs] == [293.0]
        assert painel.listar_ofertas(con, rota_id="FLN-SAO")[0]["rota_id"] == "FLN-SAO"
        al = painel.listar_alertas(con, rota_id="FLN-SAO")
        assert len(al) == 1 and al[0]["rota_id"] == "FLN-SAO"
        assert painel.listar_alertas(con, rota_id="FLN-SAO-2") == []
        hist = painel.historico(con, rota_id="FLN-SAO")
        assert hist and hist[0]["minimo"] == 293.0
        assert "FLN-SAO" in painel.filtros(con)["rotas"]
        assert "FLN-SAO-2" in painel.filtros(con)["rotas"]
    finally:
        con.close()


def test_criar_app_migra_ids_na_subida(pasta: Path):
    _rotas_sao(pasta)
    db = pasta / "dados.sqlite3"
    b = Banco(db)
    try:
        b.con.execute(
            "INSERT INTO ofertas (ts, fonte, rota, data_ida, data_volta, preco, moeda)"
            " VALUES ('2026-10-18T12:00:00+00:00','f','FLN-SAO','2026-11-04',NULL,293.0,'BRL')"
        )
        b.con.commit()
    finally:
        b.fechar()

    criar_app(banco=db, caminho_config=pasta / "config.yaml")   # dispara a migracao

    b2 = Banco(db)
    try:
        rid = b2.con.execute("SELECT rota_id FROM ofertas").fetchone()[0]
        assert rid == "FLN-SAO"
    finally:
        b2.fechar()


def test_limites_e_filtros_por_id(pasta: Path):
    _rotas_sao(pasta)
    db = pasta / "dados.sqlite3"
    Banco(db).fechar()
    app = criar_app(
        banco=db,
        caminho_config=pasta / "config.yaml",
        limites={"FLN-SAO": 300.0, "FLN-SAO-2": 500.0},
    )
    c = TestClient(app, base_url="http://127.0.0.1:8787")
    f = c.get("/api/filtros").json()
    assert f["limites"]["FLN-SAO"] == 300.0
    assert f["limites"]["FLN-SAO-2"] == 500.0


def test_endpoints_aceitam_rota_id(pasta: Path):
    _rotas_sao(pasta)
    db = pasta / "dados.sqlite3"
    _seed_duas_rotas(db)
    app = criar_app(banco=db, caminho_config=pasta / "config.yaml")
    c = TestClient(app, base_url="http://127.0.0.1:8787")
    ofs = c.get("/api/ofertas", params={"rota_id": "FLN-SAO"}).json()
    assert [o["preco"] for o in ofs["ofertas"]] == [293.0]
    assert ofs["total"] == 1
    al = c.get("/api/alertas", params={"rota_id": "FLN-SAO-2"}).json()
    assert al["alertas"] == []
    hist = c.get("/api/historico", params={"rota_id": "FLN-SAO"}).json()
    assert hist["historico"] and hist["historico"][0]["minimo"] == 293.0


def test_criar_app_nao_cria_banco_ausente_e_mantem_503(pasta: Path):
    _rotas_sao(pasta)
    db = pasta / "nao_existe.sqlite3"
    app = criar_app(banco=db, caminho_config=pasta / "config.yaml")
    assert not db.exists()
    c = TestClient(app, base_url="http://127.0.0.1:8787")
    assert c.get("/api/resumo").status_code == 503


def test_front_usa_rota_id():
    html = (RAIZ / "src" / "busca_voos" / "painel.html").read_text(encoding="utf-8")
    assert "estado.rotaId" in html
    assert "limites[o.rota_id]" in html
    assert "x.rota_id === estado.rotaId" in html
    assert "limites[o.rota]" not in html          # nao pode sobrar chave por par
    assert "limites[estado.rota]" not in html


def test_resumo_ignora_linhas_orfas(tmp_path: Path):
    db = tmp_path / "d.sqlite3"
    _seed_duas_rotas(db)
    b = Banco(db)
    try:
        orfa = Oferta(fonte="f", rota="XX-YY", origem="XX", destino="YY",
                      data_ida=date(2026, 11, 4), data_volta=None, preco=50.0,
                      moeda="BRL", link="http://z", rota_id="")
        b.salvar_ofertas([orfa], ciclo=2)
    finally:
        b.fechar()
    con = painel.conectar(db)
    try:
        assert painel.resumo(con)["menor_preco"]["preco"] == 293.0
        assert all(r["rota_id"] != "" for r in painel.resumo(con)["por_rota"])
        assert "" not in painel.filtros(con)["rotas"]
    finally:
        con.close()
