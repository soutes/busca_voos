"""Fontes das companhias (LATAM/GOL/Azul): parsing e URLs, sem rede."""
from datetime import date

from busca_voos.sources import REGISTRO
from busca_voos.sources import azul, gol, latam
from busca_voos.sources.companhias import menor_preco_json, menor_preco_texto, texto_de_bloqueio

CAL = {
    "days": [
        {
            "calendar": [
                {
                    "month": "2026-12",
                    "direction": "OUTBOUND",
                    "detailsCalendar": [
                        {"date": "2026-12-10", "fare": {"amount": 400.5}, "enabled": True},
                        {"date": "2026-12-11", "fare": {"amount": 300}, "enabled": False},
                    ],
                },
                {
                    "month": "2026-12",
                    "direction": "INBOUND",
                    "detailsCalendar": [{"date": "2026-12-17", "fare": {"amount": 317}, "enabled": True}],
                },
            ]
        }
    ]
}


def test_registro_tem_as_tres_companhias():
    for nome in ("latam", "gol", "azul"):
        assert REGISTRO[nome] is not None


def test_latam_preco_do_dia():
    assert latam.preco_do_dia(CAL, date(2026, 12, 10), "OUTBOUND") == 400.5
    assert latam.preco_do_dia(CAL, date(2026, 12, 17), "INBOUND") == 317.0
    assert latam.preco_do_dia(CAL, date(2026, 12, 11), "OUTBOUND") is None  # desabilitado
    assert latam.preco_do_dia(CAL, date(2026, 12, 10), "INBOUND") is None
    assert latam.preco_do_dia({}, date(2026, 12, 10), "OUTBOUND") is None


def test_urls():
    assert "trip=RT" in latam._url_busca("GRU", "GIG", date(2026, 12, 10), date(2026, 12, 17))
    u = gol._url_busca("GRU", "GIG", date(2026, 12, 10), date(2026, 12, 17))
    assert "ida=10-12-2026" in u and "volta=17-12-2026" in u
    u = azul._url_busca("GRU", "GIG", date(2026, 12, 10), None)
    assert "c[0].std=12/10/2026" in u and "c[1]" not in u


def test_menor_preco_json_e_texto():
    assert menor_preco_json({"a": [{"price": 900}, {"fare": {"totalAmount": {"amount": 450.9}}}, {"total": 5}]}) == 450.9
    assert menor_preco_json({"x": 1}) is None
    assert menor_preco_texto("A partir de R$ 1.234,50 ou R$ 399 e R$ 10") == 399.0


def test_texto_de_bloqueio():
    assert texto_de_bloqueio("Ops! Só um momento. Identificamos um comportamento incomum")
    assert not texto_de_bloqueio("Escolha seu voo de ida")
