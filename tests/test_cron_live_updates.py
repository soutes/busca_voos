import json
import shutil
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import pytest
from fastapi.testclient import TestClient

from busca_voos.config import (
    ErroConfig,
    carregar_config,
    obter_intervalo_cron,
    salvar_intervalo_cron,
)
from busca_voos.models import Oferta
from busca_voos.scheduler import ciclo
from busca_voos.web import _ciclo_lock, _status_ciclo, criar_app


def test_obter_e_salvar_intervalo_cron():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / "config.yaml"
        shutil.copyfile(RAIZ / "config.example.yaml", cfg_path)

        # 1. O exemplo tem 60 min: abaixo do minimo, a leitura sobe para 8 h (o seletor so tem 8/12/24/168)
        assert obter_intervalo_cron(cfg_path) == 8.0

        # 2. Salvar 12 horas -> 720 minutos
        assert salvar_intervalo_cron(cfg_path, 12) == 12.0
        assert obter_intervalo_cron(cfg_path) == 12.0
        conteudo = cfg_path.read_text(encoding="utf-8")
        assert "intervalo_minutos: 720" in conteudo
        assert 'periodicidade do modo "run"' in conteudo          # comentarios preservados
        assert "max_combinacoes_por_ciclo: 12" in conteudo

        # 3. Semanal: 168 h -> 10080 minutos
        salvar_intervalo_cron(cfg_path, 168)
        assert obter_intervalo_cron(cfg_path) == 168.0
        assert "intervalo_minutos: 10080" in cfg_path.read_text(encoding="utf-8")

        # 4. Qualquer outro valor e recusado e o arquivo nao muda
        from busca_voos.config import ErroConfig
        antes = cfg_path.read_text(encoding="utf-8")
        for proibido in (0.001, 0.5, 1, 2.5, 6, 9, 169, 0, -8, "abc"):
            with pytest.raises(ErroConfig):
                salvar_intervalo_cron(cfg_path, proibido)
        assert cfg_path.read_text(encoding="utf-8") == antes


def test_obter_intervalo_fallback_sem_agenda():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / "config_sem_agenda.yaml"
        cfg_path.write_text("moeda: BRL\nrotas: []\n", encoding="utf-8")
        # Sem agenda, o padrao e o minimo permitido: 8 h
        assert obter_intervalo_cron(cfg_path) == 8.0


def test_scheduler_progresso_cb():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_tmp = Path(tmpdir) / "teste.sqlite3"
        cfg_tmp = carregar_config(RAIZ / "config.example.yaml")
        cfg_tmp.banco = db_tmp
        cfg_tmp.agenda.pausa_entre_consultas_s = 0
        cfg_tmp.agenda.pausa_entre_fontes_s = 0
        cfg_tmp.agenda.max_combinacoes_por_ciclo = 1

        mock_oferta_1 = Oferta(
            fonte="fonte_a",
            rota="FLN-RIO",
            origem="FLN",
            destino="RIO",
            data_ida=date(2026, 12, 25),
            data_volta=date(2027, 1, 4),
            preco=500.0,
            moeda="BRL",
            link="https://exemplo.com/1",
        )
        mock_oferta_2 = Oferta(
            fonte="fonte_a",
            rota="FLN-RIO",
            origem="FLN",
            destino="RIO",
            data_ida=date(2026, 12, 25),
            data_volta=date(2027, 1, 4),
            preco=600.0,
            moeda="BRL",
            link="https://exemplo.com/2",
        )

        class MockFonteA:
            def __init__(self, cfg): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def buscar(self, o, d, ida, volta):
                return [mock_oferta_1, mock_oferta_2]

        eventos_progresso = []
        def on_progresso(info: dict):
            eventos_progresso.append(dict(info))

        with patch.dict("busca_voos.scheduler.REGISTRO", {"fonte_a": MockFonteA}, clear=False):
            resumo = ciclo(cfg_tmp, enviar_email=False, fontes=["fonte_a"], progresso_cb=on_progresso)

            assert len(eventos_progresso) >= 1
            primeiro = eventos_progresso[0]
            assert "consultas" in primeiro
            assert "ofertas" in primeiro
            assert "fonte_atual" in primeiro
            assert "detalhes_fontes" in primeiro

            assert primeiro["fonte_atual"] == "fonte_a"
            assert primeiro["ofertas"] >= 2
            assert primeiro["consultas"] >= 1


