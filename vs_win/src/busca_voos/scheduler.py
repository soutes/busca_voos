"""Orquestracao: um ciclo percorre rotas x fontes, coleta ofertas, grava no
banco e avalia o criterio de alerta (preco <= preco_maximo da rota). O e-mail do
alerta sai no ato do achado, rota por rota, para que um ciclo longo ou
interrompido (varias rotas, fontes lentas) nao deixe de avisar."""
from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone
from typing import Callable

from .combos import expandir, girar
from .config import Config
from .db import Banco
from .emailer import ErroEmail, construir_email_rota, enviar
from .models import Oferta, Rota
from .sources import REGISTRO, ErroFonte, FonteBloqueada

log = logging.getLogger("busca_voos")


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _pausar(segundos: float) -> None:
    """Espera o configurado + ate 50% a mais, sem nunca ficar abaixo do piso.

    Intervalos identicos e regulares sao o padrao tipico de bot; a variacao deixa o
    ritmo menos previsivel sem reduzir a cautela.
    """
    if segundos and segundos > 0:
        time.sleep(segundos * random.uniform(1.0, 1.5))


def _enviar_alerta(cfg: Config, rota: Rota, oferta: Oferta, enviar_email: bool) -> bool:
    """Envia o e-mail de alerta de uma rota assim que a oferta e encontrada.

    Devolve True quando o alerta pode ser registrado: o e-mail saiu, ou o envio
    esta desativado/sem SMTP configurado. Se o envio estiver ligado e falhar,
    devolve False para o alerta nao ser gravado e ser tentado de novo no proximo
    ciclo (a deduplicacao consulta a tabela de alertas).
    """
    assunto, html = construir_email_rota(
        f"{rota.origem}-{rota.destino}", [oferta], rota.preco_maximo
    )
    if not (enviar_email and cfg.email.senha and cfg.email.de and cfg.email.para):
        log.warning(
            "Sem SMTP configurado (SMTP_SENHA/.env) ou envio desativado "
            "(--sem-email). %s",
            assunto,
        )
        return True
    try:
        enviar(cfg, assunto, html)
        return True
    except ErroEmail as e:
        log.error("E-mail nao enviado para rota %s: %s — confira .env/config", rota.id, e)
    except Exception:
        log.exception("Falha ao enviar e-mail da rota %s", rota.id)
    return False


