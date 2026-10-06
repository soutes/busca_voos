"""Limites que protegem o IP de bloqueio: busca manual, ritmo das consultas e teto por fonte."""
from __future__ import annotations

import copy
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from busca_voos import scheduler  # noqa: E402
from busca_voos.config import (  # noqa: E402
    MAX_COMBINACOES_TETO,
    MAX_CONSULTAS_FONTE_TETO,
    PAUSA_MIN_CONSULTAS_S,
    PAUSA_MIN_FONTES_S,
    carregar_config,
)
from busca_voos.db import Banco  # noqa: E402
from busca_voos.sources import REGISTRO  # noqa: E402
from busca_voos.web import criar_app  # noqa: E402


def _iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) - delta).isoformat(timespec="seconds")


@pytest.fixture()
def ambiente():
    with tempfile.TemporaryDirectory() as tmp:
        pasta = Path(tmp)
        shutil.copyfile(RAIZ / "config.example.yaml", pasta / "config.yaml")
        db = pasta / "dados.sqlite3"
        Banco(db).fechar()                       # cria o schema
        app = criar_app(db, caminho_config=pasta / "config.yaml")
        yield db, pasta, TestClient(app, base_url="http://127.0.0.1:8787")


def _carimbar(db: Path, inicio: timedelta | None = None, fim: timedelta | None = None) -> None:
    b = Banco(db)
    if inicio is not None:
        b.salvar_configuracao("ultimo_ciclo_inicio", _iso(inicio))
    if fim is not None:
        b.salvar_configuracao("ultimo_ciclo_fim", _iso(fim))
    b.fechar()


def _buscar(c, **corpo):
    """POST /api/ciclo com o ciclo real trocado por um falso e rapido; espera terminar."""
    with patch("busca_voos.scheduler.ciclo", return_value={"ciclo": 1, "alertas": [], "consultas": 0}):
        r = c.post("/api/ciclo", json=corpo) if corpo else c.post("/api/ciclo")
        for _ in range(60):
            if not c.get("/api/ciclo/status").json()["rodando"]:
                break
            time.sleep(0.05)
    return r.json()


# --------------------------------------------------------- trava da busca manual

def test_sem_historico_busca_livre(ambiente):
    _, _, c = ambiente
    assert _buscar(c) == {"ok": True, "status": "iniciado"}


def test_busca_colada_e_recusada_mesmo_com_confirmacao(ambiente):
    db, _, c = ambiente
    _carimbar(db, inicio=timedelta(minutes=10))
    r = _buscar(c)
    assert r["ok"] is False and r["bloqueado"] is True and "30 minutos" in r["mensagem"]
    r = _buscar(c, confirmar=True)                     # confirmar nao destrava o bloqueio duro
    assert r["ok"] is False and r["bloqueado"] is True


def test_busca_recente_pede_confirmacao(ambiente):
    db, _, c = ambiente
    _carimbar(db, inicio=timedelta(hours=2))
    r = _buscar(c)
    assert r["ok"] is False and r["precisa_confirmar"] is True
    assert "bloquearem" in r["mensagem"] and "8 horas" in r["mensagem"] and "2 h" in r["mensagem"]
    assert _buscar(c, confirmar=True) == {"ok": True, "status": "iniciado"}


def test_confirmar_precisa_ser_true_de_verdade(ambiente):
    db, _, c = ambiente
    _carimbar(db, inicio=timedelta(hours=2))
    for falso in ("true", 1, "sim"):
        assert _buscar(c, confirmar=falso).get("precisa_confirmar") is True


def test_depois_do_intervalo_minimo_e_livre(ambiente):
    db, _, c = ambiente
    _carimbar(db, inicio=timedelta(hours=9))
    assert _buscar(c) == {"ok": True, "status": "iniciado"}


