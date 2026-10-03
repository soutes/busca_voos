"""Playwright compartilhado: navegador chromium com disfarce basico."""
from __future__ import annotations

import logging
from contextlib import contextmanager

from ..config import Config

log = logging.getLogger(__name__)

# Disfarce minimo contra deteccao de automacao (suficiente para v1).
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt', 'en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = window.chrome || {runtime: {}};
"""


@contextmanager
def abrir_navegador(cfg: Config):
    """Context manager que entrega um BrowserContext ja configurado (pt-BR)."""
    from playwright.sync_api import sync_playwright  # import tardio (custo alto)

    proxy = {"server": cfg.navegador.proxy} if cfg.navegador.proxy else None
    with sync_playwright() as p:
        if cfg.navegador.canal:
            navegador = p.chromium.launch(
                channel=cfg.navegador.canal,
                headless=cfg.navegador.headless,
                proxy=proxy,
            )
        else:
            navegador = p.chromium.launch(headless=cfg.navegador.headless, proxy=proxy)
        contexto = navegador.new_context(
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1366, "height": 850},
            user_agent=cfg.navegador.user_agent or None,
        )
        contexto.add_init_script(STEALTH_JS)
        try:
            yield contexto
        finally:
            contexto.close()
            navegador.close()