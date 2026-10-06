"""Teste offline do nucleo (sem rede): config, combos, banco, extracao,
e-mail e parser do Google Flights contra HTML real capturado no spike.

Uso:  python spikes/teste_offline.py
"""
import sys
import tempfile
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from busca_voos.combos import expandir, girar
from busca_voos.config import Config, ErroConfig, carregar_config
from busca_voos.db import Banco
from busca_voos.emailer import construir_email
from busca_voos.models import Oferta
from busca_voos.sources.extracao import (
    cia_de_texto,
    normalizar_preco,
    preco_de_texto,
)
from busca_voos.sources.google_flights import GoogleFlightsFonte

falhas = []


def verificar(nome, condicao, detalhe=""):
    status = "OK  " if condicao else "FALHA"
    print(f"{status} {nome}" + (f" — {detalhe}" if detalhe and not condicao else ""))
    if not condicao:
        falhas.append(nome)


# ---------------- config ----------------
yaml_exemplo = (RAIZ / "config.example.yaml").read_text(encoding="utf-8")
cfg = carregar_config(RAIZ / "config.example.yaml")
verificar("config: rotas lidas", len(cfg.rotas) == 1)
rota = cfg.rotas[0]
verificar("config: janela ida = 7 datas", len(rota.datas_ida) == 7)
verificar("config: janela volta = 5 datas", len(rota.datas_volta) == 5)
verificar("config: preco_maximo", rota.preco_maximo == 900)
verificar("config: fontes ativas", set(cfg.fontes_ativas()) == {
    "skiplagged", "google_flights", "skyscanner", "trip_com"
})

tmp = Path(tempfile.mkdtemp())
cfg_invalida = tmp / "config.yaml"
cfg_invalida.write_text(
    "fontes:\n  skiplagged: true\nrotas:\n  - origem: FLN\n    destino: RIO\n"
    "    janela_ida: { de: 2026-13-40, ate: 2026-12-26 }\n",
    encoding="utf-8",
)
try:
    carregar_config(cfg_invalida)
    verificar("config: data invalida rejeitada", False)
except ErroConfig:
    verificar("config: data invalida rejeitada", True)

# ---------------- combos ----------------
combos = expandir(rota)
verificar("combos: 7x5 = 35 pares", len(combos) == 35)
verificar("combos: volta sempre >= ida", all(v >= i for i, v in combos))
girados = set()
for ciclo in range(0, 35, 12):
    girados.update(girar(combos, ciclo)[:12])
verificar("combos: rodizio cobre tudo em 3 ciclos", len(girados) == 35)

# ---------------- banco ----------------
banco = Banco(tmp / "t.sqlite3")
oferta = Oferta(
    fonte="teste", rota="FLN-RIO", origem="FLN", destino="RIO",
    data_ida=date(2026, 12, 20), data_volta=date(2027, 1, 2),
    preco=800.0, moeda="BRL", link="https://exemplo/ok",
)
banco.salvar_ofertas([oferta], ciclo=1)
verificar("banco: ciclo inicia em 1", banco.proximo_ciclo() == 1)
alertar, motivo = banco.deve_alertar("teste", "FLN-RIO", date(2026, 12, 20), date(2027, 1, 2), 800, 24)
verificar("banco: primeiro alerta", alertar and motivo == "novo")
banco.registrar_alerta("teste", "FLN-RIO", date(2026, 12, 20), date(2027, 1, 2), 800, "x")
alertar, motivo = banco.deve_alertar("teste", "FLN-RIO", date(2026, 12, 20), date(2027, 1, 2), 790, 24)
verificar("banco: repetido suprimido", not alertar)
alertar, motivo = banco.deve_alertar("teste", "FLN-RIO", date(2026, 12, 20), date(2027, 1, 2), 700, 24)
verificar("banco: queda 10% realerta", alertar and "queda" in motivo)
alertar, _ = banco.deve_alertar("teste", "FLN-RIO", date(2026, 12, 21), None, 800, 24)
verificar("banco: data diferente alerta", alertar)
banco.fechar()

# ---------------- extracao ----------------
verificar("extracao: R$ 1.311", normalizar_preco("1.311") == 1311.0)
verificar("extracao: 2.560,90", normalizar_preco("2.560,90") == 2560.90)
verificar("extracao: centavos da API", normalizar_preco(131100) == 1311.0)
p, m = preco_de_texto("R$\xa01.311")
verificar("extracao: preco de texto", p == 1311.0 and m == "BRL")
verificar("extracao: cia", cia_de_texto("Operado por Gol. Sem escalas") == "GOL")

# ---------------- e-mail ----------------
assunto, html = construir_email([oferta])
verificar("email: assunto com rota e preco", "FLN-RIO" in assunto and "R$ 800" in assunto)
verificar("email: html com link", "https://exemplo/ok" in html and "<table" in html)

# ---------------- parser google_flights (HTML real do spike) ----------------
html_gf = RAIZ / "spikes" / "spike_gf.html"
if html_gf.exists():
    fonte = GoogleFlightsFonte(Config(caminho=RAIZ / "config.example.yaml"))
    ofertas = fonte._parsear(
        html_gf.read_text(encoding="utf-8"), "https://x", "FLN", "RIO",
        date(2026, 12, 20), date(2027, 1, 2),
    )
    verificar("gf parser: ofertas extraidas", len(ofertas) >= 5, f"n={len(ofertas)}")
    verificar("gf parser: sem duplicados", len(ofertas) == len({(o.preco, o.cia) for o in ofertas}))
    verificar("gf parser: moeda BRL", all(o.moeda == "BRL" for o in ofertas))
    cias = {o.cia for o in ofertas}
    verificar("gf parser: cia reconhecida", cias and all(c for c in cias), str(cias))
    verificar("gf parser: ordenavel", ofertas == sorted(ofertas, key=lambda o: o.preco))
else:
    print("PULAR gf parser (spike_gf.html ausente — rode o spike primeiro)")

print()
if falhas:
    print(f"FALHOU: {len(falhas)} teste(s): {', '.join(falhas)}")
    sys.exit(1)
print("Todos os testes offline passaram.")