def test_conta_o_fim_do_ciclo_nao_so_o_inicio(ambiente):
    # um ciclo longo comecou ha 3 h mas terminou ha 5 min: ainda e "colado"
    db, _, c = ambiente
    _carimbar(db, inicio=timedelta(hours=3), fim=timedelta(minutes=5))
    assert _buscar(c)["bloqueado"] is True


def test_banco_antigo_usa_a_ultima_coleta(ambiente):
    db, _, c = ambiente
    b = Banco(db)
    cols = [r[1] for r in b.con.execute("PRAGMA table_info(ofertas)")]
    valores = {"fonte": "x", "rota": "A-B", "origem": "A", "destino": "B", "preco": 1, "moeda": "BRL",
               "ts": _iso(timedelta(hours=1)), "ciclo": 1, "link": "", "data_ida": "2027-01-01", "data_volta": None}
    usar = [k for k in cols if k in valores]
    b.con.execute(
        f"INSERT INTO ofertas ({','.join(usar)}) VALUES ({','.join('?' * len(usar))})",
        [valores[k] for k in usar],
    )
    b.con.commit()
    b.fechar()
    assert _buscar(c).get("precisa_confirmar") is True


def test_ciclo_em_andamento_mantem_a_mensagem_antiga(ambiente):
    db, _, c = ambiente
    _carimbar(db, inicio=timedelta(minutes=1))
    from busca_voos.web import _ciclo_lock, _status_ciclo

    with _ciclo_lock:
        _status_ciclo["rodando"] = True
    try:
        r = c.post("/api/ciclo").json()
    finally:
        with _ciclo_lock:
            _status_ciclo["rodando"] = False
    assert r == {"ok": False, "mensagem": "Ciclo já em andamento"}


# ------------------------------------------------ o ciclo carimba o banco

class _FonteFalsa:
    chamadas: list = []

    def __init__(self, cfg):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def buscar(self, origem, destino, ida, volta):
        _FonteFalsa.chamadas.append((origem, destino, ida, volta))
        return []


