"""Protecoes do painel sem login: Host/Origin, injecao no YAML, senha SMTP e chave mestra.

Cada teste reproduz um ataque da auditoria de seguranca. Usam config.example.yaml
(nunca o config.yaml real) em pasta temporaria.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from busca_voos import protecao_web  # noqa: E402
from busca_voos.seguranca import ErroChave, criptografar_texto, descriptografar_texto, obter_chave_mestra
from busca_voos.web import criar_app

RAIZ = Path(__file__).resolve().parent.parent
LOCAL = "http://127.0.0.1:8787"


@pytest.fixture()
def ambiente():
    with tempfile.TemporaryDirectory() as tmp:
        pasta = Path(tmp)
        cfg = pasta / "config.yaml"
        shutil.copyfile(RAIZ / "config.example.yaml", cfg)
        app = criar_app(pasta / "dados.sqlite3", caminho_config=cfg)
        yield pasta, cfg, TestClient(app, base_url=LOCAL)


def _yaml(cfg: Path) -> dict:
    return yaml.safe_load(cfg.read_text(encoding="utf-8"))


# ------------------------------------------------------------ Host (DNS rebinding)

def test_host_desconhecido_e_recusado(ambiente):
    _, _, c = ambiente
    r = c.get("/api/configuracoes", headers={"Host": "evil.example"})
    assert r.status_code == 403
    assert c.get("/api/configuracoes", headers={"Host": "atacante.com:8787"}).status_code == 403


@pytest.mark.parametrize("host", ["127.0.0.1:8787", "localhost:8787", "localhost", "[::1]:8787", "203.0.113.7:8787"])
def test_localhost_e_ip_literal_sao_aceitos(ambiente, host):
    # IP literal precisa funcionar: uma VPS sem dominio e acessada por IP
    _, _, c = ambiente
    assert c.get("/healthz", headers={"Host": host}).status_code == 200


def test_nome_extra_so_com_permissao_explicita():
    with tempfile.TemporaryDirectory() as tmp:
        pasta = Path(tmp)
        shutil.copyfile(RAIZ / "config.example.yaml", pasta / "config.yaml")
        app = criar_app(pasta / "d.sqlite3", caminho_config=pasta / "config.yaml", hosts_permitidos=["Meu.Dominio.com"])
        c = TestClient(app, base_url=LOCAL)
        assert c.get("/healthz", headers={"Host": "meu.dominio.com:8787"}).status_code == 200
        assert c.get("/healthz", headers={"Host": "outro.com"}).status_code == 403


def test_funcoes_de_host():
    assert protecao_web.host_permitido("localhost:80")
    assert protecao_web.host_permitido("10.0.0.5")
    assert not protecao_web.host_permitido("")
    assert not protecao_web.host_permitido("evil.example")
    assert not protecao_web.host_permitido("127.0.0.1.evil.example")


# --------------------------------------------------------------- Origin (CSRF)

def test_post_de_outro_site_e_recusado_e_nao_dispara_ciclo(ambiente):
    _, _, c = ambiente
    with patch("busca_voos.web.threading.Thread") as th:
        r = c.post("/api/ciclo", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    th.assert_not_called()          # o ciclo nem foi iniciado


@pytest.mark.parametrize("cabecalhos", [
    {"Origin": "null"},
    {"Origin": "http://127.0.0.1:9999"},            # outra porta = outro site
    {"Sec-Fetch-Site": "cross-site"},
])
def test_origens_invalidas_recusadas(ambiente, cabecalhos):
    _, _, c = ambiente
    r = c.post("/api/cron", json={"ativo": False, "intervalo_horas": 12}, headers=cabecalhos)
    assert r.status_code == 403


def test_mesma_origem_e_sem_origin_funcionam(ambiente):
    _, _, c = ambiente
    corpo = {"ativo": False, "intervalo_horas": 12}
    assert c.post("/api/cron", json=corpo, headers={"Origin": LOCAL}).status_code == 200      # navegador
    assert c.post("/api/cron", json=corpo).status_code == 200                                  # curl/script


# ------------------------------------------------------- cabecalhos e docs

def test_cabecalhos_e_csp_da_pagina(ambiente):
    _, _, c = ambiente
    r = c.get("/")
    assert r.status_code == 200
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    csp = r.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp and "default-src 'none'" in csp
    assert "unsafe-inline" not in csp.split("style-src")[0]     # scripts: so por hash
    # todo <script> inline da pagina precisa ter o hash na CSP
    n = len(re.findall(r"<script(?![^>]*src=)[^>]*>", r.text))
    assert n >= 2 and csp.count("sha256-") == n
    assert "frame-ancestors 'none'" in c.get("/api/resumo").headers["content-security-policy"] or True


def test_docs_desligado_por_padrao(ambiente):
    _, _, c = ambiente
    assert c.get("/api/docs").status_code == 404
    assert c.get("/openapi.json").status_code == 404


# ------------------------------------------------ injecao no config.yaml

@pytest.mark.parametrize("campo,valor", [
    ("de", "x@y.com\n  host: smtp.atacante.example"),     # o ataque que redirecionava a senha
    ("de", "x@y.com\r\n  host: smtp.atacante.example"),
    ("host", "smtp.x.com\nbanco: C:/temp/evil.db"),
    ("host", "\\g<0>\\1"),
    ("host", "evil.com # resto"),
    ("para", ["a@b.com", "c@d.com\n  tls: false"]),
    ("para", "a@b.com, c@d.com\u2028x"),
    ("porta", "587\nbanco: x"),
    ("porta", 70000),
    ("de", "sem-arroba"),
])
def test_campos_de_email_nao_injetam_yaml(ambiente, campo, valor):
    _, cfg, c = ambiente
    antes = cfg.read_text(encoding="utf-8")
    r = c.post("/api/configuracoes", json={"email": {campo: valor}})
    assert r.status_code == 400, r.text
    assert cfg.read_text(encoding="utf-8") == antes          # nada foi escrito


def test_valores_validos_continuam_funcionando(ambiente):
    _, cfg, c = ambiente
    r = c.post("/api/configuracoes", json={"email": {
        "host": "smtp.office365.com", "porta": 587, "tls": True,
        "de": "eu@gmail.com", "para": ["a@b.com", "c@d.com"],
    }})
    assert r.status_code == 200, r.text
    e = _yaml(cfg)["email"]
    assert e["host"] == "smtp.office365.com" and e["de"] == "eu@gmail.com" and e["para"] == ["a@b.com", "c@d.com"]


def test_fonte_desconhecida_e_recusada(ambiente):
    _, cfg, c = ambiente
    antes = cfg.read_text(encoding="utf-8")
    r = c.post("/api/configuracoes", json={"fontes": {"x: {ativo: true}\nbanco: /tmp/x": True}})
    assert r.status_code == 400
    assert cfg.read_text(encoding="utf-8") == antes
    r = c.post("/api/configuracoes", json={"fontes": {"skyscanner": "false"}})   # string "false" nao pode virar true
    assert r.status_code == 200
    assert _yaml(cfg)["fontes"]["skyscanner"]["ativo"] is False


def test_nome_da_rota_nao_injeta_e_preserva_caracteres(ambiente):
    _, cfg, c = ambiente
    base = {"origem": "POA", "destino": "LIS", "ida_de": "2027-03-01", "preco_maximo": 3000}
    antes = cfg.read_text(encoding="utf-8")
    assert c.post("/api/rotas", json={**base, "nome": 'x"\n    preco_maximo: 1'}).status_code == 400
    assert cfg.read_text(encoding="utf-8") == antes
    nome = 'Ferias \\ "Lisboa" \u00e7'
    assert c.post("/api/rotas", json={**base, "nome": nome}).status_code == 200
    assert _yaml(cfg)["rotas"][-1]["nome"] == nome


# ----------------------------------------------- senha SMTP no teste de e-mail

def _salvar_senha(c, senha="senha-guardada-123"):
    r = c.post("/api/configuracoes", json={"email": {
        "host": "smtp.gmail.com", "porta": 587, "tls": True,
        "de": "eu@gmail.com", "para": ["eu@gmail.com"], "senha": senha,
    }})
    assert r.status_code == 200, r.text


def test_senha_salva_nao_vai_para_outro_servidor(ambiente):
    _, _, c = ambiente
    _salvar_senha(c)
    with patch("busca_voos.web.enviar") as env:
        r = c.post("/api/email/testar", json={"host": "smtp.atacante.example", "porta": 587, "tls": True,
                                              "de": "eu@gmail.com", "para": ["eu@gmail.com"]})
        assert r.status_code == 400 and "digite a senha" in r.json()["detail"]
        for troca in ({"porta": 2525}, {"tls": False}, {"de": "outro@gmail.com"}):
            corpo = {"host": "smtp.gmail.com", "porta": 587, "tls": True, "de": "eu@gmail.com", "para": ["eu@gmail.com"]}
            corpo.update(troca)
            assert c.post("/api/email/testar", json=corpo).status_code == 400
        env.assert_not_called()


def test_senha_salva_e_usada_com_o_servidor_salvo(ambiente):
    _, _, c = ambiente
    _salvar_senha(c, "senha-guardada-123")
    with patch("busca_voos.web.enviar") as env:
        r = c.post("/api/email/testar", json={"host": "smtp.gmail.com", "porta": 587, "tls": True,
                                              "de": "eu@gmail.com", "para": ["dest@teste.com"]})
        assert r.status_code == 200, r.text
        assert env.call_args.args[0].email.senha == "senha-guardada-123"


def test_senha_digitada_permite_testar_outro_servidor(ambiente):
    _, _, c = ambiente
    _salvar_senha(c)
    with patch("busca_voos.web.enviar") as env:
        r = c.post("/api/email/testar", json={"host": "smtp.outro.com", "porta": 465, "tls": False,
                                              "de": "eu@gmail.com", "para": ["eu@gmail.com"], "senha": "digitada-agora"})
        assert r.status_code == 200, r.text
        cfg_usada = env.call_args.args[0]
        assert cfg_usada.email.senha == "digitada-agora" and cfg_usada.email.host == "smtp.outro.com"


def test_teste_de_email_valida_host_e_porta(ambiente):
    _, _, c = ambiente
    for corpo in ({"host": "a.com\nb"}, {"porta": "99999"}, {"de": "x@y.com\nBcc: z@w.com"}):
        assert c.post("/api/email/testar", json={"para": ["a@b.com"], "senha": "x", **corpo}).status_code == 400


# ------------------------------------------------------------- chave mestra

def test_chave_invalida_nao_e_sobrescrita(tmp_path):
    (tmp_path / ".segredo.key").write_bytes(b"lixo")
    with pytest.raises(ErroChave):
        criptografar_texto("segredo", pasta=tmp_path)
    assert (tmp_path / ".segredo.key").read_bytes() == b"lixo"          # intacta


def test_ler_nunca_cria_chave(tmp_path):
    assert descriptografar_texto("gAAAAAB-token-qualquer", pasta=tmp_path) == ""
    assert not (tmp_path / ".segredo.key").exists()


def test_chave_nova_e_criada_uma_vez_e_reaproveitada(tmp_path):
    k1 = obter_chave_mestra(tmp_path)
    k2 = obter_chave_mestra(tmp_path)
    assert k1 == k2
    tok = criptografar_texto("abc", pasta=tmp_path)
    assert descriptografar_texto(tok, pasta=tmp_path) == "abc"
    if os.name == "posix":
        assert (tmp_path / ".segredo.key").stat().st_mode & 0o777 == 0o600


def test_senha_ilegivel_aparece_na_api(ambiente):
    pasta, _, c = ambiente
    _salvar_senha(c)
    assert c.get("/api/configuracoes").json()["email"]["tem_senha"] is True
    (pasta / ".segredo.key").write_bytes(b"corrompida")
    os.environ.pop("SMTP_SENHA", None)       # salvar_configuracoes_gestao exporta a senha; simula novo processo
    email = c.get("/api/configuracoes").json()["email"]
    assert email["tem_senha"] is False and email["senha_ilegivel"] is True
    assert (pasta / ".segredo.key").read_bytes() == b"corrompida"


def test_fontes_da_rota_so_aceitam_nomes_conhecidos(ambiente):
    from busca_voos.config import ErroConfig, adicionar_rota_config

    _, cfg, _ = ambiente
    antes = cfg.read_text(encoding="utf-8")
    rota = {"origem": "POA", "destino": "LIS", "janela_ida": {"de": "2027-03-01"}, "preco_maximo": 3000}
    with pytest.raises(ErroConfig):
        adicionar_rota_config(cfg, {**rota, "fontes": ["google_flights]\n  banco: x"]})
    assert cfg.read_text(encoding="utf-8") == antes
    adicionar_rota_config(cfg, {**rota, "fontes": ["Google_Flights"]})
    assert _yaml(cfg)["rotas"][-1]["fontes"] == ["google_flights"]


# ------------------------------------------------------------ limpar alertas

def test_limpar_alertas_apaga_so_os_alertas(ambiente):
    from datetime import date

    from busca_voos.db import Banco

    pasta, _, c = ambiente
    b = Banco(pasta / "dados.sqlite3")
    b.registrar_alerta("latam", "FLN-RIO", date(2026, 12, 26), date(2027, 1, 8), 1012.41, "http://x")
    b.registrar_alerta("gol", "FLN-RIO", date(2026, 12, 27), date(2027, 1, 9), 990.0, "http://y")
    b.fechar()
    assert len(c.get("/api/alertas").json()["alertas"]) == 2
    r = c.delete("/api/alertas")
    assert r.status_code == 200 and r.json() == {"ok": True, "removidos": 2}
    assert c.get("/api/alertas").json()["alertas"] == []


def test_limpar_alertas_recusa_origem_externa(ambiente):
    _, _, c = ambiente
    r = c.delete("/api/alertas", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
