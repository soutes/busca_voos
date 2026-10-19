"""Testes para atualizacao de rotas e envio isolado de alertas por rota."""
from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from busca_voos.config import (
    ErroConfig,
    atualizar_rota_config,
    carregar_config,
    listar_rotas_dict,
)
from busca_voos.emailer import ErroEmail, construir_email_rota, formatar_preco
from busca_voos.models import Oferta
from busca_voos.scheduler import ciclo
from busca_voos.web import criar_app


@pytest.fixture()
def pasta():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        shutil.copyfile(RAIZ / "config.example.yaml", p / "config.yaml")
        yield p


def _criar_oferta(
    rota: str = "FLN-GRU",
    origem: str = "FLN",
    destino: str = "GRU",
    preco: float = 300.0,
    fonte: str = "google_flights",
    data_ida: date = date(2026, 11, 10),
    data_volta: date | None = date(2026, 11, 15),
    link: str = "https://example.com/voo",
) -> Oferta:
    return Oferta(
        fonte=fonte,
        rota=rota,
        origem=origem,
        destino=destino,
        data_ida=data_ida,
        data_volta=data_volta,
        preco=preco,
        moeda="BRL",
        link=link,
        cia="Gol",
        escalas="direto",
    )


def _cfg_ciclo(pasta: Path, destinos: list[str]):
    """Config com as rotas FLN-<destino>, banco/pausas/e-mail prontos para um ciclo."""
    from busca_voos.config import adicionar_rota_config

    modelo = {
        "origem": "FLN",
        "janela_ida": {"de": "2026-11-10", "ate": "2026-11-10"},
        "preco_maximo": 1000.0,
    }
    atualizar_rota_config(pasta / "config.yaml", 0, {**modelo, "destino": destinos[0]})
    for destino in destinos[1:]:
        adicionar_rota_config(pasta / "config.yaml", {**modelo, "destino": destino})

    cfg = carregar_config(pasta / "config.yaml")
    cfg.banco = pasta / "dados.sqlite3"
    cfg.agenda.pausa_entre_consultas_s = 0
    cfg.agenda.pausa_entre_fontes_s = 0
    cfg.email.senha = "segredo-mock"
    cfg.email.de = "bot@example.com"
    cfg.email.para = ["dest@example.com"]
    return cfg


def test_atualizar_rota_config_sucesso(pasta: Path):
    cfg_path = pasta / "config.yaml"
    rotas_iniciais = listar_rotas_dict(cfg_path)
    assert len(rotas_iniciais) >= 1

    dados_atualizados = {
        "origem": "FLN",
        "destino": "BSB",
        "janela_ida": {"de": "2026-11-10", "ate": "2026-11-15"},
        "janela_volta": {"de": "2026-11-20", "ate": "2026-11-25"},
        "preco_maximo": 650.0,
        "nome": "Rota BSB Atualizada",
        "fontes": ["google_flights", "latam"],
    }

    rotas_apos = atualizar_rota_config(cfg_path, 0, dados_atualizados)
    r0 = rotas_apos[0]
    assert r0["origem"] == "FLN"
    assert r0["destino"] == "BSB"
    assert r0["id"] == "FLN-BSB"
    assert r0["preco_maximo"] == 650.0
    assert r0["nome"] == "Rota BSB Atualizada"
    assert r0["fontes"] == ["google_flights", "latam"]
    assert r0["janela_ida"] == {"de": "2026-11-10", "ate": "2026-11-15"}
    assert r0["janela_volta"] == {"de": "2026-11-20", "ate": "2026-11-25"}

    # Recarrega a configuracao e valida compatibilidade total
    cfg = carregar_config(cfg_path)
    assert cfg.rotas[0].origem == "FLN"
    assert cfg.rotas[0].destino == "BSB"
    assert cfg.rotas[0].preco_maximo == 650.0


