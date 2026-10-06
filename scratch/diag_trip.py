import sys
from pathlib import Path
from bs4 import BeautifulSoup
from busca_voos.config import carregar_config
from busca_voos.sources.navegador import abrir_navegador

cfg = carregar_config("config.yaml")
origem = "fln"
destino = "gig"
data_ida = "2026-12-25"
url = f"https://www.trip.com/flights/showfarefirst?dcity={origem}&acity={destino}&ddate={data_ida}&triptype=ow&class=y&quantity=1&lowpricesource=searchform"

print(f"Acessando URL: {url}")
with abrir_navegador(cfg) as contexto:
    pagina = contexto.new_page()
    pagina.goto(url, wait_until="domcontentloaded", timeout=30000)
    pagina.wait_for_timeout(8000)
    print("Page Title:", pagina.title())
    print("Final URL:", pagina.url)
    html = pagina.content()
    Path("scratch/trip_dump.html").write_text(html, encoding="utf-8")
    print("Salvo scratch/trip_dump.html (tamanho:", len(html), "bytes)")
    soup = BeautifulSoup(html, "html.parser")
    blocos = soup.select('div[class*="flight-item"], div[class*="itinerary"], div[class*="pr-wrap"], [class*="flight"], [class*="price"]')
    print(f"Blocos encontrados: {len(blocos)}")
    for b in blocos[:5]:
        print("Bloco classes:", b.get("class"), "texto:", b.get_text(" ", strip=True)[:100])
