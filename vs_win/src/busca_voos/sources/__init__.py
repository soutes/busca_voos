"""Registro das fontes de busca.

Fontes implementadas: skiplagged, google_flights, skyscanner, trip_com e os sites
das companhias (latam, gol, azul; Chrome visivel). Planejada (valor None): kayak — o config ja
aceita o nome; ao ativar antes da implementacao, o scheduler avisa e pula.
"""
from __future__ import annotations

from .base import ErroFonte, FonteBase, FonteBloqueada, FontePendente
from .azul import AzulFonte
from .gol import GolFonte
from .google_flights import GoogleFlightsFonte
from .latam import LatamFonte
from .skiplagged import SkiplaggedFonte
from .skyscanner import SkyscannerFonte
from .trip_com import TripComFonte

REGISTRO: dict[str, type[FonteBase] | None] = {
    "skiplagged": SkiplaggedFonte,
    "google_flights": GoogleFlightsFonte,
    "skyscanner": SkyscannerFonte,
    "trip_com": TripComFonte,
    "kayak": None,   # fase 3
    "latam": LatamFonte,
    "gol": GolFonte,
    "azul": AzulFonte,
}

__all__ = [
    "REGISTRO",
    "AzulFonte",
    "ErroFonte",
    "FonteBase",
    "FonteBloqueada",
    "FontePendente",
    "GolFonte",
    "GoogleFlightsFonte",
    "LatamFonte",
    "SkiplaggedFonte",
    "SkyscannerFonte",
    "TripComFonte",
]