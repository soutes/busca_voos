"""Teste de fumaca do painel web: API + pagina.

Cria um SQLite de exemplo (6 ciclos, 3 rotas, 3 fontes, 2 alertas), exercita
todos os endpoints com fastapi.testclient e os casos de erro, e no fim grava as
respostas reais em `spikes/_saida_painel/*.json` — que o teste do JavaScript
(`spikes/teste_painel_js.mjs`, rodado com `node`) usa para verificar a
renderizacao da pagina.

Uso:
    python spikes/teste_painel.py
    node spikes/teste_painel_js.mjs     # depois do de cima
"""
from __future__ import annotations

import builtins
import json
import shutil
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from busca_voos import painel  # noqa: E402
from busca_voos.db import Banco  # noqa: E402
from busca_voos.models import Oferta  # noqa: E402
from busca_voos.web import criar_app  # noqa: E402

BASE = Path(__file__).resolve().parent / "_saida_painel"
shutil.rmtree(BASE, ignore_errors=True)
BASE.mkdir()
DB = BASE / "dados.sqlite3"

falhas: list[str] = []


def checar(nome: str, cond: bool, extra: object = "") -> None:
    print(("  OK    " if cond else "  FALHOU") + f" {nome}" + ("" if cond else f"  -> {extra!r}"))
    if not cond:
        falhas.append(nome)


# ------------------------- banco de exemplo -------------------------
CICLOS, ROTAS, FONTES = 6, [("FLN", "RIO"), ("FLN", "GRU"), ("POA", "LIS")], ["google_flights", "skiplagged", "skyscanner"]

banco = Banco(DB)
for ciclo in range(1, CICLOS + 1):
    assert banco.proximo_ciclo() == ciclo  # igual ao daemon: mantem meta.ciclo
    for i, (origem, destino) in enumerate(ROTAS):
        ida = date(2026, 12, 20) + timedelta(days=i * 2)
        for j, fonte in enumerate(FONTES):
            banco.salvar_ofertas(
                [
                    Oferta(
                        fonte=fonte,
                        rota=f"{origem}-{destino}",
                        origem=origem,
                        destino=destino,
                        data_ida=ida,
                        data_volta=ida + timedelta(days=10),
                        preco=900 + i * 120 + j * 40 - ciclo * 25,
                        moeda="BRL",
                        link=f"https://exemplo.test/{fonte}/{origem}{destino}",
                        cia="GOL" if j % 2 else "LATAM",
                        escalas="direto" if j == 0 else "1 escala",
                    )
                ],
                ciclo=ciclo,
            )

con = banco.con
for ciclo in range(1, CICLOS + 1):
    ts = (datetime.now(timezone.utc) - timedelta(days=CICLOS - ciclo)).isoformat(timespec="seconds")
    con.execute("UPDATE ofertas SET ts = ? WHERE ciclo = ?", (ts, ciclo))
con.commit()

banco.registrar_alerta("google_flights", "FLN-RIO", date(2026, 12, 20), date(2026, 12, 30), 750.0, "https://exemplo.test/alerta")
banco.registrar_alerta("skiplagged", "POA-LIS", date(2026, 12, 22), date(2027, 1, 1), 2450.0, "javascript:alert(1)")
banco.fechar()

TOTAL_LINHAS = CICLOS * len(ROTAS) * len(FONTES)
COMBOS = len(ROTAS) * len(FONTES)

CFG_TESTE = BASE / "config.yaml"
shutil.copyfile(RAIZ / "config.yaml", CFG_TESTE)
app = criar_app(DB, limites={"FLN-RIO": 800, "POA-LIS": 2500}, caminho_config=CFG_TESTE)
cli = TestClient(app)

r = cli.get("/")
checar("GET / responde 200", r.status_code == 200, r.status_code)
checar("GET / devolve HTML", "text/html" in r.headers.get("content-type", ""), r.headers.get("content-type"))
for rota_api in ["/api/resumo", "/api/ofertas", "/api/alertas", "/api/historico", "/api/filtros", "/api/rotas", "/api/ciclo", "/api/aeroportos", "/api/cron", "/api/configuracoes", "/api/email/testar", "/api/versao"]:
    checar(f"pagina consome {rota_api}", rota_api in r.text)
