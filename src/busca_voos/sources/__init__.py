"""Registro das fontes de busca.

Fontes implementadas (fases 1-2): skiplagged, google_flights, skyscanner, trip_com.
Fontes planejadas (fase 3, valor None): kayak, latam, gol, azul — o config ja
aceita o nome; ao ativar antes da implementacao, o scheduler avisa e pula.
"""
from __future__ import annotations

from .base import ErroFonte, FonteBase, FonteBloqueada, FontePendente
from .google_flights import GoogleFlightsFonte
from .skiplagged import SkiplaggedFonte
from .skyscanner import SkyscannerFonte
from .trip_com import TripComFonte

REGISTRO: dict[str, type[FonteBase] | None] = {
    "skiplagged": SkiplaggedFonte,
    "google_flights": GoogleFlightsFonte,
    "skyscanner": SkyscannerFonte,
    "trip_com": TripComFonte,
    "kayak": None,   # fase 3
    "latam": None,   # fase 3
    "gol": None,     # fase 3
    "azul": None,    # fase 3
}

__all__ = [
    "REGISTRO",
    "ErroFonte",
    "FonteBase",
    "FonteBloqueada",
    "FontePendente",
    "GoogleFlightsFonte",
    "SkiplaggedFonte",
    "SkyscannerFonte",
    "TripComFonte",
]