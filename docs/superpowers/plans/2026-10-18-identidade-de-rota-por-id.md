# Identidade de Rota por ID Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar a cada rota cadastrada um ID unico e estavel, gravar esse ID junto de cada oferta e alerta no banco, e fazer toda a aba (KPIs, historico do menor preco, retrato de ofertas, alertas) filtrar/agrupar pelo ID — para que duas rotas com o mesmo par ORIGEM-DESTINO (1 trecho x 2 trechos, ou qualquer duplicata) nao mostrem mais dados iguais.

**Architecture:**
- Config: novo campo `id` em cada item de `rotas` no `config.yaml`, gerado automaticamente (base `ORIGEM-DESTINO`, sufixo `-2`, `-3`, ... em duplicata). Preservado ao editar datas/teto/nome; regerado se origem/destino mudarem.
- Modelo: `models.Rota` ganha campo `id` (hoje e uma property derivada); `models.Oferta` ganha `rota_id`.
- Banco: coluna `rota_id TEXT NOT NULL DEFAULT ''` em `ofertas` e `alertas` (a coluna `rota` de exibicao continua). Migracao aditiva/idempotente que preenche `rota_id` vazio pelo par + trecho + janela de datas. Dedupe de alerta passa a chavear por `rota_id`.
- Coleta: as fontes continuam gravando `rota=ORIGEM-DESTINO`; o agendador carimba `oferta.rota_id = rota.id` logo apos `fonte.buscar(...)`.
- API/painel: `limites` e todos os filtros passam a usar `rota_id`; o front usa o id como estado da rota ativa e exibe o par legivel.

**Tech Stack:** Python 3.14 (roda com `$env:PYTHONPATH="src"; python -m pytest -q`), SQLite3 (stdlib), FastAPI/Starlette + TestClient (opcional, extra "web"), JS puro (sem framework, sem CDN), PyYAML.

**Spec:** `docs/superpowers/specs/2026-10-18-identidade-de-rota-por-id-design.md`

## Global Constraints

- SEM EMOJIS em nenhum arquivo, texto, mensagem de commit ou log.
- Front em DOM puro: sem `innerHTML` com dado nao confiavel, sem CDN.
- Integridade do YAML: editar rotas preserva comentarios fora do bloco `rotas:` e revalida com `carregar_config`.
- `vs_win/` e `vs_linux/` sao copias byte a byte de `src/busca_voos/` (mais `config.example.yaml` e `README.md` no root). Devem ficar identicas — sincronizar no fim (Task 8).
- Nao ler `.env` (as senhas vem do banco/`os.getenv`); nao alterar `.env`.
- Retrocompatibilidade: `registrar_alerta` ganha `rota_id` como parametro nomeado com default `""` para nao quebrar chamadas posicionais existentes. Nenhum teste chama `deve_alertar`/`ofertas` direto.
- `cli.py` ja monta `limites = {rota.id: rota.preco_maximo ...}` (linha 221): com `Rota.id` virando o ID unico, nao precisa mudar.

## Review Focus

Cinco modos de falha que mais provavelmente mordem (cada um vira um teste na tarefa dona):

1. Linha antiga cujo `rota` nao existe mais no config (rota removida) -> nao pode quebrar a migracao nem aparecer em nenhuma rota (Task 3).
2. Duas rotas com o mesmo par E mesmo trecho E mesma janela (indistinguiveis) -> migracao nao pode duplicar nem quebrar; escolhe a primeira na ordem do config (Task 3).
3. Painel aberto num banco antigo, antes de qualquer ciclo -> a migracao roda na subida do painel e o `ULTIMAS` (que particiona por `rota_id`) tem a coluna disponivel (Task 6).
4. Editar origem/destino de uma rota no painel -> o ID acompanha o par; o historico antigo nao aparece sob a rota nova e `limites` fica com a chave nova (Tasks 1, 6).
5. `config.yaml` com `id` explicito duplicado (escrito a mao) -> IDs unicos determinam quem fica; `carregar_config` nao corrompe (Task 1).

---

## Task 1: ID de rota no config e no modelo

**Files:**
- Modify: `src/busca_voos/models.py`
- Modify: `src/busca_voos/config.py`
- Modify: `config.example.yaml`
- Create: `tests/test_rota_identidade.py`

**Interfaces:**
- Produces: `models.Rota.id: str` (campo, nao property); `models.Oferta.rota_id: str = ""`; `config._normalizar_ids_rotas(rotas: list[dict]) -> list[str]`; `listar_rotas_dict(...)[i]["id"]` = ID unico; `carregar_config(...).rotas[i].id` = ID unico; `_formatar_bloco_rotas` grava `id` em cada item.

- [ ] **Step 1: Escrever os testes que falham**

Em `tests/test_rota_identidade.py` (novo arquivo; use o cabecalho de `tests/test_rotas_email.py`: `sys.path.insert(0, str(RAIZ / "src"))`):

