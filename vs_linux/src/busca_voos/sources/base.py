"""Contrato das fontes de busca (Google Flights, Skyscanner, etc.)."""
from __future__ import annotations

from datetime import date

from ..config import Config
from ..models import Oferta


class ErroFonte(Exception):
    """Falha generica e recuperavel de uma fonte."""


class FonteBloqueada(ErroFonte):
    """A fonte bloqueou o acesso (captcha/anti-bot) — provavelmente persistente."""


class FontePendente(ErroFonte):
    """Fonte registrada, mas ainda sem implementacao (fase 3)."""


class FonteBase:
    """Toda fonte implementa `buscar()` e pode exigir navegador."""

    nome = "base"
    requer_navegador = False

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def buscar(
        self,
        origem: str,
        destino: str,
        data_ida: date,
        data_volta: date | None = None,
    ) -> list[Oferta]:
        """Faz a busca e devolve ofertas (pode voltar lista vazia)."""
        raise NotImplementedError

    def _oferta(
        self,
        origem: str,
        destino: str,
        data_ida: date | None,
        data_volta: date | None,
        preco: float,
        link: str,
        moeda: str | None = None,
        cia: str | None = None,
        escalas: str | None = None,
    ) -> Oferta:
        return Oferta(
            fonte=self.nome,
            rota=f"{origem}-{destino}",
            origem=origem,
            destino=destino,
            data_ida=data_ida,
            data_volta=data_volta,
            preco=preco,
            moeda=moeda or self.cfg.moeda,
            link=link,
            cia=cia,
            escalas=escalas,
        )

    def __enter__(self) -> "FonteBase":
        return self

    def __exit__(self, *exc) -> bool:
        return False