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

import ipaddress
import logging
import os
import threading
import time
import webbrowser
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .aeroportos import buscar_aeroportos
from .config import (
    ErroConfig,
    adicionar_rota_config,
    listar_rotas_dict,
    obter_configuracoes_gestao,
    obter_intervalo_cron,
    remover_rota_config,
    salvar_configuracoes_gestao,
    salvar_intervalo_cron,
)
from .emailer import ErroEmail, enviar
from . import protecao_web
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

_ciclo_lock = threading.Lock()
_ciclo_status: dict[str, Any] = {
    "rodando": False,
    "ultimo_ciclo": None,
    "erro": None,
    "mensagem": None,
    "iniciado_em": None,
    "consultas_feitas": 0,
    "ofertas_encontradas": 0,
    "fonte_atual": None,
    "diagnostico": {
        "detalhes_fontes": {},
        "fontes_ok": [],
        "fontes_erro": {},
        "consultas": 0,
        "alertas_count": 0,
    },
}
_status_ciclo = _ciclo_status

_HTML = Path(__file__).with_name("painel.html")
_STATIC = Path(__file__).with_name("static")

_AJUDA_INSTALL = (
    "O painel precisa de dependencias extras (fastapi/uvicorn). "
    'Instale com: pip install -e ".[web]"'
)


def _ler_html() -> str:
    try:
        return _HTML.read_text(encoding="utf-8")
    except OSError as e:  # arquivo faltando => instalacao incompleta
        raise ErroPainel(f"Nao consegui ler '{_HTML}': {e}")


