import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from fastapi.testclient import TestClient

from busca_voos.aeroportos import (
    buscar_aeroportos,
    resolver_para_fonte,
    validar_iata,
)
from busca_voos.config import carregar_config
from busca_voos.models import Oferta
from busca_voos.scheduler import ciclo
from busca_voos.sources.base import ErroFonte, FonteBloqueada
from busca_voos.sources.skiplagged import SkiplaggedFonte
from busca_voos.web import criar_app

RAIZ = Path(__file__).resolve().parent.parent


def test_catalogo_aeroportos_br():
    for cod in ["FLN", "GRU", "CGH", "VCP", "GIG", "SDU", "BSB", "CNF", "SSA", "REC", "FOR", "POA", "CWB", "VIX", "GYN"]:
        info = validar_iata(cod)
        assert info is not None
        assert info["pais"] == "Brasil"
        assert info["codigo"] == cod


def test_metropolitanos():
    assert resolver_para_fonte("RIO", "skiplagged") == "GIG"
    assert resolver_para_fonte("rio", "skiplagged") == "GIG"
    assert resolver_para_fonte("SAO", "skiplagged") == "GRU"
    assert resolver_para_fonte("BHZ", "skiplagged") == "CNF"
    assert resolver_para_fonte("BUE", "skiplagged") == "EZE"
    assert resolver_para_fonte("NYC", "skiplagged") == "JFK"
    assert resolver_para_fonte("LON", "skiplagged") == "LHR"
    assert resolver_para_fonte("PAR", "skiplagged") == "CDG"
    assert resolver_para_fonte("FLN", "skiplagged") == "FLN"
    assert resolver_para_fonte("RIO", "google_flights") == "RIO"


def test_buscar_aeroportos():
    top15 = buscar_aeroportos("")
    assert len(top15) == 15
    assert top15[0]["pais"] == "Brasil"

    res_fln = buscar_aeroportos("florianopolis")
    assert res_fln[0]["codigo"] == "FLN"

    res_rio = buscar_aeroportos("rio", limite=5)
    assert len(res_rio) == 5
    assert res_rio[0]["codigo"] == "RIO"


def test_skiplagged_resolucao():
    cfg = carregar_config(RAIZ / "config.yaml")
    fonte = SkiplaggedFonte(cfg)
    with patch.object(fonte, "_via_api", return_value=[]) as mock_api:
        with patch.object(fonte, "_via_navegador", return_value=[]):
            fonte.buscar("FLN", "RIO", date(2026, 12, 25))
            args = mock_api.call_args[0]
            assert args[0] == "FLN"
            assert args[1] == "GIG"


def test_scheduler_diagnostico_e_json_serializable():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_tmp = Path(tmpdir) / "teste.sqlite3"
        cfg_tmp = carregar_config(RAIZ / "config.yaml")
        cfg_tmp.banco = db_tmp
        cfg_tmp.agenda.pausa_entre_consultas_s = 0
        cfg_tmp.agenda.pausa_entre_fontes_s = 0
        cfg_tmp.agenda.max_combinacoes_por_ciclo = 1

        mock_oferta = Oferta(
            fonte="google_flights",
            rota="FLN-RIO",
            origem="FLN",
            destino="RIO",
            data_ida=date(2026, 12, 25),
            data_volta=date(2027, 1, 4),
            preco=750.0,
            moeda="BRL",
            link="https://google.com",
        )

        class MockOk:
            def __init__(self, cfg): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def buscar(self, o, d, ida, volta): return [mock_oferta]

        class MockVazia:
            def __init__(self, cfg): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def buscar(self, o, d, ida, volta): return []

        with patch.dict("busca_voos.scheduler.REGISTRO", {"ok": MockOk, "vazia": MockVazia}, clear=False):
            resumo = ciclo(cfg_tmp, enviar_email=False, fontes=["ok", "vazia", "pendente"])
            assert "detalhes_fontes" in resumo
            assert resumo["detalhes_fontes"]["ok"]["status"] == "ok"
            assert resumo["detalhes_fontes"]["ok"]["ofertas"] > 0
            assert resumo["detalhes_fontes"]["vazia"]["status"] == "aviso"
            assert resumo["detalhes_fontes"]["vazia"]["ofertas"] == 0
            assert resumo["detalhes_fontes"]["pendente"]["status"] == "erro"
            assert "diagnostico" in resumo

            # Serialização JSON completa
            serializado = json.dumps(resumo)
            assert len(serializado) > 0


def test_web_endpoints():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "dados.sqlite3"
        cfg_path = Path(tmpdir) / "config.yaml"
        shutil.copyfile(RAIZ / "config.yaml", cfg_path)

        app = criar_app(db_path, caminho_config=cfg_path)
        client = TestClient(app)

        # GET /api/aeroportos
        r = client.get("/api/aeroportos?q=rio&limite=5")
        assert r.status_code == 200
        assert len(r.json()["aeroportos"]) == 5
        assert r.json()["aeroportos"][0]["codigo"] == "RIO"

        # GET /api/ciclo/status
        r_st = client.get("/api/ciclo/status")
        assert r_st.status_code == 200
        diag = r_st.json().get("diagnostico")
        assert diag is not None
        assert "detalhes_fontes" in diag
        assert "fontes_ok" in diag
        assert "fontes_erro" in diag
        assert "consultas" in diag
        assert "alertas_count" in diag
