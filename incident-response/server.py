"""Servidor Webhook de Incident Response para o Busca Voos (Porta 8001)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from collect_evidence import gerar_pacote_evidencias
from responder import executar_agente_oncall

app = FastAPI(title="Busca Voos — Incident Responder")
INCIDENTS_DIR = Path(__file__).resolve().parent / "incidents"
INCIDENTS_DIR.mkdir(parents=True, exist_ok=True)


def processar_alerta_em_background(incident_id: str, alert: dict[str, Any]) -> None:
    incident_dir = INCIDENTS_DIR / incident_id
    incident_dir.mkdir(parents=True, exist_ok=True)

    # 1. Salva o alerta original
    (incident_dir / "alert.json").write_text(
        json.dumps(alert, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 2. Coleta evidencias delimitadas (Loki, Tempo, Codigo)
    evidencias = gerar_pacote_evidencias(alert)

    # 3. Executa o agente on-call em modo headless
    executar_agente_oncall(incident_dir, evidencias)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/alerts", status_code=202)
def receber_alertas(payload: dict[str, Any], background_tasks: BackgroundTasks) -> JSONResponse:
    alerts = payload.get("alerts")
    if not alerts and isinstance(payload, dict):
        alerts = [payload]

    if not alerts:
        raise HTTPException(status_code=400, detail="Payload deve conter uma lista de alertas")

    incident_ids = []
    for alert in alerts:
        incident_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8]
        incident_ids.append(incident_id)
        background_tasks.add_task(processar_alerta_em_background, incident_id, alert)

    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "incidents": incident_ids,
            "message": "Alerta recebido com sucesso. Investigacao automatizada iniciada.",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
