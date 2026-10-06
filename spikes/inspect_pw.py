"""Inspeciona HTMLs salvos dos spikes Playwright (descartavel)."""
import re
from collections import Counter
from pathlib import Path

PASTA = Path(__file__).parent


def ver(nome):
    caminho = PASTA / nome
    if not caminho.exists():
        print(f"--- {nome}: ausente")
        return
    html = caminho.read_text(encoding="utf-8", errors="ignore")
    print(f"--- {nome}: {len(html):,} bytes")
    for padrao, rotulo in [
        (r"R\$\s?\xa0?[\d.,]+", "R$"),
        (r"US\$\s?\xa0?[\d.,]+", "US$"),
        (r'"price"\s*:\s*[\d.]+', '"price":'),
        (r"price_[\w-]+", "price_* class"),
        (r"class=\"[^\"]*price[^\"]*\"", "class *price*"),
    ]:
        m = re.findall(padrao, html)[:6]
        if m:
            print(f"  {rotulo}: {m}")
    # classes com 'price'
    classes = Counter(re.findall(r'class="([^"]*price[^"]*)"', html))
    for c, n in classes.most_common(6):
        print(f"  class: {n}x {c[:80]}")
    # contexto de cada R$
    for m in list(re.finditer(r"R\$", html))[:4]:
        ini = max(0, m.start() - 260)
        print("  ctx:", repr(html[ini:m.end() + 160])[:420])


ver("skiplagged-chromium-headed.html")
ver("tripcom-chromium-headed.html")
ver("tripcom_seo-chromium-headed.html")