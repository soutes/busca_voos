import sys
from pathlib import Path
from bs4 import BeautifulSoup
from busca_voos.config import carregar_config
from busca_voos.sources.navegador import abrir_navegador

cfg = carregar_config("config.yaml")
origem = "fln"
destino = "gig"
data_ida = "261225"
url = f"https://www.skyscanner.com.br/transporte/passagens-aereas/{origem}/{destino}/{data_ida}/?adultsv2=1&cabinclass=economy&adults=1&children=0&infants=0"

print(f"Acessando URL: {url}")
with abrir_navegador(cfg) as contexto:
    pagina = contexto.new_page()
    pagina.goto(url, wait_until="domcontentloaded", timeout=30000)
    pagina.wait_for_timeout(5000)
    print("Page Title:", pagina.title())
    print("Final URL:", pagina.url)
    html = pagina.content()
    Path("scratch/skyscanner_dump.html").write_text(html, encoding="utf-8")
    print("Salvo scratch/skyscanner_dump.html (tamanho:", len(html), "bytes)")
    # Test selectors
    soup = BeautifulSoup(html, "html.parser")
    for sel in ['[data-test="journey-row"]', 'li[class*="ResultListItem"]', 'div[class*="ResultListItem"]', '[data-testid]', 'button', 'h1']:
        matches = soup.select(sel)
        print(f"Seletor '{sel}': {len(matches)} encontrados")