```python
"""Testes da identidade de rota por id (config, banco, migracao, painel e API)."""
from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from busca_voos.config import (
    adicionar_rota_config,
    atualizar_rota_config,
    carregar_config,
    listar_rotas_dict,
)
from busca_voos.models import Oferta, Rota


@pytest.fixture()
def pasta():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        shutil.copyfile(RAIZ / "config.example.yaml", p / "config.yaml")
        yield p


def _rotas_sao(pasta: Path):
    """Duas FLN-SAO: uma so ida (teto 300) e uma ida+volta (teto 500)."""
    atualizar_rota_config(pasta / "config.yaml", 0, {
        "origem": "FLN", "destino": "SAO",
        "janela_ida": {"de": "2026-11-01", "ate": "2026-11-04"},
        "preco_maximo": 300.0, "nome": "IDA SP",
    })
    adicionar_rota_config(pasta / "config.yaml", {
        "origem": "FLN", "destino": "SAO",
        "janela_ida": {"de": "2026-11-01", "ate": "2026-11-04"},
        "janela_volta": {"de": "2026-11-05", "ate": "2026-11-06"},
        "preco_maximo": 500.0, "nome": "Sao Paulo",
    })


def test_ids_de_rotas_duplicadas_sao_unicos(pasta: Path):
    _rotas_sao(pasta)
    rotas = listar_rotas_dict(pasta / "config.yaml")
    assert [r["id"] for r in rotas] == ["FLN-SAO", "FLN-SAO-2"]


def test_carregar_config_traz_os_mesmos_ids(pasta: Path):
    _rotas_sao(pasta)
    cfg = carregar_config(pasta / "config.yaml")
    assert [r.id for r in cfg.rotas] == ["FLN-SAO", "FLN-SAO-2"]
    assert cfg.rotas[0].datas_volta == []
    assert cfg.rotas[1].datas_volta == [date(2026, 11, 5), date(2026, 11, 6)]


def test_id_preservado_ao_editar_datas_teto_e_nome(pasta: Path):
    _rotas_sao(pasta)
    rotas = atualizar_rota_config(pasta / "config.yaml", 0, {
        "origem": "FLN", "destino": "SAO",
        "janela_ida": {"de": "2026-12-01", "ate": "2026-12-03"},
        "preco_maximo": 250.0, "nome": "IDA SP nova",
    })
    assert rotas[0]["id"] == "FLN-SAO"


def test_id_acompanha_o_par_ao_editar_origem_destino(pasta: Path):
    _rotas_sao(pasta)
    rotas = atualizar_rota_config(pasta / "config.yaml", 0, {
        "origem": "FLN", "destino": "BSB",
        "janela_ida": {"de": "2026-11-01", "ate": "2026-11-04"},
        "preco_maximo": 300.0,
    })
    assert rotas[0]["id"] == "FLN-BSB"
    assert rotas[1]["id"] == "FLN-SAO-2"


def test_nova_rota_recebe_id_livre(pasta: Path):
    _rotas_sao(pasta)
    rotas = adicionar_rota_config(pasta / "config.yaml", {
        "origem": "FLN", "destino": "SAO",
        "janela_ida": {"de": "2026-11-01", "ate": "2026-11-04"},
        "preco_maximo": 700.0,
    })
    assert rotas[-1]["id"] == "FLN-SAO-3"


def test_id_explicito_duplicado_no_yaml_nao_quebra(pasta: Path):
    (pasta / "config.yaml").write_text(
        "fontes: {google_flights: {ativo: true}}\n"
        "rotas:\n"
        "  - id: X\n    origem: FLN\n    destino: SAO\n"
        "    janela_ida: { de: 2026-11-01, ate: 2026-11-02 }\n    preco_maximo: 100\n"
        "  - id: X\n    origem: FLN\n    destino: SAO\n"
        "    janela_ida: { de: 2026-11-01, ate: 2026-11-02 }\n    preco_maximo: 200\n",
        encoding="utf-8",
    )
    rotas = listar_rotas_dict(pasta / "config.yaml")
    assert [r["id"] for r in rotas] == ["X", "FLN-SAO-2"]
    assert len({r["id"] for r in carregar_config(pasta / "config.yaml").rotas}) == 2


def test_oferta_tem_rota_id_default_vazio():
    o = Oferta(fonte="f", rota="FLN-SAO", origem="FLN", destino="SAO",
              data_ida=date(2026, 11, 1), data_volta=None, preco=1.0,
              moeda="BRL", link="http://x")
    assert o.rota_id == ""
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_rota_identidade.py -q`
Expected: FAIL (nao existe `Rota.id` como campo com id unico, nem `Oferta.rota_id`, nem `_normalizar_ids_rotas`).

- [ ] **Step 3: `models.py`**

Substituir a property `id` por um campo e adicionar `rota_id` em `Oferta`:

```python
@dataclass
class Rota:
    """Uma rota com janela(s) de datas e limite de preco para alerta."""

    origem: str
    destino: str
    datas_ida: list[date]
    datas_volta: list[date] = field(default_factory=list)
    preco_maximo: float = 10_000.0
    fontes: list[str] | None = None  # override por rota (None = usa as globais)
    nome: str = ""
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"{self.origem}-{self.destino}"
```

Em `Oferta`, adicionar o campo no fim (tem default, entao nao quebra construcoes posicionais):

```python
    coletado_em: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    rota_id: str = ""
```

- [ ] **Step 4: `config.py` — helper de normalizacao**

Adicionar logo acima de `_formatar_bloco_rotas` (apos `listar_rotas_dict`, ~linha 444):

```python
def _normalizar_ids_rotas(rotas: list[dict]) -> list[str]:
    """Devolve o id de cada rota, na ordem. Reaproveita o id explicito quando
    valido e unico; caso contrario gera base ORIGEM-DESTINO (+ -2, -3, ...)."""
    usados: set[str] = set()
    ids: list[str] = []
    for r in rotas:
        if not isinstance(r, dict):
            ids.append("")
            continue
        base = (
            f"{str(r.get('origem', '')).strip().upper()}-"
            f"{str(r.get('destino', '')).strip().upper()}"
        )
        explicito = str(r.get("id", "") or "").strip()
        candidato = explicito if (explicito and explicito not in usados) else ""
        if not candidato:
            candidato = base
            n = 2
            while candidato and candidato in usados:
                candidato = f"{base}-{n}"
                n += 1
        usados.add(candidato)
        ids.append(candidato)
    return ids
```

Nota: se `base` for vazio (registro invalido) e colidir, o `while` gera `-2`, `-3`, ... a partir de `base` vazio; registros invalidos falham depois na validacao, entao o id gerado nao chega a ser usado.

- [ ] **Step 5: `config.py` — usar os ids**

1. Em `listar_rotas_dict` (linha ~416), calcular os ids e usa-los no item:

```python
    ids = _normalizar_ids_rotas(rotas_raw)
    resultado: list[dict] = []
    for i, r in enumerate(rotas_raw):
        ...
        item: dict[str, Any] = {
            "indice": i,
            "id": ids[i],
            ...
```

2. Em `_formatar_bloco_rotas` (linha ~446), emitir o `id` como primeiro campo de cada item:

```python
def _formatar_bloco_rotas(rotas: list[dict]) -> str:
    linhas = ["rotas:"]
    ids = _normalizar_ids_rotas(rotas)
    for i, r in enumerate(rotas):
        linhas.append(f"  - id: {json.dumps(ids[i], ensure_ascii=False)}")
        origem = str(r.get("origem", "")).strip().upper()
        ...
```

3. Em `carregar_config` (linha ~262), calcular os ids antes do laco e passar `id=` para `Rota`:

```python
    rotas = cru.get("rotas") or []
    if not isinstance(rotas, list) or not rotas:
        raise ErroConfig("Defina ao menos uma rota em 'rotas'")
    ids_rotas = _normalizar_ids_rotas(rotas)
    for i, no in enumerate(rotas):
        ...
        cfg.rotas.append(
            Rota(
                origem=origem,
                destino=destino,
                datas_ida=datas_ida,
                datas_volta=datas_volta,
                preco_maximo=preco_maximo,
                fontes=fontes_rota,
                nome=str(no.get("nome", "") or ""),
                id=ids_rotas[i],
            )
        )
```

4. Em `atualizar_rota_config` (linha ~623), preservar o id quando o par nao muda:

