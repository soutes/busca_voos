import json
import os
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import pytest
from fastapi.testclient import TestClient

from busca_voos.config import (
    carregar_config,
    obter_configuracoes_gestao,
    salvar_configuracoes_gestao,
)
from busca_voos.db import Banco
from busca_voos.emailer import ErroEmail
from busca_voos.seguranca import (
    CHAVE_ARQUIVO,
    criptografar_texto,
    descriptografar_texto,
    mascarar_senha,
    obter_chave_mestra,
)
from busca_voos.sources.base import FonteBloqueada
from busca_voos.sources.navegador import abrir_navegador
from busca_voos.sources.skyscanner import SkyscannerFonte
from busca_voos.sources.trip_com import TripComFonte
from busca_voos.web import criar_app


def test_seguranca_fernet_e_mascara():
    with tempfile.TemporaryDirectory() as tmpdir:
        pasta = Path(tmpdir)
        chave = obter_chave_mestra(pasta)
        assert len(chave) > 20
        assert (pasta / CHAVE_ARQUIVO.name).is_file()

        # Re-obter deve ser a mesma chave
        assert obter_chave_mestra(pasta) == chave

        texto_original = "minha_senha_super_secreta_123"
        token = criptografar_texto(texto_original, pasta=pasta)
        assert token != texto_original
        assert len(token) > 20

        decriptado = descriptografar_texto(token, pasta=pasta)
        assert decriptado == texto_original

        # Token invalido retorna string vazia
        assert descriptografar_texto("token_invalido_qualquer", pasta=pasta) == ""
        assert descriptografar_texto("", pasta=pasta) == ""

        # Mascara
        assert mascarar_senha("qualquer_senha") == "••••••••••••"
        assert mascarar_senha("") == ""
        assert mascarar_senha("   ") == ""


def test_banco_tabela_configuracoes():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "teste.sqlite3"
        banco = Banco(db_path)

        # Padrao se chave nao existir
        assert banco.obter_configuracao("chave_inexistente", "padrao") == "padrao"

        # Salvar e recuperar
        banco.salvar_configuracao("smtp_senha", "token_encriptado_abc")
        assert banco.obter_configuracao("smtp_senha") == "token_encriptado_abc"

        # Update on conflict
        banco.salvar_configuracao("smtp_senha", "token_encriptado_novo")
        assert banco.obter_configuracao("smtp_senha") == "token_encriptado_novo"

        # Listar configuracoes
        banco.salvar_configuracao("tema", "escuro")
        todas = banco.listar_configuracoes()
        assert todas["smtp_senha"] == "token_encriptado_novo"
        assert todas["tema"] == "escuro"

        banco.fechar()


def test_gestao_configuracoes_e_fallback_senha():
    with tempfile.TemporaryDirectory() as tmpdir:
        pasta = Path(tmpdir)
        cfg_path = pasta / "config.yaml"
        db_path = pasta / "dados.sqlite3"
        shutil.copyfile(RAIZ / "config.example.yaml", cfg_path)

        # Limpa env var temporariamente
        old_env = os.environ.get("SMTP_SENHA")
        if "SMTP_SENHA" in os.environ:
            del os.environ["SMTP_SENHA"]

        try:
            # 1. Leitura inicial
            dados = obter_configuracoes_gestao(cfg_path, db_path)
            assert "email" in dados
            assert "fontes" in dados
            assert "cron" in dados
            assert dados["email"]["host"] == "smtp.gmail.com"
            assert dados["email"]["tem_senha"] is False
            assert dados["email"]["senha_mascarada"] == ""
            assert dados["fontes"]["google_flights"] is True

            # 2. Salvar novas configuracoes de email com senha criptografada e fontes
            novos_dados = {
                "email": {
                    "host": "smtp.office365.com",
                    "porta": 587,
                    "tls": True,
                    "de": "alertas@empresa.com",
                    "para": ["usuario1@empresa.com", "usuario2@empresa.com"],
                    "senha": "senha_de_app_12345",
                },
                "fontes": {
                    "google_flights": True,
                    "trip_com": False,
                    "skyscanner": True,
                    "skiplagged": False,
                },
                "cron": {
                    "intervalo_horas": 12.0,
                },
            }

            retorno = salvar_configuracoes_gestao(cfg_path, db_path, novos_dados)
            assert retorno["email"]["host"] == "smtp.office365.com"
            assert retorno["email"]["de"] == "alertas@empresa.com"
            assert retorno["email"]["para"] == ["usuario1@empresa.com", "usuario2@empresa.com"]
            assert retorno["email"]["tem_senha"] is True
            assert retorno["email"]["senha_mascarada"] == "••••••••••••"
            assert retorno["fontes"]["trip_com"] is False
            assert retorno["fontes"]["skiplagged"] is False
            assert retorno["cron"]["intervalo_horas"] == 12.0

            # Verifica se senha foi gravada criptografada no banco
            banco = Banco(db_path)
            token_db = banco.obter_configuracao("smtp_senha")
            banco.fechar()
            assert token_db != ""
            assert token_db != "senha_de_app_12345"
            assert descriptografar_texto(token_db, pasta=pasta) == "senha_de_app_12345"

            # 3. Testar carregar_config com fallback de senha do SQLite
            if "SMTP_SENHA" in os.environ:
                del os.environ["SMTP_SENHA"]

            cfg_carregada = carregar_config(cfg_path)
            assert cfg_carregada.email.senha == "senha_de_app_12345"
            assert os.environ.get("SMTP_SENHA") == "senha_de_app_12345"

            # 4. Salvar com senha mascarada NAO deve sobrescrever a senha existente
            salvar_configuracoes_gestao(
                cfg_path,
                db_path,
                {
                    "email": {
                        "senha": "••••••••••••",
                        "host": "smtp.office365.com",
                    }
                },
            )
            banco = Banco(db_path)
            token_depois = banco.obter_configuracao("smtp_senha")
            banco.fechar()
            assert descriptografar_texto(token_depois, pasta=pasta) == "senha_de_app_12345"

        finally:
            if old_env is not None:
                os.environ["SMTP_SENHA"] = old_env
            elif "SMTP_SENHA" in os.environ:
                del os.environ["SMTP_SENHA"]


def test_web_endpoints_gestao_e_versao():
    with tempfile.TemporaryDirectory() as tmpdir:
        pasta = Path(tmpdir)
        cfg_path = pasta / "config.yaml"
        db_path = pasta / "dados.sqlite3"
        shutil.copyfile(RAIZ / "config.example.yaml", cfg_path)

        app = criar_app(db_path, caminho_config=cfg_path)
        client = TestClient(app, base_url="http://127.0.0.1:8787")

        # GET /api/versao
        r_ver = client.get("/api/versao")
        assert r_ver.status_code == 200
        assert r_ver.json() == {"versao": "1.2.0", "nome": "busca_voos", "repositorio": "local"}

        # GET /api/configuracoes
        r_get = client.get("/api/configuracoes")
        assert r_get.status_code == 200
        dados = r_get.json()
        assert "email" in dados
        assert "fontes" in dados
        assert "cron" in dados
        assert "ativo" in dados["cron"]
        assert "segundos_restantes" in dados["cron"]

        # POST /api/configuracoes
        payload = {
            "email": {
                "host": "smtp.gmail.com",
                "porta": 587,
                "tls": True,
                "de": "teste@gmail.com",
                "para": ["destino@gmail.com"],
                "senha": "senha_teste_api",
            },
            "fontes": {
                "google_flights": True,
                "trip_com": True,
                "skyscanner": False,
                "skiplagged": True,
            },
            "cron": {
                "ativo": True,
                "intervalo_horas": 24.0,
            },
        }
        r_post = client.post("/api/configuracoes", json=payload)
        assert r_post.status_code == 200
        res = r_post.json()
        assert res["ok"] is True
        cfg_resp = res["configuracoes"]
        assert cfg_resp["email"]["de"] == "teste@gmail.com"
        assert cfg_resp["email"]["tem_senha"] is True
        assert cfg_resp["fontes"]["skyscanner"] is False
        assert cfg_resp["cron"]["intervalo_horas"] == 24.0
        assert cfg_resp["cron"]["ativo"] is True
        assert cfg_resp["cron"]["proxima_execucao"] is not None


