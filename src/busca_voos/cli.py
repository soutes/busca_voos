"""CLI do busca_voos.

Comandos:
  init         primeiro uso: cria config.yaml/.env dos exemplos e o banco
  uma          executa um ciclo e sai (bom para cron/teste)
  run          roda em loop — para systemd/daemon
  testar       teste rapido de UMA fonte (sem banco, sem e-mail)
  email-teste  envia um e-mail de verificacao do SMTP
  painel       sobe o painel web local (somente leitura) do historico

As tabelas do SQLite nascem sozinhas no primeiro ciclo (init/uma/run): o schema
usa CREATE TABLE IF NOT EXISTS, entao rodar de novo nunca apaga nada.
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sqlite3
from datetime import date
from pathlib import Path

from .config import ErroConfig, carregar_config
from .db import Banco
from .emailer import ErroEmail, formatar_preco, enviar
from .logging_setup import configurar_logs
from .scheduler import ciclo, executar
from .sources import REGISTRO, ErroFonte, FonteBloqueada

log = logging.getLogger("busca_voos")


def _fontes_do(args) -> list[str] | None:
    if getattr(args, "fontes", None):
        return [f.strip().lower() for f in args.fontes.split(",") if f.strip()]
    return None


def cmd_uma(args) -> int:
    cfg = carregar_config(args.config)
    resumo = ciclo(cfg, enviar_email=not args.sem_email, fontes=_fontes_do(args))
    log.info(
        "Ciclo %d concluido | consultas=%d | alertas=%d | ok=%s | erros=%s",
        resumo["ciclo"],
        resumo["consultas"],
        len(resumo["alertas"]),
        resumo["fontes_ok"] or "-",
        resumo["fontes_erro"] or "-",
    )
    return 0


def cmd_run(args) -> int:
    cfg = carregar_config(args.config)
    log.info(
        "Modo daemon — ciclo a cada %d min. Ctrl+C para sair.",
        cfg.agenda.intervalo_minutos,
    )
    executar(cfg, enviar_email=not args.sem_email, fontes=_fontes_do(args))
    return 0


def cmd_testar(args) -> int:
    cfg = carregar_config(args.config)
    nome = args.fonte.strip().lower()
    classe = REGISTRO.get(nome)
    if classe is None:
        if nome in REGISTRO:
            log.error("Fonte '%s' planejada para a fase 3 (ainda nao implementada).", nome)
        else:
            log.error(
                "Fonte '%s' desconhecida. Disponiveis: %s",
                nome,
                ", ".join(sorted(REGISTRO)),
            )
        return 2
    data_ida = date.fromisoformat(args.ida)
    data_volta = date.fromisoformat(args.volta) if args.volta else None
    log.info(
        "Testando %s: %s -> %s (%s%s)...",
        nome,
        args.origem.upper(),
        args.destino.upper(),
        data_ida,
        f" volta {data_volta}" if data_volta else "",
    )
    with classe(cfg) as fonte:
        try:
            ofertas = fonte.buscar(
                args.origem.strip().upper(), args.destino.strip().upper(), data_ida, data_volta
            )
        except FonteBloqueada as e:
            log.error("%s bloqueou o acesso: %s", nome, e)
            return 5
        except ErroFonte as e:
            log.error("%s falhou: %s", nome, e)
            return 6
        except Exception as e:  # noqa: BLE001 - queremos mensagem limpa, nao traceback
            if args.debug:
                log.exception("%s falhou de forma inesperada", nome)
            else:
                log.error(
                    "%s falhou de forma inesperada: %s: %s (rode com --debug para o traceback)",
                    nome,
                    type(e).__name__,
                    e,
                )
            return 7
    if not ofertas:
        log.info("Nenhuma oferta extraida. Rode com --debug para detalhes.")
        return 0
    ofertas = sorted(ofertas, key=lambda o: o.preco)
    log.info("%d oferta(s):", len(ofertas))
    for o in ofertas[: args.top]:
        extra = " · ".join(x for x in (o.cia, o.escalas) if x)
        log.info(
            "  %s  %s %s%s",
            formatar_preco(o),
            o.rota,
            extra and f"| {extra} " or "",
            o.link,
        )
    return 0


def cmd_email_teste(args) -> int:
    cfg = carregar_config(args.config)
    enviar(cfg, "busca_voos: teste de e-mail", "<p>Se voce recebeu isso, o SMTP esta OK.</p>")
    log.info("E-mail de teste enviado para %s", cfg.email.para)
    return 0


def _exemplo(nome: str) -> Path | None:
    """Acha um arquivo de exemplo no cwd ou na raiz do projeto."""
    raiz = Path(__file__).resolve().parents[2]
    for candidato in (Path(nome), raiz / nome):
        if candidato.exists():
            return candidato
    return None


def cmd_init(args) -> int:
    """Primeiro uso: cria config.yaml, .env e o schema do banco.

    Nao sobrescreve nada que ja exista: rodar de novo e seguro.
    """
    destino = Path(args.config)

    if destino.exists():
        log.info("config: '%s' ja existe — mantido.", destino)
    else:
        origem = _exemplo("config.example.yaml")
        if origem is None:
            raise ErroConfig(
                "Nao encontrei 'config.example.yaml' para copiar. Rode o init na "
                "pasta do projeto (onde estao os arquivos de exemplo)."
            )
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origem, destino)
        log.info("config: '%s' criado a partir de '%s'.", destino, origem)

    if Path(".env").exists():
        log.info(".env: ja existe — mantido.")
    else:
        origem_env = _exemplo(".env.example")
        if origem_env is not None:
            shutil.copyfile(origem_env, Path(".env").resolve())
            log.info(".env: criado a partir de '%s'.", origem_env)

    cfg = carregar_config(destino)

    caminho_banco = Path(cfg.banco)
    existia = caminho_banco.exists()
    try:
        conexao = Banco(caminho_banco)
    except sqlite3.OperationalError as e:
        raise ErroConfig(
            f"Nao consegui criar o banco em '{caminho_banco}': {e}. "
            "Confira a chave 'banco' do config (o caminho e relativo a pasta atual)."
        )
    conexao.fechar()
    log.info(
        "banco: '%s' %s, com as tabelas ofertas/alertas/meta.",
        caminho_banco,
        "ja existia" if existia else "criado agora",
    )

    log.info(
        "config: %d rota(s) | fontes ativas: %s",
        len(cfg.rotas),
        ", ".join(cfg.fontes_ativas()) or "nenhuma",
    )
    if cfg.email.senha and cfg.email.de and cfg.email.para:
        log.info("e-mail: pronto para enviar para %s.", ", ".join(cfg.email.para))
    else:
        log.info(
            "e-mail: ainda nao configurado (SMTP_SENHA no .env + email.de/para no "
            "config) — use --sem-email para testar sem enviar."
        )

    rota = cfg.rotas[0]
    log.info("Proximos passos:")
    log.info("  1. ajuste '%s' (rotas, preco_maximo, email) e o .env.", destino)
    log.info(
        "  2. teste uma fonte: busca-voos testar google_flights --origem %s"
        " --destino %s --ida %s",
        rota.origem,
        rota.destino,
        rota.datas_ida[0],
    )
    log.info("  3. rode um ciclo:   busca-voos uma --sem-email")
    log.info("  4. veja o painel:   busca-voos painel --abrir")
    return 0


def cmd_painel(args) -> int:
    # import tardio: fastapi/uvicorn sao opcionais (extra "web")
    from .web import ErroPainel, servir

    cfg = carregar_config(args.config)
    limites = {rota.id: rota.preco_maximo for rota in cfg.rotas}
    try:
        return servir(
            cfg.banco,
            host=args.host,
            porta=args.porta,
            abrir_navegador=args.abrir,
            debug=args.debug,
            limites=limites,
        )
    except ErroPainel as e:
        log.error("%s", e)
        return 4


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="busca-voos",
        description="Monitor de passagens aereas (Google Flights, Skyscanner, Trip.com, Skiplagged e cia.)",
    )
    parser.add_argument("--debug", action="store_true", help="logs detalhados")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_init = sub.add_parser("init", help="primeiro uso: cria config.yaml, .env e o banco")
    p_init.add_argument("--config", default="config.yaml")
    p_init.set_defaults(func=cmd_init)

    p_uma = sub.add_parser("uma", help="executa um ciclo e sai")
    p_uma.add_argument("--config", default="config.yaml")
    p_uma.add_argument("--fontes", default=None, help="fontes separadas por virgula (sobrepoe o config)")
    p_uma.add_argument("--sem-email", action="store_true", help="nao envia e-mail (alerta so no log)")
    p_uma.set_defaults(func=cmd_uma)

    p_run = sub.add_parser("run", help="roda em loop (daemon/systemd)")
    p_run.add_argument("--config", default="config.yaml")
    p_run.add_argument("--fontes", default=None)
    p_run.add_argument("--sem-email", action="store_true")
    p_run.set_defaults(func=cmd_run)

    p_test = sub.add_parser("testar", help="teste rapido de uma fonte (sem banco, sem e-mail)")
    p_test.add_argument("fonte", help="skiplagged | google_flights | skyscanner | trip_com")
    p_test.add_argument("--origem", required=True)
    p_test.add_argument("--destino", required=True)
    p_test.add_argument("--ida", required=True, help="AAAA-MM-DD")
    p_test.add_argument("--volta", default=None, help="AAAA-MM-DD (ida e volta)")
    p_test.add_argument("--config", default="config.yaml")
    p_test.add_argument("--top", type=int, default=8)
    p_test.set_defaults(func=cmd_testar)

    p_email = sub.add_parser("email-teste", help="envia um e-mail de verificacao")
    p_email.add_argument("--config", default="config.yaml")
    p_email.set_defaults(func=cmd_email_teste)

    p_painel = sub.add_parser(
        "painel", help="sobe o painel web local do historico (somente leitura)"
    )
    p_painel.add_argument("--config", default="config.yaml")
    p_painel.add_argument("--host", default="127.0.0.1", help="padrao: 127.0.0.1 (so a sua maquina)")
    p_painel.add_argument("--porta", type=int, default=8787)
    p_painel.add_argument("--abrir", action="store_true", help="abre o navegador ao subir")
    p_painel.set_defaults(func=cmd_painel)

    args = parser.parse_args(argv)
    configurar_logs(args.debug)
    try:
        return args.func(args)
    except ErroConfig as e:
        log.error("config: %s", e)
        return 2
    except ErroEmail as e:
        log.error("e-mail: %s", e)
        return 3
    except KeyboardInterrupt:
        log.info("Encerrado.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())