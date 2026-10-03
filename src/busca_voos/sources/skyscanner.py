"""Fonte: Skyscanner Brasil via Playwright (site JS com anti-bot DataDome)."""
from __future__ import annotations

import logging
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Oferta
from .base import FonteBase, FonteBloqueada
from .extracao import cia_de_texto, escalas_de_texto, preco_de_texto
from .navegador import abrir_navegador

log = logging.getLogger(__name__)

_SELETORES_LINHA = (
    '[data-test="journey-row"], li[class*="ResultListItem"], div[class*="ResultListItem"]'
)
_BASE = "https://www.skyscanner.com.br"


def _url_busca(origem: str, destino: str, data_ida: date, data_volta: date | None) -> str:
    o, d = origem.lower(), destino.lower()
    url = f"{_BASE}/transporte/passagens-aereas/{o}/{d}/{data_ida:%y%m%d}/"
    params = "adultsv2=1&cabinclass=economy&adults=1&children=0&infants=0"
    if data_volta:
        params += f"&rtn={data_volta:%y%m%d}"
    return f"{url}?{params}"


class SkyscannerFonte(FonteBase):
    nome = "skyscanner"
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
                pagina.wait_for_timeout(3000)
                titulo = (pagina.title() or "").lower()
                inicio = (pagina.content() or "")[:4000].lower()
                if "datadome" in titulo or "captcha" in titulo or "datadome" in inicio:
                    raise FonteBloqueada(
                        "anti-bot (DataDome) exibiu desafio — tentar proxy ou canal chrome"
                    )
                pagina.wait_for_selector(_SELETORES_LINHA, timeout=20_000)
                pagina.mouse.wheel(0, 1500)
                pagina.wait_for_timeout(2500)
                html = pagina.content()
            except FonteBloqueada:
                raise
            except Exception as e:
                log.warning("skyscanner: sem linhas de resultado (%s)", e)
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
        linhas = soup.select(_SELETORES_LINHA)
        ofertas: list[Oferta] = []
        for linha in linhas[:10]:
            texto = linha.get_text(" ", strip=True)
            preco, moeda = preco_de_texto(texto)
            if preco is None or preco <= 0:
                continue
            link = url
            ancora = linha.select_one(
                'a[data-test="booking-link"], a[href*="/transporte/oferta/"]'
            )
            if ancora and ancora.get("href"):
                link = urljoin(_BASE, ancora["href"])
            cia = cia_de_texto(texto)
            if not cia:
                img = linha.select_one("img[alt]")
                if img and (img.get("alt") or "").strip():
                    cia = img["alt"].strip()[:40]
            ofertas.append(
                self._oferta(
                    origem,
                    destino,
                    data_ida,
                    data_volta,
                    preco,
                    link,
                    moeda=moeda,
                    cia=cia,
                    escalas=escalas_de_texto(texto),
                )
            )
        if not ofertas:
            log.info("skyscanner: pagina carregada, mas nenhum preco extraido")
        return ofertas