checar("GET /healthz ok", cli.get("/healthz").json() == {"ok": True})
checar("GET /api/docs ok", cli.get("/api/docs").status_code == 200)

print("\n== resumo ==")
j = cli.get("/api/resumo").json()
checar("total_ofertas", j["total_ofertas"] == TOTAL_LINHAS, j["total_ofertas"])
checar("total_alertas", j["total_alertas"] == 2, j["total_alertas"])
checar("ciclo atual", j["ciclo"] == CICLOS, j["ciclo"])
checar("ultima_coleta preenchida", bool(j["ultima_coleta"]), j["ultima_coleta"])
checar("menor preco = FLN-RIO 750", j["menor_preco"]["preco"] == 750 and j["menor_preco"]["rota"] == "FLN-RIO", j["menor_preco"])
checar("por_rota: 1 melhor por rota", len(j["por_rota"]) == 3, j["por_rota"])
checar("por_fonte: 3 fontes", len(j["por_fonte"]) == 3, j["por_fonte"])

print("\n== filtros ==")
f = cli.get("/api/filtros").json()
checar("3 rotas no filtro", f["rotas"] == ["FLN-GRU", "FLN-RIO", "POA-LIS"], f["rotas"])
checar("3 fontes no filtro", len(f["fontes"]) == 3, f["fontes"])
checar("limites do config chegam na tela", f["limites"]["FLN-RIO"] == 800, f["limites"])

print("\n== ofertas ==")
j = cli.get("/api/ofertas", params={"rota": "FLN-RIO", "ordem": "preco"}).json()
checar("total filtrado por rota", j["total"] == 3, j["total"])
checar("so a rota pedida", {o["rota"] for o in j["ofertas"]} == {"FLN-RIO"})
precos = [o["preco"] for o in j["ofertas"]]
checar("ordenado por preco asc", precos == sorted(precos), precos)
checar("retrato mais recente (ciclo 6)", all(o["ciclo"] == CICLOS for o in j["ofertas"]), [o["ciclo"] for o in j["ofertas"]])

j = cli.get("/api/ofertas", params={"ordem": "preco_desc"}).json()
checar("ordem desc", [o["preco"] for o in j["ofertas"]] == sorted([o["preco"] for o in j["ofertas"]], reverse=True))

j = cli.get("/api/ofertas", params={"limite": 2}).json()
checar("limite respeitado", len(j["ofertas"]) == 2 and j["total"] == COMBOS, (len(j["ofertas"]), j["total"]))

j = cli.get("/api/ofertas", params={"preco_max": 800}).json()
checar("filtro preco_max", j["total"] > 0 and all(o["preco"] <= 800 for o in j["ofertas"]), j["total"])

j = cli.get("/api/ofertas", params={"de": "2026-12-22", "ate": "2026-12-24"}).json()
checar("filtro de datas", j["total"] > 0 and all("2026-12-22" <= o["data_ida"] <= "2026-12-24" for o in j["ofertas"]), j["total"])

j = cli.get("/api/ofertas", params={"fonte": "skiplagged"}).json()
checar("filtro por fonte", j["total"] == len(ROTAS) and {o["fonte"] for o in j["ofertas"]} == {"skiplagged"})

print("\n== alertas ==")
j = cli.get("/api/alertas").json()
checar("2 alertas, mais novo primeiro", len(j["alertas"]) == 2 and j["alertas"][0]["rota"] == "POA-LIS", j["alertas"])

print("\n== historico ==")
j = cli.get("/api/historico", params={"rota": "FLN-RIO", "dias": 30}).json()
dias = [p["dia"] for p in j["historico"]]
checar("6 dias de serie", len(dias) == CICLOS, dias)
checar("dias em ordem", dias == sorted(dias), dias)
minimos = [p["minimo"] for p in j["historico"]]
checar("minimo cai a cada ciclo", minimos == sorted(minimos, reverse=True), minimos)
checar("historico com fonte", len(cli.get("/api/historico", params={"fonte": "skiplagged"}).json()["historico"]) == CICLOS)