def criar_app(
    banco: Path | str,
    limites: dict[str, float] | None = None,
    caminho_config: Path | str | None = None,
    hosts_permitidos: list[str] | str | None = None,
):
    """Monta o app FastAPI. Importado tarde para nao exigir fastapi no daemon.

    `hosts_permitidos`: nomes extras aceitos no cabecalho Host (alem de localhost e
    IPs). Tambem lido de BUSCA_VOOS_HOSTS. Ver `protecao_web`.

    `limites` mapeia rota (``FLN-RIO``) -> ``preco_maximo`` do config.yaml, para a
    tela marcar o que passaria do limite de alerta.
    """
    limites = limites or {}
    caminho_config = Path(caminho_config) if caminho_config else Path("config.yaml")
    try:
        from fastapi import Body, FastAPI, HTTPException, Query
        from fastapi.responses import HTMLResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as e:  # pragma: no cover - depende do ambiente
        raise ErroPainel(f"{_AJUDA_INSTALL} ({e})") from e

    paginas = {"html": _ler_html()}
    app = FastAPI(
        title="busca_voos — painel",
        description="Historico de ofertas e alertas (somente leitura).",
        # a documentacao interativa busca JS em CDN (quebra offline) e expoe o mapa da API:
        # so liga com BUSCA_VOOS_DOCS=1
        docs_url="/api/docs" if os.environ.get("BUSCA_VOOS_DOCS") == "1" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if os.environ.get("BUSCA_VOOS_DOCS") == "1" else None,
    )
    protecao_web.instalar(
        app, hosts_permitidos if hosts_permitidos else os.environ.get("BUSCA_VOOS_HOSTS")
    )

    class _Estaticos(StaticFiles):
        """Revalida a cada uso (ETag): depois de atualizar o app, o navegador nao serve CSS velho."""

        async def get_response(self, path, scope):
            resp = await super().get_response(path, scope)
            resp.headers["Cache-Control"] = "no-cache"
            return resp

    # CSS, fontes e logos locais: o painel funciona offline, sem CDN
    app.mount("/static", _Estaticos(directory=_STATIC), name="static")

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
        html = _ler_html()
        return HTMLResponse(
            html,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Content-Security-Policy": protecao_web.csp_da_pagina(html),
            },
        )

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

    # ---------------- gestao de rotas e ciclo ----------------

    @app.get("/api/rotas")
    def api_rotas() -> dict:
        try:
            return {"rotas": listar_rotas_dict(caminho_config)}
        except ErroConfig as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.post("/api/rotas")
    def api_adicionar_rota(body: dict = Body(...)) -> dict:
        try:
            if not isinstance(body, dict):
                raise HTTPException(status_code=400, detail="Corpo deve ser um objeto JSON")

            origem = str(body.get("origem", "") or "").strip().upper()
            destino = str(body.get("destino", "") or "").strip().upper()
            if not origem:
                raise ErroConfig("Campo 'origem' obrigatorio")
            if not destino:
                raise ErroConfig("Campo 'destino' obrigatorio")

            pm_val = body.get("preco_maximo")
            if pm_val is None:
                raise ErroConfig("Campo 'preco_maximo' obrigatorio")
            try:
                preco_maximo = float(pm_val)
            except (TypeError, ValueError):
                raise ErroConfig(f"Campo 'preco_maximo' invalido: {pm_val!r}")

            nova_rota: dict[str, Any] = {
                "origem": origem,
                "destino": destino,
                "preco_maximo": preco_maximo,
                "nome": str(body.get("nome", "") or "").strip(),
            }
            if body.get("janela_ida"):
                nova_rota["janela_ida"] = body["janela_ida"]
            elif body.get("ida_de"):
                nova_rota["janela_ida"] = {
                    "de": body["ida_de"],
                    "ate": body.get("ida_ate") or body["ida_de"],
                }
            else:
                raise ErroConfig("Informe 'ida_de' ou 'janela_ida'")

            if body.get("janela_volta"):
                nova_rota["janela_volta"] = body["janela_volta"]
            elif body.get("volta_de"):
                nova_rota["janela_volta"] = {
                    "de": body["volta_de"],
                    "ate": body.get("volta_ate") or body["volta_de"],
                }

            rotas = adicionar_rota_config(caminho_config, nova_rota)
            limites[f"{origem}-{destino}"] = preco_maximo
            return {"ok": True, "rotas": rotas}
        except (ErroConfig, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.delete("/api/rotas/{indice}")
    def api_remover_rota(indice: int) -> dict:
        try:
            rotas = remover_rota_config(caminho_config, indice)
            return {"ok": True, "rotas": rotas}
        except (IndexError, ErroConfig, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        intervalo_inicial = obter_intervalo_cron(caminho_config)
    except Exception:
        intervalo_inicial = 1.0

    _cron_lock = threading.Lock()
    _cron_state: dict[str, Any] = {
        "ativo": False,
        "intervalo_horas": intervalo_inicial,
        "proxima_execucao": None,
        "ultima_execucao": None,
    }

    def _executar_ciclo() -> bool:
        with _ciclo_lock:
            if _status_ciclo["rodando"]:
                return False
            _status_ciclo["rodando"] = True
            _status_ciclo["erro"] = None
            _status_ciclo["mensagem"] = "Ciclo em andamento"
            _status_ciclo["iniciado_em"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            _status_ciclo["consultas_feitas"] = 0
            _status_ciclo["ofertas_encontradas"] = 0
            _status_ciclo["fonte_atual"] = None

        def _rodar():
            from .config import carregar_config
            from .scheduler import ciclo
            try:
                cfg = carregar_config(caminho_config)

                def _progresso_cb(p: dict) -> None:
                    with _ciclo_lock:
                        _status_ciclo["ofertas_encontradas"] = p.get("ofertas", 0)
                        _status_ciclo["consultas_feitas"] = p.get("consultas", 0)
                        _status_ciclo["fonte_atual"] = p.get("fonte_atual")
                        _status_ciclo["mensagem"] = (
                            f"Consultando {p.get('fonte_atual')} "
                            f"({p.get('ofertas', 0)} ofertas encontradas até agora)..."
                        )

                resumo = ciclo(cfg, enviar_email=False, progresso_cb=_progresso_cb)
                with _ciclo_lock:
                    _status_ciclo["rodando"] = False
                    _status_ciclo["ultimo_ciclo"] = resumo.get("ciclo")
                    _status_ciclo["mensagem"] = f"Ciclo {resumo.get('ciclo')} finalizado com sucesso"
                    _status_ciclo["erro"] = None
                    _status_ciclo["diagnostico"] = resumo.get("diagnostico") or {
                        "detalhes_fontes": resumo.get("detalhes_fontes", {}),
                        "fontes_ok": resumo.get("fontes_ok", []),
                        "fontes_erro": resumo.get("fontes_erro", {}),
                        "consultas": resumo.get("consultas", 0),
                        "alertas_count": len(resumo.get("alertas", [])),
                    }
            except Exception as e:
                log.exception("Erro durante execucao do ciclo via API")
                with _ciclo_lock:
                    _status_ciclo["rodando"] = False
                    _status_ciclo["erro"] = str(e)
                    _status_ciclo["mensagem"] = f"Erro no ciclo: {e}"

        th = threading.Thread(target=_rodar, daemon=True)
        th.start()
        return True

    def _obter_dt_proxima() -> datetime | None:
        p = _cron_state.get("proxima_execucao")
        if p is None:
            return None
        if isinstance(p, datetime):
            return p if p.tzinfo else p.replace(tzinfo=timezone.utc)
        if isinstance(p, str):
            try:
                dt = datetime.fromisoformat(p)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                return None
        return None

    def _obter_status_cron() -> dict:
        with _cron_lock:
            now = datetime.now(timezone.utc)
            intervalo_h = float(_cron_state.get("intervalo_horas", 1.0))
            intervalo_m = max(1, int(round(intervalo_h * 60)))
            dt_proxima = _obter_dt_proxima()
            proxima_str: str | None = dt_proxima.isoformat() if dt_proxima else None
            segundos_restantes: int | None = None
            if _cron_state.get("ativo") and dt_proxima is not None:
                segundos_restantes = max(0, int(round((dt_proxima - now).total_seconds())))

            ultima = _cron_state.get("ultima_execucao")
            if isinstance(ultima, datetime):
                ultima_str = ultima.isoformat()
            elif isinstance(ultima, str):
                ultima_str = ultima
            else:
                ultima_str = None

            return {
                "ativo": bool(_cron_state.get("ativo", False)),
                "intervalo_horas": intervalo_h,
                "intervalo_minutos": intervalo_m,
                "proxima_execucao": proxima_str,
                "ultima_execucao": ultima_str,
                "segundos_restantes": segundos_restantes,
            }

    def _loop_cron():
        while True:
            time.sleep(2.0)
            try:
                with _cron_lock:
                    if not _cron_state.get("ativo"):
                        continue
                    with _ciclo_lock:
                        rodando = _status_ciclo.get("rodando", False)
                    if rodando:
                        continue

                    now = datetime.now(timezone.utc)
                    intervalo_horas = float(_cron_state.get("intervalo_horas", 1.0))
                    dt_proxima = _obter_dt_proxima()

                    if dt_proxima is None:
                        _cron_state["proxima_execucao"] = now + timedelta(hours=intervalo_horas)
                        continue

                    if now >= dt_proxima:
                        _executar_ciclo()
                        _cron_state["ultima_execucao"] = now.isoformat()
                        _cron_state["proxima_execucao"] = now + timedelta(hours=intervalo_horas)
            except Exception:
                log.exception("Erro no loop cron em segundo plano")

    th_cron = threading.Thread(target=_loop_cron, daemon=True)
    th_cron.start()

    @app.get("/api/cron")
    def api_obter_cron() -> dict:
        return _obter_status_cron()

    @app.post("/api/cron")
    def api_configurar_cron(body: dict = Body(...)) -> dict:
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Corpo deve ser um objeto JSON")

        if "intervalo_horas" in body:
            try:
                val = float(body["intervalo_horas"])
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="intervalo_horas deve ser um número")
            if val < 0.1 or val > 168:
                raise HTTPException(
                    status_code=400,
                    detail="intervalo_horas deve estar entre 0.1 e 168 horas",
                )
            intervalo_horas = val
        else:
            with _cron_lock:
                intervalo_horas = float(_cron_state.get("intervalo_horas", 1.0))

        if "ativo" in body:
            ativo_val = body["ativo"]
            if isinstance(ativo_val, str):
                ativo = ativo_val.strip().lower() in ("true", "1", "yes", "sim")
            else:
                ativo = bool(ativo_val)
        else:
            with _cron_lock:
                ativo = bool(_cron_state.get("ativo", False))

        try:
            salvar_intervalo_cron(caminho_config, intervalo_horas)
        except ErroConfig as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Erro ao salvar intervalo: {e}") from e

        with _cron_lock:
            _cron_state["ativo"] = ativo
            _cron_state["intervalo_horas"] = intervalo_horas
            now = datetime.now(timezone.utc)
            if ativo:
                _cron_state["proxima_execucao"] = now + timedelta(hours=intervalo_horas)
            else:
                _cron_state["proxima_execucao"] = None

        return _obter_status_cron()

    @app.post("/api/ciclo")
    def api_iniciar_ciclo() -> dict:
        if not _executar_ciclo():
            return {"ok": False, "mensagem": "Ciclo já em andamento"}
        return {"ok": True, "status": "iniciado"}

    @app.get("/api/ciclo/status")
    def api_ciclo_status() -> dict:
        with _ciclo_lock:
            return dict(_status_ciclo)

    @app.get("/api/aeroportos")
    def api_aeroportos(
        q: str = Query(default="", max_length=50),
        limite: int = Query(default=15, ge=1, le=50),
    ) -> dict:
        return {"aeroportos": buscar_aeroportos(q, limite=limite)}

    # ---------------- gestao e configuracoes ----------------

    @app.get("/api/configuracoes")
    def api_obter_configuracoes() -> dict:
        cfg_dict = obter_configuracoes_gestao(caminho_config, banco)
        status_cron = _obter_status_cron()
        cfg_dict["cron"]["ativo"] = status_cron["ativo"]
        cfg_dict["cron"]["segundos_restantes"] = status_cron["segundos_restantes"]
        cfg_dict["cron"]["proxima_execucao"] = status_cron["proxima_execucao"]
        return cfg_dict

    @app.post("/api/configuracoes")
    def api_salvar_configuracoes(body: dict = Body(...)) -> dict:
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Corpo deve ser um objeto JSON")

        try:
            salvar_configuracoes_gestao(caminho_config, banco, body)
        except ErroConfig as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Erro ao salvar configurações: {e}") from e

        if "cron" in body and isinstance(body["cron"], dict):
            cron_dados = body["cron"]
            with _cron_lock:
                if "ativo" in cron_dados:
                    ativo_val = cron_dados["ativo"]
                    if isinstance(ativo_val, str):
                        ativo_bool = ativo_val.strip().lower() in ("true", "1", "yes", "sim")
                    else:
                        ativo_bool = bool(ativo_val)
                    _cron_state["ativo"] = ativo_bool
                    now = datetime.now(timezone.utc)
                    if ativo_bool:
                        _cron_state["proxima_execucao"] = now + timedelta(hours=float(_cron_state["intervalo_horas"]))
                    else:
                        _cron_state["proxima_execucao"] = None

                if "intervalo_horas" in cron_dados:
                    try:
                        interv = float(cron_dados["intervalo_horas"])
                        if 0.1 <= interv <= 168:
                            _cron_state["intervalo_horas"] = interv
                            if _cron_state.get("ativo"):
                                now = datetime.now(timezone.utc)
                                _cron_state["proxima_execucao"] = now + timedelta(hours=interv)
                    except (TypeError, ValueError):
                        pass

        cfg_dict = obter_configuracoes_gestao(caminho_config, banco)
        status_cron = _obter_status_cron()
        cfg_dict["cron"]["ativo"] = status_cron["ativo"]
        cfg_dict["cron"]["segundos_restantes"] = status_cron["segundos_restantes"]
        cfg_dict["cron"]["proxima_execucao"] = status_cron["proxima_execucao"]
        return {"ok": True, "configuracoes": cfg_dict}

    @app.post("/api/email/testar")
    def api_testar_email(body: dict = Body(default={})) -> dict:
        """Envia um e-mail de teste.

        Regra de seguranca: a senha SALVA so e usada com o servidor/porta/TLS/remetente
        SALVOS. Para testar outro servidor (ex.: antes de salvar) e preciso digitar a
        senha, assim a senha guardada nunca e entregue a um host escolhido pela requisicao.
        """
        import copy
        from .config import (
            Config,
            carregar_config,
            validar_email,
            validar_host_smtp,
            validar_lista_emails,
            validar_porta_smtp,
        )

        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Corpo deve ser um objeto JSON")

        try:
            cfg_base = carregar_config(caminho_config)
        except Exception:
            cfg_base = Config(caminho=Path(caminho_config), banco=Path(banco))

        cfg_teste = copy.deepcopy(cfg_base)
        try:
            if body.get("host"):
                cfg_teste.email.host = validar_host_smtp(body["host"])
            if body.get("porta"):
                cfg_teste.email.porta = validar_porta_smtp(body["porta"])
            if "tls" in body:
                cfg_teste.email.tls = bool(body["tls"])
            if body.get("de"):
                cfg_teste.email.de = validar_email(body["de"], "E-mail remetente")
            if body.get("para"):
                cfg_teste.email.para = validar_lista_emails(body["para"], "Destinatarios")
        except ErroConfig as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        muda_servidor = (
            cfg_teste.email.host != cfg_base.email.host
            or cfg_teste.email.porta != cfg_base.email.porta
            or cfg_teste.email.tls != cfg_base.email.tls
            or cfg_teste.email.de != cfg_base.email.de
        )

        senha_digitada = ""
        if "senha" in body:
            s_val = str(body["senha"] or "").strip()
            if s_val and not s_val.startswith("•"):
                senha_digitada = s_val

        if senha_digitada:
            cfg_teste.email.senha = senha_digitada
        elif "senha" in body and not str(body["senha"] or "").strip():
            cfg_teste.email.senha = ""   # campo enviado vazio: cai em "Senha SMTP ausente"
        elif muda_servidor:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Para testar outro servidor ou remetente, digite a senha no campo. "
                    "A senha salva so e usada com o servidor salvo."
                ),
            )
        elif not cfg_teste.email.senha:
            try:
                from .db import Banco
                from .seguranca import descriptografar_texto

                pb = Path(banco)
                if not pb.is_absolute() and Path(caminho_config).parent:
                    pb_cand = Path(caminho_config).parent / pb
                    if pb_cand.exists():
                        pb = pb_cand
                if pb.exists():
                    b_obj = Banco(pb)
                    tok = b_obj.obter_configuracao("smtp_senha", "")
                    b_obj.fechar()
                    if tok:
                        cfg_teste.email.senha = descriptografar_texto(
                            tok, pasta=Path(caminho_config).parent
                        )
            except Exception:
                pass

        if not cfg_teste.email.de:
            raise HTTPException(status_code=400, detail="Campo 'de' (remetente) obrigatório.")
        if not cfg_teste.email.para:
            raise HTTPException(status_code=400, detail="Campo 'para' (destinatário) obrigatório.")
        if not cfg_teste.email.senha:
            raise HTTPException(
                status_code=400,
                detail="Senha SMTP ausente. Preencha a senha ou configure SMTP_SENHA.",
            )

        assunto = "busca_voos — Teste de Configuração de E-mail"
        html = (
            "<!doctype html><html lang=\"pt-BR\"><body style=\"font-family:Arial,sans-serif;color:#222\">"
            "<h3>busca_voos — Teste de Envio</h3>"
            "<p>Se você recebeu esta mensagem, as configurações de SMTP estão funcionando perfeitamente!</p>"
            "<p style=\"color:#888;font-size:12px\">Enviado automaticamente pelo painel do busca_voos.</p>"
            "</body></html>"
        )

        try:
            enviar(cfg_teste, assunto, html)
            return {"ok": True, "mensagem": "E-mail de teste enviado com sucesso!"}
        except ErroEmail as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Falha ao enviar e-mail de teste: {e}") from e

    @app.get("/api/versao")
    def api_versao() -> dict:
        return {"versao": "1.2.0", "nome": "busca_voos", "repositorio": "local"}

    app.state.cron_state = _cron_state
    app.state.ciclo_status = _status_ciclo
    app.state.executar_ciclo = _executar_ciclo
    app.state.obter_status_cron = _obter_status_cron

    return app


def _e_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def servir(
    banco: Path | str,
    host: str = "127.0.0.1",
    porta: int = 8787,
    abrir_navegador: bool = False,
    debug: bool = False,
    limites: dict[str, float] | None = None,
    caminho_config: Path | str | None = None,
    hosts_permitidos: list[str] | None = None,
) -> int:
    """Sobe o servidor (bloqueante). Retorna o codigo de saida do CLI."""
    try:
        import uvicorn
    except ImportError as e:
        raise ErroPainel(f"{_AJUDA_INSTALL} ({e})") from e

    app = criar_app(
        banco, limites=limites, caminho_config=caminho_config, hosts_permitidos=hosts_permitidos
    )
    if not _e_loopback(host):
        log.warning(
            "O painel esta exposto em %s e NAO tem login: qualquer pessoa que alcance "
            "a porta %s pode ver e alterar rotas, e-mail e agenda. Restrinja pelo firewall "
            "da VPS ou acesse por tunel SSH (ssh -L %s:127.0.0.1:%s usuario@servidor).",
            host, porta, porta, porta,
        )
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
