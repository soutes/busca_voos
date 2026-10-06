"""Spike 3: descobre o esquema atual do Skiplagged (logando chamadas /api/)
e testa Trip.com com curr=BRL. Requer permissao ampliada (pipes).
"""
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from busca_voos.config import carregar_config
from busca_voos.sources.navegador import abrir_navegador

cfg = carregar_config(RAIZ / "config.example.yaml")
cfg.navegador.headless = False
ida, volta = date(2026, 12, 20), date(2027, 1, 2)

alvos = {
    "skip-query": f"https://skiplagged.com/flights/FLN/RIO?depart_date={ida}&return_date={volta}",
    "skip-dash": f"https://skiplagged.com/flights/FLN-RIO/{ida:%Y-%m-%d}/{volta:%Y-%m-%d}",
    "trip-brl": (
        "https://www.trip.com/flights/showfarefirst"
        f"?dcity=fln&acity=rio&ddate={ida}&rdate={volta}"
        "&triptype=rt&class=y&quantity=1&lowpricesource=searchform&curr=BRL"
    ),
}

with abrir_navegador(cfg) as contexto:
    pagina = contexto.new_page()
    chamadas: list[str] = []

    def registrar(req):
        u = req.url
        if "skiplagged.com/api/" in u or "/api/" in u and "skiplagged" in u:
            chamadas.append(u)

    pagina.on("request", registrar)
    for nome, url in alvos.items():
        chamadas.clear()
        try:
            pagina.goto(url, wait_until="domcontentloaded", timeout=45_000)
            pagina.wait_for_timeout(18_000)
            pagina.mouse.wheel(0, 2000)
            pagina.wait_for_timeout(6_000)
            html = pagina.content()
            (RAIZ / "spikes" / f"{nome}.html").write_text(html, encoding="utf-8")
            print(
                f"{nome}: {len(html):,} bytes | R$={html.count('R$')} | "
                f"US$={html.count('US$')} | title={pagina.title()[:60]!r}"
            )
            api = [c for c in chamadas if "skiplagged.com/api" in c]
            for c in sorted(set(api))[:6]:
                print("   API:", c[:140])
        except Exception as e:
            print(f"{nome}: ERRO {type(e).__name__}: {str(e)[:150]}")

print("FIM SPIKE 3")