def test_web_cron_endpoints_get_e_post():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "dados.sqlite3"
        cfg_path = Path(tmpdir) / "config.yaml"
        shutil.copyfile(RAIZ / "config.example.yaml", cfg_path)

        app = criar_app(db_path, caminho_config=cfg_path)
        client = TestClient(app, base_url="http://127.0.0.1:8787")

        # 1. GET /api/cron inicial
        r_get = client.get("/api/cron")
        assert r_get.status_code == 200
        dados_cron = r_get.json()
        assert dados_cron["ativo"] is False
        assert dados_cron["intervalo_horas"] == 8.0
        assert dados_cron["intervalo_minutos"] == 480
        assert dados_cron["proxima_execucao"] is None
        assert dados_cron["segundos_restantes"] is None

        # 2. POST /api/cron invalido: curto demais (risco de bloqueio de IP)
        for curto in (0.05, 1, 2.0, 6):
            r_err1 = client.post("/api/cron", json={"ativo": True, "intervalo_horas": curto})
            assert r_err1.status_code == 400
            assert "bloquearem" in r_err1.json()["detail"]
        assert client.get("/api/cron").json()["ativo"] is False         # nada foi ligado

        # 3. POST /api/cron invalido: acima de 168 ou fora da lista
        assert client.post("/api/cron", json={"ativo": True, "intervalo_horas": 169}).status_code == 400
        assert client.post("/api/cron", json={"ativo": True, "intervalo_horas": 10}).status_code == 400

        # 4. POST /api/cron valido: ativar com 12 horas
        r_post = client.post("/api/cron", json={"ativo": True, "intervalo_horas": 12})
        assert r_post.status_code == 200
        novo_cron = r_post.json()
        assert novo_cron["ativo"] is True
        assert novo_cron["intervalo_horas"] == 12.0
        assert novo_cron["intervalo_minutos"] == 720
        assert novo_cron["proxima_execucao"] is not None
        assert novo_cron["segundos_restantes"] is not None
        assert novo_cron["segundos_restantes"] > 0

        # Confirma que config.yaml foi atualizado no disco
        assert obter_intervalo_cron(cfg_path) == 12.0

        # 4b. Semanal
        r_sem = client.post("/api/cron", json={"ativo": True, "intervalo_horas": 168})
        assert r_sem.status_code == 200 and r_sem.json()["intervalo_minutos"] == 10080

        # 5. POST /api/cron desativando
        r_post_desativar = client.post("/api/cron", json={"ativo": False, "intervalo_horas": 12})
        assert r_post_desativar.status_code == 200
        desativado = r_post_desativar.json()
        assert desativado["ativo"] is False
        assert desativado["proxima_execucao"] is None
        assert desativado["segundos_restantes"] is None


def test_web_cron_background_trigger():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "dados.sqlite3"
        cfg_path = Path(tmpdir) / "config.yaml"
        shutil.copyfile(RAIZ / "config.example.yaml", cfg_path)

        app = criar_app(db_path, caminho_config=cfg_path)
        client = TestClient(app, base_url="http://127.0.0.1:8787")

        # Mock de _executar_ciclo para inspecionar chamada pelo loop cron
        chamadas_execucao = []
        app.state.executar_ciclo = lambda: chamadas_execucao.append(True)

        assert isinstance(app.state.cron_state, dict)

        # Ativa cron e simula proxima_execucao no passado
        now = datetime.now(timezone.utc)
        passado = now - timedelta(seconds=10)
        app.state.cron_state["ativo"] = True
        app.state.cron_state["intervalo_horas"] = 1.0
        app.state.cron_state["proxima_execucao"] = passado

        # Aguarda a thread de loop cron (checa a cada ~2s) disparar
        inicio = time.time()
        while time.time() - inicio < 4.5:
            if app.state.cron_state.get("ultima_execucao") is not None:
                break
            time.sleep(0.3)

        assert app.state.cron_state.get("ultima_execucao") is not None
        proxima = app.state.cron_state.get("proxima_execucao")
        assert proxima is not None
        if isinstance(proxima, str):
            proxima_dt = datetime.fromisoformat(proxima)
        else:
            proxima_dt = proxima
        if proxima_dt.tzinfo is None:
            proxima_dt = proxima_dt.replace(tzinfo=timezone.utc)
        # Proxima execucao deve ter sido avancada para o futuro
        assert proxima_dt > now

        # Desativa para limpar estado
        app.state.cron_state["ativo"] = False


