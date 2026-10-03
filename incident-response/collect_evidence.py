"""Coleta delimitada de evidencias operacionais (Loki, Tempo, Git e Codigo-fonte)."""
from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100")
TEMPO_URL = os.getenv("TEMPO_URL", "http://localhost:3200")


def _get_json(url: str, timeout: int = 5) -> dict[str, Any]:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"erro": str(e), "url": url}


def coletar_logs_loki(fonte: str = "google_flights", minutos: int = 5) -> dict[str, Any]:
    agora = datetime.now(timezone.utc)
    inicio = agora - timedelta(minutes=minutos)
    query = f'{{service_name="busca-voos"}} |= "{fonte}"'
    params = urllib.parse.urlencode({
        "query": query,
        "start": str(int(inicio.timestamp() * 1_000_000_000)),
        "end": str(int(agora.timestamp() * 1_000_000_000)),
        "limit": 100,
    })
    return _get_json(f"{LOKI_URL}/loki/api/v1/query_range?{params}")


def coletar_traces_tempo(minutos: int = 5) -> dict[str, Any]:
    agora = datetime.now(timezone.utc)
    inicio = agora - timedelta(minutes=minutos)
    params = urllib.parse.urlencode({
        "tags": "service.name=busca-voos",
        "start": str(int(inicio.timestamp())),
        "end": str(int(agora.timestamp())),
        "limit": 20,
    })
    return _get_json(f"{TEMPO_URL}/api/search?{params}")


def coletar_codigo_fonte() -> str:
    alvo = REPO_ROOT / "src" / "busca_voos" / "sources" / "google_flights.py"
    if alvo.exists():
        return alvo.read_text(encoding="utf-8")
    return ""


def coletar_status_git() -> str:
    try:
        res = subprocess.run(
            ["git", "status", "--short"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return res.stdout
    except Exception as e:
        return f"git error: {e}"


def gerar_pacote_evidencias(alert_data: dict[str, Any]) -> dict[str, Any]:
    """Gera um pacote estruturado e seguro contendo tudo que o agente precisa para diagnosticar."""
    labels = alert_data.get("labels", {})
    fonte = labels.get("fonte", "google_flights")

    return {
        "timestamp_coleta": datetime.now(timezone.utc).isoformat(),
        "alerta": alert_data,
        "fonte_afetada": fonte,
        "logs_loki": coletar_logs_loki(fonte),
        "traces_tempo": coletar_traces_tempo(),
        "codigo_fonte_parser": coletar_codigo_fonte(),
        "git_status": coletar_status_git(),
    }
