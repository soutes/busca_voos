"""Spike Playwright 2: testa estrategias (headless/visivel/Chrome real) em
Skyscanner, Trip.com (2 URLs) e Skiplagged, salvando HTML por combinacao.

Requer permissao ampliada (driver do Playwright usa named pipes).
"""
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from busca_voos.config import carregar_config
from busca_voos.sources.navegador import abrir_navegador

cfg = carregar_config(RAIZ / "config.example.yaml")
ida, volta = date(2026, 12, 20), date(2027, 1, 2)

chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
if not chrome.exists():
    chrome = Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe")

alvos = {
    "skyscanner": f"https://www.skyscanner.com.br/transporte/passagens-aereas/fln/rio/{ida:%y%m%d}/?adultsv2=1&cabinclass=economy&adults=1&children=0&infants=0&rtn={volta:%y%m%d}",
    "tripcom": f"https://www.trip.com/flights/showfarefirst?dcity=fln&acity=rio&ddate={ida}&rdate={volta}&triptype=rt&class=y&quantity=1&lowpricesource=searchform",
    "tripcom_seo": f"https://www.trip.com/flights/fln-to-rio/tickets-fln-rio?dcity=fln&acity=rio&ddate={ida}&rdate={volta}&triptype=rt&class=y&quantity=1&searchboxid=&searchvalue=",
    "skiplagged": f"https://skiplagged.com/flights/FLN/RIO/{ida}/{volta}",
}

estrategias = [("chromium-headed", False, None)]
if chrome.exists():
    estrategias.append(("chrome-headed", False, "chrome"))

for nome_estrategia, headless, canal in estrategias:
    cfg.navegador.headless = headless
    cfg.navegador.canal = canal
    print(f"\n##### estrategia: {nome_estrategia}")
    try:
        with abrir_navegador(cfg) as contexto:
            pagina = contexto.new_page()
            for nome, url in alvos.items():
                arquivo = RAIZ / "spikes" / f"{nome}-{nome_estrategia}.html"
                try:
                    pagina.goto(url, wait_until="domcontentloaded", timeout=45_000)
                    pagina.wait_for_timeout(15_000)
                    pagina.mouse.wheel(0, 2000)
                    pagina.wait_for_timeout(5_000)
                    html = pagina.content()
                    arquivo.write_text(html, encoding="utf-8")
                    print(
                        f"  {nome}: {len(html):,} bytes | R$={html.count('R$')} "
                        f"captcha={html.lower().count('captcha')} "
                        f"whaleguard={html.lower().count('whaleguard')} "
                        f"px={html.lower().count('px-cloud')} -> {arquivo.name}"
                    )
                except Exception as e:
                    print(f"  {nome}: ERRO {type(e).__name__}: {str(e)[:120]}")
    except Exception as e:
        print(f"  navegador falhou: {type(e).__name__}: {str(e)[:200]}")

print("\nFIM SPIKE 2")