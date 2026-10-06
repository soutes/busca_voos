"""Spike Playwright: navega em Skyscanner e Trip.com de verdade e salva o
HTML de resultados em spikes/ para iteracao dos seletores offline.

Requer permissao ampliada (driver do Playwright usa named pipes).
Uso:  python spikes/spike_playwright.py
"""
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from busca_voos.config import carregar_config
from busca_voos.sources.navegador import abrir_navegador
from busca_voos.sources.skyscanner import _url_busca as url_skyscanner
from busca_voos.sources.trip_com import _url_busca as url_tripcom

cfg = carregar_config(RAIZ / "config.example.yaml")
ida, volta = date(2026, 12, 20), date(2027, 1, 2)

alvos = [
    ("skyscanner", url_skyscanner("FLN", "RIO", ida, volta), "skyscanner.html"),
    ("trip_com", url_tripcom("FLN", "RIO", ida, volta), "tripcom.html"),
]

with abrir_navegador(cfg) as contexto:
    pagina = contexto.new_page()
    for nome, url, arquivo in alvos:
        print(f"=== {nome}: {url}")
        try:
            pagina.goto(url, wait_until="domcontentloaded", timeout=45_000)
            pagina.wait_for_timeout(9000)  # XHR de resultados
            pagina.mouse.wheel(0, 1500)
            pagina.wait_for_timeout(3000)
            html = pagina.content()
            (RAIZ / "spikes" / arquivo).write_text(html, encoding="utf-8")
            print(f"  titulo: {pagina.title()!r}")
            print(f"  html salvo: spikes/{arquivo} ({len(html):,} bytes)")
            print(f"  marcadores: R$={html.count('R$')} captcha={html.lower().count('captcha')} datadome={html.lower().count('datadome')}")
        except Exception as e:
            print(f"  ERRO: {type(e).__name__}: {e}")

print("FIM SPIKE PLAYWRIGHT")