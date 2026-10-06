"""Configuracao de logging para CLI e servico."""
from __future__ import annotations

import logging
import sys


def _tolerante(stream) -> None:
    """Evita perder linha de log por causa de encoding.

    No Windows com a saida redirecionada (Agendador de Tarefas, ``> log.txt``)
    o stdout vira cp1252; um caractere vindo do scraping que nao exista nessa
    tabela faz o handler do logging descartar a linha inteira e cuspir um
    traceback no stderr. Com ``errors="replace"`` o caractere vira ``?`` e o
    resto da linha sobrevive.
    """
    try:
        stream.reconfigure(errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


def configurar_logs(debug: bool = False) -> None:
    nivel = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=nivel,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%d/%m %H:%M:%S",
        stream=sys.stdout,
    )
    _tolerante(sys.stdout)
    _tolerante(sys.stderr)
    for ruidoso in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(ruidoso).setLevel(
            logging.DEBUG if debug else logging.WARNING
        )