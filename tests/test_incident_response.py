import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Adiciona incident-response no path para importar server
ir_path = Path(__file__).resolve().parent.parent / "incident-response"
if str(ir_path) not in sys.path:
    sys.path.insert(0, str(ir_path))

from server import app


def test_responder_healthz():
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_responder_recebe_alerta_sintetico_de_teste():
    client = TestClient(app)
    payload = {
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "ResponderTest",
                    "test": "true",
                    "fonte": "google_flights",
                },
                "annotations": {
                    "summary": "Test notification; no incident to fix"
                },
            }
        ]
    }
    resp = client.post("/alerts", json=payload)
    assert resp.status_code == 202
    dados = resp.json()
    assert dados["status"] == "accepted"
    assert len(dados["incidents"]) == 1
