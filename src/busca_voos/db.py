"""SQLite: historico de ofertas, alertas enviados e contador de ciclos."""
from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from .models import Oferta, Rota

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ofertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    ciclo INTEGER,
    fonte TEXT NOT NULL,
    rota TEXT NOT NULL,
    rota_id TEXT NOT NULL DEFAULT '',
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
    rota_id TEXT NOT NULL DEFAULT '',
    data_ida TEXT,
    data_volta TEXT,
    preco REAL NOT NULL,
    link TEXT
);
CREATE TABLE IF NOT EXISTS meta (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS configuracoes (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ofertas_chave ON ofertas (fonte, rota, data_ida, data_volta);
CREATE INDEX IF NOT EXISTS ix_alertas_chave ON alertas (fonte, rota, data_ida, data_volta);
"""


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _chave_data(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _na_janela(rota_ida: list, rota_volta: list, di: str | None, dv: str | None) -> bool:
    if not rota_ida or not di:
        return False
    try:
        di_d = date.fromisoformat(di)
    except ValueError:
        return False
    if not (min(rota_ida) <= di_d <= max(rota_ida)):
        return False
    if dv and rota_volta:
        try:
            dv_d = date.fromisoformat(dv)
        except ValueError:
            return False
        if not (min(rota_volta) <= dv_d <= max(rota_volta)):
            return False
    return True


def _id_legado(candidatas: list, data_ida: str | None, data_volta: str | None) -> str | None:
    """Escolhe o id da rota para uma linha antiga: filtra por trecho e janela;
    empate ou nada que case cai na primeira candidata do par (ordem do config)."""
    if not candidatas:
        return None
    tem_volta = bool(data_volta)
    por_trecho = [r for r in candidatas if bool(r.datas_volta) == tem_volta]
    base = por_trecho or list(candidatas)
    dentro = [r for r in base if _na_janela(r.datas_ida, r.datas_volta, data_ida, data_volta)]
    return (dentro or base)[0].id


class Banco:
    def __init__(self, caminho: Path):
        self.caminho = Path(caminho)
        self.con = sqlite3.connect(self.caminho)
        self.con.executescript(_SCHEMA)
        self._garantir_coluna_rota_id()
        self.con.commit()

    def _garantir_coluna_rota_id(self) -> None:
        """Adiciona rota_id em bancos criados antes desta versao (so aditivo)."""
        for tabela in ("ofertas", "alertas"):
            cols = {p[1] for p in self.con.execute(f"PRAGMA table_info({tabela})")}
            if "rota_id" not in cols:
                self.con.execute(
                    f"ALTER TABLE {tabela} ADD COLUMN rota_id TEXT NOT NULL DEFAULT ''"
                )

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
                o.rota_id,
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
            "INSERT INTO ofertas (ts, ciclo, fonte, rota, rota_id, data_ida, data_volta,"
            " preco, moeda, cia, escalas, link) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            dados,
        )
        self.con.commit()

    # ---------------- alertas ----------------

    def _ultimo_alerta(
        self, fonte: str, rota_id: str, data_ida: date | None, data_volta: date | None
    ) -> tuple[str, float] | None:
        cur = self.con.execute(
            "SELECT ts, preco FROM alertas WHERE fonte = ? AND rota_id = ?"
            " AND data_ida IS ? AND data_volta IS ? ORDER BY id DESC LIMIT 1",
            (fonte, rota_id, _chave_data(data_ida), _chave_data(data_volta)),
        )
        return cur.fetchone()

    def deve_alertar(
        self,
        fonte: str,
        rota_id: str,
        data_ida: date | None,
        data_volta: date | None,
        preco: float,
        dedupe_horas: float,
        queda_pct: float = 10.0,
    ) -> tuple[bool, str]:
        """Politica: alerta se e a primeira vez, se passou a janela de dedupe,
        ou se o preco caiu >= queda_pct em relacao ao ultimo alerta (por rota_id)."""
        linha = self._ultimo_alerta(fonte, rota_id, data_ida, data_volta)
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
        rota_id: str = "",
    ) -> None:
        self.con.execute(
            "INSERT INTO alertas (ts, fonte, rota, rota_id, data_ida, data_volta, preco, link)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _iso(datetime.now(timezone.utc)),
                fonte,
                rota,
                rota_id,
                _chave_data(data_ida),
                _chave_data(data_volta),
                preco,
                link,
            ),
        )
        self.con.commit()

    # ---------------- configuracoes ----------------

    def obter_configuracao(self, chave: str, padrao: str = "") -> str:
        """Obtem valor de configuracao salva no banco pelo nome da chave."""
        cur = self.con.execute("SELECT valor FROM configuracoes WHERE chave = ?", (chave,))
        linha = cur.fetchone()
        return str(linha[0]) if linha else padrao

    def salvar_configuracao(self, chave: str, valor: str) -> None:
        """Salva ou atualiza uma configuracao no banco."""
        agora = _iso(datetime.now(timezone.utc))
        self.con.execute(
            "INSERT INTO configuracoes (chave, valor, atualizado_em) VALUES (?, ?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, atualizado_em = excluded.atualizado_em",
            (chave, str(valor), agora),
        )
        self.con.commit()

    def listar_configuracoes(self) -> dict[str, str]:
        """Retorna todas as configuracoes chave-valor da tabela configuracoes."""
        cur = self.con.execute("SELECT chave, valor FROM configuracoes")
        return {linha[0]: linha[1] for linha in cur.fetchall()}

    def limpar_alertas(self) -> int:
        """Apaga o historico de alertas (libera a regra anti-spam). Devolve quantos."""
        n = self.con.execute("DELETE FROM alertas").rowcount
        self.con.commit()
        return max(0, n)

    def migrar_rota_ids(self, rotas: list[Rota]) -> int:
        """Preenche rota_id vazio (ofertas/alertas) pela rota que casa por
        par + trecho + janela de datas. Aditivo e idempotente."""
        self._garantir_coluna_rota_id()
        por_par: dict[str, list[Rota]] = {}
        for r in rotas:
            por_par.setdefault(f"{r.origem}-{r.destino}", []).append(r)

        mudou = 0
        for tabela in ("ofertas", "alertas"):
            linhas = self.con.execute(
                f"SELECT id, rota, data_ida, data_volta FROM {tabela}"
                " WHERE rota_id IS NULL OR rota_id = ''"
            ).fetchall()
            for linha_id, rota, data_ida, data_volta in linhas:
                escolhida = _id_legado(por_par.get(rota, []), data_ida, data_volta)
                if escolhida:
                    self.con.execute(
                        f"UPDATE {tabela} SET rota_id = ? WHERE id = ?",
                        (escolhida, linha_id),
                    )
                    mudou += 1
        self.con.commit()
        return mudou

    def fechar(self) -> None:
        self.con.close()