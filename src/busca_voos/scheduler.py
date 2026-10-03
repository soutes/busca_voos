"""Orquestracao: um ciclo percorre rotas x fontes, coleta ofertas, grava no
banco, avalia o criterio de alerta (preco <= preco_maximo da rota) e envia
um unico e-mail por ciclo com todos os novos alertas."""
from __future__ import annotations

import logging
import time

from .combos import expandir, girar
from .config import Config
from .db import Banco
from .emailer import ErroEmail, construir_email, enviar
from .models import Oferta
from .sources import REGISTRO, ErroFonte, FonteBloqueada

log = logging.getLogger("busca_voos")


def ciclo(cfg: Config, enviar_email: bool = True, fontes: list[str] | None = None) -> dict:
    """Executa um ciclo completo. Retorna resumo para o CLI."""
    banco = Banco(cfg.banco)
    n_ciclo = banco.proximo_ciclo()
    ativas = fontes if fontes else cfg.fontes_ativas()
    resumo: dict = {
        "ciclo": n_ciclo,
        "fontes_ok": [],
        "fontes_erro": {},
        "alertas": [],
        "consultas": 0,
    }
    log.info("Ciclo %d | fontes: %s", n_ciclo, ", ".join(ativas) or "-")
    alertas: list[Oferta] = []

    for nome_fonte in ativas:
        classe = REGISTRO.get(nome_fonte)
        if classe is None:
            log.warning(
                "Fonte '%s' registrada mas ainda nao implementada (fase 3) — pulando.",
                nome_fonte,
            )
            resumo["fontes_erro"][nome_fonte] = "pendente (fase 3)"
            continue
        inicio = time.monotonic()
        try:
            with classe(cfg) as fonte:
                for rota in cfg.rotas:
                    if rota.fontes is not None and nome_fonte not in rota.fontes:
                        continue
                    combos = girar(expandir(rota), n_ciclo)[
                        : cfg.agenda.max_combinacoes_por_ciclo
                    ]
                    for data_ida, data_volta in combos:
                        try:
                            ofertas = fonte.buscar(
                                rota.origem, rota.destino, data_ida, data_volta
                            )
                        except FonteBloqueada as e:
                            log.error(
                                "[%s] bloqueado: %s — pulando o resto desta fonte.",
                                nome_fonte,
                                e,
                            )
                            resumo["fontes_erro"][nome_fonte] = f"bloqueado: {e}"
                            break  # segue para a proxima fonte
                        except ErroFonte as e:
                            log.error(
                                "[%s] %s-%s %s: %s",
                                nome_fonte,
                                rota.origem,
                                rota.destino,
                                data_ida,
                                e,
                            )
                            resumo["fontes_erro"].setdefault(nome_fonte, "erros pontuais")
                            continue
                        except Exception:
                            log.exception("[%s] erro inesperado na consulta", nome_fonte)
                            resumo["fontes_erro"].setdefault(nome_fonte, "erros pontuais")
                            continue

                        resumo["consultas"] += 1
                        if ofertas:
                            banco.salvar_ofertas(ofertas, ciclo=n_ciclo)
                            melhor = min(ofertas, key=lambda o: o.preco)
                            if melhor.preco <= rota.preco_maximo:
                                alertar, motivo = banco.deve_alertar(
                                    melhor.fonte,
                                    melhor.rota,
                                    melhor.data_ida,
                                    melhor.data_volta,
                                    melhor.preco,
                                    dedupe_horas=cfg.agenda.dedupe_horas,
                                    queda_pct=cfg.agenda.queda_realerta_pct,
                                )
                                if alertar:
                                    banco.registrar_alerta(
                                        melhor.fonte,
                                        melhor.rota,
                                        melhor.data_ida,
                                        melhor.data_volta,
                                        melhor.preco,
                                        melhor.link,
                                    )
                                    log.info(
                                        "ACHEI: %s %s por %s %s (%s) — %s",
                                        melhor.rota,
                                        melhor.data_ida,
                                        melhor.moeda,
                                        melhor.preco,
                                        melhor.fonte,
                                        motivo,
                                    )
                                    alertas.append(melhor)
                        if cfg.agenda.pausa_entre_consultas_s:
                            time.sleep(cfg.agenda.pausa_entre_consultas_s)
            resumo["fontes_ok"].append(nome_fonte)
            log.info(
                "[%s] ok em %.1fs", nome_fonte, time.monotonic() - inicio
            )
        except Exception:
            log.exception("Falha geral na fonte %s", nome_fonte)
            resumo["fontes_erro"][nome_fonte] = "falha geral"
        if cfg.agenda.pausa_entre_fontes_s:
            time.sleep(cfg.agenda.pausa_entre_fontes_s)

    if alertas:
        assunto, html = construir_email(alertas)
        if enviar_email and cfg.email.senha and cfg.email.de and cfg.email.para:
            try:
                enviar(cfg, assunto, html)
            except ErroEmail as e:
                log.error("E-mail nao enviado: %s — confira .env/config", e)
            except Exception:
                log.exception("Falha ao enviar e-mail; alertas ficaram gravados no banco")
        else:
            log.warning(
                "Sem SMTP configurado (SMTP_SENHA/.env) ou envio desativado "
                "(--sem-email). %d alerta(s), ex.: %s",
                len(alertas),
                assunto,
            )
    resumo["alertas"] = alertas
    banco.fechar()
    return resumo


def executar(cfg: Config, enviar_email: bool = True, fontes: list[str] | None = None) -> None:
    """Modo daemon: repete o ciclo a cada intervalo_minutos (para systemd)."""
    intervalo_s = max(60, cfg.agenda.intervalo_minutos * 60)
    while True:
        inicio = time.monotonic()
        try:
            ciclo(cfg, enviar_email=enviar_email, fontes=fontes)
        except Exception:
            log.exception("Ciclo falhou; o proximo tenta de novo")
        espera = max(30, intervalo_s - (time.monotonic() - inicio))
        log.info("Proximo ciclo em ~%d min.", round(espera / 60))
        try:
            time.sleep(espera)
        except KeyboardInterrupt:
            log.info("Encerrado.")
            return