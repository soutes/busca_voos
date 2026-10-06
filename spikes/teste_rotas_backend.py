"""Teste completo do backend de gestao de rotas e ciclo."""
from __future__ import annotations

import copy
import shutil
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from fastapi.testclient import TestClient

from busca_voos.config import (
    ErroConfig,
    adicionar_rota_config,
    carregar_config,
    listar_rotas_dict,
    remover_rota_config,
)
from busca_voos.web import criar_app

falhas: list[str] = []


def checar(nome: str, cond: bool, extra: object = "") -> None:
    print(("  OK    " if cond else "  FALHOU") + f" {nome}" + ("" if cond else f"  -> {extra!r}"))
    if not cond:
        falhas.append(nome)


# ---------------------------------------------------------------------
# 1. Testes de config.py em arquivo temporario
# ---------------------------------------------------------------------
print("\n== 1. Testes de config.py (adicionar/remover/listar/preservar) ==")

with tempfile.TemporaryDirectory() as tmpdir:
    cfg_path = Path(tmpdir) / "config.yaml"
    cfg_base = RAIZ / "config.example.yaml" if (RAIZ / "config.example.yaml").exists() else RAIZ / "config.yaml"
    shutil.copyfile(cfg_base, cfg_path)
    conteudo_orig = cfg_path.read_text(encoding="utf-8")

    # Listar rotas
    rotas_iniciais = listar_rotas_dict(cfg_path)
    checar("listar_rotas_dict retorna 1 rota inicial", len(rotas_iniciais) == 1, rotas_iniciais)
    r0 = rotas_iniciais[0]
    checar("r0.indice == 0", r0["indice"] == 0, r0["indice"])
    checar("r0.id == 'FLN-RIO'", r0["id"] == "FLN-RIO", r0["id"])
    checar("r0.origem == 'FLN'", r0["origem"] == "FLN", r0["origem"])
    checar("r0.destino == 'RIO'", r0["destino"] == "RIO", r0["destino"])
    checar("r0.janela_ida tem de e ate", r0["janela_ida"] == {"de": "2026-12-20", "ate": "2026-12-26"}, r0["janela_ida"])
    checar("r0.janela_volta tem de e ate", r0["janela_volta"] == {"de": "2027-01-02", "ate": "2027-01-06"}, r0["janela_volta"])
    checar("r0.preco_maximo == 900.0", r0["preco_maximo"] == 900.0, r0["preco_maximo"])

    # Validacoes ao adicionar rota
    casos_invalidos = [
        ("origem vazia", {"origem": "", "destino": "GRU", "janela_ida": {"de": "2026-11-01", "ate": "2026-11-05"}, "preco_maximo": 500}),
        ("origem com 1 char", {"origem": "F", "destino": "GRU", "janela_ida": {"de": "2026-11-01", "ate": "2026-11-05"}, "preco_maximo": 500}),
        ("origem com > 5 chars", {"origem": "FLORIPA", "destino": "GRU", "janela_ida": {"de": "2026-11-01", "ate": "2026-11-05"}, "preco_maximo": 500}),
        ("destino vazio", {"origem": "FLN", "destino": "", "janela_ida": {"de": "2026-11-01", "ate": "2026-11-05"}, "preco_maximo": 500}),
        ("origem == destino", {"origem": "FLN", "destino": "FLN", "janela_ida": {"de": "2026-11-01", "ate": "2026-11-05"}, "preco_maximo": 500}),
        ("janela_ida invertida", {"origem": "FLN", "destino": "GRU", "janela_ida": {"de": "2026-11-10", "ate": "2026-11-01"}, "preco_maximo": 500}),
        ("janela_volta anterior a ida", {"origem": "FLN", "destino": "GRU", "janela_ida": {"de": "2026-11-10", "ate": "2026-11-15"}, "janela_volta": {"de": "2026-11-05", "ate": "2026-11-08"}, "preco_maximo": 500}),
        ("janela_volta invertida", {"origem": "FLN", "destino": "GRU", "janela_ida": {"de": "2026-11-10", "ate": "2026-11-15"}, "janela_volta": {"de": "2026-11-25", "ate": "2026-11-20"}, "preco_maximo": 500}),
        ("preco_maximo zero", {"origem": "FLN", "destino": "GRU", "janela_ida": {"de": "2026-11-10", "ate": "2026-11-15"}, "preco_maximo": 0}),
        ("preco_maximo negativo", {"origem": "FLN", "destino": "GRU", "janela_ida": {"de": "2026-11-10", "ate": "2026-11-15"}, "preco_maximo": -100}),
    ]

    for rotulo, payload in casos_invalidos:
        try:
            adicionar_rota_config(cfg_path, payload)
            checar(f"validacao rejeitou: {rotulo}", False, "nao gerou erro")
        except ErroConfig:
            checar(f"validacao rejeitou: {rotulo}", True)

    # Adicionar rota valida 2
    nova_rota = {
        "origem": "fln",
        "destino": "gru",
        "janela_ida": {"de": "2026-12-10", "ate": "2026-12-15"},
        "janela_volta": {"de": "2026-12-20", "ate": "2026-12-25"},
        "preco_maximo": 450,
        "nome": "Floripa para Guarulhos",
    }
    rotas_atualizadas = adicionar_rota_config(cfg_path, nova_rota)
    checar("adicionar rota aumentou para 2 rotas", len(rotas_atualizadas) == 2, len(rotas_atualizadas))
    checar("rota 2 id == 'FLN-GRU'", rotas_atualizadas[1]["id"] == "FLN-GRU", rotas_atualizadas[1])
    checar("rota 2 nome preservado", rotas_atualizadas[1]["nome"] == "Floripa para Guarulhos")

    # Verifica se os comentarios foram preservados
    conteudo_novo = cfg_path.read_text(encoding="utf-8")
    checar("comentario de moeda preservado", "# moeda pedida nas buscas" in conteudo_novo)
    checar("comentario de fontes preservado", "# true = busca nesta fonte a cada ciclo" in conteudo_novo)
    checar("comentario de email preservado", "# conta que envia" in conteudo_novo)
    checar("comentario de agenda preservado", "# periodicidade do modo \"run\" (daemon)" in conteudo_novo)
    checar("comentario de navegador preservado", "# false para ver o navegador (depurar)" in conteudo_novo)

    # Verifica validacao carregar_config
    cfg_carregado = carregar_config(cfg_path)
    checar("carregar_config validou novo arquivo", len(cfg_carregado.rotas) == 2)

    # Remover rota invalida
    try:
        remover_rota_config(cfg_path, 99)
        checar("remover rota com indice invalido", False)
    except IndexError:
        checar("remover rota com indice invalido gerou IndexError", True)

    try:
        remover_rota_config(cfg_path, -1)
        checar("remover rota com indice -1 gerou IndexError", False)
    except IndexError:
        checar("remover rota com indice -1 gerou IndexError", True)

    # Remover rota 0
    rotas_apos_remocao = remover_rota_config(cfg_path, 0)
    checar("remover rota 0 deixou 1 rota", len(rotas_apos_remocao) == 1, len(rotas_apos_remocao))
    checar("rota restante e FLN-GRU com indice 0", rotas_apos_remocao[0]["id"] == "FLN-GRU" and rotas_apos_remocao[0]["indice"] == 0)

    # Tentar remover a unica rota restante (deve falhar)
    try:
        remover_rota_config(cfg_path, 0)
        checar("remover a unica rota restante deve falhar", False)
    except ErroConfig as e:
        checar("remover unica rota restante gerou ErroConfig", "ao menos uma rota" in str(e).lower(), str(e))


