from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from busca_voos.db import Banco
from busca_voos.web import criar_app


@pytest.fixture
def banco_teste(tmp_path: Path):
    arquivo_db = tmp_path / "teste.sqlite3"
    Banco(arquivo_db)
    return arquivo_db


def test_healthz_endpoint(banco_teste: Path):
    app = criar_app(banco_teste)
    # host-local: o painel so responde a 127.0.0.1/hosts permitidos (protecao_web)
    client = TestClient(app, base_url="http://127.0.0.1:8787")

    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_api_filtros_endpoint(banco_teste: Path):
    app = criar_app(banco_teste, limites={"GRU-FLN": 500.0})
    client = TestClient(app, base_url="http://127.0.0.1:8787")

    response = client.get("/api/filtros")
    assert response.status_code == 200
    dados = response.json()
    assert "limites" in dados
    assert dados["limites"]["GRU-FLN"] == 500.0
