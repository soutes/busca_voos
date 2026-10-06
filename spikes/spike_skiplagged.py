"""Spike: testa a API interna packed.js do Skiplagged (descartavel)."""
from datetime import date

import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
headers = {"User-Agent": UA, "Referer": "https://skiplagged.com/", "Accept": "application/json"}

params = {
    "from": "FLN",
    "to": "RIO",
    "depart_date": date(2026, 12, 20).isoformat(),
    "return_date": date(2027, 1, 2).isoformat(),
    "format": "json",
    "currency": "BRL",
    "adults": 1,
}

for url in [
    "https://skiplagged.com/api/packed.js",
]:
    try:
        r = httpx.get(url, params=params, headers=headers, follow_redirects=True, timeout=30)
        print(url, "->", r.status_code, "| final:", str(r.url)[:100])
        print("corpo (primeiros 600):", r.text[:600].replace("\n", " ")[:600])
    except Exception as e:
        print(url, "ERRO:", type(e).__name__, e)

# pagina HTML direta (server-side rendering?)
try:
    r2 = httpx.get(
        "https://skiplagged.com/flights/FLN/RIO/2026-12-20/2027-01-02",
        headers={"User-Agent": UA},
        follow_redirects=True,
        timeout=30,
    )
    html = r2.text
    print("HTML direto status:", r2.status_code, "len:", len(html))
    print("trip-cost:", html.count("trip-cost"), "| R$:", html.count("R$"))
except Exception as e:
    print("HTML direto ERRO:", type(e).__name__, e)