def test_web_endpoint_testar_email():
    with tempfile.TemporaryDirectory() as tmpdir:
        pasta = Path(tmpdir)
        cfg_path = pasta / "config.yaml"
        db_path = pasta / "dados.sqlite3"
        shutil.copyfile(RAIZ / "config.example.yaml", cfg_path)

        app = criar_app(db_path, caminho_config=cfg_path)
        client = TestClient(app, base_url="http://127.0.0.1:8787")

        # Sem credenciais/remetente valido -> deve retornar 400
        r_fail = client.post("/api/email/testar", json={"de": "", "para": []})
        assert r_fail.status_code == 400

        # Com remetente e destinatario mas sem senha -> 400
        r_sem_senha = client.post(
            "/api/email/testar",
            json={"de": "remetente@teste.com", "para": ["dest@teste.com"], "senha": ""},
        )
        assert r_sem_senha.status_code == 400
        assert "Senha SMTP ausente" in r_sem_senha.json()["detail"]

        # Sucesso simulado via mock de enviar
        with patch("busca_voos.web.enviar") as mock_enviar:
            mock_enviar.return_value = None
            r_ok = client.post(
                "/api/email/testar",
                json={
                    "host": "smtp.teste.com",
                    "porta": 587,
                    "tls": True,
                    "de": "remetente@teste.com",
                    "para": ["dest@teste.com"],
                    "senha": "senha_smtp_correta",
                },
            )
            assert r_ok.status_code == 200
            assert r_ok.json()["ok"] is True
            assert "sucesso" in r_ok.json()["mensagem"]
            mock_enviar.assert_called_once()

        # Falha simulada do servidor SMTP -> 400
        with patch("busca_voos.web.enviar", side_effect=ErroEmail("Falha na autenticacao")):
            r_smtp_erro = client.post(
                "/api/email/testar",
                json={
                    "de": "remetente@teste.com",
                    "para": ["dest@teste.com"],
                    "senha": "senha_errada",
                },
            )
            assert r_smtp_erro.status_code == 400
            assert "Falha na autenticacao" in r_smtp_erro.json()["detail"]


def test_scraper_anti_bot_navegador_args():
    cfg = carregar_config(RAIZ / "config.example.yaml")

    mock_playwright = MagicMock()
    mock_chromium = MagicMock()
    mock_playwright.chromium = mock_chromium

    with patch("playwright.sync_api.sync_playwright") as mock_sync:
        mock_sync.return_value.__enter__.return_value = mock_playwright
        try:
            with abrir_navegador(cfg):
                pass
        except Exception:
            pass

        assert mock_chromium.launch.called
        kwargs = mock_chromium.launch.call_args[1]
        assert "args" in kwargs
        assert "--disable-blink-features=AutomationControlled" in kwargs["args"]
        assert "--no-sandbox" in kwargs["args"]


def test_scraper_trip_com_whaleguard_e_seletores():
    cfg = carregar_config(RAIZ / "config.example.yaml")
    fonte = TripComFonte(cfg)

    # 1. HTML com "whaleguard block" dispara FonteBloqueada
    mock_page_bloqueada = MagicMock()
    mock_page_bloqueada.content.return_value = "<html><body>WhaleGuard block detection</body></html>"
    mock_ctx = MagicMock()
    mock_ctx.new_page.return_value = mock_page_bloqueada

    with patch("busca_voos.sources.trip_com.abrir_navegador") as mock_nav:
        mock_nav.return_value.__enter__.return_value = mock_ctx
        with pytest.raises(FonteBloqueada, match="WhaleGuard"):
            fonte.buscar("FLN", "RIO", date(2026, 12, 25))

    # 2. HTML muito curto (< 300 chars) dispara FonteBloqueada
    mock_page_curta = MagicMock()
    mock_page_curta.content.return_value = "<html><body>Empty</body></html>"
    mock_ctx.new_page.return_value = mock_page_curta

    with patch("busca_voos.sources.trip_com.abrir_navegador") as mock_nav:
        mock_nav.return_value.__enter__.return_value = mock_ctx
        with pytest.raises(FonteBloqueada, match="WhaleGuard"):
            fonte.buscar("FLN", "RIO", date(2026, 12, 25))


def test_scraper_skyscanner_url_captcha_px():
    cfg = carregar_config(RAIZ / "config.example.yaml")
    fonte = SkyscannerFonte(cfg)

    mock_page = MagicMock()
    mock_page.url = "https://www.skyscanner.com.br/px/challenge/captcha"
    mock_ctx = MagicMock()
    mock_ctx.new_page.return_value = mock_page

    with patch("busca_voos.sources.skyscanner.abrir_navegador") as mock_nav:
        mock_nav.return_value.__enter__.return_value = mock_ctx
        with pytest.raises(FonteBloqueada, match="PerimeterX / Captcha"):
            fonte.buscar("FLN", "RIO", date(2026, 12, 25))
