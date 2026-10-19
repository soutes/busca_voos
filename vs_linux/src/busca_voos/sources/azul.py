"""Fonte: Azul (site oficial, via Chrome visivel).

Deep link `selecao-voo` do proprio site. A Azul usa Akamai com bloqueio por
reputacao de IP: algumas buscas seguidas bastam para aparecer "Ops! Só um
momento" — nesse caso levantamos FonteBloqueada e o ciclo pula a fonte.

ATENCAO: nao foi possivel validar a extracao ao vivo (IP de desenvolvimento
bloqueado). Extrai o menor "R$" visivel da lista de voos, apos a pagina carregar.
"""
from __future__ import annotations

import logging
from datetime import date

from ..models import Oferta
from .base import ErroFonte, FonteBase, FonteBloqueada
from .companhias import menor_preco_texto, texto_de_bloqueio
from .navegador import abrir_navegador

log = logging.getLogger(__name__)


def _url_busca(origem: str, destino: str, data_ida: date, data_volta: date | None) -> str:
    url = (
        "https://www.voeazul.com.br/br/pt/home/selecao-voo"
        f"?c[0].ds={origem}&c[0].std={data_ida:%m/%d/%Y}&c[0].as={destino}"
    )
    if data_volta:
        url += f"&c[1].ds={destino}&c[1].std={data_volta:%m/%d/%Y}&c[1].as={origem}"
    return url + "&p[0].t=ADT&p[0].c=1&p[0].cp=false&f.dl=3&f.dr=3&cc=BRL"


class AzulFonte(FonteBase):
    nome = "azul"
    requer_navegador = True

    def buscar(
        self, origem: str, destino: str, data_ida: date, data_volta: date | None = None
    ) -> list[Oferta]:
        url = _url_busca(origem, destino, data_ida, data_volta)
        try:
            ctx_mgr = abrir_navegador(self.cfg, chrome_visivel=True)
            contexto = ctx_mgr.__enter__()
        except Exception as e:
            raise ErroFonte(f"Azul precisa do Google Chrome com janela visivel: {e}") from e
        try:
            pagina = contexto.new_page()
            try:
                pagina.goto(url, wait_until="domcontentloaded", timeout=self.cfg.navegador.timeout_ms)
            except Exception as e:
                raise ErroFonte(f"Azul: pagina nao carregou ({e})") from e
            preco = None
            for _ in range(20):  # ate ~30 s pelos precos
                pagina.wait_for_timeout(1500)
                try:
                    texto = pagina.inner_text("body")
                except Exception:
                    continue
                if texto_de_bloqueio(texto):
                    raise FonteBloqueada("anti-bot da Azul bloqueou o IP (Ops! Só um momento)")
                preco = menor_preco_texto(texto)
                if preco:
                    break
        finally:
            ctx_mgr.__exit__(None, None, None)
        if not preco:
            log.info("azul: pagina carregada, mas nenhum preco extraido")
            return []
        return [self._oferta(origem, destino, data_ida, data_volta, preco, url, moeda="BRL", cia="Azul")]
