"""Carga e validacao da configuracao (config.yaml + segredos do .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .models import Rota


class ErroConfig(Exception):
    """Erro de configuracao com mensagem acionavel."""


@dataclass
class FonteCfg:
    ativo: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmailCfg:
    host: str = "smtp.gmail.com"
    porta: int = 587
    tls: bool = True
    de: str = ""
    para: list[str] = field(default_factory=list)
    assunto_prefixo: str = "\u2708\ufe0f busca_voos"
    senha: str = ""  # vem de SMTP_SENHA no .env


@dataclass
class AgendaCfg:
    intervalo_minutos: int = 60
    max_combinacoes_por_ciclo: int = 12
    dedupe_horas: float = 24
    queda_realerta_pct: float = 10.0
    pausa_entre_consultas_s: int = 8
    pausa_entre_fontes_s: int = 20


@dataclass
class NavegadorCfg:
    headless: bool = True
    canal: str | None = None  # ex.: "chrome" para usar o Chrome instalado
    timeout_ms: int = 45_000
    proxy: str | None = None
    user_agent: str | None = None


@dataclass
class Config:
    caminho: Path
    moeda: str = "BRL"
    idioma: str = "pt-BR"
    pais: str = "BR"
    fontes: dict[str, FonteCfg] = field(default_factory=dict)
    rotas: list[Rota] = field(default_factory=list)
    email: EmailCfg = field(default_factory=EmailCfg)
    agenda: AgendaCfg = field(default_factory=AgendaCfg)
    navegador: NavegadorCfg = field(default_factory=NavegadorCfg)
    banco: Path = Path("dados.sqlite3")

    def fontes_ativas(self) -> list[str]:
        return [nome for nome, f in self.fontes.items() if f.ativo]


# --------------------- helpers de validacao ---------------------

def _data(valor: Any, onde: str) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor.strip())
        except ValueError:
            pass
    raise ErroConfig(f"Data invalida em {onde}: {valor!r} — use AAAA-MM-DD")


def _lista_datas(no: Any, onde: str) -> list[date]:
    """Aceita data unica, lista de datas ou janela {de: ..., ate: ...}."""
    if no is None:
        return []
    if isinstance(no, list):
        return [_data(v, onde) for v in no]
    if isinstance(no, dict):
        if "de" not in no:
            raise ErroConfig(f"Janela precisa de 'de' e 'ate' em {onde}")
        de = _data(no["de"], onde)
        ate = _data(no.get("ate", no["de"]), onde)
        if ate < de:
            raise ErroConfig(f"Janela invertida em {onde}: {de} e maior que {ate}")
        return [de + timedelta(days=i) for i in range((ate - de).days + 1)]
    return [_data(no, onde)]


def _texto(no: Any, onde: str) -> str:
    if not isinstance(no, str) or not no.strip():
        raise ErroConfig(f"Texto obrigatorio ausente em {onde}")
    return no.strip().upper()


def _num(no: Any, onde: str, minimo: float = 0.0) -> float:
    try:
        v = float(no)
    except (TypeError, ValueError):
        raise ErroConfig(f"Numero invalido em {onde}: {no!r}")
    if v <= minimo:
        raise ErroConfig(f"Numero em {onde} deve ser maior que {minimo}")
    return v


def _bool(no: Any, onde: str) -> bool:
    if isinstance(no, bool):
        return no
    if isinstance(no, str):
        return no.strip().lower() in ("1", "true", "sim", "yes", "on")
    return bool(no)


# ------------------------ carga principal ------------------------

def carregar_config(caminho: Path | str) -> Config:
    caminho = Path(caminho)
    if not caminho.exists():
        alternativas = [
            Path("busca_voos") / caminho.name,
            Path(__file__).resolve().parents[2] / caminho.name,
        ]
        alternativa = next((p for p in alternativas if p.exists()), None)
        if alternativa is None:
            raise ErroConfig(
                f"Config '{caminho}' nao encontrado. Copie 'busca_voos/config.example.yaml'"
                " para 'config.yaml' na pasta onde vai rodar, e ajuste."
            )
        caminho = alternativa

    load_dotenv()
    try:
        cru = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ErroConfig(f"YAML invalido em '{caminho}': {e}")
    except ValueError as e:
        raise ErroConfig(
            f"Valor invalido em '{caminho}' ({e}) — datas usam AAAA-MM-DD"
        )
    if not isinstance(cru, dict):
        raise ErroConfig(f"Config '{caminho}' precisa ser um mapeamento YAML")

    cfg = Config(caminho=caminho)
    cfg.moeda = str(cru.get("moeda", cfg.moeda)).upper()
    cfg.idioma = str(cru.get("idioma", cfg.idioma))
    cfg.pais = str(cru.get("pais", cfg.pais)).upper()
    cfg.banco = Path(str(cru.get("banco", cfg.banco)))

    fontes = cru.get("fontes") or {}
    if not isinstance(fontes, dict) or not fontes:
        raise ErroConfig("Secao 'fontes' deve ser um mapeamento nome -> {ativo: true/false}")
    for nome, no in fontes.items():
        if isinstance(no, bool):
            no = {"ativo": no}
        if not isinstance(no, dict):
            raise ErroConfig(f"Fonte '{nome}' deve ser 'true'/'false' ou um mapeamento")
        extra = {k: v for k, v in no.items() if k != "ativo"}
        cfg.fontes[str(nome).strip().lower()] = FonteCfg(
            ativo=_bool(no.get("ativo", False), f"fontes.{nome}.ativo"), extra=extra
        )

    rotas = cru.get("rotas") or []
    if not isinstance(rotas, list) or not rotas:
        raise ErroConfig("Defina ao menos uma rota em 'rotas'")
    for i, no in enumerate(rotas):
        onde = f"rotas[{i}]"
        origem = _texto(no.get("origem"), f"{onde}.origem")
        destino = _texto(no.get("destino"), f"{onde}.destino")
        if origem == destino:
            raise ErroConfig(f"{onde}: origem e destino iguais ({origem})")
        datas_ida = _lista_datas(no.get("janela_ida", no.get("datas_ida")), f"{onde}.janela_ida")
        datas_volta = _lista_datas(no.get("janela_volta", no.get("datas_volta")), f"{onde}.janela_volta")
        if not datas_ida:
            raise ErroConfig(f"{onde}: informe 'janela_ida' (de/ate) ou 'datas_ida'")
        preco_maximo = _num(no.get("preco_maximo", 10_000), f"{onde}.preco_maximo")
        fontes_rota = no.get("fontes")
        if fontes_rota is not None:
            if not isinstance(fontes_rota, list) or not fontes_rota:
                raise ErroConfig(f"{onde}.fontes deve ser uma lista de nomes, ex.: [skiplagged]")
            fontes_rota = [str(f).strip().lower() for f in fontes_rota]
        cfg.rotas.append(
            Rota(
                origem=origem,
                destino=destino,
                datas_ida=datas_ida,
                datas_volta=datas_volta,
                preco_maximo=preco_maximo,
                fontes=fontes_rota,
                nome=str(no.get("nome", "") or ""),
            )
        )

    email_no = cru.get("email") or {}
    cfg.email.host = str(email_no.get("host", cfg.email.host))
    cfg.email.porta = int(email_no.get("porta", cfg.email.porta))
    cfg.email.tls = _bool(email_no.get("tls", True), "email.tls")
    cfg.email.de = str(email_no.get("de", "")).strip()
    cfg.email.para = [str(x).strip() for x in (email_no.get("para") or []) if str(x).strip()]
    cfg.email.assunto_prefixo = str(email_no.get("assunto_prefixo", cfg.email.assunto_prefixo))
    cfg.email.senha = os.getenv("SMTP_SENHA", "")

    agenda_no = cru.get("agenda") or {}
    a = cfg.agenda
    a.intervalo_minutos = int(agenda_no.get("intervalo_minutos", a.intervalo_minutos))
    a.max_combinacoes_por_ciclo = int(
        agenda_no.get("max_combinacoes_por_ciclo", a.max_combinacoes_por_ciclo)
    )
    a.dedupe_horas = float(agenda_no.get("dedupe_horas", a.dedupe_horas))
    a.queda_realerta_pct = float(agenda_no.get("queda_realerta_pct", a.queda_realerta_pct))
    a.pausa_entre_consultas_s = int(
        agenda_no.get("pausa_entre_consultas_s", a.pausa_entre_consultas_s)
    )
    a.pausa_entre_fontes_s = int(agenda_no.get("pausa_entre_fontes_s", a.pausa_entre_fontes_s))
    a.max_combinacoes_por_ciclo = max(1, a.max_combinacoes_por_ciclo)

    nav_no = cru.get("navegador") or {}
    n = cfg.navegador
    n.headless = _bool(nav_no.get("headless", True), "navegador.headless")
    n.canal = nav_no.get("canal") or None
    n.timeout_ms = int(nav_no.get("timeout_ms", n.timeout_ms))
    n.proxy = nav_no.get("proxy") or None
    n.user_agent = nav_no.get("user_agent") or None
    return cfg