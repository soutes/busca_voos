"""SQLite: historico de ofertas, alertas enviados e contador de ciclos."""
from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from .models import Oferta

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ofertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    ciclo INTEGER,
    fonte TEXT NOT NULL,
    rota TEXT NOT NULL,
    data_ida TEXT,
    data_volta TEXT,
    preco REAL NOT NULL,
    moeda TEXT NOT NULL,
    cia TEXT,
    escalas TEXT,
    link TEXT
);
CREATE TABLE IF NOT EXISTS alertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    fonte TEXT NOT NULL,
    rota TEXT NOT NULL,
    data_ida TEXT,
    data_volta TEXT,
    preco REAL NOT NULL,
    link TEXT
);
CREATE TABLE IF NOT EXISTS meta (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_ofertas_chave ON ofertas (fonte, rota, data_ida, data_volta);
CREATE INDEX IF NOT EXISTS ix_alertas_chave ON alertas (fonte, rota, data_ida, data_volta);
"""


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _chave_data(d: date | None) -> str | None:
    return d.isoformat() if d else None


class Banco:
    def __init__(self, caminho: Path):
        self.caminho = Path(caminho)
        self.con = sqlite3.connect(self.caminho)
        self.con.executescript(_SCHEMA)
        self.con.commit()

    # ---------------- ciclos ----------------

    def proximo_ciclo(self) -> int:
        cur = self.con.execute("SELECT valor FROM meta WHERE chave = 'ciclo'")
        linha = cur.fetchone()
        n = (int(linha[0]) if linha else 0) + 1
        self.con.execute(
            "INSERT INTO meta (chave, valor) VALUES ('ciclo', ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
            (str(n),),
        )
        self.con.commit()
        return n

    # ---------------- ofertas ----------------

    def salvar_ofertas(self, ofertas: list[Oferta], ciclo: int = 0) -> None:
        agora = _iso(datetime.now(timezone.utc))
        dados = [
            (
                agora,
                ciclo,
                o.fonte,
                o.rota,
                _chave_data(o.data_ida),
                _chave_data(o.data_volta),
                o.preco,
                o.moeda,
                o.cia,
                o.escalas,
                o.link,
            )
            for o in ofertas
        ]
        self.con.executemany(
            "INSERT INTO ofertas (ts, ciclo, fonte, rota, data_ida, data_volta, preco,"
            " moeda, cia, escalas, link) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            dados,
        )
        self.con.commit()

    # ---------------- alertas ----------------

    def _ultimo_alerta(
        self, fonte: str, rota: str, data_ida: date | None, data_volta: date | None
    ) -> tuple[str, float] | None:
        cur = self.con.execute(
            "SELECT ts, preco FROM alertas WHERE fonte = ? AND rota = ?"
            " AND data_ida IS ? AND data_volta IS ? ORDER BY id DESC LIMIT 1",
            (fonte, rota, _chave_data(data_ida), _chave_data(data_volta)),
        )
        return cur.fetchone()

    def deve_alertar(
        self,
        fonte: str,
        rota: str,
        data_ida: date | None,
        data_volta: date | None,
        preco: float,
        dedupe_horas: float,
        queda_pct: float = 10.0,
    ) -> tuple[bool, str]:
        """Politica: alerta se e a primeira vez, se passou a janela de dedupe,
        ou se o preco caiu >= queda_pct em relacao ao ultimo alerta."""
        linha = self._ultimo_alerta(fonte, rota, data_ida, data_volta)
        if linha is None:
            return True, "novo"
        ts = datetime.fromisoformat(linha[0])
        idade_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        if idade_h >= dedupe_horas:
            return True, "realerta (janela expirou)"
        if preco <= float(linha[1]) * (1 - queda_pct / 100):
            return True, f"queda >= {queda_pct:g}%"
        return False, "repetido"

    def registrar_alerta(
        self,
        fonte: str,
        rota: str,
        data_ida: date | None,
        data_volta: date | None,
        preco: float,
        link: str,
    ) -> None:
        self.con.execute(
            "INSERT INTO alertas (ts, fonte, rota, data_ida, data_volta, preco, link)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                _iso(datetime.now(timezone.utc)),
                fonte,
                rota,
                _chave_data(data_ida),
                _chave_data(data_volta),
                preco,
                link,
            ),
        )
        self.con.commit()

    def fechar(self) -> None:
        self.con.close()