"""Fonte: Google Flights via HTTP com token 'tfs' (protobuf) — sem navegador.

O parametro `tfs` da URL do Google Flights e um protobuf em base64url que
descreve a busca (trajos, classe, passageiros). Com ele, o Google devolve a
pagina de resultados ja renderizada no servidor, que parseamos sem browser.
Se o markup mudar, o parser cai em lista vazia e o log avisa (as demais
fontes continuam funcionando).
"""
from __future__ import annotations

import base64
import logging
import re
from datetime import date

import httpx
from bs4 import BeautifulSoup

from ..config import Config
from ..models import Oferta
from ..telemetry import (
    medir_tempo,
    obter_tracer,
    registrar_busca,
    registrar_erro,
    registrar_ofertas,
)
from .base import ErroFonte, FonteBase, FonteBloqueada
from .extracao import (
    cia_de_texto,
    escalas_de_texto,
    normalizar_preco,
    preco_de_texto,
)

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# ------------------- codificacao do token tfs (protobuf minimo) -------------------
# Schema (validado contra o protobuf real do Google Flights / fast-flights 3.x):
#   message Airport  { string airport = 2; }
#   message FlightData { string date = 2; Airport from_airport = 13; Airport to_airport = 14; }
#   message Info {
#     repeated FlightData data = 3;
#     repeated Passenger passengers = 8;   // enum: ADULT=1, CHILD=2, ...
#     Seat seat = 9;                        // enum: ECONOMY=1 ...
#     Trip trip = 19;                       // enum: ROUND_TRIP=1, ONE_WAY=2
#   }
# O tfs e o base64 (padrao, com padding) de Info serializado.

def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _campo(num: int, payload: bytes) -> bytes:
    """Campo length-delimited (wire type 2)."""
    return _varint((num << 3) | 2) + _varint(len(payload)) + payload


def _campo_varint(num: int, valor: int) -> bytes:
    return _varint((num << 3) | 0) + _varint(valor)


def _aeroporto(codigo: str) -> bytes:
    # mensagem aeroporto: campo 2 = codigo IATA (string)
    return _campo(2, codigo.encode())


def _trajo(data: date, origem: str, destino: str) -> bytes:
    # trajo: 2 = data "AAAA-MM-DD"; 13 = aeroporto origem; 14 = aeroporto destino
    return (
        _campo(2, data.isoformat().encode())
        + _campo(13, _aeroporto(origem))
        + _campo(14, _aeroporto(destino))
    )


def _tfs(trajos: list[tuple[date, str, str]]) -> str:
    corpo = b"".join(_campo(3, _trajo(d, o, dt)) for d, o, dt in trajos)
    corpo += _campo_varint(8, 1)                       # passageiro ADULT
    corpo += _campo_varint(9, 1)                       # classe ECONOMY
    corpo += _campo_varint(19, 2 if len(trajos) == 1 else 1)  # ONE_WAY / ROUND_TRIP
    return base64.b64encode(corpo).decode()


# ----------------------------- fonte -----------------------------

class GoogleFlightsFonte(FonteBase):
    nome = "google_flights"

    def buscar(
        self, origem: str, destino: str, data_ida: date, data_volta: date | None = None
    ) -> list[Oferta]:
        tracer = obter_tracer()
        span_cm = (
            tracer.start_as_current_span(
                "google_flights.buscar",
                attributes={"origem": origem, "destino": destino, "fonte": "google_flights"},
            )
            if tracer
            else None
        )

        with medir_tempo("google_flights"):
            try:
                trajos = [(data_ida, origem, destino)]
                if data_volta:
                    trajos.append((data_volta, destino, origem))
                tfs = _tfs(trajos)
                url = (
                    "https://www.google.com/travel/flights/search?tfs=" + tfs
                    + f"&hl={self.cfg.idioma}&curr={self.cfg.moeda}"
                )
                headers = {
                    "User-Agent": UA,
                    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                    "Accept": "text/html,application/xhtml+xml",
                }
                cookies = {"CONSENT": "YES+cb.20210328-17-p0.en+FX+419"}
                try:
                    with httpx.Client(
                        headers=headers, cookies=cookies, timeout=30, follow_redirects=True
                    ) as cliente:
                        resp = cliente.get(url)
                except httpx.HTTPError as e:
                    registrar_erro("google_flights", "rede")
                    raise ErroFonte(f"falha de rede: {e}")
                if resp.status_code != 200:
                    registrar_erro("google_flights", f"http_{resp.status_code}")
                    raise ErroFonte(f"HTTP {resp.status_code}")
                html = resp.text
                inicio = html[:3000].lower()
                if "consent.google" in inicio or "/consent" in inicio:
                    registrar_erro("google_flights", "consentimento")
                    raise FonteBloqueada(
                        "Google pediu consentimento (IP de servidor/VPN costuma causar isso)"
                    )
                if "sorry/index" in inicio or "detected unusual traffic" in html.lower():
                    registrar_erro("google_flights", "captcha")
                    raise FonteBloqueada("Google exibiu captcha de trafego incomum")

                ofertas = self._parsear(html, url, origem, destino, data_ida, data_volta)
                registrar_ofertas("google_flights", len(ofertas))
                registrar_busca(origem, destino, sucesso=True)
                if not ofertas:
                    registrar_erro("google_flights", "zero_ofertas_layout")
                return ofertas
            finally:
                if span_cm:
                    span_cm.end()

    # ------------------------ parser ------------------------

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
        # itens de itinerario: classe atual 'pIav2d' (era 'pIavEd' antigamente)
        blocos = soup.select("li.pIav2d") or soup.select("li.pIavEd")
        if not blocos:
            # markup pode ter mudado: tenta blocos genericos de resultado
            blocos = soup.select(
                'div[jsname][role="listitem"], li[role="listitem"]'
            )
            if blocos:
                log.debug("google_flights: usando seletores alternativos")
        ofertas: list[Oferta] = []
        vistos: set[tuple[float, str | None]] = set()
        for bloco in blocos[:12]:
            texto = bloco.get_text(" ", strip=True)
            if not texto:
                continue
            # preco confiavel: aria-label do span de preco ("1311 Reais brasileiros")
            preco = None
            moeda = self.cfg.moeda
            span = bloco.select_one(
                'span[aria-label*="Reais"], span[aria-label*="real"], span.FpEdX span'
            )
            if span:
                etiqueta = span.get("aria-label") or ""
                m = re.match(r"\s*([\d.,]+)\s*Reais", etiqueta)
                if m:
                    preco = normalizar_preco(m.group(1))
            if preco is None:
                preco, moeda_txt = preco_de_texto(texto)
                moeda = moeda_txt or moeda
            if preco is None or preco <= 0:
                continue
            cia = cia_de_texto(texto)
            escalas = escalas_de_texto(texto)
            chave = (preco, cia)
            if chave in vistos:
                continue  # "Melhores" e "Mais baratos" repetem itinerarios
            vistos.add(chave)
            ofertas.append(
                self._oferta(
                    origem,
                    destino,
                    data_ida,
                    data_volta,
                    preco,
                    url,
                    moeda=moeda or self.cfg.moeda,
                    cia=cia,
                    escalas=escalas,
                )
            )
        if not ofertas:
            log.info(
                "google_flights: nenhum resultado parseado "
                "(markup mudou? as outras fontes seguem normais)"
            )
        return ofertas[:10]