"""E-mail HTML com as ofertas encontradas (rota, datas, preco e link)."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from .config import Config
from .models import Oferta

log = logging.getLogger(__name__)

_SIMBOLOS = {"BRL": "R$", "USD": "US$", "EUR": "\u20ac", "GBP": "\u00a3"}


def formatar_preco(oferta: Oferta) -> str:
    """Preco legivel, ex.: 'R$ 2.560' (usado no CLI e no e-mail)."""
    simbolo = _SIMBOLOS.get(oferta.moeda.upper(), oferta.moeda + " ")
    if oferta.preco == int(oferta.preco):
        valor = f"{int(oferta.preco):,}".replace(",", ".")
    else:
        valor = f"{oferta.preco:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{simbolo} {valor}"


_fmt_preco = formatar_preco  # apelido interno usado em construir_email


def _fmt_periodo(oferta: Oferta) -> str:
    ida = oferta.data_ida.strftime("%d/%m/%Y") if oferta.data_ida else "\u2014"
    if oferta.data_volta:
        return f"{ida} \u2192 {oferta.data_volta.strftime('%d/%m/%Y')}"
    return ida


def construir_email(ofertas: list[Oferta]) -> tuple[str, str]:
    """Monta (assunto, html) com uma tabela de alertas ordenada por preco."""
    ofertas = sorted(ofertas, key=lambda o: o.preco)
    melhor = ofertas[0]
    assunto = f"{melhor.rota} por {_fmt_preco(melhor)} ({melhor.fonte})"
    if len(ofertas) > 1:
        assunto += f" +{len(ofertas) - 1} alerta(s)"

    linhas = []
    for o in ofertas:
        cia = f" \u00b7 {escape(o.cia)}" if o.cia else ""
        if o.escalas:
            cia += f" \u00b7 {escape(o.escalas)}"
        linhas.append(
            "<tr>"
            f"<td>{escape(o.rota)}</td>"
            f"<td>{escape(_fmt_periodo(o))}</td>"
            f"<td><b>{escape(_fmt_preco(o))}</b></td>"
            f"<td>{escape(o.fonte)}{cia}</td>"
            f"<td><a href='{escape(o.link, quote=True)}'>abrir oferta</a></td>"
            "</tr>"
        )

    html = (
        "<!doctype html><html lang=\"pt-BR\"><body style=\"font-family:Arial,sans-serif;color:#222\">"
        "<h2 style=\"margin-bottom:4px\">\u2708\ufe0f Passagem(s) encontrada(s)</h2>"
        "<p style=\"color:#555;margin-top:0\">Preco dentro do limite definido no config.yaml</p>"
        "<table cellpadding=\"8\" cellspacing=\"0\" border=\"1\" style=\"border-collapse:collapse;border-color:#ccc\">"
        "<tr style=\"background:#f2f2f2;text-align:left\">"
        "<th>Rota</th><th>Datas (ida \u2192 volta)</th><th>Preco</th><th>Fonte</th><th>Link</th>"
        "</tr>"
        + "".join(linhas)
        + "</table>"
        "<p style=\"color:#888;font-size:12px\">Enviado por busca_voos \u2014 precos mudam"
        " rapido; confira no site antes de comprar.</p>"
        "</body></html>"
    )
    return assunto, html


class ErroEmail(Exception):
    pass


def enviar(cfg: Config, assunto: str, html: str) -> None:
    """Envia via SMTP. Senha vem de SMTP_SENHA (variavel de ambiente/.env)."""
    if not cfg.email.senha:
        raise ErroEmail("SMTP_SENHA ausente no .env")
    if not cfg.email.de or not cfg.email.para:
        raise ErroEmail("email.de / email.para ausentes no config.yaml")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = cfg.email.de
    msg["To"] = ", ".join(cfg.email.para)
    msg.attach(MIMEText(html, "html", "utf-8"))

    if cfg.email.tls:
        servidor = smtplib.SMTP(cfg.email.host, cfg.email.porta, timeout=30)
        servidor.ehlo()
        servidor.starttls(context=ssl.create_default_context())
    else:
        servidor = smtplib.SMTP_SSL(cfg.email.host, cfg.email.porta, timeout=30)
    try:
        servidor.login(cfg.email.de, cfg.email.senha)
        servidor.sendmail(cfg.email.de, cfg.email.para, msg.as_string())
        log.info("E-mail enviado para %s", cfg.email.para)
    finally:
        servidor.quit()