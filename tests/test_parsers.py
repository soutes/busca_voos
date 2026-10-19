from datetime import date
from pathlib import Path

from busca_voos.config import Config
from busca_voos.sources.google_flights import GoogleFlightsFonte

FIXTURES_DIR = Path(__file__).parent / "fixtures"


CONFIG_PATH = Path(__file__).parent.parent / "config.example.yaml"


def test_google_flights_parser_extrai_ofertas():
    html_sample = (FIXTURES_DIR / "google_flights_sample.html").read_text(encoding="utf-8")
    cfg = Config(caminho=CONFIG_PATH)
    fonte = GoogleFlightsFonte(cfg)

    ofertas = fonte._parsear(
        html=html_sample,
        url="https://google.com/travel/flights",
        origem="GRU",
        destino="FLN",
        data_ida=date(2026, 11, 10),
        data_volta=None,
    )

    assert len(ofertas) == 2
    assert ofertas[0].origem == "GRU"
    assert ofertas[0].destino == "FLN"
    assert ofertas[0].preco == 480.0
    assert ofertas[0].cia == "LATAM"
    assert ofertas[1].preco == 520.0
    assert ofertas[1].cia == "GOL"


def test_google_flights_parser_retorna_vazio_quando_html_invalido():
    cfg = Config(caminho=CONFIG_PATH)
    fonte = GoogleFlightsFonte(cfg)

    ofertas = fonte._parsear(
        html="<html><body>Sem resultados</body></html>",
        url="https://google.com/travel/flights",
        origem="GRU",
        destino="FLN",
        data_ida=date(2026, 11, 10),
        data_volta=None,
    )

    assert ofertas == []