# ---------------------------------------------------------------------
# 2. Testes de endpoints do FastAPI (web.py)
# ---------------------------------------------------------------------
print("\n== 2. Testes dos endpoints web (/api/rotas e /api/ciclo) ==")

with tempfile.TemporaryDirectory() as tmpdir:
    db_path = RAIZ / "spikes" / "_saida_painel" / "dados.sqlite3"
    cfg_path = Path(tmpdir) / "config.yaml"
    cfg_base = RAIZ / "config.example.yaml" if (RAIZ / "config.example.yaml").exists() else RAIZ / "config.yaml"
    shutil.copyfile(cfg_base, cfg_path)

    limites = {"FLN-RIO": 900.0}
    app = criar_app(db_path, limites=limites, caminho_config=cfg_path)
    cli = TestClient(app, base_url="http://127.0.0.1:8787")

    # GET /api/rotas
    r = cli.get("/api/rotas")
    checar("GET /api/rotas responde 200", r.status_code == 200, r.status_code)
    checar("GET /api/rotas retorna 1 rota", len(r.json()["rotas"]) == 1, r.json())

    # POST /api/rotas (invalido)
    r_inv = cli.post("/api/rotas", json={"origem": "RIO", "destino": "RIO", "ida_de": "2026-11-01", "preco_maximo": 500})
    checar("POST /api/rotas origem==destino -> 400", r_inv.status_code == 400, r_inv.status_code)

    r_inv2 = cli.post("/api/rotas", json={"origem": "RIO", "destino": "FLN", "preco_maximo": -10})
    checar("POST /api/rotas preco_maximo negativo -> 400", r_inv2.status_code == 400, r_inv2.status_code)

    # POST /api/rotas (valido)
    payload_nova = {
        "origem": "POA",
        "destino": "LIS",
        "ida_de": "2026-12-15",
        "ida_ate": "2026-12-20",
        "volta_de": "2027-01-05",
        "volta_ate": "2027-01-10",
        "preco_maximo": 2800.0,
        "nome": "Porto Alegre - Lisboa",
    }
    r_post = cli.post("/api/rotas", json=payload_nova)
    checar("POST /api/rotas valido -> 200", r_post.status_code == 200, r_post.status_code)
    checar("POST /api/rotas ok == True", r_post.json().get("ok") is True)
    checar("POST /api/rotas agora tem 2 rotas", len(r_post.json()["rotas"]) == 2)
    checar("limites do app atualizado com POA-LIS", limites.get("POA-LIS") == 2800.0, limites)

    # DELETE /api/rotas/{indice}
    r_del_inv = cli.delete("/api/rotas/99")
    checar("DELETE /api/rotas/99 -> 400", r_del_inv.status_code == 400, r_del_inv.status_code)

    r_del = cli.delete("/api/rotas/1")
    checar("DELETE /api/rotas/1 -> 200", r_del.status_code == 200, r_del.status_code)
    checar("DELETE /api/rotas volta para 1 rota", len(r_del.json()["rotas"]) == 1)

    # DELETE ultima rota restante -> 400
    r_del_last = cli.delete("/api/rotas/0")
    checar("DELETE unica rota restante -> 400", r_del_last.status_code == 400, r_del_last.status_code)

    # GET /api/ciclo/status
    r_st = cli.get("/api/ciclo/status")
    checar("GET /api/ciclo/status responde 200", r_st.status_code == 200, r_st.status_code)
    st = r_st.json()
    checar("status tem rodando", "rodando" in st)
    checar("status tem ultimo_ciclo", "ultimo_ciclo" in st)
    checar("status tem erro", "erro" in st)
    checar("status tem mensagem", "mensagem" in st)
    checar("status tem iniciado_em", "iniciado_em" in st)

    # POST /api/ciclo
    # Para nao executar web scraping real que demora, podemos mockar ciclo
    from unittest.mock import patch
    with patch("busca_voos.scheduler.ciclo", return_value={"ciclo": 99, "ts": "2026-10-05T00:00:00Z"}):
        r_ciclo = cli.post("/api/ciclo")
        checar("POST /api/ciclo responde 200", r_ciclo.status_code == 200, r_ciclo.status_code)
        checar("POST /api/ciclo retorna ok=True e status=iniciado", r_ciclo.json() == {"ok": True, "status": "iniciado"}, r_ciclo.json())

        # Aguarda thread do ciclo terminar
        time.sleep(0.5)
        st2 = cli.get("/api/ciclo/status").json()
        checar("ciclo finalizou: rodando == False", st2["rodando"] is False, st2)
        checar("ultimo_ciclo atualizado para 99", st2["ultimo_ciclo"] == 99, st2)

print("\n" + "=" * 60)
if falhas:
    print(f"{len(falhas)} FALHA(S): " + "; ".join(falhas))
    sys.exit(1)
print("TODOS OS TESTES DE ROTAS E CICLO PASSARAM COM SUCESSO!")