def test_web_live_progresso_status():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "dados.sqlite3"
        cfg_path = Path(tmpdir) / "config.yaml"
        shutil.copyfile(RAIZ / "config.example.yaml", cfg_path)

        app = criar_app(db_path, caminho_config=cfg_path)
        client = TestClient(app, base_url="http://127.0.0.1:8787")

        # Simula progresso ao vivo em _status_ciclo
        with _ciclo_lock:
            _status_ciclo["rodando"] = True
            _status_ciclo["ofertas_encontradas"] = 15
            _status_ciclo["consultas_feitas"] = 4
            _status_ciclo["fonte_atual"] = "skiplagged"
            _status_ciclo["mensagem"] = "Consultando skiplagged (15 ofertas encontradas até agora)..."

        r = client.get("/api/ciclo/status")
        assert r.status_code == 200
        dados = r.json()
        assert dados["rodando"] is True
        assert dados["ofertas_encontradas"] == 15
        assert dados["consultas_feitas"] == 4
        assert dados["fonte_atual"] == "skiplagged"
        assert dados["mensagem"] == "Consultando skiplagged (15 ofertas encontradas até agora)..."

        # Limpa apos o teste
        with _ciclo_lock:
            _status_ciclo["rodando"] = False


def test_iniciar_ciclo_endpoint():
    import threading

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "dados.sqlite3"
        cfg_path = Path(tmpdir) / "config.yaml"
        shutil.copyfile(RAIZ / "config.example.yaml", cfg_path)

        app = criar_app(db_path, caminho_config=cfg_path)
        client = TestClient(app, base_url="http://127.0.0.1:8787")

        bloqueio = threading.Event()
        iniciou = threading.Event()

        def _ciclo_bloqueado(*a, **k):
            iniciou.set()
            bloqueio.wait(timeout=2.0)
            return {"ciclo": 1, "alertas": [], "consultas": 2}

        with patch("busca_voos.scheduler.ciclo", side_effect=_ciclo_bloqueado):
            # Primeiro POST inicia ciclo
            r1 = client.post("/api/ciclo")
            assert r1.status_code == 200
            assert r1.json()["ok"] is True
            assert r1.json()["status"] == "iniciado"

            # Aguarda a thread de ciclo comecar a rodar efetivamente
            assert iniciou.wait(timeout=2.0)

            # Enquanto estiver rodando, segundo POST recusa
            r2 = client.post("/api/ciclo")
            assert r2.status_code == 200
            assert r2.json()["ok"] is False
            assert "já em andamento" in r2.json()["mensagem"]

            # Libera a thread para finalizar
            bloqueio.set()
            time.sleep(0.1)


def test_post_cron_payloads_parciais():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "dados.sqlite3"
        cfg_path = Path(tmpdir) / "config.yaml"
        shutil.copyfile(RAIZ / "config.example.yaml", cfg_path)

        app = criar_app(db_path, caminho_config=cfg_path)
        client = TestClient(app, base_url="http://127.0.0.1:8787")

        # Atualiza apenas intervalo_horas sem enviar ativo
        r1 = client.post("/api/cron", json={"intervalo_horas": 24})
        assert r1.status_code == 200
        assert r1.json()["intervalo_horas"] == 24.0
        assert r1.json()["intervalo_minutos"] == 1440

        # Atualiza apenas ativo sem enviar intervalo_horas
        r2 = client.post("/api/cron", json={"ativo": True})
        assert r2.status_code == 200
        assert r2.json()["ativo"] is True
        assert r2.json()["intervalo_horas"] == 24.0
        assert r2.json()["proxima_execucao"] is not None