def test_atualizar_rota_config_apenas_ida(pasta: Path):
    cfg_path = pasta / "config.yaml"
    dados_apenas_ida = {
        "origem": "SDU",
        "destino": "CGH",
        "janela_ida": {"de": "2026-12-01", "ate": "2026-12-05"},
        "preco_maximo": 400.0,
    }
    rotas = atualizar_rota_config(cfg_path, 0, dados_apenas_ida)
    assert rotas[0]["janela_volta"] is None
    cfg = carregar_config(cfg_path)
    assert cfg.rotas[0].datas_volta == []


def test_atualizar_rota_config_validacoes(pasta: Path):
    cfg_path = pasta / "config.yaml"

    # Indice invalido
    with pytest.raises(IndexError):
        atualizar_rota_config(cfg_path, 999, {"origem": "FLN", "destino": "GRU", "preco_maximo": 100})
    with pytest.raises(IndexError):
        atualizar_rota_config(cfg_path, -1, {"origem": "FLN", "destino": "GRU", "preco_maximo": 100})

    # Origem igual ao destino
    with pytest.raises(ErroConfig):
        atualizar_rota_config(cfg_path, 0, {
            "origem": "GRU",
            "destino": "GRU",
            "janela_ida": {"de": "2026-11-10", "ate": "2026-11-15"},
            "preco_maximo": 500,
        })

    # Preco invalido ou <= 0
    with pytest.raises(ErroConfig):
        atualizar_rota_config(cfg_path, 0, {
            "origem": "FLN",
            "destino": "GRU",
            "janela_ida": {"de": "2026-11-10", "ate": "2026-11-15"},
            "preco_maximo": 0,
        })
    with pytest.raises(ErroConfig):
        atualizar_rota_config(cfg_path, 0, {
            "origem": "FLN",
            "destino": "GRU",
            "janela_ida": {"de": "2026-11-10", "ate": "2026-11-15"},
            "preco_maximo": -100,
        })

    # Janela ida invertida
    with pytest.raises(ErroConfig):
        atualizar_rota_config(cfg_path, 0, {
            "origem": "FLN",
            "destino": "GRU",
            "janela_ida": {"de": "2026-11-20", "ate": "2026-11-10"},
            "preco_maximo": 500,
        })

    # Janela volta anterior a ida
    with pytest.raises(ErroConfig):
        atualizar_rota_config(cfg_path, 0, {
            "origem": "FLN",
            "destino": "GRU",
            "janela_ida": {"de": "2026-11-20", "ate": "2026-11-25"},
            "janela_volta": {"de": "2026-11-10", "ate": "2026-11-15"},
            "preco_maximo": 500,
        })


def test_api_put_rota_endpoint(pasta: Path):
    from busca_voos.db import Banco
    Banco(pasta / "dados.sqlite3").fechar()

    app = criar_app(banco=pasta / "dados.sqlite3", caminho_config=pasta / "config.yaml")
    client = TestClient(app, base_url="http://127.0.0.1:8787")

    # 1. Sucesso na atualizacao
    payload = {
        "origem": "FLN",
        "destino": "GIG",
        "janela_ida": {"de": "2026-12-10", "ate": "2026-12-12"},
        "janela_volta": {"de": "2026-12-18", "ate": "2026-12-20"},
        "preco_maximo": 490.0,
        "nome": "Rio Fim de Ano",
    }
    resp = client.put("/api/rotas/0", json=payload)
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["ok"] is True
    assert dados["rotas"][0]["origem"] == "FLN"
    assert dados["rotas"][0]["destino"] == "GIG"
    assert dados["rotas"][0]["preco_maximo"] == 490.0

    # Verifica se os limites em /api/filtros foram atualizados
    resp_filtros = client.get("/api/filtros")
    assert resp_filtros.status_code == 200
    assert resp_filtros.json()["limites"]["FLN-GIG"] == 490.0
    assert "FLN-RIO" not in resp_filtros.json()["limites"]

    # 2. Indice inexistente retorna 400
    resp_invalido = client.put("/api/rotas/999", json=payload)
    assert resp_invalido.status_code == 400

    # 3. Validacao incorreta (ex.: origem igual a destino) retorna 400
    payload_invalido = dict(payload)
    payload_invalido["destino"] = "FLN"
    resp_err = client.put("/api/rotas/0", json=payload_invalido)
    assert resp_err.status_code == 400

    # 4. Adiciona uma segunda rota para permitir a exclusao sem violar o minimo de 1 rota
    resp_add = client.post(
        "/api/rotas",
        json={
            "origem": "GRU",
            "destino": "MIA",
            "ida_de": "2027-01-10",
            "preco_maximo": 2500.0,
        },
    )
    assert resp_add.status_code == 200

    # 5. Exclusao de rota limpa o limite correspondente
    resp_del = client.delete("/api/rotas/0")
    assert resp_del.status_code == 200
    resp_filtros_pos_del = client.get("/api/filtros")
    assert "FLN-GIG" not in resp_filtros_pos_del.json()["limites"]
    assert resp_filtros_pos_del.json()["limites"]["GRU-MIA"] == 2500.0


