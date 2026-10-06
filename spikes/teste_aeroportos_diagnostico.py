"""Testes unitários e de integração para:
1. Catálogo de aeroportos (aeroportos.py)
2. Resolução de rotas no Skiplagged (skiplagged.py)
3. Diagnóstico e resumo enriquecido no agendador (scheduler.py)
4. Endpoints web /api/aeroportos e /api/ciclo/status (web.py)
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from fastapi.testclient import TestClient

from busca_voos.aeroportos import (
    AEROPORTOS,
    METROPOLITANOS_CONFIG,
    METROPOLITANOS_PRIMARIOS,
    TOP_AEROPORTOS_BR,
    buscar_aeroportos,
    resolver_para_fonte,
    validar_iata,
)
from busca_voos.config import Config, carregar_config
from busca_voos.models import Oferta, Rota
from busca_voos.scheduler import ciclo
from busca_voos.sources.skiplagged import SkiplaggedFonte
from busca_voos.web import criar_app

falhas: list[str] = []


def checar(nome: str, cond: bool, extra: object = "") -> None:
    status = "  OK    " if cond else "  FALHOU"
    msg = f"{status} {nome}" + ("" if cond else f"  -> {extra!r}")
    print(msg)
    if not cond:
        falhas.append(nome)


# =====================================================================
# 1. TESTES DO CATÁLOGO DE AEROPORTOS (aeroportos.py)
# =====================================================================
print("\n== 1. Testes do catálogo de aeroportos (aeroportos.py) ==")

# 1.1 Aeroportos comerciais no Brasil exigidos no escopo
aeroportos_br_obrigatorios = [
    "FLN", "GRU", "CGH", "VCP", "GIG", "SDU", "BSB", "CNF", "SSA", "REC",
    "FOR", "POA", "CWB", "VIX", "GYN", "BEL", "MAO", "MCZ", "NAT", "IGU",
    "NVT", "XAP", "UDI", "CGB", "CGR", "JPA", "AJU", "SLZ", "PMW", "PVH",
    "BPS", "IOS", "JDO", "IMP", "MGF", "LDB", "CXJ", "JOI",
]
for cod in aeroportos_br_obrigatorios:
    info = validar_iata(cod)
    checar(f"Catálogo BR contém {cod}", info is not None and info["pais"] == "Brasil", info)

# 1.2 Códigos metropolitanos exigidos no escopo
metros_obrigatorios = {
    "RIO": ("GIG", ["GIG", "SDU"]),
    "SAO": ("GRU", ["GRU", "CGH", "VCP"]),
    "BHZ": ("CNF", ["CNF"]),
    "BUE": ("EZE", ["EZE", "AEP"]),
    "NYC": ("JFK", ["JFK", "EWR", "LGA"]),
    "LON": ("LHR", ["LHR", "LGW", "STN", "LTN", "LCY"]),
    "PAR": ("CDG", ["CDG", "ORY"]),
}
for cod, (primario_esp, alts_esp) in metros_obrigatorios.items():
    info = validar_iata(cod)
    checar(f"Catálogo contém metropolitano {cod}", info is not None and info["tipo"] == "metropolitano", info)
    checar(f"{cod} primário é {primario_esp}", info is not None and info.get("primario") == primario_esp, info)
    checar(f"{cod} alternativos conferem", info is not None and set(alts_esp).issubset(set(info.get("alternativos", []))), info)

# 1.3 Destinos internacionais populares exigidos
internacionais_obrigatorios = [
    "MIA", "MCO", "JFK", "LIS", "OPO", "MAD", "CDG", "FCO", "EZE", "SCL",
    "BOG", "MVD", "LIM", "PTY", "CUN",
]
for cod in internacionais_obrigatorios:
    info = validar_iata(cod)
    checar(f"Catálogo contém internacional {cod}", info is not None, info)

# 1.4 Estrutura de campos de cada item
for item in AEROPORTOS.values():
    campos_esperados = {"codigo", "cidade", "nome", "estado", "pais", "tipo", "descricao"}
    checar(
        f"Item {item['codigo']} possui campos obrigatórios",
        campos_esperados.issubset(item.keys()),
        item,
    )
    checar(
        f"Item {item['codigo']} tipo é válido",
        item["tipo"] in ("aeroporto", "metropolitano"),
        item["tipo"],
    )

# 1.5 buscar_aeroportos com termo vazio (retorna top 15 BR)
top15 = buscar_aeroportos("")
checar("buscar_aeroportos('') retorna 15 itens", len(top15) == 15, len(top15))
checar("Top 15 são do Brasil", all(a["pais"] == "Brasil" for a in top15))
checar("Top 15 contém GRU", any(a["codigo"] == "GRU" for a in top15))
checar("Top 15 contém FLN", any(a["codigo"] == "FLN" for a in top15))
checar("Top 15 respeita limite=5", len(buscar_aeroportos("", limite=5)) == 5)

# 1.6 buscar_aeroportos tolerante a acentos e maiúsculas/minúsculas
res_sp1 = buscar_aeroportos("São Paulo")
res_sp2 = buscar_aeroportos("sao paulo")
checar("Busca 'São Paulo' e 'sao paulo' retornam resultados", len(res_sp1) > 0 and len(res_sp2) > 0)
checar("Busca 'sao paulo' inclui GRU e SAO", {"GRU", "SAO"}.issubset({a["codigo"] for a in res_sp2}))

res_fln = buscar_aeroportos("florianopolis")
checar("Busca sem acento 'florianopolis' traz FLN no topo", len(res_fln) > 0 and res_fln[0]["codigo"] == "FLN")

res_rio = buscar_aeroportos("rio")
checar("Busca 'rio' traz RIO no topo por correspondência exata de código", len(res_rio) > 0 and res_rio[0]["codigo"] == "RIO")
checar("Busca 'rio' traz GIG e SDU nas primeiras posições", {"GIG", "SDU"}.issubset({a["codigo"] for a in res_rio[:5]}))

# 1.7 validar_iata
checar("validar_iata('FLN') retorna dict com FLN", validar_iata("FLN") is not None and validar_iata("FLN")["codigo"] == "FLN")
checar("validar_iata('  fln  ') case-insensitive", validar_iata("  fln  ") is not None and validar_iata("  fln  ")["codigo"] == "FLN")
checar("validar_iata('XYZ999') inválido retorna None", validar_iata("XYZ999") is None)
checar("validar_iata('') retorna None", validar_iata("") is None)

# 1.8 resolver_para_fonte
checar("resolver_para_fonte('RIO', 'skiplagged') mapeia para GIG", resolver_para_fonte("RIO", "skiplagged") == "GIG")
checar("resolver_para_fonte('rio', 'skiplagged') case-insensitive", resolver_para_fonte("rio", "skiplagged") == "GIG")
checar("resolver_para_fonte('SAO', 'skiplagged') mapeia para GRU", resolver_para_fonte("SAO", "skiplagged") == "GRU")
checar("resolver_para_fonte('BHZ', 'skiplagged') mapeia para CNF", resolver_para_fonte("BHZ", "skiplagged") == "CNF")
checar("resolver_para_fonte('BUE', 'skiplagged') mapeia para EZE", resolver_para_fonte("BUE", "skiplagged") == "EZE")
checar("resolver_para_fonte('NYC', 'skiplagged') mapeia para JFK", resolver_para_fonte("NYC", "skiplagged") == "JFK")
checar("resolver_para_fonte('LON', 'skiplagged') mapeia para LHR", resolver_para_fonte("LON", "skiplagged") == "LHR")
checar("resolver_para_fonte('PAR', 'skiplagged') mapeia para CDG", resolver_para_fonte("PAR", "skiplagged") == "CDG")
checar("resolver_para_fonte('FLN', 'skiplagged') mantém FLN", resolver_para_fonte("FLN", "skiplagged") == "FLN")
checar("resolver_para_fonte('RIO', 'google_flights') mantém RIO", resolver_para_fonte("RIO", "google_flights") == "RIO")
checar("resolver_para_fonte('RIO', 'skyscanner') mantém RIO", resolver_para_fonte("RIO", "skyscanner") == "RIO")


# =====================================================================
# 2. TESTES DA FONTE SKIPLAGGED (skiplagged.py)
# =====================================================================
print("\n== 2. Testes de resolução no Skiplagged (skiplagged.py) ==")

cfg_teste = carregar_config(RAIZ / "config.yaml")
fonte_skip = SkiplaggedFonte(cfg_teste)

# Mocka _via_api para interceptar os parâmetros passados
with patch.object(fonte_skip, "_via_api", return_value=[]) as mock_api:
    with patch.object(fonte_skip, "_via_navegador", return_value=[]):
        fonte_skip.buscar("FLN", "RIO", date(2026, 12, 25))
        checar("buscar('FLN', 'RIO') chamou _via_api", mock_api.called)
        args_chamada = mock_api.call_args[0]
        checar("origem resolvida passada para _via_api é FLN", args_chamada[0] == "FLN", args_chamada)
        checar("destino resolvido passado para _via_api é GIG (não RIO)", args_chamada[1] == "GIG", args_chamada)

with patch.object(fonte_skip, "_via_api", return_value=[]) as mock_api:
    with patch.object(fonte_skip, "_via_navegador", return_value=[]):
        fonte_skip.buscar("SAO", "BUE", date(2026, 12, 25))
        args_chamada = mock_api.call_args[0]
        checar("SAO -> BUE resolve para GRU -> EZE no Skiplagged", args_chamada[0] == "GRU" and args_chamada[1] == "EZE", args_chamada)


# =====================================================================
# 3. TESTES DO AGENDADOR E DIAGNÓSTICO (scheduler.py)
# =====================================================================
print("\n== 3. Testes de diagnóstico e resumo enriquecido (scheduler.py) ==")

with tempfile.TemporaryDirectory() as tmpdir:
    db_tmp = Path(tmpdir) / "teste.sqlite3"
    cfg_tmp = carregar_config(RAIZ / "config.yaml")
    cfg_tmp.banco = db_tmp
    cfg_tmp.agenda.pausa_entre_consultas_s = 0
    cfg_tmp.agenda.pausa_entre_fontes_s = 0
    cfg_tmp.agenda.max_combinacoes_por_ciclo = 1

    # Mocka as fontes para testar diferentes cenários em ciclo()
    mock_oferta = Oferta(
        fonte="google_flights",
        rota="FLN-RIO",
        origem="FLN",
        destino="RIO",
        data_ida=date(2026, 12, 25),
        data_volta=date(2027, 1, 4),
        preco=800.0,
        moeda="BRL",
        link="https://google.com/flights",
    )

    class MockFonteOk:
        def __init__(self, cfg):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def buscar(self, origem, destino, ida, volta):
            return [mock_oferta]

    class MockFonteVazia:
        def __init__(self, cfg):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def buscar(self, origem, destino, ida, volta):
            return []

    from busca_voos.sources.base import ErroFonte, FonteBloqueada

    class MockFonteBloqueada:
        def __init__(self, cfg):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def buscar(self, origem, destino, ida, volta):
            raise FonteBloqueada("Simulação de captcha detectado")

    class MockFonteErroPontual:
        def __init__(self, cfg):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def buscar(self, origem, destino, ida, volta):
            raise ErroFonte("Timeout de requisição")

    patches_registro = {
        "fonte_ok": MockFonteOk,
        "fonte_vazia": MockFonteVazia,
        "fonte_bloq": MockFonteBloqueada,
        "fonte_erro": MockFonteErroPontual,
    }

    with patch.dict("busca_voos.scheduler.REGISTRO", patches_registro, clear=False):
        resumo_teste = ciclo(
            cfg_tmp,
            enviar_email=False,
            fontes=["fonte_ok", "fonte_vazia", "fonte_bloq", "fonte_erro", "fonte_inexistente"],
        )

        checar("resumo contém 'detalhes_fontes'", "detalhes_fontes" in resumo_teste)
        checar("resumo contém 'diagnostico'", "diagnostico" in resumo_teste)
        checar("resumo contém 'alertas_count'", "alertas_count" in resumo_teste)
        det = resumo_teste["detalhes_fontes"]

        # Cenário: fonte com ofertas
        checar("fonte_ok tem status 'ok'", det.get("fonte_ok", {}).get("status") == "ok", det.get("fonte_ok"))
        checar("fonte_ok ofertas > 0", det.get("fonte_ok", {}).get("ofertas", 0) > 0, det.get("fonte_ok"))
        checar("fonte_ok mensagem amigável", "sucesso" in det.get("fonte_ok", {}).get("mensagem", "").lower(), det.get("fonte_ok"))

        # Cenário: fonte sem ofertas (0 ofertas)
        checar("fonte_vazia tem status 'aviso'", det.get("fonte_vazia", {}).get("status") == "aviso", det.get("fonte_vazia"))
        checar("fonte_vazia ofertas == 0", det.get("fonte_vazia", {}).get("ofertas") == 0, det.get("fonte_vazia"))
        checar("fonte_vazia mensagem amigável para 0 ofertas", "nenhuma oferta" in det.get("fonte_vazia", {}).get("mensagem", "").lower(), det.get("fonte_vazia"))

        # Cenário: fonte bloqueada
        checar("fonte_bloq tem status 'erro'", det.get("fonte_bloq", {}).get("status") == "erro", det.get("fonte_bloq"))
        checar("fonte_bloq mensagem amigável de bloqueio", "bloqueado" in det.get("fonte_bloq", {}).get("mensagem", "").lower(), det.get("fonte_bloq"))

        # Cenário: fonte com erro pontual
        checar("fonte_erro tem status 'erro' ou 'aviso'", det.get("fonte_erro", {}).get("status") in ("erro", "aviso"), det.get("fonte_erro"))

        # Cenário: fonte pendente (não implementada)
        checar("fonte_inexistente tem status 'erro'", det.get("fonte_inexistente", {}).get("status") == "erro", det.get("fonte_inexistente"))
        checar("fonte_inexistente mensagem amigável", "não implementada" in det.get("fonte_inexistente", {}).get("mensagem", "").lower(), det.get("fonte_inexistente"))

        # Verificação do campo diagnostico
        diag = resumo_teste["diagnostico"]
        checar("diagnostico possui 'detalhes_fontes'", "detalhes_fontes" in diag)
        checar("diagnostico possui 'fontes_ok'", "fontes_ok" in diag)
        checar("diagnostico possui 'fontes_erro'", "fontes_erro" in diag)
        checar("diagnostico possui 'consultas'", "consultas" in diag)
        checar("diagnostico possui 'alertas_count'", "alertas_count" in diag)

        # Verificação crucial: serializabilidade JSON pura
        try:
            resumo_json = json.dumps(resumo_teste)
            checar("resumo completo é serializável em JSON sem erros", len(resumo_json) > 0)
        except Exception as e:
            checar("resumo completo é serializável em JSON", False, str(e))


# =====================================================================
# 4. TESTES DOS ENDPOINTS DO FASTAPI (web.py)
# =====================================================================
print("\n== 4. Testes dos endpoints web (/api/aeroportos e /api/ciclo/status) ==")

with tempfile.TemporaryDirectory() as tmpdir:
    db_path = Path(tmpdir) / "dados.sqlite3"
    cfg_path = Path(tmpdir) / "config.yaml"
    shutil.copyfile(RAIZ / "config.yaml", cfg_path)

    app = criar_app(db_path, caminho_config=cfg_path)
    client = TestClient(app, base_url="http://127.0.0.1:8787")

    # 4.1 GET /api/aeroportos (default)
    r_aero_default = client.get("/api/aeroportos")
    checar("GET /api/aeroportos responde 200", r_aero_default.status_code == 200, r_aero_default.status_code)
    dados_aero = r_aero_default.json()
    checar("GET /api/aeroportos tem chave 'aeroportos'", "aeroportos" in dados_aero)
    checar("GET /api/aeroportos default retorna 15 aeroportos", len(dados_aero["aeroportos"]) == 15, len(dados_aero["aeroportos"]))

    # 4.2 GET /api/aeroportos com parâmetro q e limite
    r_aero_q = client.get("/api/aeroportos?q=rio&limite=5")
    checar("GET /api/aeroportos?q=rio&limite=5 responde 200", r_aero_q.status_code == 200)
    lista_rio = r_aero_q.json()["aeroportos"]
    checar("Retornou 5 itens para q=rio e limite=5", len(lista_rio) == 5, len(lista_rio))
    checar("Primeiro item é RIO", lista_rio[0]["codigo"] == "RIO", lista_rio[0])

    r_aero_accent = client.get("/api/aeroportos?q=Florianópolis")
    checar("GET /api/aeroportos com acento responde 200", r_aero_accent.status_code == 200)
    checar("Primeiro item é FLN", r_aero_accent.json()["aeroportos"][0]["codigo"] == "FLN")

    # 4.3 GET /api/ciclo/status (diagnostico presente inicialmente)
    r_st = client.get("/api/ciclo/status")
    checar("GET /api/ciclo/status responde 200", r_st.status_code == 200)
    st = r_st.json()
    checar("status inicial contém campo 'diagnostico'", "diagnostico" in st, st)
    diag_st = st.get("diagnostico") or {}
    checar("diagnostico contém 'detalhes_fontes'", "detalhes_fontes" in diag_st)
    checar("diagnostico contém 'fontes_ok'", "fontes_ok" in diag_st)
    checar("diagnostico contém 'fontes_erro'", "fontes_erro" in diag_st)
    checar("diagnostico contém 'consultas'", "consultas" in diag_st)
    checar("diagnostico contém 'alertas_count'", "alertas_count" in diag_st)

    # 4.4 POST /api/ciclo atualiza diagnostico ao concluir
    mock_resumo_ciclo = {
        "ciclo": 42,
        "consultas": 12,
        "fontes_ok": ["google_flights", "skiplagged"],
        "fontes_erro": {},
        "detalhes_fontes": {
            "google_flights": {"status": "ok", "ofertas": 8, "consultas": 6, "mensagem": "8 ofertas coletadas"},
            "skiplagged": {"status": "ok", "ofertas": 5, "consultas": 6, "mensagem": "5 ofertas coletadas"},
        },
        "alertas": [],
        "alertas_count": 0,
        "diagnostico": {
            "detalhes_fontes": {
                "google_flights": {"status": "ok", "ofertas": 8, "consultas": 6, "mensagem": "8 ofertas coletadas"},
                "skiplagged": {"status": "ok", "ofertas": 5, "consultas": 6, "mensagem": "5 ofertas coletadas"},
            },
            "fontes_ok": ["google_flights", "skiplagged"],
            "fontes_erro": {},
            "consultas": 12,
            "alertas_count": 0,
        },
    }

    import time
    with patch("busca_voos.scheduler.ciclo", return_value=mock_resumo_ciclo):
        r_post_ciclo = client.post("/api/ciclo")
        checar("POST /api/ciclo responde 200", r_post_ciclo.status_code == 200)
        time.sleep(0.4)
        st_pos = client.get("/api/ciclo/status").json()
        checar("ciclo terminou: rodando == False", st_pos.get("rodando") is False)
        checar("ultimo_ciclo atualizado para 42", st_pos.get("ultimo_ciclo") == 42)
        checar("diagnostico pós-ciclo atualizado com detalhes_fontes", "google_flights" in st_pos.get("diagnostico", {}).get("detalhes_fontes", {}))
        checar("diagnostico pós-ciclo consultas == 12", st_pos.get("diagnostico", {}).get("consultas") == 12)

print("\n" + "=" * 60)
if falhas:
    print(f"ATENÇÃO: {len(falhas)} FALHA(S) ENCONTRADA(S):")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("TODOS OS TESTES PASSARAM COM 100% DE SUCESSO!")
