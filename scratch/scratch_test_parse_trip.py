from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from busca_voos.sources.extracao import preco_de_texto, cia_de_texto, escalas_de_texto

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        viewport={"width": 1366, "height": 850},
    )
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    page = context.new_page()
    url = "https://www.trip.com/flights/showfarefirst?dcity=fln&acity=gig&ddate=2026-12-25&triptype=ow&class=y&quantity=1&lowpricesource=searchform"
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(7000)
    page.mouse.wheel(0, 1500)
    page.wait_for_timeout(3000)
    html = page.content()
    browser.close()

soup = BeautifulSoup(html, "html.parser")
blocos = soup.select('div[class*="flight-item"], div[class*="itinerary"], div[class*="pr-wrap"]')
print(f"Total blocos: {len(blocos)}")
for i, b in enumerate(blocos[:5]):
    txt = b.get_text(" ", strip=True)
    print(f"\n--- Bloco {i} (len={len(txt)}) ---")
    print(txt[:300])
    p, m = preco_de_texto(txt)
    print("Preco extraído:", p, m)
    print("Cia:", cia_de_texto(txt))