print("\n== entradas invalidas ==")
checar("ordem desconhecida -> 400", cli.get("/api/ofertas", params={"ordem": "hack"}).status_code == 400)
checar("data invalida -> 422", cli.get("/api/ofertas", params={"de": "2026-13-01"}).status_code == 422)
checar("ate antes de de -> 400", cli.get("/api/ofertas", params={"de": "2027-01-01", "ate": "2026-01-01"}).status_code == 400)
checar("limite acima do teto -> 422", cli.get("/api/ofertas", params={"limite": 99999}).status_code == 422)
checar("preco negativo -> 422", cli.get("/api/ofertas", params={"preco_max": -5}).status_code == 422)
checar("dias absurdo -> 422", cli.get("/api/historico", params={"dias": 0}).status_code == 422)

r = cli.get("/api/ofertas", params={"rota": "FLN-RIO'; DROP TABLE ofertas; --"})
checar("tentativa de injection nao quebra", r.status_code == 200 and r.json()["ofertas"] == [], r.status_code)
checar("tabela segue intacta", cli.get("/api/resumo").json()["total_ofertas"] == TOTAL_LINHAS)

print("\n== leitura somente ==")
c = painel.conectar(DB)
try:
    c.execute("DELETE FROM ofertas")
    escreveu = True
except sqlite3.OperationalError:
    escreveu = False
c.close()
checar("conexao do painel recusa escrita", not escreveu)
checar("linhas continuam la", painel.conectar(DB).execute("SELECT COUNT(*) n FROM ofertas").fetchone()["n"] == TOTAL_LINHAS)

print("\n== banco ausente / invalido ==")
r = TestClient(criar_app(BASE / "nao_existe.sqlite3")).get("/api/resumo")
checar("banco ausente -> 503", r.status_code == 503, r.status_code)
checar("mensagem orienta o usuario", "busca-voos uma" in r.json()["detail"], r.json()["detail"])

ruim = BASE / "nao_e_sqlite.txt"
ruim.write_text("isto nao e um banco", encoding="utf-8")
r = TestClient(criar_app(ruim)).get("/api/resumo")
checar("arquivo nao-SQLite -> 503", r.status_code == 503, r.status_code)

print("\n== agendador cron e status de ciclo ==")
rc = cli.get("/api/cron")
checar("GET /api/cron 200", rc.status_code == 200, rc.status_code)
cron_dados = rc.json()
checar("cron tem campo ativo", "ativo" in cron_dados)
checar("cron tem campo intervalo_horas", "intervalo_horas" in cron_dados)
checar("cron intervalo_horas default 1.0", cron_dados["intervalo_horas"] == 1.0)

# Validacoes de intervalo cron
checar("POST /api/cron intervalo <= 0 -> 400", cli.post("/api/cron", json={"intervalo_horas": 0}).status_code == 400)
checar("POST /api/cron intervalo > 168 -> 400", cli.post("/api/cron", json={"intervalo_horas": 999}).status_code == 400)
checar("POST /api/cron tipo invalido -> 400", cli.post("/api/cron", json={"intervalo_horas": "xyz"}).status_code == 400)

# Ativacao valida
r_cron_post = cli.post("/api/cron", json={"ativo": True, "intervalo_horas": 2.0})
checar("POST /api/cron ativa com sucesso", r_cron_post.status_code == 200 and r_cron_post.json()["ativo"] is True)
checar("POST /api/cron proxima_execucao calculada", r_cron_post.json()["proxima_execucao"] is not None)
checar("POST /api/cron segundos_restantes presente", r_cron_post.json()["segundos_restantes"] is not None)

# Desativar para manter estado limpo
r_cron_desat = cli.post("/api/cron", json={"ativo": False, "intervalo_horas": 1.0})
checar("POST /api/cron desativa", r_cron_desat.status_code == 200 and r_cron_desat.json()["ativo"] is False)

# Checagem de progresso ao vivo em /api/ciclo/status
st_resp = cli.get("/api/ciclo/status")
checar("GET /api/ciclo/status 200", st_resp.status_code == 200)
st = st_resp.json()
for c in ["rodando", "ultimo_ciclo", "ofertas_encontradas", "consultas_feitas", "fonte_atual", "mensagem", "diagnostico"]:
    checar(f"campo {c} presente em status", c in st)

