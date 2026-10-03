"""Helpers de extracao de preco/cia a partir de textos do DOM."""
from __future__ import annotations

import re

# R$, US$, US $, $, EUR, € ...
_RE_VALOR = re.compile(r"(R\$\s?|US\$\s?|U\$D\s?|\$\s?|\u20ac\s?|EUR\s?)([\d.,]+)")
_RE_CIAS = [
    "LATAM", "GOL", "Azul", "American Airlines", "Iberia", "Air Europa",
    "Avianca", "Copa Airlines", "Copa", "Delta", "United", "TAP",
    "Turkish Airlines", "Emirates", "Aerol\u00edneas Argentinas", "Arajet",
    "JetSMART", "Sky Airline", "ITA Airways", "KLM", "Air France", "Lufthansa",
    "Qatar Airways", "Swiss", "British Airways", "Flybondi", "Conviasa",
    "Boliviana", "Aerom\u00e9xico", "Etihad", "Ethiopian", "Voepass",
]
_RE_CIA = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in _RE_CIAS) + r")\b", re.IGNORECASE
)

_SIMBOLO_MOEDA = {
    "R$": "BRL",
    "US$": "USD",
    "U$D": "USD",
    "$": "USD",
    "\u20ac": "EUR",
    "EUR": "EUR",
}


def normalizar_preco(bruto: str | float | int | None) -> float | None:
    """Converte "R$ 2.560", "2.560,90", "2560", 2560.0 (centavos) em float.

    Heuristica pt-BR: ponto = milhar quando seguido de exatamente 3 digitos.
    """
    if bruto is None:
        return None
    if isinstance(bruto, (int, float)):
        v = float(bruto)
        if v > 100_000:  # API costuma devolver centavos
            v /= 100.0
        return v
    s = str(bruto).strip()
    m = re.search(r"([\d.,]+)", s)
    if not m:
        return None
    s = m.group(1).strip(".,")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    elif "." in s:
        partes = s.split(".")
        if len(partes) > 2 or (len(partes) == 2 and len(partes[1]) == 3):
            s = s.replace(".", "")  # separador de milhar
    try:
        return float(s)
    except ValueError:
        return None


def preco_de_texto(texto: str) -> tuple[float | None, str | None]:
    """Devolve (preco, moeda) do primeiro valor monetario no texto."""
    m = _RE_VALOR.search(texto)
    if not m:
        return None, None
    moeda = _SIMBOLO_MOEDA.get(m.group(1).strip(), "BRL")
    return normalizar_preco(m.group(2)), moeda


def cia_de_texto(texto: str) -> str | None:
    m = _RE_CIA.search(texto)
    return m.group(1).title().replace("Latam", "LATAM").replace("Gol", "GOL") if m else None


def escalas_de_texto(texto: str) -> str | None:
    t = texto.lower()
    if "direto" in t or "nonstop" in t or "sem conex" in t:
        return "direto"
    m = re.search(r"(\d+)\s*parada", t)
    if m:
        n = int(m.group(1))
        return f"{n} parada" + ("s" if n > 1 else "")
    return None