```python
    ids_antes = _normalizar_ids_rotas(rotas_raw)
    id_atual = ids_antes[indice]
    antiga = rotas_raw[indice]
    par_antigo = (
        str(antiga.get("origem", "")).strip().upper(),
        str(antiga.get("destino", "")).strip().upper(),
    )

    rota_dict = _validar_e_montar_dict_rota(dados_atualizados)
    par_novo = (rota_dict["origem"], rota_dict["destino"])
    if par_novo == par_antigo:
        rota_dict["id"] = id_atual
    rotas_raw[indice] = rota_dict
    _salvar_rotas_yaml(p, rotas_raw, conteudo_original=conteudo)
    return listar_rotas_dict(p)
```

`adicionar_rota_config` e `remover_rota_config` nao precisam de mudanca: `_salvar_rotas_yaml` -> `_formatar_bloco_rotas` normaliza e grava todos os ids (o arquivo se auto-corrige). `obter_configuracoes_gestao`/`salvar_configuracoes_gestao` nao tocam no bloco `rotas:` (verificado), entao tambem ficam como estao.

- [ ] **Step 6: `config.example.yaml` — documentar o campo**

No primeiro item de `rotas:` (linha ~27), logo apos `- origem: FLN                 # codigo IATA ...`, adicionar a linha do id e um comentario curto:

```yaml
  - origem: FLN                 # codigo IATA (aeroporto ou cidade, ex.: RIO)
    destino: RIO
    # id: FLN-RIO               # opcional: gerado sozinho (base ORIGEM-DESTINO, -2 em duplicata)
```

- [ ] **Step 7: Rodar os testes**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_rota_identidade.py tests/test_rotas_email.py tests/test_limites_de_busca.py -q`
Expected: PASS. (`test_api_put_rota_endpoint` continua passando porque o id segue o par: `FLN-GIG` e `GRU-MIA`.)

- [ ] **Step 8: Commit**

```
git add src/busca_voos/models.py src/busca_voos/config.py config.example.yaml tests/test_rota_identidade.py
git commit -m "feat(rotas): id unico por rota no config e no modelo"
```

---

## Task 2: Banco — coluna `rota_id`, gravacao e dedupe por id

**Files:**
- Modify: `src/busca_voos/db.py`
- Modify: `tests/test_rota_identidade.py`

**Interfaces:**
- Consumes: `models.Oferta.rota_id` (Task 1).
- Produces: `Banco._garantir_coluna_rota_id() -> None`; `Banco.salvar_ofertas(...)` grava `rota_id`; `Banco._ultimo_alerta(fonte, rota_id, data_ida, data_volta)`; `Banco.deve_alertar(fonte, rota_id, data_ida, data_volta, preco, dedupe_horas, queda_pct=10.0)`; `Banco.registrar_alerta(fonte, rota, data_ida, data_volta, preco, link, rota_id="")`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao fim de `tests/test_rota_identidade.py`:

```python
from busca_voos.db import Banco


def _temp_db(tmp_path: Path) -> Banco:
    return Banco(tmp_path / "d.sqlite3")


def test_schema_tem_rota_id(tmp_path: Path):
    b = _temp_db(tmp_path)
    try:
        for tabela in ("ofertas", "alertas"):
            cols = {r[1] for r in b.con.execute(f"PRAGMA table_info({tabela})")}
            assert "rota_id" in cols
    finally:
        b.fechar()


def test_coluna_rota_id_adicionada_em_banco_antigo(tmp_path: Path):
    caminho = tmp_path / "velho.sqlite3"
    con = sqlite3.connect(caminho)
    con.executescript(
        "CREATE TABLE ofertas (id INTEGER PRIMARY KEY, ts TEXT, ciclo INTEGER,"
        " fonte TEXT, rota TEXT, data_ida TEXT, data_volta TEXT, preco REAL,"
        " moeda TEXT, cia TEXT, escalas TEXT, link TEXT);"
        "CREATE TABLE alertas (id INTEGER PRIMARY KEY, ts TEXT, fonte TEXT, rota TEXT,"
        " data_ida TEXT, data_volta TEXT, preco REAL, link TEXT);"
        "CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT);"
    )
    con.commit()
    con.close()
    b = Banco(caminho)   # __init__ deve ALTERar as tabelas
    try:
        for tabela in ("ofertas", "alertas"):
            cols = {r[1] for r in b.con.execute(f"PRAGMA table_info({tabela})")}
            assert "rota_id" in cols
    finally:
        b.fechar()


def test_salvar_ofertas_grava_rota_id(tmp_path: Path):
    b = _temp_db(tmp_path)
    try:
        o = Oferta(fonte="f", rota="FLN-SAO", origem="FLN", destino="SAO",
                   data_ida=date(2026, 11, 1), data_volta=None, preco=250.0,
                   moeda="BRL", link="http://x", rota_id="FLN-SAO-2")
        b.salvar_ofertas([o], ciclo=1)
        rid = b.con.execute("SELECT rota_id FROM ofertas").fetchone()[0]
        assert rid == "FLN-SAO-2"
    finally:
        b.fechar()


def test_dedupe_separa_rotas_do_mesmo_par(tmp_path: Path):
    b = _temp_db(tmp_path)
    try:
        d = date(2026, 11, 1)
        b.registrar_alerta("f", "FLN-SAO", d, None, 250.0, "http://x", rota_id="FLN-SAO")
        # outra rota do mesmo par, outra janela de dedupe: ainda deve alertar
        alertar, _ = b.deve_alertar("f", "FLN-SAO-2", d, None, 250.0, dedupe_horas=24)
        assert alertar is True
        # a mesma rota (id) com o mesmo preco: suprimido
        alertar2, motivo = b.deve_alertar("f", "FLN-SAO", d, None, 250.0, dedupe_horas=24)
        assert alertar2 is False and motivo == "repetido"
    finally:
        b.fechar()


def test_registrar_alerta_posicional_ainda_funciona(tmp_path: Path):
    b = _temp_db(tmp_path)
    try:
        d = date(2026, 11, 1)
        b.registrar_alerta("f", "FLN-RIO", d, None, 100.0, "http://x")   # sem rota_id
        n = b.con.execute("SELECT COUNT(*) FROM alertas").fetchone()[0]
        assert n == 1
    finally:
        b.fechar()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_rota_identidade.py -q -k "schema or antigo or salvar_ofertas or dedupe or posicional"`
Expected: FAIL.

- [ ] **Step 3: `db.py` — schema e coluna**

1. Em `_SCHEMA`, adicionar `rota_id` nas duas tabelas (apos `rota TEXT NOT NULL,`):

```sql
    rota TEXT NOT NULL,
    rota_id TEXT NOT NULL DEFAULT '',
