"""Helpers das fontes de companhias aereas (GOL, Azul): bloqueio e extracao de preco."""
from __future__ import annotations

import re
from typing import Any

_MARCAS_BLOQUEIO = (
    "comportamento incomum",  # Azul / Akamai
    "access denied",
    "acesso foi limitado",
    "captcha",
    "unusual traffic",
)

# chaves de JSON que costumam guardar o valor total de uma tarifa
_CHAVES_PRECO = ("totalAmount", "totalPrice", "fareTotal", "lowestPrice", "price", "amount", "total")


def texto_de_bloqueio(texto: str) -> bool:
    t = (texto or "")[:3000].lower()
    return any(m in t for m in _MARCAS_BLOQUEIO)


def _numero(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if v > 0 else None
    if isinstance(v, dict):  # {"amount": 123.4, "currency": "BRL"}
        return _numero(v.get("amount") if "amount" in v else v.get("value"))
    return None


def menor_preco_json(dados: Any, minimo: float = 30.0) -> float | None:
    """Menor valor plausivel de tarifa em um JSON de busca de voos.

    Varre o JSON inteiro procurando as chaves de `_CHAVES_PRECO`. Heuristica
    deliberada: os formatos de resposta das companhias mudam sem aviso.
    """
    achados: list[float] = []

    def varrer(no: Any) -> None:
        if isinstance(no, dict):
            for k, v in no.items():
                if k in _CHAVES_PRECO:
                    n = _numero(v)
                    if n is not None and n >= minimo:
                        achados.append(n)
                if isinstance(v, (dict, list)):
                    varrer(v)
        elif isinstance(no, list):
            for item in no:
                varrer(item)

    varrer(dados)
    return min(achados) if achados else None


_RE_REAIS = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?)")


def menor_preco_texto(texto: str, minimo: float = 50.0) -> float | None:
    """Menor 'R$ x' plausivel no texto da pagina."""
    valores = []
    for m in _RE_REAIS.finditer(texto or ""):
        v = float(m.group(1).replace(".", "").replace(",", "."))
        if v >= minimo:
            valores.append(v)
    return min(valores) if valores else None
