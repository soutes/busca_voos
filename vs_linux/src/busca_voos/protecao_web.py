"""Protecoes do painel web, sem login: Host, Origin e cabecalhos de seguranca.

O painel nao tem autenticacao (uso local ou numa VPS acessada por IP). Mesmo
assim, uma pagina maliciosa aberta no seu navegador pode tentar falar com ele:

* DNS rebinding: o site do atacante passa a apontar para 127.0.0.1 e o
  navegador trata o painel como "do mesmo site". Barramos exigindo que o
  cabecalho ``Host`` seja ``localhost`` ou um IP literal (um IP nunca e
  rebindavel, porque o atacante precisa de um *nome*). Outros nomes entram so
  se voce listar em ``--host-permitido`` / ``BUSCA_VOOS_HOSTS``.
* CSRF: um ``<form>`` em outro site consegue enviar POST sem preflight. Em
  metodos que alteram estado, recusamos ``Origin`` diferente de ``Host`` e
  ``Sec-Fetch-Site: cross-site``.
* Clickjacking / conteudo inesperado: CSP restritiva, X-Frame-Options etc.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import re
from urllib.parse import urlsplit

from fastapi.responses import JSONResponse

METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS"})
NOMES_LOCAIS = frozenset({"localhost"})

# CSP das respostas que nao sao a pagina (JSON, CSS, fontes): nada executa.
CSP_API = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"

CABECALHOS_FIXOS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}

_RE_SCRIPT_INLINE = re.compile(r"<script(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>", re.S | re.I)


def _nome_do_host(valor: str) -> str:
    """'127.0.0.1:8787' -> '127.0.0.1'; '[::1]:80' -> '::1'; invalido -> ''."""
    try:
        return (urlsplit("//" + valor.strip()).hostname or "").lower()
    except ValueError:
        return ""


def normalizar_extras(valores) -> frozenset[str]:
    """Aceita lista ou 'a.com,b.com'; guarda so os nomes, em minusculas."""
    if not valores:
        return frozenset()
    if isinstance(valores, str):
        valores = valores.split(",")
    nomes = (_nome_do_host(str(v)) for v in valores if str(v).strip())
    return frozenset(n for n in nomes if n)


def host_permitido(valor: str, extras: frozenset[str] = frozenset()) -> bool:
    nome = _nome_do_host(valor or "")
    if not nome:
        return False
    if nome in NOMES_LOCAIS or nome in extras:
        return True
    try:
        ipaddress.ip_address(nome)
        return True
    except ValueError:
        return False


def csp_da_pagina(html: str) -> str:
    """CSP da pagina principal: scripts so do proprio site + os blocos inline conhecidos (por hash).

    O navegador normaliza CRLF para LF antes de calcular o hash do script, entao
    fazemos o mesmo aqui.
    """
    hashes = []
    for m in _RE_SCRIPT_INLINE.finditer(html):
        texto = m.group(1).replace("\r\n", "\n").replace("\r", "\n")
        digest = hashlib.sha256(texto.encode("utf-8")).digest()
        hashes.append("'sha256-" + base64.b64encode(digest).decode("ascii") + "'")
    return "; ".join([
        "default-src 'none'",
        "script-src 'self' " + " ".join(hashes),
        "style-src 'self' 'unsafe-inline'",   # a marcacao usa style="" em varios pontos
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
    ])


def _negar(motivo: str) -> JSONResponse:
    resp = JSONResponse({"detail": motivo}, status_code=403)
    for k, v in CABECALHOS_FIXOS.items():
        resp.headers[k] = v
    resp.headers["Content-Security-Policy"] = CSP_API
    return resp


def instalar(app, hosts_permitidos=None) -> frozenset[str]:
    """Liga a verificacao de Host/Origin e os cabecalhos de seguranca no app FastAPI."""
    extras = normalizar_extras(hosts_permitidos)

    @app.middleware("http")
    async def protecao(request, call_next):
        host = request.headers.get("host", "")
        if not host_permitido(host, extras):
            return _negar(
                "Host nao permitido. Acesse por localhost ou pelo IP do servidor "
                "(ou liste o nome em --host-permitido)."
            )
        if request.method not in METODOS_SEGUROS:
            origem = request.headers.get("origin")
            if origem is not None:
                if origem.strip().lower() == "null" or urlsplit(origem).netloc.lower() != host.strip().lower():
                    return _negar("Origem da requisicao nao permitida.")
            if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
                return _negar("Requisicao de outro site bloqueada.")
        resp = await call_next(request)
        for k, v in CABECALHOS_FIXOS.items():
            resp.headers.setdefault(k, v)
        resp.headers.setdefault("Content-Security-Policy", CSP_API)
        return resp

    return extras
