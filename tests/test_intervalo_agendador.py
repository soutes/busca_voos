"""Intervalo do agendador: so 8 h, 12 h, 24 h ou semanal (evita bloqueio de IP pelas fontes)."""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from busca_voos.config import (  # noqa: E402
    INTERVALO_MINIMO_MIN,
    INTERVALOS_PERMITIDOS_H,
    ErroConfig,
    carregar_config,
    normalizar_intervalo_horas,
    obter_intervalo_cron,
    validar_intervalo_horas,
)
from busca_voos.web import criar_app  # noqa: E402


@pytest.fixture()
def pasta():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        shutil.copyfile(RAIZ / "config.example.yaml", p / "config.yaml")
        yield p


def _com_intervalo(pasta: Path, minutos: int) -> Path:
    cfg = pasta / "config.yaml"
    t = cfg.read_text(encoding="utf-8")
    cfg.write_text(re.sub(r"intervalo_minutos:\s*\d+", f"intervalo_minutos: {minutos}", t, count=1), encoding="utf-8")
    return cfg


def test_opcoes_do_seletor_na_tela():
    html = (RAIZ / "src" / "busca_voos" / "painel.html").read_text(encoding="utf-8")
    for id_ in ("cron-horas", "cfg-cron-horas"):
        bloco = re.search(rf'<select[^>]*id="{id_}".*?</select>', html, re.S).group(0)
        valores = re.findall(r'<option value="([^"]+)"', bloco)
        assert valores == ["8", "12", "24", "168"], (id_, valores)
        assert re.search(r'<option value="168">Semanal</option>', bloco)
    assert INTERVALOS_PERMITIDOS_H == (8.0, 12.0, 24.0, 168.0)


def test_normalizar_sobe_para_o_proximo_permitido():
    assert [normalizar_intervalo_horas(x) for x in (0.5, 1, 6, 8, 9, 12, 13, 24, 30, 168, 500)] == \
           [8, 8, 8, 8, 12, 12, 24, 24, 168, 168, 168]


@pytest.mark.parametrize("ok", [8, 12, 24, 168, 8.0, "12", "168"])
def test_validar_aceita_so_a_lista(ok):
    assert validar_intervalo_horas(ok) in INTERVALOS_PERMITIDOS_H


@pytest.mark.parametrize("ruim", [0, 0.5, 1, 2.5, 4, 6, 7.99, 10, 48, 169, -8, "abc", None])
def test_validar_recusa_o_resto(ruim):
    with pytest.raises(ErroConfig):
        validar_intervalo_horas(ruim)


def test_config_antiga_curta_sobe_para_8h_no_modo_run(pasta):
    # o modo "run" (daemon/systemd) tambem nao pode consultar mais de 3x por dia
    for curto in (1, 30, 60, 360, 479):
        cfg = carregar_config(_com_intervalo(pasta, curto))
        assert cfg.agenda.intervalo_minutos == INTERVALO_MINIMO_MIN == 480
    assert carregar_config(_com_intervalo(pasta, 720)).agenda.intervalo_minutos == 720      # valido: intacto
    assert carregar_config(_com_intervalo(pasta, 10080)).agenda.intervalo_minutos == 10080


def test_painel_mostra_valor_que_o_seletor_conhece(pasta):
    cfg = _com_intervalo(pasta, 360)                     # 6 h (valor antigo do config.yaml)
    assert obter_intervalo_cron(cfg) == 8.0
    c = TestClient(criar_app(pasta / "d.sqlite3", caminho_config=cfg), base_url="http://127.0.0.1:8787")
    assert c.get("/api/cron").json()["intervalo_horas"] == 8.0


def test_salvar_gestao_com_intervalo_invalido_nao_grava_nada(pasta):
    cfg = pasta / "config.yaml"
    antes = cfg.read_text(encoding="utf-8")
    c = TestClient(criar_app(pasta / "d.sqlite3", caminho_config=cfg), base_url="http://127.0.0.1:8787")
    r = c.post("/api/configuracoes", json={
        "email": {"host": "smtp.office365.com", "de": "novo@gmail.com"},
        "cron": {"intervalo_horas": 2.5},
    })
    assert r.status_code == 400 and "nao permitido" in r.json()["detail"]
    assert cfg.read_text(encoding="utf-8") == antes                   # nem o e-mail foi gravado pela metade
    r = c.post("/api/configuracoes", json={"email": {"de": "novo@gmail.com"}, "cron": {"intervalo_horas": 168}})
    assert r.status_code == 200 and r.json()["configuracoes"]["cron"]["intervalo_horas"] == 168.0