def ciclo(
    cfg: Config,
    enviar_email: bool = True,
    fontes: list[str] | None = None,
    progresso_cb: Callable[[dict], None] | None = None,
) -> dict:
    """Executa um ciclo completo. Retorna resumo para o CLI."""
    banco = Banco(cfg.banco)
    try:
        banco.migrar_rota_ids(cfg.rotas)
    except Exception:
        log.exception("Falha ao migrar ids de rota; seguindo o ciclo")
    banco.salvar_configuracao("ultimo_ciclo_inicio", _agora_iso())
    n_ciclo = banco.proximo_ciclo()
    ativas = fontes if fontes else cfg.fontes_ativas()
    resumo: dict = {
        "ciclo": n_ciclo,
        "fontes_ok": [],
        "fontes_erro": {},
        "detalhes_fontes": {},
        "alertas": [],
        "alertas_count": 0,
        "consultas": 0,
    }
    log.info("Ciclo %d | fontes: %s", n_ciclo, ", ".join(ativas) or "-")
    alertas: list[Oferta] = []
    total_ofertas = 0

    for nome_fonte in ativas:
        classe = REGISTRO.get(nome_fonte)
        if classe is None:
            log.warning(
                "Fonte '%s' registrada mas ainda nao implementada (fase 3) — pulando.",
                nome_fonte,
            )
            resumo["fontes_erro"][nome_fonte] = "pendente (fase 3)"
            resumo["detalhes_fontes"][nome_fonte] = {
                "status": "erro",
                "ofertas": 0,
                "consultas": 0,
                "mensagem": "Fonte registrada, mas ainda não implementada (fase 3)",
            }
            continue
        inicio = time.monotonic()
        ofertas_fonte = 0
        consultas_fonte = 0
        erros_pontuais = 0
        bloqueado = False
        mensagem_bloqueio = ""
        rotas_da_fonte = [
            r for r in cfg.rotas if r.fontes is None or nome_fonte in r.fontes
        ]
        # teto de consultas a esta fonte no ciclo, repartido igualmente entre as rotas
        # (sem isso, as ultimas rotas da lista nunca seriam consultadas)
        teto_fonte = max(1, cfg.agenda.max_consultas_por_fonte)
        por_rota = max(1, teto_fonte // max(1, len(rotas_da_fonte)))
        try:
            with classe(cfg) as fonte:
                for rota in rotas_da_fonte:
                    combos = girar(expandir(rota), n_ciclo)[
                        : min(cfg.agenda.max_combinacoes_por_ciclo, por_rota)
                    ]
                    for data_ida, data_volta in combos:
                        if consultas_fonte >= teto_fonte:
                            log.info("[%s] teto de %d consultas por ciclo atingido.", nome_fonte, teto_fonte)
                            break
                        consultas_fonte += 1
                        resumo["consultas"] += 1
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
                            bloqueado = True
                            mensagem_bloqueio = str(e)
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
                            erros_pontuais += 1
                            resumo["fontes_erro"].setdefault(nome_fonte, "erros pontuais")
                            continue
                        except Exception:
                            log.exception("[%s] erro inesperado na consulta", nome_fonte)
                            erros_pontuais += 1
                            resumo["fontes_erro"].setdefault(nome_fonte, "erros pontuais")
                            continue

                        if ofertas:
                            for _o in ofertas:
                                _o.rota_id = rota.id
                            ofertas_fonte += len(ofertas)
                            banco.salvar_ofertas(ofertas, ciclo=n_ciclo)
                            total_ofertas += len(ofertas)
                            if progresso_cb:
                                progresso_cb(
                                    {
                                        "consultas": resumo["consultas"],
                                        "ofertas": total_ofertas,
                                        "fonte_atual": nome_fonte,
                                        "detalhes_fontes": resumo.get("detalhes_fontes", {}),
                                    }
                                )
                            melhor = min(ofertas, key=lambda o: o.preco)
                            if melhor.preco <= rota.preco_maximo:
                                alertar, motivo = banco.deve_alertar(
                                    melhor.fonte,
                                    rota.id,
                                    melhor.data_ida,
                                    melhor.data_volta,
                                    melhor.preco,
                                    dedupe_horas=cfg.agenda.dedupe_horas,
                                    queda_pct=cfg.agenda.queda_realerta_pct,
                                )
                                if alertar:
                                    log.info(
                                        "ACHEI: %s %s por %s %s (%s) — %s",
                                        melhor.rota,
                                        melhor.data_ida,
                                        melhor.moeda,
                                        melhor.preco,
                                        melhor.fonte,
                                        motivo,
                                    )
                                    # O e-mail sai no ato do achado: se o ciclo
                                    # nao chegar ao fim, o alerta ja gravado na
                                    # tabela impediria o reenvio por dedupe.
                                    if _enviar_alerta(cfg, rota, melhor, enviar_email):
                                        banco.registrar_alerta(
                                            melhor.fonte,
                                            melhor.rota,
                                            melhor.data_ida,
                                            melhor.data_volta,
                                            melhor.preco,
                                            melhor.link,
                                            rota_id=rota.id,
                                        )
                                        alertas.append(melhor)
                                    else:
                                        log.warning(
                                            "Alerta %s nao registrado; sera tentado de novo no proximo ciclo.",
                                            rota.id,
                                        )
                        _pausar(cfg.agenda.pausa_entre_consultas_s)
                    if bloqueado:
                        break

            if bloqueado:
                resumo["detalhes_fontes"][nome_fonte] = {
                    "status": "erro",
                    "ofertas": ofertas_fonte,
                    "consultas": consultas_fonte,
                    "mensagem": f"Acesso bloqueado pela fonte: {mensagem_bloqueio}",
                }
            else:
                resumo["fontes_ok"].append(nome_fonte)
                log.info(
                    "[%s] ok em %.1fs", nome_fonte, time.monotonic() - inicio
                )
                if consultas_fonte == 0:
                    status = "aviso"
                    msg = "Nenhuma consulta realizada para esta fonte"
                elif ofertas_fonte == 0:
                    status = "aviso"
                    if erros_pontuais > 0:
                        msg = f"Nenhuma oferta encontrada ({erros_pontuais} erro(s) pontual(is) nas consultas)"
                    else:
                        msg = "Nenhuma oferta encontrada para os critérios informados"
                else:
                    if erros_pontuais > 0:
                        status = "aviso"
                        msg = f"{ofertas_fonte} oferta(s) coletada(s), com {erros_pontuais} falha(s) pontual(is)"
                    else:
                        status = "ok"
                        msg = f"{ofertas_fonte} oferta(s) coletada(s) com sucesso"

                resumo["detalhes_fontes"][nome_fonte] = {
                    "status": status,
                    "ofertas": ofertas_fonte,
                    "consultas": consultas_fonte,
                    "mensagem": msg,
                }
        except Exception as e:
            log.exception("Falha geral na fonte %s", nome_fonte)
            resumo["fontes_erro"][nome_fonte] = "falha geral"
            resumo["detalhes_fontes"][nome_fonte] = {
                "status": "erro",
                "ofertas": ofertas_fonte,
                "consultas": consultas_fonte,
                "mensagem": f"Falha geral ao conectar na fonte: {e}",
            }
        _pausar(cfg.agenda.pausa_entre_fontes_s)

    resumo["alertas_count"] = len(alertas)
    resumo["alertas"] = [
        {
            "fonte": a.fonte,
            "rota": a.rota,
            "origem": a.origem,
            "destino": a.destino,
            "data_ida": a.data_ida.isoformat() if a.data_ida else None,
            "data_volta": a.data_volta.isoformat() if a.data_volta else None,
            "preco": a.preco,
            "moeda": a.moeda,
            "link": a.link,
            "cia": a.cia,
            "escalas": a.escalas,
            "coletado_em": a.coletado_em.isoformat() if a.coletado_em else None,
        }
        for a in alertas
    ]
    resumo["diagnostico"] = {
        "detalhes_fontes": resumo["detalhes_fontes"],
        "fontes_ok": resumo["fontes_ok"],
        "fontes_erro": resumo["fontes_erro"],
        "consultas": resumo["consultas"],
        "alertas_count": len(alertas),
    }
    banco.salvar_configuracao("ultimo_ciclo_fim", _agora_iso())
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