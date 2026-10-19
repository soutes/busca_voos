"""Fonte: LATAM (site oficial, calendario de tarifas do proprio site).

A busca de voos da LATAM (`offers/search`) trava para navegador automatizado, mas o
calendario de precos que alimenta a barra de datas da home responde normalmente:
`/bff/web-products-searchbox/v1/calendar` (BRL, sem login, `extended=true` traz
os precos). Devolve a MENOR tarifa de cada dia/direcao — serve para monitorar
preco, nao lista voos individuais.

Requisitos: Chrome instalado e janela visivel (o headless leva 403 do Akamai) e
os headers `x-latam-*` (sem eles a API responde 400), que enviamos por fetch
dentro da propria pagina para herdar os cookies anti-bot.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date

from ..models import Oferta
from .base import ErroFonte, FonteBase, FonteBloqueada
from .navegador import abrir_navegador

log = logging.getLogger(__name__)

_HOME = "https://www.latamairlines.com/br/pt"
_CALENDARIO = "/bff/web-products-searchbox/v1/calendar"

_JS_FETCH = """async ([url, headers]) => {
  const r = await fetch(url, {headers});
  return [r.status, await r.text()];
}"""


def _url_busca(origem: str, destino: str, data_ida: date, data_volta: date | None) -> str:
    url = (
        "https://www.latamairlines.com/br/pt/oferta-voos"
        f"?origin={origem}&destination={destino}"
        f"&outbound={data_ida.isoformat()}T12:00:00.000Z"
    )
    if data_volta:
        url += f"&inbound={data_volta.isoformat()}T12:00:00.000Z"
    trip = "RT" if data_volta else "OW"
    return (
        f"{url}&adt=1&chd=0&inf=0&trip={trip}&cabin=Economy"
        "&redemption=false&sort=RECOMMENDED"
    )


def _headers() -> dict[str, str]:
    return {
        "accept": "application/json, text/plain, */*",
        "x-latam-application-country": "br",
        "x-latam-application-oc": "br",
        "x-latam-application-lang": "pt",
        "x-latam-application-name": "xp-web-products-searchbox-lib",
        "x-latam-client-name": "xp-web-products-searchbox-lib",
        "x-latam-request-id": str(uuid.uuid4()),
        "x-latam-app-session-id": str(uuid.uuid4()),
        "x-latam-track-id": str(uuid.uuid4()),
    }


def preco_do_dia(dados: dict, dia: date, direcao: str) -> float | None:
    """Menor tarifa (BRL) de `dia` na `direcao` (OUTBOUND/INBOUND) do calendario."""
    mes = f"{dia:%Y-%m}"
    for bloco in dados.get("days") or []:
        for cal in bloco.get("calendar") or []:
            if cal.get("direction") != direcao or cal.get("month") != mes:
                continue
            for d in cal.get("detailsCalendar") or []:
                if d.get("date") != dia.isoformat() or d.get("enabled") is False:
                    continue
                valor = (d.get("fare") or {}).get("amount")
                if isinstance(valor, (int, float)) and valor > 0:
                    return float(valor)
    return None


class LatamFonte(FonteBase):
    nome = "latam"
    requer_navegador = True

    def buscar(
        self, origem: str, destino: str, data_ida: date, data_volta: date | None = None
    ) -> list[Oferta]:
        try:
            ctx_mgr = abrir_navegador(self.cfg, chrome_visivel=True)
            contexto = ctx_mgr.__enter__()
        except Exception as e:  # Chrome ausente / sem display
            raise ErroFonte(f"LATAM precisa do Google Chrome com janela visivel: {e}") from e
        try:
            pagina = contexto.new_page()
            pagina.goto(_HOME, wait_until="domcontentloaded", timeout=self.cfg.navegador.timeout_ms)
            pagina.wait_for_timeout(4000)
            corpo = (pagina.content() or "")[:3000].lower()
            if "access denied" in corpo:
                raise FonteBloqueada("Akamai negou acesso (Access Denied)")

            ida = self._calendario(pagina, origem, destino, data_ida, bool(data_volta))
            preco_ida = preco_do_dia(ida, data_ida, "OUTBOUND")
            if preco_ida is None:
                log.info("latam: sem tarifa para %s %s-%s", data_ida, origem, destino)
                return []
            total = preco_ida
            if data_volta:
                volta = ida
                if f"{data_volta:%Y-%m}" != f"{data_ida:%Y-%m}":
                    volta = self._calendario(pagina, origem, destino, data_volta, True)
                preco_volta = preco_do_dia(volta, data_volta, "INBOUND")
                if preco_volta is None:
                    log.info("latam: sem tarifa de volta em %s", data_volta)
                    return []
                total += preco_volta
        finally:
            ctx_mgr.__exit__(None, None, None)
        return [
            self._oferta(
                origem,
                destino,
                data_ida,
                data_volta,
                round(total, 2),
                _url_busca(origem, destino, data_ida, data_volta),
                moeda="BRL",
                cia="LATAM",
            )
        ]

    def _calendario(self, pagina, origem: str, destino: str, dia: date, ida_volta: bool) -> dict:
        url = (
            f"{_CALENDARIO}?origin={origem}&destination={destino}"
            f"&month={dia.month}&year={dia.year}"
            f"&isRoundTrip={'true' if ida_volta else 'false'}&extended=true"
        )
        status, texto = pagina.evaluate(_JS_FETCH, [url, _headers()])
        if status == 403 or "access denied" in texto[:500].lower():
            raise FonteBloqueada("Akamai negou acesso ao calendario")
        if status != 200:
            raise ErroFonte(f"calendario LATAM HTTP {status}: {texto[:120]}")
        try:
            return json.loads(texto)
        except ValueError as e:
            raise ErroFonte("calendario LATAM devolveu resposta nao-JSON") from e