```

2. Em `Banco.__init__`, garantir a coluna em bancos existentes:

```python
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
```

- [ ] **Step 4: `db.py` — gravacao e dedupe**

1. `salvar_ofertas`: incluir `o.rota_id` na tupla e na lista de colunas:

```python
        dados = [
            (
                agora, ciclo, o.fonte, o.rota, o.rota_id,
                _chave_data(o.data_ida), _chave_data(o.data_volta),
                o.preco, o.moeda, o.cia, o.escalas, o.link,
            )
            for o in ofertas
        ]
        self.con.executemany(
            "INSERT INTO ofertas (ts, ciclo, fonte, rota, rota_id, data_ida, data_volta,"
            " preco, moeda, cia, escalas, link) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            dados,
        )
```

2. `_ultimo_alerta` e `deve_alertar` passam a chavear por `rota_id`:

```python
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
        """... (mesma politica, agora por rota_id)"""
        linha = self._ultimo_alerta(fonte, rota_id, data_ida, data_volta)
        ...
```

3. `registrar_alerta` ganha `rota_id` nomeado no fim:

```python
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
                _iso(datetime.now(timezone.utc)), fonte, rota, rota_id,
                _chave_data(data_ida), _chave_data(data_volta), preco, link,
            ),
        )
        self.con.commit()
```

- [ ] **Step 5: Rodar os testes**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_rota_identidade.py tests/test_protecao_painel.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```
git add src/busca_voos/db.py tests/test_rota_identidade.py
git commit -m "feat(db): coluna rota_id e dedupe de alertas por id"
```

---

## Task 3: Migracao dos ids antigos

**Files:**
- Modify: `src/busca_voos/db.py`
- Modify: `tests/test_rota_identidade.py`

**Interfaces:**
- Consumes: `models.Rota` (Task 1), coluna `rota_id` (Task 2).
- Produces: `Banco.migrar_rota_ids(rotas: list[Rota]) -> int` (idempotente; devolve quantas linhas preencheu); helpers de modulo `db._na_janela(...)` e `db._id_legado(...)`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar a `tests/test_rota_identidade.py`:

```python
def _legado(b: Banco, tabela: str, rota: str, data_ida: str | None, data_volta: str | None) -> None:
    b.con.execute(
        f"INSERT INTO {tabela} (ts, fonte, rota, data_ida, data_volta, preco"
        + (", moeda" if tabela == "ofertas" else "")
        + ") VALUES (?, ?, ?, ?, ?, ?"
        + (", ?" if tabela == "ofertas" else "")
        + ")",
        (("2026-10-18T12:00:00+00:00", "f", rota, data_ida, data_volta, 100.0)
         + (("BRL",) if tabela == "ofertas" else ())),
    )
    b.con.commit()


def _rotas_migracao() -> list[Rota]:
    return [
        Rota(origem="FLN", destino="SAO",
             datas_ida=[date(2026, 11, 1), date(2026, 11, 4)], datas_volta=[],
             preco_maximo=300.0, nome="IDA SP", id="FLN-SAO"),
        Rota(origem="FLN", destino="SAO",
             datas_ida=[date(2026, 11, 1), date(2026, 11, 4)],
             datas_volta=[date(2026, 11, 5), date(2026, 11, 6)],
             preco_maximo=500.0, nome="Sao Paulo", id="FLN-SAO-2"),
    ]


def test_migracao_separa_so_ida_de_ida_volta(tmp_path: Path):
    b = _temp_db(tmp_path)
    try:
        _legado(b, "ofertas", "FLN-SAO", "2026-11-04", None)      # so ida, R$ later
        _legado(b, "ofertas", "FLN-SAO", "2026-11-03", "2026-11-05")
        _legado(b, "alertas", "FLN-SAO", "2026-11-04", None)
        n = b.migrar_rota_ids(_rotas_migracao())
        assert n == 3
        so_ida = b.con.execute(
            "SELECT rota_id FROM ofertas WHERE data_volta IS NULL"
        ).fetchone()[0]
        ida_volta = b.con.execute(
            "SELECT rota_id FROM ofertas WHERE data_volta IS NOT NULL"
        ).fetchone()[0]
        assert so_ida == "FLN-SAO"
        assert ida_volta == "FLN-SAO-2"
    finally:
        b.fechar()


def test_migracao_rota_orfa_fica_vazia(tmp_path: Path):
    b = _temp_db(tmp_path)
    try:
        _legado(b, "ofertas", "XX-YY", "2026-11-01", None)
        assert b.migrar_rota_ids(_rotas_migracao()) == 0
        rid = b.con.execute("SELECT rota_id FROM ofertas").fetchone()[0]
        assert rid == ""
    finally:
        b.fechar()


def test_migracao_e_idempotente(tmp_path: Path):
    b = _temp_db(tmp_path)
    try:
        _legado(b, "ofertas", "FLN-SAO", "2026-11-04", None)
        assert b.migrar_rota_ids(_rotas_migracao()) == 1
        assert b.migrar_rota_ids(_rotas_migracao()) == 0   # nada mais a preencher
    finally:
        b.fechar()


def test_migracao_ambigua_escolhe_a_primeira(tmp_path: Path):
    b = _temp_db(tmp_path)
    try:
        # janela/trecho da 1a rota, mas linha sem data que case em nenhuma: cai na 1a do par
        _legado(b, "ofertas", "FLN-SAO", "2027-01-01", None)
        b.migrar_rota_ids(_rotas_migracao())
        rid = b.con.execute("SELECT rota_id FROM ofertas").fetchone()[0]
        assert rid == "FLN-SAO"
    finally:
        b.fechar()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_rota_identidade.py -q -k migracao`
Expected: FAIL (`migrar_rota_ids` inexistente).

- [ ] **Step 3: Implementar em `db.py`**

Adicionar `from .models import Oferta, Rota` no topo e, no fim da classe `Banco` (antes de `fechar`), o metodo:

```python
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
```

E, no nivel do modulo (perto de `_chave_data`):

```python
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
```

- [ ] **Step 4: Rodar os testes**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_rota_identidade.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add src/busca_voos/db.py tests/test_rota_identidade.py
git commit -m "feat(db): migracao de rota_id por par, trecho e janela"
```

---

## Task 4: Agendador — carimba `rota_id` e alerta por id

**Files:**
- Modify: `src/busca_voos/scheduler.py`
- Modify: `tests/test_rota_identidade.py`

**Interfaces:**
- Consumes: `Rota.id`, `Oferta.rota_id`, `Banco.migrar_rota_ids`, `Banco.deve_alertar`, `Banco.registrar_alerta` (Tasks 1-3).
- Produces: ofertas gravadas com `rota_id` da rota consultada; e-mail com rotulo `ORIGEM-DESTINO` (sem sufixo de id); migracao no inicio do ciclo.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar a `tests/test_rota_identidade.py`:

