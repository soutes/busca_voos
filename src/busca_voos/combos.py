"""Expansao de janelas de datas em combinacoes (ida, volta) com rodizio."""
from __future__ import annotations

from datetime import date

from .models import Rota


def expandir(rota: Rota) -> list[tuple[date, date | None]]:
    """Gera todos os pares (ida, volta) validos da rota.

    So ida: pares (ida, None). Ida e volta: produto cartesiano com volta >= ida.
    """
    combos: list[tuple[date, date | None]] = []
    for ida in rota.datas_ida:
        if rota.datas_volta:
            for volta in rota.datas_volta:
                if volta >= ida:
                    combos.append((ida, volta))
        else:
            combos.append((ida, None))
    return combos


def girar(combos: list, deslocamento: int) -> list:
    """Rotaciona a lista conforme o ciclo, para variar quais pares sao testados.

    Com max_combinacoes_por_ciclo = N, ao longo dos ciclos todos os pares
    acabam sendo visitados.
    """
    n = len(combos)
    if n == 0:
        return combos
    d = deslocamento % n
    return combos[d:] + combos[:d]