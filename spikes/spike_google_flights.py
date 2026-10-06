"""Spike 2: valida o tfs corrigido contra o Google Flights real (descartavel)."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx

from busca_voos.sources.google_flights import UA, _tfs

trajos = [
    (date(2026, 12, 20), "FLN", "RIO"),
    (date(2027, 1, 2), "RIO", "FLN"),
]
tfs_meu = _tfs(trajos)
print("TFS meu  :", tfs_meu[:100], "...")

try:
    from fast_flights import FlightQuery, Passengers, create_query

    q = create_query(
        flights=[
            FlightQuery(date="2026-12-20", from_airport="FLN", to_airport="RIO"),
            FlightQuery(date="2027-01-02", from_airport="RIO", to_airport="FLN"),
        ],
        trip="round-trip",
        seat="economy",
        passengers=Passengers(adults=1),
        language="pt-BR",
        currency="BRL",
    )
    print("TFS lib  :", q.to_str()[:100], "...")
    print("bytes iguais:", q.to_bytes() == __import__("base64").b64decode(tfs_meu))
except Exception as e:
    print("lib indisponivel:", e)

url = (
    "https://www.google.com/travel/flights/search?tfs=" + tfs_meu
    + "&hl=pt-BR&curr=BRL"
)
headers = {"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"}
cookies = {"CONSENT": "YES+cb.20210328-17-p0.en+FX+419"}

r = httpx.get(url, headers=headers, cookies=cookies, follow_redirects=True, timeout=30)
print("status:", r.status_code, "| url final:", str(r.url)[:80])
html = r.text
Path(__file__).with_name("spike_gf.html").write_text(html, encoding="utf-8")
print("tamanho html:", len(html))
for marca in [
    "Melhores voos", "Best flights", "pIavEd", "explor", "consent.google",
    "unusual traffic", "R$",
]:
    print(f"  {marca!r}: {html.count(marca)}")

# precos com R$ >= 100 (indicativo de resultados, nao tiles de sugestao)
import re
precos = [m.group(1) for m in re.finditer(r"R\$\xa0?([\d.,]{3,10})", html)]
print("amostra de precos:", precos[:12])