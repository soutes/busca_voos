"""Fonte: GOL (site oficial, via Chrome visivel).

O deep link `busca-parceiros` abre a selecao de voos e a propria pagina chama
`POST bff-flight.voegol.com.br/flights/search` (token anonimo + sensor anti-bot
em JS, por isso nao da para chamar a API por HTTP puro). Capturamos essa resposta.

ATENCAO: o formato da resposta de sucesso ainda nao foi validado ao vivo (o IP de
desenvolvimento tomou 406 do anti-bot); a extracao usa `menor_preco_json`.
"""
from __future__ import annotations

import json
import logging
from datetime import date

from ..models import Oferta
from .base import ErroFonte, FonteBase, FonteBloqueada
from .companhias import menor_preco_json, menor_preco_texto, texto_de_bloqueio
from .navegador import abrir_navegador

log = logging.getLogger(__name__)


def _url_busca(origem: str, destino: str, data_ida: date, data_volta: date | None) -> str:
    url = (
        "https://b2c.voegol.com.br/compra/busca-parceiros?pv=br&tipo=DF"
        f"&de={origem}&para={destino}&ida={data_ida:%d-%m-%Y}"
    )
    if data_volta:
        url += f"&volta={data_volta:%d-%m-%Y}"
    return url + "&ADT=1&CHD=0&INF=0"


class GolFonte(FonteBase):
    nome = "gol"
    requer_navegador = True

    def buscar(
        self, origem: str, destino: str, data_ida: date, data_volta: date | None = None
    ) -> list[Oferta]:
        url = _url_busca(origem, destino, data_ida, data_volta)
        respostas: list[tuple[int, str]] = []
        try:
            ctx_mgr = abrir_navegador(self.cfg, chrome_visivel=True)
            contexto = ctx_mgr.__enter__()
        except Exception as e:
            raise ErroFonte(f"GOL precisa do Google Chrome com janela visivel: {e}") from e
        try:
            pagina = contexto.new_page()

            def ao_responder(r) -> None:
                if "bff-flight.voegol.com.br/flights/search" in r.url:
                    try:
                        respostas.append((r.status, r.text()))
                    except Exception:
                        respostas.append((r.status, ""))

            pagina.on("response", ao_responder)
            try:
                pagina.goto(url, wait_until="domcontentloaded", timeout=self.cfg.navegador.timeout_ms)
            except Exception as e:
                raise ErroFonte(f"GOL: pagina nao carregou ({e})") from e
            for _ in range(20):  # ate ~30 s pela resposta da busca
                pagina.wait_for_timeout(1500)
                if respostas:
                    break
            pagina.wait_for_timeout(1500)
            texto = ""
            try:
                texto = pagina.inner_text("body")
            except Exception:
                pass
        finally:
            ctx_mgr.__exit__(None, None, None)

        if not respostas:
            if texto_de_bloqueio(texto):
                raise FonteBloqueada("anti-bot da GOL exibiu desafio")
            log.info("gol: a pagina nao chamou a API de busca")
            return []
        if any(st in (403, 406, 429) for st, _ in respostas):
            raise FonteBloqueada("anti-bot da GOL recusou a busca (HTTP 406/403)")

        precos = []
        for st, corpo in respostas:
            if st != 200:
                continue
            try:
                p = menor_preco_json(json.loads(corpo))
            except ValueError:
                p = None
            if p:
                precos.append(p)
        if not precos:
            p = menor_preco_texto(texto)
            if p:
                precos.append(p)
        if not precos:
            log.info("gol: busca respondeu, mas nenhum preco foi extraido")
            return []
        # ida+volta: soma o menor preco de cada trecho; ida simples: so um
        total = sum(precos) if (data_volta and len(precos) > 1) else precos[0]
        return [
            self._oferta(origem, destino, data_ida, data_volta, round(total, 2), url, moeda="BRL", cia="GOL")
        ]
