"""Leitura do SQLite para o painel web — somente leitura.

O daemon grava em `ofertas`/`alertas`; aqui o arquivo e aberto em modo
`mode=ro`, entao o painel nunca disputa lock com um ciclo em andamento nem
corre o risco de alterar o historico.

A tabela `ofertas` guarda **uma linha por consulta a cada ciclo**. Por isso o
painel trabalha em cima da CTE `ultimas`: o retrato mais recente de cada
combinacao (fonte, rota, data_ida, data_volta). O historico completo continua
disponivel em `historico()`.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote


class ErroPainel(Exception):
    """Erro do painel com mensagem acionavel para o usuario."""


_TABELAS = ("ofertas", "alertas", "meta")

#: Ultima cotacao de cada chave (fonte, rota, ida, volta).
ULTIMAS = """
WITH ultimas AS (
    SELECT o.* FROM ofertas o
    JOIN (
        SELECT MAX(id) AS id FROM ofertas
        GROUP BY fonte, rota, data_ida, data_volta
    ) u ON o.id = u.id
)
"""

#: ordem aceita -> ORDER BY (colunas fixas; nunca vem texto do usuario)
ORDENS = {
    "preco": "preco ASC, rota ASC",
    "preco_desc": "preco DESC, rota ASC",
    "data_ida": "data_ida ASC, preco ASC",
    "recentes": "ts DESC, preco ASC",
    "rota": "rota ASC, preco ASC",
}


# ------------------------------ conexao ------------------------------

def conectar(caminho: Path | str) -> sqlite3.Connection:
    """Abre o banco em modo somente-leitura, com mensagens de erro uteis."""
    p = Path(caminho).expanduser()
    if not p.exists():
        raise ErroPainel(
            f"Banco '{p}' nao existe ainda. Rode um ciclo primeiro "
            "(busca-voos uma --sem-email) ou aponte --config para o config.yaml certo."
        )
    if not p.is_file():
        raise ErroPainel(f"'{p}' nao e um arquivo de banco SQLite.")

    # as_uri evita problemas com ':' do drive no Windows e com espacos/acentos
    con = sqlite3.connect(f"file:{quote(p.resolve().as_posix(), safe='/:')}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        faltando = [t for t in _TABELAS if not _tem_tabela(con, t)]
    except sqlite3.DatabaseError as e:
        # arquivo existe mas nao e SQLite (ex.: log grande com esse nome)
        con.close()
        raise ErroPainel(f"'{p}' nao parece um banco SQLite valido: {e}") from e
    if faltando:
        con.close()
        raise ErroPainel(
            f"Banco '{p}' nao tem a(s) tabela(s) {', '.join(faltando)} — "
            "rode um ciclo (busca-voos uma) para criar o schema."
        )
    return con


def _tem_tabela(con: sqlite3.Connection, nome: str) -> bool:
    cur = con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (nome,))
    return cur.fetchone() is not None


def _linhas(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


# ------------------------------ filtros ------------------------------

def filtros(con: sqlite3.Connection) -> dict:
    """Valores disponiveis para montar os filtros da tela."""
    rotas = con.execute(
        "SELECT rota FROM (SELECT rota FROM ofertas UNION SELECT rota FROM alertas)"
        " ORDER BY rota"
    ).fetchall()
    fontes = con.execute(
        "SELECT fonte FROM (SELECT fonte FROM ofertas UNION SELECT fonte FROM alertas)"
        " ORDER BY fonte"
    ).fetchall()
    moedas = con.execute("SELECT DISTINCT moeda FROM ofertas ORDER BY moeda").fetchall()
    periodo = con.execute("SELECT MIN(data_ida) AS de, MAX(data_ida) AS ate FROM ofertas").fetchone()
    return {
        "rotas": [r["rota"] for r in rotas],
        "fontes": [r["fonte"] for r in fontes],
        "moedas": [r["moeda"] for r in moedas],
        "periodo": {"de": periodo["de"] if periodo else None, "ate": periodo["ate"] if periodo else None},
    }


# --------------------------- where de ofertas ---------------------------

def _onde_ofertas(
    rota: str | None, fonte: str | None, de: str | None, ate: str | None, preco_max: float | None
) -> tuple[str, list]:
    """WHERE parametrizado (valores sempre via placeholder)."""
    cond: list[str] = []
    params: list = []
    if rota:
        cond.append("rota = ?")
        params.append(rota)
    if fonte:
        cond.append("fonte = ?")
        params.append(fonte)
    if de:
        cond.append("data_ida >= ?")
        params.append(de)
    if ate:
        cond.append("data_ida <= ?")
        params.append(ate)
    if preco_max is not None:
        cond.append("preco <= ?")
        params.append(preco_max)
    return (" WHERE " + " AND ".join(cond) if cond else ""), params


# ------------------------------ consultas ------------------------------

def resumo(con: sqlite3.Connection) -> dict:
    """Cartoes do topo da tela: totais, menor preco e melhor preco por rota."""
    total_ofertas = con.execute("SELECT COUNT(*) AS n FROM ofertas").fetchone()["n"]
    total_alertas = con.execute("SELECT COUNT(*) AS n FROM alertas").fetchone()["n"]
    ciclo = con.execute("SELECT valor FROM meta WHERE chave = 'ciclo'").fetchone()
    if ciclo:
        n_ciclo = int(ciclo["valor"])
    else:
        # banco sem meta (ex.: gravado por uma versao antiga): deduz da tabela
        n_ciclo = con.execute("SELECT MAX(ciclo) AS n FROM ofertas").fetchone()["n"]
    ultima_coleta = con.execute("SELECT MAX(ts) AS ts FROM ofertas").fetchone()["ts"]
    ultimo_alerta = con.execute("SELECT MAX(ts) AS ts FROM alertas").fetchone()["ts"]

    menor = None
    if total_ofertas:
        linha = con.execute(
            ULTIMAS + "SELECT * FROM ultimas ORDER BY preco ASC LIMIT 1"
        ).fetchone()
        menor = _oferta(linha)

    por_rota: list[dict] = []
    if total_ofertas:
        por_rota = _linhas(
            con.execute(
                ULTIMAS
                + """
                , melhores AS (SELECT rota, MIN(preco) AS preco FROM ultimas GROUP BY rota)
                SELECT u.rota, u.preco, u.moeda, u.fonte, u.data_ida, u.data_volta, u.link, u.ts,
                       (SELECT COUNT(*) FROM ultimas x WHERE x.rota = u.rota) AS cotacoes
                FROM ultimas u JOIN melhores m ON m.rota = u.rota AND m.preco = u.preco
                ORDER BY u.rota
                """
            )
        )

    por_fonte = _linhas(
        con.execute(
            ULTIMAS
            + """
            SELECT fonte,
                   COUNT(*) AS cotacoes,
                   MIN(preco) AS menor_preco,
                   MAX(ts) AS ultima
            FROM ultimas GROUP BY fonte ORDER BY fonte
            """
        )
    )

    return {
        "total_ofertas": total_ofertas,
        "total_alertas": total_alertas,
        "ciclo": n_ciclo,
        "ultima_coleta": ultima_coleta,
        "ultimo_alerta": ultimo_alerta,
        "menor_preco": menor,
        "por_rota": por_rota,
        "por_fonte": por_fonte,
    }


def _oferta(linha) -> dict | None:
    if linha is None:
        return None
    return {
        "preco": linha["preco"],
        "moeda": linha["moeda"],
        "rota": linha["rota"],
        "fonte": linha["fonte"],
        "data_ida": linha["data_ida"],
        "data_volta": linha["data_volta"],
        "cia": linha["cia"],
        "escalas": linha["escalas"],
        "link": linha["link"],
        "ts": linha["ts"],
        "ciclo": linha["ciclo"],
    }


def contar_ofertas(
    con: sqlite3.Connection,
    rota: str | None = None,
    fonte: str | None = None,
    de: str | None = None,
    ate: str | None = None,
    preco_max: float | None = None,
) -> int:
    onde, params = _onde_ofertas(rota, fonte, de, ate, preco_max)
    sql = ULTIMAS + f"SELECT COUNT(*) AS n FROM ultimas{onde}"
    return con.execute(sql, params).fetchone()["n"]


def listar_ofertas(
    con: sqlite3.Connection,
    rota: str | None = None,
    fonte: str | None = None,
    de: str | None = None,
    ate: str | None = None,
    preco_max: float | None = None,
    ordem: str = "preco",
    limite: int = 200,
) -> list[dict]:
    """Retrato mais recente de cada combinacao, filtrado e ordenado."""
    onde, params = _onde_ofertas(rota, fonte, de, ate, preco_max)
    sql = (
        ULTIMAS
        + f"SELECT * FROM ultimas{onde} ORDER BY {ORDENS.get(ordem, ORDENS['preco'])} LIMIT ?"
    )
    return [_oferta(r) for r in con.execute(sql, [*params, max(1, min(int(limite), 1000))])]


def listar_alertas(
    con: sqlite3.Connection,
    rota: str | None = None,
    fonte: str | None = None,
    limite: int = 100,
) -> list[dict]:
    """Alertas gravados (o que virou e-mail), do mais novo para o mais antigo."""
    cond: list[str] = []
    params: list = []
    if rota:
        cond.append("rota = ?")
        params.append(rota)
    if fonte:
        cond.append("fonte = ?")
        params.append(fonte)
    onde = " WHERE " + " AND ".join(cond) if cond else ""
    sql = f"SELECT * FROM alertas{onde} ORDER BY id DESC LIMIT ?"
    return _linhas(con.execute(sql, [*params, max(1, min(int(limite), 1000))]))


def historico(
    con: sqlite3.Connection,
    rota: str | None = None,
    fonte: str | None = None,
    dias: int = 90,
) -> list[dict]:
    """Preco minimo/maximo por dia (serie do grafico)."""
    desde = (datetime.now(timezone.utc) - timedelta(days=max(1, int(dias)))).isoformat(
        timespec="seconds"
    )
    cond = ["ts >= ?"]
    params: list = [desde]
    if rota:
        cond.append("rota = ?")
        params.append(rota)
    if fonte:
        cond.append("fonte = ?")
        params.append(fonte)
    sql = (
        "SELECT substr(ts, 1, 10) AS dia, MIN(preco) AS minimo, MAX(preco) AS maximo,"
        " COUNT(*) AS cotacoes FROM ofertas WHERE "
        + " AND ".join(cond)
        + " GROUP BY dia ORDER BY dia"
    )
    return _linhas(con.execute(sql, params))