print("\n== respostas reais para o teste de JS ==")
alvos = {
    "filtros.json": ("/api/filtros", {}),
    "resumo.json": ("/api/resumo", {}),
    "ofertas.json": ("/api/ofertas", {"ordem": "preco", "limite": 200}),
    "alertas.json": ("/api/alertas", {"limite": 100}),
    "historico.json": ("/api/historico", {"dias": 180}),
    "rotas.json": ("/api/rotas", {}),
    "ciclo_status.json": ("/api/ciclo/status", {}),
    "aeroportos.json": ("/api/aeroportos", {"limite": 50}),
    "cron.json": ("/api/cron", {}),
    "configuracoes.json": ("/api/configuracoes", {}),
    "versao.json": ("/api/versao", {}),
}
for arquivo, (rota_api, params) in alvos.items():
    resposta = cli.get(rota_api, params=params)
    resposta.raise_for_status()
    (BASE / arquivo).write_text(json.dumps(resposta.json(), ensure_ascii=False), encoding="utf-8")
checar(f"{len(alvos)} respostas salvas em _saida_painel/", len(list(BASE.glob("*.json"))) >= len(alvos))
print("        agora rode: node spikes/teste_painel_js.mjs")

print("\n== fallback de ciclo ==")
c2 = sqlite3.connect(DB)
c2.execute("DELETE FROM meta WHERE chave = 'ciclo'")
c2.commit()
c2.close()
checar("sem meta.ciclo, usa MAX(ciclo) da tabela", cli.get("/api/resumo").json()["ciclo"] == CICLOS, cli.get("/api/resumo").json()["ciclo"])

print("\n== pagina estatica ==")
html = (RAIZ / "src" / "busca_voos" / "painel.html").read_text(encoding="utf-8")
checar("sem CDN / script externo", "cdn." not in html and "<script src" not in html and "<link" not in html)
checar("nao usa innerHTML com dados do banco", "innerHTML" not in html)
checar("filtra link javascript:", "linkSeguro" in html and "http:" in html)

print("\n== servir(): --abrir, porta ocupada e deps ausentes ==")
import uvicorn  # noqa: E402

from busca_voos import web as modulo_web  # noqa: E402

run_original = uvicorn.run
abrir_original = modulo_web.webbrowser.open
abertos: list[str] = []
modulo_web.webbrowser.open = abertos.append
uvicorn.run = lambda *a, **k: None  # nao bloqueia o teste
try:
    codigo = modulo_web.servir(DB, porta=8123, abrir_navegador=True)
finally:
    uvicorn.run = run_original
    modulo_web.webbrowser.open = abrir_original
time.sleep(1.3)  # o Timer do --abrir dispara depois de 1s
checar("servir() retorna 0", codigo == 0, codigo)
checar("--abrir abre a URL certa", abertos == ["http://127.0.0.1:8123"], abertos)

def _porta_ocupada(*a, **k):
    raise OSError("[Errno 98] Address already in use")

uvicorn.run = _porta_ocupada
try:
    modulo_web.servir(DB, porta=8123)
    checar("porta ocupada -> ErroPainel", False, "nao levantou nada")
except modulo_web.ErroPainel as e:
    checar("porta ocupada -> ErroPainel com dica de --porta", "--porta" in str(e), str(e))
finally:
    uvicorn.run = run_original

import_original = builtins.__import__


def _sem_fastapi(nome, *a, **k):
    if nome.split(".")[0] in ("fastapi", "uvicorn"):
        raise ImportError(f"{nome} indisponivel (simulado)")
    return import_original(nome, *a, **k)


builtins.__import__ = _sem_fastapi
try:
    criar_app(DB)
    checar("fastapi ausente -> ErroPainel", False, "nao levantou nada")
except modulo_web.ErroPainel as e:
    checar("fastapi ausente -> mensagem de instalacao", "pip install -e" in str(e), str(e))
finally:
    builtins.__import__ = import_original

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} FALHA(S): " + "; ".join(falhas))
    sys.exit(1)
print("TODOS OS TESTES PASSARAM")
