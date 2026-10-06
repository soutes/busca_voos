"""Modelos de dados centrais do busca_voos."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone


@dataclass
class Rota:
    """Uma rota com janela(s) de datas e limite de preco para alerta."""

    origem: str
    destino: str
    datas_ida: list[date]
    datas_volta: list[date] = field(default_factory=list)
    preco_maximo: float = 10_000.0
    fontes: list[str] | None = None  # override por rota (None = usa as globais)
    nome: str = ""

    @property
    def id(self) -> str:
        return f"{self.origem}-{self.destino}"


@dataclass
class Oferta:
    """Um itinerario com preco, coletado de uma fonte."""

    fonte: str
    rota: str
    origem: str
    destino: str
    data_ida: date | None
    data_volta: date | None
    preco: float
    moeda: str
    link: str
    cia: str | None = None
    escalas: str | None = None
    coletado_em: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )