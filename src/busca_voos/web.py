"""Painel web local para o historico do busca_voos.

Sobe um servidor **somente leitura** em cima do mesmo SQLite que o daemon
alimenta: resumo, ofertas mais recentes, alertas enviados e grafico de
historico de preco. Nada aqui dispara buscas nem envia e-mail.

Uso:
    pip install -e ".[web]"
    busca-voos painel --porta 8787

Dependencias de web sao opcionais: o daemon (uma/run/testar) continua
funcionando sem fastapi instalado.
"""
from __future__ import annotations

import logging
import threading
import webbrowser
from contextlib import closing
from datetime import date
from pathlib import Path

from .painel import (
    ORDENS,
    ErroPainel,
    conectar,
    contar_ofertas,
    filtros,
    historico,
    listar_alertas,
    listar_ofertas,
    resumo,
)

log = logging.getLogger("busca_voos")

_HTML = Path(__file__).with_name("painel.html")

_AJUDA_INSTALL = (
    "O painel precisa de dependencias extras (fastapi/uvicorn). "
    'Instale com: pip install -e ".[web]"'
)


def _ler_html() -> str:
    try:
        return _HTML.read_text(encoding="utf-8")
    except OSError as e:  # arquivo faltando => instalacao incompleta
        raise ErroPainel(f"Nao consegui ler '{_HTML}': {e}")


def criar_app(banco: Path | str, limites: dict[str, float] | None = None):
    """Monta o app FastAPI. Importado tarde para nao exigir fastapi no daemon.

    `limites` mapeia rota (``FLN-RIO``) -> ``preco_maximo`` do config.yaml, para a
    tela marcar o que passaria do limite de alerta.
    """
    limites = limites or {}
    try:
        from fastapi import FastAPI, HTTPException, Query
        from fastapi.responses import HTMLResponse
    except ImportError as e:  # pragma: no cover - depende do ambiente
        raise ErroPainel(f"{_AJUDA_INSTALL} ({e})") from e

    paginas = {"html": _ler_html()}
    app = FastAPI(
        title="busca_voos — painel",
        description="Historico de ofertas e alertas (somente leitura).",
        docs_url="/api/docs",
        redoc_url=None,
    )

    # Instrumentacao OpenTelemetry
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from .telemetry import configurar_telemetria
        configurar_telemetria("busca-voos-web")
        FastAPIInstrumentor.instrument_app(app)
    except Exception as e:
        log.debug("OpenTelemetry nao instrumentado no FastAPI: %s", e)

    def _abrir():
        """Uma conexao por requisicao: o daemon escreve em paralelo."""
        try:
            return conectar(banco)
        except ErroPainel as e:
            # 503: o servidor esta de pe, o banco e que ainda nao esta pronto
            raise HTTPException(status_code=503, detail=str(e)) from e

    def _ok(ordem: str) -> str:
        if ordem not in ORDENS:
            raise HTTPException(
                status_code=400,
                detail=f"ordem invalida: '{ordem}'. Use uma de: {', '.join(ORDENS)}",
            )
        return ordem

    @app.get("/", response_class=HTMLResponse)
    def pagina() -> HTMLResponse:
        return HTMLResponse(paginas["html"])

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/api/filtros")
    def api_filtros() -> dict:
        with closing(_abrir()) as con:
            return {**filtros(con), "limites": limites}

    @app.get("/api/resumo")
    def api_resumo() -> dict:
        with closing(_abrir()) as con:
            return resumo(con)

    @app.get("/api/ofertas")
    def api_ofertas(
        rota: str | None = None,
        fonte: str | None = None,
        de: date | None = None,
        ate: date | None = None,
        preco_max: float | None = Query(default=None, ge=0),
        ordem: str = "preco",
        limite: int = Query(default=200, ge=1, le=1000),
    ) -> dict:
        ordem = _ok(ordem)
        if de and ate and ate < de:
            raise HTTPException(status_code=400, detail="'ate' e anterior a 'de'")
        args = {
            "rota": rota,
            "fonte": fonte,
            "de": de.isoformat() if de else None,
            "ate": ate.isoformat() if ate else None,
            "preco_max": preco_max,
        }
        with closing(_abrir()) as con:
            return {
                "ofertas": listar_ofertas(con, ordem=ordem, limite=limite, **args),
                "total": contar_ofertas(con, **args),
                "ordem": ordem,
                "limite": limite,
            }

    @app.get("/api/alertas")
    def api_alertas(
        rota: str | None = None,
        fonte: str | None = None,
        limite: int = Query(default=100, ge=1, le=1000),
    ) -> dict:
        with closing(_abrir()) as con:
            return {"alertas": listar_alertas(con, rota=rota, fonte=fonte, limite=limite)}

    @app.get("/api/historico")
    def api_historico(
        rota: str | None = None,
        fonte: str | None = None,
        dias: int = Query(default=90, ge=1, le=3650),
    ) -> dict:
        with closing(_abrir()) as con:
            return {"historico": historico(con, rota=rota, fonte=fonte, dias=dias)}

    return app


def servir(
    banco: Path | str,
    host: str = "127.0.0.1",
    porta: int = 8787,
    abrir_navegador: bool = False,
    debug: bool = False,
    limites: dict[str, float] | None = None,
) -> int:
    """Sobe o servidor (bloqueante). Retorna o codigo de saida do CLI."""
    try:
        import uvicorn
    except ImportError as e:
        raise ErroPainel(f"{_AJUDA_INSTALL} ({e})") from e

    app = criar_app(banco, limites=limites)
    url = f"http://{host}:{porta}"
    log.info("Painel em %s (somente leitura) — banco: %s", url, Path(banco))
    log.info("Ctrl+C para sair.")
    if abrir_navegador:
        threading.Timer(1.0, webbrowser.open, args=[url]).start()
    try:
        uvicorn.run(app, host=host, port=porta, log_level="debug" if debug else "warning")
    except KeyboardInterrupt:
        log.info("Painel encerrado.")
    except OSError as e:
        raise ErroPainel(
            f"Nao consegui abrir {url}: {e}. A porta {porta} pode estar em uso — "
            "tente --porta 8788."
        ) from e
    return 0
