"""Inspeciona o HTML salvo do spike do Google Flights (descartavel)."""
import re
from collections import Counter
from pathlib import Path

html = (Path(__file__).with_name("spike_gf.html")).read_text(encoding="utf-8")

# 1) contexto de cada R$
print("=== contextos de R$ (primeiros 6) ===")
for m in list(re.finditer(r"R\$", html))[:6]:
    ini, fim = max(0, m.start() - 200), min(len(html), m.end() + 120)
    print(repr(html[ini:fim])[:420])
    print("---")

# 2) classes mais comuns perto de precos
contagem = Counter()
for m in re.finditer(r"R\$\s?\d", html):
    janela = html[max(0, m.start() - 600): m.end() + 200]
    for c in re.findall(r'class="([^"]{4,80})"', janela):
        contagem[c] += 1
print("=== classes perto de precos (top 20) ===")
for classe, n in contagem.most_common(20):
    print(f"{n:4d}  {classe}")

# 3) candidatos a item de resultado: tags <li ...> repetidas
li_classes = Counter(re.findall(r'<li class="([^"]+)"', html))
print("=== classes de <li> (top 10) ===")
for classe, n in li_classes.most_common(10):
    print(f"{n:4d}  {classe}")

# 4) procura por aria-label com preço e por "partnership"/airline markers
print("=== aria-labels com R$ (amostra) ===")
for m in list(re.finditer(r'aria-label="[^"]*R\$[^"]*"', html))[:4]:
    print(repr(m.group(0))[:300])

# 5) nomes de companhias presentes
for cia in ["LATAM", "GOL", "Azul", "Iberia", "Air Europa", "Avianca"]:
    print(cia, "->", html.count(cia))