```python
from unittest.mock import patch

from busca_voos.scheduler import ciclo


def test_ciclo_carimba_rota_id_por_rota(pasta: Path):
    _rotas_sao(pasta)
    cfg = carregar_config(pasta / "config.yaml")
    cfg.banco = pasta / "dados.sqlite3"
    cfg.agenda.pausa_entre_consultas_s = 0
    cfg.agenda.pausa_entre_fontes_s = 0
    cfg.email.senha = "x"
    cfg.email.de = "a@b.com"
    cfg.email.para = ["c@d.com"]

    class MockFonte:
        def __init__(self, _cfg): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def buscar(self, origem, destino, data_ida, data_volta=None):
            return [Oferta(fonte="fonte_teste", rota="FLN-SAO", origem="FLN",
                           destino="SAO", data_ida=data_ida, data_volta=data_volta,
                           preco=200.0, moeda="BRL", link="http://x")]

    with patch("busca_voos.scheduler.REGISTRO", {"fonte_teste": MockFonte}):
        with patch("busca_voos.scheduler.enviar"):
            ciclo(cfg, enviar_email=True, fontes=["fonte_teste"])

    b = Banco(pasta / "dados.sqlite3")
    try:
        pares = b.con.execute(
            "SELECT DISTINCT rota_id FROM ofertas ORDER BY rota_id"
        ).fetchall()
        ids = {p[0] for p in pares}
        assert ids and "" not in ids
        assert ids.issubset({"FLN-SAO", "FLN-SAO-2"})
    finally:
        b.fechar()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_rota_identidade.py -q -k carimba`
Expected: FAIL (ofertas gravadas com `rota_id` vazio).

- [ ] **Step 3: `scheduler.py` — carimbar e usar o id**

1. Em `_enviar_alerta`, o assunto usa o par legivel (nao o id, que pode ter sufixo):

```python
    assunto, html = construir_email_rota(
        f"{rota.origem}-{rota.destino}", [oferta], rota.preco_maximo
    )
```
(manter `rota.id` nos logs).

2. Em `ciclo`, logo apos `banco = Banco(cfg.banco)` e antes de `salvar_configuracao`, migrar:

```python
    banco = Banco(cfg.banco)
    try:
        banco.migrar_rota_ids(cfg.rotas)
    except Exception:
        log.exception("Falha ao migrar ids de rota; seguindo o ciclo")
```

3. Antes de `banco.salvar_ofertas(ofertas, ciclo=n_ciclo)` (linha ~161), carimbar cada oferta:

```python
                        if ofertas:
                            for _o in ofertas:
                                _o.rota_id = rota.id
                            ofertas_fonte += len(ofertas)
                            banco.salvar_ofertas(ofertas, ciclo=n_ciclo)
```

4. Dedupe e registro por id (linhas ~174 e ~197): trocar `melhor.rota` por `rota.id` no `deve_alertar` e passar `rota_id=rota.id` em `registrar_alerta`:

```python
                                alertar, motivo = banco.deve_alertar(
                                    melhor.fonte,
                                    rota.id,
                                    melhor.data_ida,
                                    melhor.data_volta,
                                    melhor.preco,
                                    dedupe_horas=cfg.agenda.dedupe_horas,
                                    queda_pct=cfg.agenda.queda_realerta_pct,
                                )
                                ...
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
```

- [ ] **Step 4: Rodar os testes**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_rota_identidade.py tests/test_rotas_email.py -q`
Expected: PASS (inclui os dois testes de regressao de e-mail ja existentes).

- [ ] **Step 5: Commit**

```
git add src/busca_voos/scheduler.py tests/test_rota_identidade.py
git commit -m "feat(scheduler): carimbar rota_id na coleta e deduplicar por id"
```

---

## Task 5: Painel — consultas por `rota_id`

**Files:**
- Modify: `src/busca_voos/painel.py`
- Modify: `tests/test_rota_identidade.py`

**Interfaces:**
- Consumes: coluna `rota_id` (Task 2).
- Produces: `resumo()[...]["por_rota"][i]["rota_id"]`; `_oferta(...)["rota_id"]`; `filtros()["rotas"]` = ids distintos; `contar_ofertas`, `listar_ofertas`, `listar_alertas`, `historico` aceitam `rota_id` (no lugar de `rota`).

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar a `tests/test_rota_identidade.py`:

```python
from busca_voos import painel


def _seed_duas_rotas(caminho: Path) -> None:
    b = Banco(caminho)
    try:
        o1 = Oferta(fonte="f", rota="FLN-SAO", origem="FLN", destino="SAO",
                    data_ida=date(2026, 11, 4), data_volta=None, preco=293.0,
                    moeda="BRL", link="http://x", rota_id="FLN-SAO")
        o2 = Oferta(fonte="f", rota="FLN-SAO", origem="FLN", destino="SAO",
                    data_ida=date(2026, 11, 4), data_volta=date(2026, 11, 5),
                    preco=590.0, moeda="BRL", link="http://y", rota_id="FLN-SAO-2")
        b.salvar_ofertas([o1, o2], ciclo=1)
        b.registrar_alerta("f", "FLN-SAO", date(2026, 11, 4), None, 293.0, "http://x",
                           rota_id="FLN-SAO")
    finally:
        b.fechar()


def test_resumo_separa_rotas_do_mesmo_par(tmp_path: Path):
    db = tmp_path / "d.sqlite3"
    _seed_duas_rotas(db)
    con = painel.conectar(db)
    try:
        por_rota = {r["rota_id"]: r["preco"] for r in painel.resumo(con)["por_rota"]}
        assert por_rota == {"FLN-SAO": 293.0, "FLN-SAO-2": 590.0}
    finally:
        con.close()


def test_filtros_ofertas_alertas_e_historico_por_rota_id(tmp_path: Path):
    db = tmp_path / "d.sqlite3"
    _seed_duas_rotas(db)
    con = painel.conectar(db)
    try:
        assert painel.contar_ofertas(con, rota_id="FLN-SAO") == 1
        assert painel.contar_ofertas(con, rota_id="FLN-SAO-2") == 1
        ofs = painel.listar_ofertas(con, rota_id="FLN-SAO")
        assert [o["preco"] for o in ofs] == [293.0]
        assert painel.listar_ofertas(con, rota_id="FLN-SAO")[0]["rota_id"] == "FLN-SAO"
        al = painel.listar_alertas(con, rota_id="FLN-SAO")
        assert len(al) == 1 and al[0]["rota_id"] == "FLN-SAO"
        assert painel.listar_alertas(con, rota_id="FLN-SAO-2") == []
        hist = painel.historico(con, rota_id="FLN-SAO")
        assert hist and hist[0]["minimo"] == 293.0
        assert "FLN-SAO" in painel.filtros(con)["rotas"]
        assert "FLN-SAO-2" in painel.filtros(con)["rotas"]
    finally:
        con.close()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_rota_identidade.py -q -k "resumo_separa or por_rota_id"`
Expected: FAIL.

- [ ] **Step 3: Editar `painel.py`**

1. `ULTIMAS`: particionar por `rota_id` (duas ocorrencias de PARTITION BY):

```sql
        SELECT id FROM (
            SELECT id,
                   MAX(substr(ts, 1, 10)) OVER (
                       PARTITION BY fonte, rota_id, data_ida, data_volta
                   ) AS max_dia,
                   substr(ts, 1, 10) AS dia,
                   ROW_NUMBER() OVER (
                       PARTITION BY fonte, rota_id, data_ida, data_volta, substr(ts, 1, 10)
                       ORDER BY preco ASC, ts DESC, id DESC
                   ) AS rn
            FROM ofertas
        ) WHERE dia = max_dia AND rn = 1