def test_construir_email_rota_oferta_unica():
    o1 = _criar_oferta(rota="FLN-GRU", preco=280.0, fonte="google_flights")
    assunto, html = construir_email_rota("FLN-GRU", [o1], preco_maximo=500.0)

    assert assunto == f"busca_voos - FLN-GRU por {formatar_preco(o1)} (google_flights)"
    assert "+1 alerta(s)" not in assunto
    assert "FLN-GRU" in html
    assert formatar_preco(o1) in html
    assert "google_flights" in html
    assert o1.link in html
    assert "Passagem(s) encontrada(s) - FLN-GRU" in html


def test_construir_email_rota_multiplas_ofertas():
    o1 = _criar_oferta(rota="FLN-GRU", preco=450.0, fonte="latam")
    o2 = _criar_oferta(rota="FLN-GRU", preco=250.0, fonte="google_flights")
    assunto, html = construir_email_rota("FLN-GRU", [o1, o2], preco_maximo=500.0)

    # Ordenado por preco: o2 (250) deve ser o melhor
    assert assunto == f"busca_voos - FLN-GRU por {formatar_preco(o2)} (google_flights) +1 alerta(s)"
    assert "latam" in html
    assert "google_flights" in html


def test_construir_email_rota_vazia():
    with pytest.raises(ValueError):
        construir_email_rota("FLN-GRU", [])


def test_scheduler_disparo_alertas_isolado_por_rota(pasta: Path):
    cfg = carregar_config(pasta / "config.yaml")
    cfg.banco = pasta / "dados.sqlite3"
    cfg.agenda.pausa_entre_consultas_s = 0
    cfg.agenda.pausa_entre_fontes_s = 0
    cfg.email.senha = "segredo-mock"
    cfg.email.de = "bot@example.com"
    cfg.email.para = ["dest@example.com"]

    # Duas rotas com limites que serao atingidos
    o_rota1 = _criar_oferta(rota="FLN-GRU", origem="FLN", destino="GRU", preco=200.0, fonte="fonte_teste")
    o_rota2 = _criar_oferta(rota="FLN-GIG", origem="FLN", destino="GIG", preco=250.0, fonte="fonte_teste")

    class MockFonte:
        def __init__(self, _cfg):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def buscar(self, origem, destino, data_ida, data_volta=None):
            if origem == "FLN" and destino == "GRU":
                return [o_rota1]
            if origem == "FLN" and destino == "GIG":
                return [o_rota2]
            return []

    # Ajusta as rotas da config para FLN-GRU e FLN-GIG com precos maximos altos
    atualizar_rota_config(pasta / "config.yaml", 0, {
        "origem": "FLN",
        "destino": "GRU",
        "janela_ida": {"de": "2026-11-10", "ate": "2026-11-10"},
        "preco_maximo": 1000.0,
    })
    # Se so tiver uma rota, adicionamos a segunda rota
    from busca_voos.config import adicionar_rota_config
    adicionar_rota_config(pasta / "config.yaml", {
        "origem": "FLN",
        "destino": "GIG",
        "janela_ida": {"de": "2026-11-10", "ate": "2026-11-10"},
        "preco_maximo": 1000.0,
    })

    cfg_recarregada = carregar_config(pasta / "config.yaml")
    cfg_recarregada.banco = pasta / "dados.sqlite3"
    cfg_recarregada.agenda.pausa_entre_consultas_s = 0
    cfg_recarregada.agenda.pausa_entre_fontes_s = 0
    cfg_recarregada.email.senha = "segredo-mock"
    cfg_recarregada.email.de = "bot@example.com"
    cfg_recarregada.email.para = ["dest@example.com"]

    with patch("busca_voos.scheduler.REGISTRO", {"fonte_teste": MockFonte}):
        with patch("busca_voos.scheduler.enviar") as mock_enviar:
            resumo = ciclo(cfg_recarregada, enviar_email=True, fontes=["fonte_teste"])

            # Deve haver dois disparos de email separados, um para cada rota
            assert mock_enviar.call_count == 2
            chamada1_assunto = mock_enviar.call_args_list[0][0][1]
            chamada2_assunto = mock_enviar.call_args_list[1][0][1]

            assuntos = {chamada1_assunto, chamada2_assunto}
            assert any("FLN-GRU" in a for a in assuntos)
            assert any("FLN-GIG" in a for a in assuntos)

            # Resumo consolidado mantem total
            assert resumo["alertas_count"] == 2
            assert len(resumo["alertas"]) == 2


