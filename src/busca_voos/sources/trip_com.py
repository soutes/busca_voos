"""Fonte: Trip.com via Playwright (paginas JS; resultados chegam via XHR)."""
from __future__ import annotations

import logging
from datetime import date

from bs4 import BeautifulSoup

from ..models import Oferta
from .base import FonteBase
from .extracao import cia_de_texto, escalas_de_texto, preco_de_texto
from .navegador import abrir_navegador

log = logging.getLogger(__name__)


def _url_busca(origem: str, destino: str, data_ida: date, data_volta: date | None) -> str:
    o, d = origem.lower(), destino.lower()
    if data_volta:
        return (
            "https://www.trip.com/flights/showfarefirst"
            f"?dcity={o}&acity={d}&ddate={data_ida}&rdate={data_volta}"
            "&triptype=rt&class=y&quantity=1&lowpricesource=searchform"
        )
    return (
        "https://www.trip.com/flights/showfarefirst"
        f"?dcity={o}&acity={d}&ddate={data_ida}"
        "&triptype=ow&class=y&quantity=1&lowpricesource=searchform"
    )


class TripComFonte(FonteBase):
    nome = "trip_com"
    requer_navegador = True

    def buscar(
        self, origem: str, destino: str, data_ida: date, data_volta: date | None = None
    ) -> list[Oferta]:
        url = _url_busca(origem, destino, data_ida, data_volta)
        with abrir_navegador(self.cfg) as contexto:
            pagina = contexto.new_page()
            try:
                pagina.goto(
                    url, wait_until="domcontentloaded", timeout=self.cfg.navegador.timeout_ms
                )
                try:
                    pagina.wait_for_selector(
                        'div[class*="flight-item"], div[class*="itinerary"], .flight-list',
                        timeout=20_000,
                    )
                except Exception:
                    pass  # pode demorar; seguimos e olhamos o HTML final
                pagina.wait_for_timeout(5000)
                pagina.mouse.wheel(0, 1200)
                pagina.wait_for_timeout(2000)
                html = pagina.content()
            except Exception as e:
                log.warning("trip_com: falha ao carregar pagina (%s)", e)
                return []
        return self._parsear(html, url, origem, destino, data_ida, data_volta)

    def _parsear(
        self,
        html: str,
        url: str,
        origem: str,
        destino: str,
        data_ida: date,
        data_volta: date | None,
    ) -> list[Oferta]:
        soup = BeautifulSoup(html, "html.parser")
        blocos = soup.select(
            'div[class*="flight-item"], div[class*="itinerary"], div[class*="pr-wrap"]'
        )
        ofertas: list[Oferta] = []
        vistos: set[tuple[float | None, str | None]] = set()
        for bloco in blocos:
            texto = bloco.get_text(" ", strip=True)
            if not texto or len(texto) > 900:  # container acima do nivel do voo
                continue
            preco, moeda = preco_de_texto(texto)
            if preco is None or preco <= 0:
                continue
            cia = cia_de_texto(texto)
            chave = (preco, cia)
            if chave in vistos:
                continue
            vistos.add(chave)
            ofertas.append(
                self._oferta(
                    origem,
                    destino,
                    data_ida,
                    data_volta,
                    preco,
                    url,
                    moeda=moeda,
                    cia=cia,
                    escalas=escalas_de_texto(texto),
                )
            )
        ofertas.sort(key=lambda o: o.preco)
        if not ofertas:
            log.info("trip_com: pagina carregada, mas nenhum preco extraido")
        return ofertas[:10]