```

2. `filtros`: devolver ids distintos:

```python
    rotas = con.execute(
        "SELECT rota_id FROM (SELECT rota_id FROM ofertas UNION SELECT rota_id FROM alertas)"
        " WHERE rota_id <> '' ORDER BY rota_id"
    ).fetchall()
    ...
        "rotas": [r["rota_id"] for r in rotas],
```

3. `_onde_ofertas(rota_id, ...)`: `cond.append("rota_id = ?")` (param `rota_id`).

4. `resumo`: agrupar por `rota_id` e expor as duas colunas:

```python
                ULTIMAS
                + """
                , melhores AS (SELECT rota_id, MIN(preco) AS preco FROM ultimas GROUP BY rota_id)
                SELECT u.rota_id, u.rota, u.preco, u.moeda, u.fonte, u.data_ida, u.data_volta,
                       u.link, u.ts,
                       (SELECT COUNT(*) FROM ultimas x WHERE x.rota_id = u.rota_id) AS cotacoes
                FROM ultimas u JOIN melhores m ON m.rota_id = u.rota_id AND m.preco = u.preco
                ORDER BY u.rota
                """
```

5. `_oferta`: incluir `"rota_id": linha["rota_id"] if "rota_id" in linha.keys() else ""`.

6. `contar_ofertas`/`listar_ofertas`: trocar o parametro `rota` por `rota_id` e repassar a `_onde_ofertas(rota_id, ...)`.

7. `listar_alertas`: `if rota_id: cond.append("rota_id = ?")`.

8. `historico`: `if rota_id: cond.append("rota_id = ?")`.

Manter `ORDENS["rota"] = "rota ASC, preco ASC"` (exibicao continua pelo texto).

- [ ] **Step 4: Rodar os testes**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_rota_identidade.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add src/busca_voos/painel.py tests/test_rota_identidade.py
git commit -m "feat(painel): consultas por rota_id (resumo, ofertas, alertas, historico)"
```

---

## Task 6: API web — `limites` por id, `rota_id` nos endpoints, migracao na subida

**Files:**
- Modify: `src/busca_voos/web.py`
- Modify: `tests/test_rota_identidade.py`

**Interfaces:**
- Consumes: `painel.*(rota_id=...)` (Task 5), `Banco.migrar_rota_ids` (Task 3), `config.listar_rotas_dict`/`carregar_config` (Task 1).
- Produces: `/api/filtros` com `limites` indexado por id; `/api/ofertas`, `/api/alertas`, `/api/historico` aceitam `rota_id`; `criar_app` migra ids na subida.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar a `tests/test_rota_identidade.py`:

```python
from fastapi.testclient import TestClient

from busca_voos.web import criar_app


def test_criar_app_migra_ids_na_subida(pasta: Path):
    _rotas_sao(pasta)
    db = pasta / "dados.sqlite3"
    b = Banco(db)
    try:
        b.con.execute(
            "INSERT INTO ofertas (ts, fonte, rota, data_ida, data_volta, preco, moeda)"
            " VALUES ('2026-10-18T12:00:00+00:00','f','FLN-SAO','2026-11-04',NULL,293.0,'BRL')"
        )
        b.con.commit()
    finally:
        b.fechar()

    criar_app(banco=db, caminho_config=pasta / "config.yaml")   # dispara a migracao

    b2 = Banco(db)
    try:
        rid = b2.con.execute("SELECT rota_id FROM ofertas").fetchone()[0]
        assert rid == "FLN-SAO"
    finally:
        b2.fechar()


def test_limites_e_filtros_por_id(pasta: Path):
    _rotas_sao(pasta)
    db = pasta / "dados.sqlite3"
    Banco(db).fechar()
    app = criar_app(
        banco=db,
        caminho_config=pasta / "config.yaml",
        limites={"FLN-SAO": 300.0, "FLN-SAO-2": 500.0},
    )
    c = TestClient(app, base_url="http://127.0.0.1:8787")
    f = c.get("/api/filtros").json()
    assert f["limites"]["FLN-SAO"] == 300.0
    assert f["limites"]["FLN-SAO-2"] == 500.0


def test_endpoints_aceitam_rota_id(pasta: Path):
    _rotas_sao(pasta)
    db = pasta / "dados.sqlite3"
    _seed_duas_rotas(db)
    app = criar_app(banco=db, caminho_config=pasta / "config.yaml")
    c = TestClient(app, base_url="http://127.0.0.1:8787")
    ofs = c.get("/api/ofertas", params={"rota_id": "FLN-SAO"}).json()
    assert [o["preco"] for o in ofs["ofertas"]] == [293.0]
    assert ofs["total"] == 1
    al = c.get("/api/alertas", params={"rota_id": "FLN-SAO-2"}).json()
    assert al["alertas"] == []
    hist = c.get("/api/historico", params={"rota_id": "FLN-SAO"}).json()
    assert hist["historico"] and hist["historico"][0]["minimo"] == 293.0
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_rota_identidade.py -q -k "migra_ids_na_subida or filtros_por_id or aceitam_rota_id"`
Expected: FAIL.

- [ ] **Step 3: `web.py` — endpoints por `rota_id`**

1. `api_ofertas`: renomear o parametro e o dicionario de args:

```python
    @app.get("/api/ofertas")
    def api_ofertas(
        rota_id: str | None = None,
        ...
    ) -> dict:
        ...
        args = {
            "rota_id": rota_id,
            "fonte": fonte,
            ...
```

2. `api_alertas`: `rota_id: str | None = None` e `listar_alertas(con, rota_id=rota_id, fonte=fonte, limite=limite)`.

3. `api_historico`: `rota_id: str | None = None` e `historico(con, rota_id=rota_id, fonte=fonte, dias=dias)`.

4. `api_adicionar_rota`: substituir `limites[f"{origem}-{destino}"] = preco_maximo` por reconstruir pelos ids retornados:

