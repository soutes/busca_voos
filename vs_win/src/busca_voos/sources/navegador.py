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
def abrir_navegador(cfg: Config, chrome_visivel: bool = False):
    """Context manager que entrega um BrowserContext ja configurado (pt-BR).

    `chrome_visivel=True` e para os sites das companhias (LATAM/GOL/Azul): o
    anti-bot deles (Akamai) barra Chromium headless e o Chrome "automatizado",
    entao abrimos o Chrome instalado, com janela, sem a flag --enable-automation.
    """
    from playwright.sync_api import sync_playwright  # import tardio (custo alto)

    proxy = {"server": cfg.navegador.proxy} if cfg.navegador.proxy else None
    with sync_playwright() as p:
        args_launch = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        if chrome_visivel:
            navegador = p.chromium.launch(
                channel="chrome",
                headless=False,
                proxy=proxy,
                args=args_launch,
                ignore_default_args=["--enable-automation"],
            )
        elif cfg.navegador.canal:
            navegador = p.chromium.launch(
                channel=cfg.navegador.canal,
                headless=cfg.navegador.headless,
                proxy=proxy,
                args=args_launch,
            )
        else:
            navegador = p.chromium.launch(
                headless=cfg.navegador.headless,
                proxy=proxy,
                args=args_launch,
            )
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