@pytest.fixture()
def cfg_falsa(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        pasta = Path(tmp)
        shutil.copyfile(RAIZ / "config.example.yaml", pasta / "config.yaml")
        cfg = carregar_config(pasta / "config.yaml")
        cfg.banco = pasta / "dados.sqlite3"
        cfg.agenda.pausa_entre_consultas_s = 0      # atribuicao direta nao passa pelo piso; so acelera o teste
        cfg.agenda.pausa_entre_fontes_s = 0
        monkeypatch.setitem(REGISTRO, "fonte_falsa", _FonteFalsa)
        _FonteFalsa.chamadas = []
        yield cfg


def test_ciclo_grava_inicio_e_fim(cfg_falsa):
    scheduler.ciclo(cfg_falsa, enviar_email=False, fontes=["fonte_falsa"])
    b = Banco(cfg_falsa.banco)
    ini, fim = b.obter_configuracao("ultimo_ciclo_inicio"), b.obter_configuracao("ultimo_ciclo_fim")
    b.fechar()
    assert ini and fim and datetime.fromisoformat(ini) <= datetime.fromisoformat(fim)


# --------------------------------------------------- teto de consultas por fonte

def _rotas(cfg, n):
    base = cfg.rotas[0]
    rotas = []
    for i in range(n):
        r = copy.deepcopy(base)
        r.destino = ["RIO", "GRU", "SDU", "CNF", "BSB"][i]
        rotas.append(r)
    cfg.rotas = rotas


def test_teto_por_fonte_e_dividido_entre_as_rotas(cfg_falsa):
    _rotas(cfg_falsa, 3)
    cfg_falsa.agenda.max_combinacoes_por_ciclo = 24
    cfg_falsa.agenda.max_consultas_por_fonte = 12
    scheduler.ciclo(cfg_falsa, enviar_email=False, fontes=["fonte_falsa"])
    por_rota = {}
    for _, destino, *_ in _FonteFalsa.chamadas:
        por_rota[destino] = por_rota.get(destino, 0) + 1
    assert len(_FonteFalsa.chamadas) == 12
    assert sorted(por_rota.values()) == [4, 4, 4]          # nenhuma rota fica sem consulta


def test_teto_nunca_e_ultrapassado_com_muitas_rotas(cfg_falsa):
    _rotas(cfg_falsa, 5)
    cfg_falsa.agenda.max_consultas_por_fonte = 3          # menos que o numero de rotas
    scheduler.ciclo(cfg_falsa, enviar_email=False, fontes=["fonte_falsa"])
    assert len(_FonteFalsa.chamadas) == 3


def test_max_combinacoes_continua_valendo(cfg_falsa):
    cfg_falsa.agenda.max_combinacoes_por_ciclo = 2
    cfg_falsa.agenda.max_consultas_por_fonte = 50
    scheduler.ciclo(cfg_falsa, enviar_email=False, fontes=["fonte_falsa"])
    assert len(_FonteFalsa.chamadas) == 2


# -------------------------------------------------------------------- pausas

def test_pausa_varia_para_cima_e_nunca_abaixo_do_configurado():
    with patch("busca_voos.scheduler.time.sleep") as dorme:
        for _ in range(200):
            scheduler._pausar(8)
        esperas = [c.args[0] for c in dorme.call_args_list]
    assert min(esperas) >= 8 and max(esperas) <= 12 + 1e-9
    assert len(set(round(e, 3) for e in esperas)) > 50     # nao e sempre o mesmo valor


def test_pausa_zero_ou_negativa_nao_dorme():
    with patch("busca_voos.scheduler.time.sleep") as dorme:
        scheduler._pausar(0)
        scheduler._pausar(-3)
    dorme.assert_not_called()


# ------------------------------------------------------------ pisos no config

def _config_com(tmp: Path, **campos) -> Path:
    cfg = tmp / "config.yaml"
    t = (RAIZ / "config.example.yaml").read_text(encoding="utf-8")
    for k, v in campos.items():
        t = re.sub(rf"^(\s*){k}:\s*\d+", rf"\g<1>{k}: {v}", t, count=1, flags=re.M)
    cfg.write_text(t, encoding="utf-8")
    return cfg


def test_valores_perigosos_do_config_sobem_para_o_piso():
    with tempfile.TemporaryDirectory() as tmp:
        a = carregar_config(_config_com(
            Path(tmp), pausa_entre_consultas_s=0, pausa_entre_fontes_s=3,
            max_combinacoes_por_ciclo=500, max_consultas_por_fonte=999,
        )).agenda
    assert a.pausa_entre_consultas_s == PAUSA_MIN_CONSULTAS_S == 8      # 0 desligava a pausa
    assert a.pausa_entre_fontes_s == PAUSA_MIN_FONTES_S == 20
    assert a.max_combinacoes_por_ciclo == MAX_COMBINACOES_TETO == 24
    assert a.max_consultas_por_fonte == MAX_CONSULTAS_FONTE_TETO == 60


def test_valores_seguros_do_config_ficam_como_estao():
    with tempfile.TemporaryDirectory() as tmp:
        a = carregar_config(_config_com(
            Path(tmp), pausa_entre_consultas_s=15, pausa_entre_fontes_s=45,
            max_combinacoes_por_ciclo=6, max_consultas_por_fonte=20,
        )).agenda
    assert (a.pausa_entre_consultas_s, a.pausa_entre_fontes_s, a.max_combinacoes_por_ciclo, a.max_consultas_por_fonte) \
        == (15, 45, 6, 20)


def test_config_de_exemplo_ja_esta_dentro_dos_limites():
    a = carregar_config(RAIZ / "config.example.yaml").agenda
    assert (a.pausa_entre_consultas_s, a.pausa_entre_fontes_s, a.max_consultas_por_fonte) == (8, 20, 36)