```python
            rotas = adicionar_rota_config(caminho_config, nova_rota)
            limites.clear()
            limites.update({r["id"]: r["preco_maximo"] for r in rotas})
            return {"ok": True, "rotas": rotas}
```

5. `api_atualizar_rota` e `api_remover_rota`: trocar a chave de `f"{r['origem']}-{r['destino']}"` por `r["id"]`.

- [ ] **Step 4: `web.py` — migracao na subida**

Logo apos `caminho_config = ...` (linha ~109), antes do `try` de import do fastapi:

```python
    limites = limites or {}
    caminho_config = Path(caminho_config) if caminho_config else Path("config.yaml")

    # migra ids de rota ausentes antes de servir (aditivo e idempotente)
    try:
        from .config import carregar_config
        from .db import Banco

        cfg_mig = carregar_config(caminho_config)
        bm = Banco(Path(banco))
        try:
            bm.migrar_rota_ids(cfg_mig.rotas)
        finally:
            bm.fechar()
    except Exception:
        log.warning("Nao foi possivel migrar ids de rota ao subir o painel", exc_info=True)
```

Remover a linha duplicada `limites = limites or {}` / `caminho_config = ...` que hoje esta logo depois (linhas 108-109) para nao repetir a atribuicao.

- [ ] **Step 5: Rodar os testes**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_rota_identidade.py tests/test_rotas_email.py tests/test_protecao_painel.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```
git add src/busca_voos/web.py tests/test_rota_identidade.py
git commit -m "feat(web): limites por id, rota_id nos endpoints e migracao na subida"
```

---

## Task 7: Front (`painel.html`) por id

**Files:**
- Modify: `src/busca_voos/painel.html`
- Modify: `tests/test_rota_identidade.py`

**Interfaces:**
- Consumes: `/api/filtros` com `limites` por id (Task 6); `por_rota[i].rota_id` e ofertas/alertas com `rota_id` (Task 5).

- [ ] **Step 1: Escrever o teste que falha (asserção estatica)**

Acrescentar a `tests/test_rota_identidade.py`:

```python
def test_front_usa_rota_id():
    html = (RAIZ / "src" / "busca_voos" / "painel.html").read_text(encoding="utf-8")
    assert "estado.rotaId" in html
    assert "limites[o.rota_id]" in html
    assert "x.rota_id === estado.rotaId" in html
    assert "limites[o.rota]" not in html          # nao pode sobrar chave por par
    assert "limites[estado.rota]" not in html
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_rota_identidade.py -q -k front`
Expected: FAIL.

- [ ] **Step 3: Editar `painel.html`**

O front guarda duas coisas: `rotaAtivaIndice` (indice nas pills) e `estado.rota` (o par, usado nos KPIs e nos filtros da API). Troque `estado.rota` por `estado.rotaId` (o id) e passe `rota_id` nas chamadas de API. A navegacao por `rotaAtivaIndice` continua; so o texto de exibicao segue vindo de `rota` (par). Pontos exatos (linhas do arquivo atual):

- Linha 439 (literal de `estado`): `const estado = { rotaId:"", fonte:"", de:"", ate:"", precoMax:"", ordem:"preco", limite:200, auto:false };`
- Linha 652 (`celulaPreco`): `const lim = limites[o.rota_id];`
- Linha 678-679: `const chaveRota = estado.rotaId; const lim = limites[chaveRota];`
- Linha 726: `const infoRota = porRota.find((x) => x.rota_id === estado.rotaId) || porRota[0] || null;`
- Linha 741: `const lim = limites[o.rota_id];`
- Linhas 744, 774 e 799 (coluna "Rota"): manter `rotaNo(o.rota)` para exibir o par; acrescentar o nome da rota para desempatar as duas `FLN -> SAO`. Trocar a coluna por:

```js
{ rotulo:"Rota", valor:(o) => rotuloRota(o) }
```

  e adicionar o helper logo abaixo de `rotaNo` (linha ~576):

```js
  /** Par (FLN -> SAO) + nome da rota, para desempatar rotas do mesmo par. */
  function rotuloRota(o){
    const r = rotasCadastradas.find((x) => x.id === o.rota_id);
    const par = rotaNo(r ? r.origem + "-" + r.destino : o.rota);
    return r && r.nome ? el("span", { classe:"bv-route-stack" }, par, el("span", { classe:"bv-badge bv-badge--flat bvx-tag", texto:r.nome })) : par;
  }
```

  (`rotasCadastradas` e o array global na linha 441.)
- Linha 823: `const teto = estado.rotaId ? Number(limites[estado.rotaId]) : NaN;`
- Linha 903: `if ($("f-rota") && $("f-rota").tagName === "SELECT") preencher("f-rota", f.rotas, estado.rotaId);`
- Linha 930: `const rotaAtual = estado.rotaId;`
- Linha 931: `const filtros = { rota_id:rotaAtual, fonte:estado.fonte, de:estado.de, ate:estado.ate, preco_max:estado.precoMax };`
- Linha 934: `api("/api/alertas", { rota_id:rotaAtual, fonte:estado.fonte, limite:100 }),`
- Linha 935: `api("/api/historico", { rota_id:rotaAtual, fonte:estado.fonte, dias:180 }),`
- Linha 945: `const infoRota = porRota.find((x) => x.rota_id === rotaAtual);`
- Linhas 1214-1217 (`renderSubpaginaRota`): `const chaveRota = rota.id;` / `estado.rotaId = chaveRota;` / `if (fRota) fRota.value = chaveRota;` (o `f-rota` e hidden, mas fica coerente).
- Linha 1343 (`salvarEdicaoRota`): apagar a linha `limites[origem + "-" + destino] = precoMaximo;` — a funcao ja chama `carregarFiltros()` (~linha 1348), que recarrega `limites` do servidor.
- Linha 1365 (`carregarRotas`): `limites[r.id] = r.preco_maximo;`
- Linha 2055 (`ligarEventos.ler`): `estado.rotaId = $("f-rota") ? $("f-rota").value : "";`

Depois de editar, rode `grep -n "estado\.rota\b\|limites\[o\.rota\]\|limites\[estado\.rota\]\|rota:rotaAtual" src/busca_voos/painel.html` e confirme que sobraram zero ocorrencias.