def test_email_sai_no_ato_do_achado_e_nao_no_fim_do_ciclo(pasta: Path):
    """Regressao: com varias rotas, o alerta precisa sair assim que a passagem e
    achada. Antes o envio ficava para o fim do ciclo; um ciclo longo ou
    interrompido nunca chegava la e o e-mail nao saia (o alerta ja estava gravado,
    e o dedupe bloqueava o reenvio)."""
    cfg = _cfg_ciclo(pasta, ["GRU", "GIG"])
    o_rota1 = _criar_oferta(rota="FLN-GRU", origem="FLN", destino="GRU", preco=200.0, fonte="fonte_teste")
    o_rota2 = _criar_oferta(rota="FLN-GIG", origem="FLN", destino="GIG", preco=250.0, fonte="fonte_teste")
    envios_ao_chegar_na_2a_rota: list[int] = []

    with patch("busca_voos.scheduler.enviar") as mock_enviar:
        class MockFonte:
            def __init__(self, _cfg):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

            def buscar(self, origem, destino, data_ida, data_volta=None):
                if destino == "GRU":
                    return [o_rota1]
                # ao chegar na 2a rota, o e-mail da 1a ja deveria ter saido
                envios_ao_chegar_na_2a_rota.append(mock_enviar.call_count)
                return [o_rota2]

        with patch("busca_voos.scheduler.REGISTRO", {"fonte_teste": MockFonte}):
            ciclo(cfg, enviar_email=True, fontes=["fonte_teste"])

    assert envios_ao_chegar_na_2a_rota == [1], "o e-mail da 1a rota deveria sair antes da 2a busca"
    assert mock_enviar.call_count == 2


def test_email_falho_nao_registra_alerta_para_retentar(pasta: Path):
    """Se o envio falha, o alerta nao e gravado no banco: o proximo ciclo tenta de novo."""
    cfg = _cfg_ciclo(pasta, ["GRU"])
    oferta = _criar_oferta(rota="FLN-GRU", origem="FLN", destino="GRU", preco=200.0, fonte="fonte_teste")

    class MockFonte:
        def __init__(self, _cfg):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def buscar(self, origem, destino, data_ida, data_volta=None):
            return [oferta]

    with patch("busca_voos.scheduler.REGISTRO", {"fonte_teste": MockFonte}):
        with patch("busca_voos.scheduler.enviar", side_effect=ErroEmail("smtp fora do ar")) as mock_enviar:
            resumo = ciclo(cfg, enviar_email=True, fontes=["fonte_teste"])

    assert mock_enviar.call_count == 1
    assert resumo["alertas_count"] == 0

    from busca_voos.db import Banco
    b = Banco(pasta / "dados.sqlite3")
    try:
        gravados = b.con.execute("SELECT COUNT(*) FROM alertas").fetchone()[0]
    finally:
        b.fechar()
    assert gravados == 0
