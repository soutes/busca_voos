"""Fonte: Skiplagged.

Estrategia em duas etapas:
1) API interna `packed.js` (HTTP puro, sem navegador);
2) se a API nao responder como esperado, abre a pagina de busca no
   Playwright e extrai os precos do DOM (markup `.trip-cost`).
"""
from __future__ import annotations

import logging
import re
from datetime import date

import httpx
from bs4 import BeautifulSoup

from ..config import Config
from ..models import Oferta
from .base import ErroFonte, FonteBase
from .extracao import cia_de_texto, preco_de_texto
from .navegador import abrir_navegador

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _url_busca(origem: str, destino: str, data_ida: date, data_volta: date | None) -> str:
    url = f"https://skiplagged.com/flights/{origem}/{destino}/{data_ida.isoformat()}"
    if data_volta:
        url += f"/{data_volta.isoformat()}"
    return url


class SkiplaggedFonte(FonteBase):
    nome = "skiplagged"

    def buscar(
        self, origem: str, destino: str, data_ida: date, data_volta: date | None = None
    ) -> list[Oferta]:
        ofertas: list[Oferta] | None = None
        try:
            ofertas = self._via_api(origem, destino, data_ida, data_volta)
        except Exception as e:  # API mudou? cai para o navegador
            log.debug("skiplagged API falhou (%s) — tentando navegador", e)
        if not ofertas:
            ofertas = self._via_navegador(origem, destino, data_ida, data_volta)
        return ofertas

    # ------------------------- API interna -------------------------

    def _via_api(
        self, origem: str, destino: str, data_ida: date, data_volta: date | None
    ) -> list[Oferta] | None:
        params: dict[str, str | int] = {
            "from": origem,
            "to": destino,
            "depart_date": data_ida.isoformat(),
            "format": "json",
            "currency": self.cfg.moeda,
            "adults": 1,
        }
        if data_volta:
            params["return_date"] = data_volta.isoformat()
        headers = {
            "User-Agent": UA,
            "Referer": "https://skiplagged.com/",
            "Accept": "application/json, text/plain, */*",
        }
        with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as cliente:
            resp = cliente.get("https://skiplagged.com/api/packed.js", params=params)
        if resp.status_code != 200:
            log.debug("skiplagged API: HTTP %s", resp.status_code)
            return None
        try:
            dados = resp.json()
        except ValueError:
            log.debug("skiplagged API: resposta nao-JSON")
            return None
        resultado = dados.get("result") or {}
        jornadas = resultado.get("journeys") or []
        trips = dados.get("trips") or {}
        if not jornadas:
            return None
        ofertas = []
        for j in jornadas[:10]:
            preco = j.get("price")
            if preco is None:
                continue
            voos = j.get("flights") or []
            cia = None
            escalas = None
            if voos:
                detalhe = trips.get(voos[0])
                if isinstance(detalhe, dict):
                    cia = (
                        detalhe.get("airline_name")
                        or detalhe.get("airline_code")
                        or None
                    )
                escalas = f"{max(0, len(voos) - 1)} trecho(s)"
            ofertas.append(
                self._oferta(
                    origem,
                    destino,
                    data_ida,
                    data_volta,
                    preco,
                    _url_busca(origem, destino, data_ida, data_volta),
                    cia=cia,
                    escalas=escalas,
                )
            )
        return ofertas or None

    # --------------------- navegador (fallback) ---------------------

    def _via_navegador(
        self, origem: str, destino: str, data_ida: date, data_volta: date | None
    ) -> list[Oferta]:
        url = _url_busca(origem, destino, data_ida, data_volta)
        with abrir_navegador(self.cfg) as contexto:
            pagina = contexto.new_page()
            try:
                pagina.goto(
                    url, wait_until="domcontentloaded", timeout=self.cfg.navegador.timeout_ms
                )
                pagina.wait_for_selector(
                    ".trip-cost", timeout=self.cfg.navegador.timeout_ms
                )
                pagina.mouse.wheel(0, 1500)  # resultados preguicosos abaixo da dobra
                pagina.wait_for_timeout(2500)
                html = pagina.content()
            except Exception as e:
                log.warning("skiplagged: pagina sem precos (%s)", e)
                return []
        soup = BeautifulSoup(html, "html.parser")
        ofertas = []
        for bloco in soup.select("div.trip-cost")[:10]:
            texto = bloco.get_text(" ", strip=True)
            preco, moeda = preco_de_texto(texto)
            if preco is None:
                continue
            ofertas.append(
                self._oferta(
                    origem, destino, data_ida, data_volta, preco, url, moeda=moeda
                )
            )
        if not ofertas:
            log.info("skiplagged: navegador abriu a pagina mas nao achou precos")
        return ofertas