- [ ] **Step 4: Rodar o teste estatico e a suite**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_rota_identidade.py tests/test_protecao_painel.py -q`
Expected: PASS.

- [ ] **Step 5: Verificacao manual no navegador**

Com um banco semeado com duas rotas do mesmo par, suba o painel e confira no navegador que as duas rotas mostram KPIs/grafico distintos. Passos concretos:

1. Criar a pasta de verificacao e semear (o `banco: dados.sqlite3` do `config.example.yaml` e relativo ao cwd):

```powershell
$dir = "C:\Users\luiz_\AppData\Local\Temp\opencode\verif_rota_id"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Copy-Item "$PWD\config.example.yaml" "$dir\config.yaml" -Force
$env:PYTHONPATH="$PWD\src"
@'
from datetime import date
from pathlib import Path
from busca_voos.config import adicionar_rota_config, atualizar_rota_config
from busca_voos.db import Banco
from busca_voos.models import Oferta

d = Path(r"C:\Users\luiz_\AppData\Local\Temp\opencode\verif_rota_id")
atualizar_rota_config(d / "config.yaml", 0, {"origem": "FLN", "destino": "SAO",
    "janela_ida": {"de": "2026-11-01", "ate": "2026-11-04"}, "preco_maximo": 300.0, "nome": "IDA SP"})
adicionar_rota_config(d / "config.yaml", {"origem": "FLN", "destino": "SAO",
    "janela_ida": {"de": "2026-11-01", "ate": "2026-11-04"},
    "janela_volta": {"de": "2026-11-05", "ate": "2026-11-06"}, "preco_maximo": 500.0, "nome": "Sao Paulo"})
b = Banco(d / "dados.sqlite3")
b.salvar_ofertas([Oferta(fonte="f", rota="FLN-SAO", origem="FLN", destino="SAO",
    data_ida=date(2026, 11, 4), data_volta=None, preco=293.0, moeda="BRL", link="http://x", rota_id="FLN-SAO")], ciclo=1)
b.salvar_ofertas([Oferta(fonte="f", rota="FLN-SAO", origem="FLN", destino="SAO",
    data_ida=date(2026, 11, 4), data_volta=date(2026, 11, 5), preco=590.0, moeda="BRL", link="http://y", rota_id="FLN-SAO-2")], ciclo=1)
b.fechar()
print("seed ok")
'@ | Set-Content "$dir\seed.py" -Encoding utf8
python "$dir\seed.py"
```

2. Subir o painel em segundo plano (rode de dentro da pasta semeada para o `banco` relativo resolver):

```powershell
cd $dir
$env:PYTHONPATH="C:\Users\luiz_\_DS\_ds_ok\busca_voos\src"
python -c "from busca_voos.cli import main; main(['painel','--config','config.yaml','--porta','8791'])"
```

3. Abrir `http://127.0.0.1:8791` com `browser.tabs.open`, clicar nas duas pills `FLN -> SAO` e confirmar: a "IDA SP" mostra menor preco R$ 293 e teto R$ 300; a "Sao Paulo" mostra R$ 590 e teto R$ 500; o grafico e os alertas diferem. Registrar o resultado no relatorio da tarefa e encerrar o servidor.

- [ ] **Step 6: Commit**

```
git add src/busca_voos/painel.html tests/test_rota_identidade.py
git commit -m "feat(painel): front usa rotaId como estado da rota ativa"
```

---

## Task 8: Documentacao, espelhos e suite completa

**Files:**
- Modify: `README.md`
- Modify (sync): `vs_win/src/busca_voos/*`, `vs_linux/src/busca_voos/*`, `vs_win/config.example.yaml`, `vs_linux/config.example.yaml`, `vs_win/README.md`, `vs_linux/README.md`

- [ ] **Step 1: Documentar o id no `README.md`**

Na secao de rotas, acrescentar uma nota curta (sem emoji):

```
Cada rota ganha um `id` automatico no config.yaml (base `ORIGEM-DESTINO`,
sufixo `-2`, `-3`, ... se voce cadastrar duas rotas com o mesmo par). Ele nao e
editavel: e a chave usada no banco e no painel. Trocar as datas ou o teto
preserva o id; trocar origem/destino cria um id novo.
```

- [ ] **Step 2: Sincronizar os espelhos**

Rodar (e conferir que nao ha diferencas restantes):

```powershell
cd "C:\Users\luiz_\_DS\_ds_ok\busca_voos"
Copy-Item src/busca_voos/models.py,src/busca_voos/config.py,src/busca_voos/db.py,src/busca_voos/scheduler.py,src/busca_voos/painel.py,src/busca_voos/web.py,src/busca_voos/painel.html vs_win/src/busca_voos/ -Force
Copy-Item src/busca_voos/models.py,src/busca_voos/config.py,src/busca_voos/db.py,src/busca_voos/scheduler.py,src/busca_voos/painel.py,src/busca_voos/web.py,src/busca_voos/painel.html vs_linux/src/busca_voos/ -Force
Copy-Item config.example.yaml,README.md vs_win/ -Force
Copy-Item config.example.yaml,README.md vs_linux/ -Force
```

Depois, comparar por hash cada arquivo de `src/busca_voos` contra `vs_win` e `vs_linux` (o script abaixo deve imprimir `0`):

```powershell
$d=0; Get-ChildItem src/busca_voos -Recurse -File | Where-Object { $_.FullName -notmatch '__pycache__' } | ForEach-Object { $rel=$_.FullName.Replace("$PWD\src\busca_voos\",""); foreach ($v in @("vs_win","vs_linux")) { $o="$v/src/busca_voos/$rel"; if ((Get-FileHash $_.FullName).Hash -ne (Get-FileHash $o).Hash) { "DIFF $v/$rel"; $d++ } } }; "diffs=$d"
```

- [ ] **Step 3: Suite completa**

Run: `$env:PYTHONPATH="src"; python -m pytest -q`
Expected: PASS (as 118 anteriores + os novos).

- [ ] **Step 4: Revisar que nao sobrou referencia ao id antigo**

Run: `grep -rn "estado\.rota\b\|limites\[o\.rota\]\|f\"{r\['origem'\]}-{r\['destino'\]}\":" src/busca_voos vs_win/src/busca_voos vs_linux/src/busca_voos`
Expected: nenhuma ocorrencia nos pontos mapeados (a coluna de exibicao `rota` continua, mas nao como chave).

- [ ] **Step 5: Commit**

```
git add README.md config.example.yaml vs_win vs_linux
git commit -m "docs+chore: documentar id de rota e sincronizar espelhos"
```

---

## Pendencias (fora das tarefas)

- `config.yaml` real com as 4 rotas (nesta maquina o arquivo tem so 2). Ele nao e versionado (`.gitignore`). A migracao so separa as duas `FLN-SAO` do banco quando o config com as 4 rotas estiver presente; sem ele, a separacao fica para quando o arquivo chegar. Nao commitar `config.yaml`/`dados.sqlite3`.
- Depois da implementacao, rodar a migracao no banco real (`dados.sqlite3`) abrindo o painel uma vez (a migracao roda na subida) e conferir a separacao do R$ 293 (so ida) contra a tarifa ida+volta.
