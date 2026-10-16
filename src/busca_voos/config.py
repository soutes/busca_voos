"""Carga e validacao da configuracao (config.yaml + segredos do .env)."""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .models import Rota

log = logging.getLogger("busca_voos")


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
    intervalo_minutos: int = 480
    max_combinacoes_por_ciclo: int = 12
    dedupe_horas: float = 24
    queda_realerta_pct: float = 10.0
    pausa_entre_consultas_s: int = 8
    pausa_entre_fontes_s: int = 20
    max_consultas_por_fonte: int = 36   # teto de consultas a UMA fonte num ciclo (todas as rotas somadas)


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


# ------------------ validacao de texto que vai para o YAML ------------------
# O config.yaml e editado por substituicao de texto (para preservar comentarios).
# Tudo que vem do painel e entra nele passa por aqui: sem quebra de linha, sem
# caracteres de controle e so com o formato esperado. Assim um valor nunca vira
# uma chave nova do YAML (ex.: "x@y.com\n  host: servidor-do-atacante").

_CONTROLE = re.compile(r"[\x00-\x1f\x7f\u0085\u2028\u2029]")
_RE_HOST_SMTP = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)
_RE_EMAIL = re.compile(r"^[A-Za-z0-9._+\-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9.\-]{0,251}[A-Za-z0-9])?\.[A-Za-z]{2,}$")
FONTES_VALIDAS = (
    "skiplagged", "google_flights", "skyscanner", "trip_com", "kayak", "latam", "gol", "azul",
)


def _sem_controle(valor: Any, campo: str) -> str:
    s = str(valor if valor is not None else "").strip()
    if _CONTROLE.search(s):
        raise ErroConfig(f"{campo}: caracteres de controle ou quebra de linha nao sao permitidos")
    return s


def validar_host_smtp(valor: Any) -> str:
    s = _sem_controle(valor, "Servidor SMTP")
    if not _RE_HOST_SMTP.match(s):
        raise ErroConfig(f"Servidor SMTP invalido: {s[:60]!r}. Use um nome como smtp.gmail.com.")
    return s


def validar_porta_smtp(valor: Any) -> int:
    try:
        porta = int(str(valor).strip())
    except (TypeError, ValueError):
        raise ErroConfig(f"Porta SMTP invalida: {str(valor)[:20]!r}")
    if not 1 <= porta <= 65535:
        raise ErroConfig(f"Porta SMTP fora do intervalo 1-65535: {porta}")
    return porta


def validar_email(valor: Any, campo: str) -> str:
    s = _sem_controle(valor, campo)
    if not _RE_EMAIL.match(s):
        raise ErroConfig(f"{campo}: e-mail invalido ({s[:60]!r}).")
    return s


def validar_lista_emails(valor: Any, campo: str) -> list[str]:
    if isinstance(valor, list):
        itens = [str(x) for x in valor]
    elif isinstance(valor, str):
        itens = valor.split(",")
    else:
        raise ErroConfig(f"{campo}: informe uma lista de e-mails")
    limpos = [x.strip() for x in itens if x.strip()]
    if len(limpos) > 20:
        raise ErroConfig(f"{campo}: no maximo 20 destinatarios")
    return [validar_email(x, campo) for x in limpos]


def validar_nome_rota(valor: Any) -> str:
    s = _sem_controle(valor, "Nome da rota")
    if len(s) > 60:
        raise ErroConfig("Nome da rota: no maximo 60 caracteres")
    return s


def validar_nome_fonte(valor: Any) -> str:
    s = _sem_controle(valor, "Fonte").lower()
    if s not in FONTES_VALIDAS:
        raise ErroConfig(f"Fonte desconhecida: {s[:30]!r}. Use uma de: {', '.join(FONTES_VALIDAS)}")
    return s


# ------------------------ carga principal ------------------------

def _resolver_caminho(caminho: Path | str) -> Path:
    p = Path(caminho)
    if p.exists():
        return p
    alternativas = [
        Path("busca_voos") / p.name,
        Path(__file__).resolve().parents[2] / p.name,
    ]
    alternativa = next((alt for alt in alternativas if alt.exists()), None)
    if alternativa is not None:
        return alternativa
    raise ErroConfig(
        f"Config '{caminho}' nao encontrado. Copie 'busca_voos/config.example.yaml'"
        " para 'config.yaml' na pasta onde vai rodar, e ajuste."
    )


def carregar_config(caminho: Path | str) -> Config:
    caminho = _resolver_caminho(caminho)
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
    cfg.email.senha = os.getenv("SMTP_SENHA", "")
    if not cfg.email.senha and cfg.banco:
        try:
            from .db import Banco
            from .seguranca import descriptografar_texto

            p_banco = Path(cfg.banco)
            if not p_banco.is_absolute() and caminho.parent:
                p_banco_cand = caminho.parent / p_banco
                if p_banco_cand.exists():
                    p_banco = p_banco_cand
            if p_banco.exists():
                b = Banco(p_banco)
                token = b.obter_configuracao("smtp_senha", "")
                b.fechar()
                if token:
                    senha_dec = descriptografar_texto(token, pasta=caminho.parent)
                    if senha_dec:
                        cfg.email.senha = senha_dec
                        os.environ["SMTP_SENHA"] = senha_dec
        except Exception:
            pass

    agenda_no = cru.get("agenda") or {}
    a = cfg.agenda
    a.intervalo_minutos = int(agenda_no.get("intervalo_minutos", a.intervalo_minutos))
    if a.intervalo_minutos < INTERVALO_MINIMO_MIN:
        if a.intervalo_minutos not in _AVISOS_INTERVALO:
            _AVISOS_INTERVALO.add(a.intervalo_minutos)
            log.warning(
                "agenda.intervalo_minutos=%d e curto demais: usando %d (8 h) para evitar bloqueio de IP "
                "pelas fontes. Ajuste o config.yaml para silenciar este aviso.",
                a.intervalo_minutos, INTERVALO_MINIMO_MIN,
            )
        a.intervalo_minutos = INTERVALO_MINIMO_MIN
    a.max_combinacoes_por_ciclo = int(
        agenda_no.get("max_combinacoes_por_ciclo", a.max_combinacoes_por_ciclo)
    )
    a.dedupe_horas = float(agenda_no.get("dedupe_horas", a.dedupe_horas))
    a.queda_realerta_pct = float(agenda_no.get("queda_realerta_pct", a.queda_realerta_pct))
    a.pausa_entre_consultas_s = int(
        agenda_no.get("pausa_entre_consultas_s", a.pausa_entre_consultas_s)
    )
    a.pausa_entre_fontes_s = int(agenda_no.get("pausa_entre_fontes_s", a.pausa_entre_fontes_s))
    a.max_consultas_por_fonte = int(agenda_no.get("max_consultas_por_fonte", a.max_consultas_por_fonte))
    a.max_combinacoes_por_ciclo = _limitar(
        "max_combinacoes_por_ciclo", max(1, a.max_combinacoes_por_ciclo), 1, MAX_COMBINACOES_TETO
    )
    a.max_consultas_por_fonte = _limitar(
        "max_consultas_por_fonte", a.max_consultas_por_fonte, 1, MAX_CONSULTAS_FONTE_TETO
    )
    a.pausa_entre_consultas_s = _limitar("pausa_entre_consultas_s", a.pausa_entre_consultas_s, PAUSA_MIN_CONSULTAS_S)
    a.pausa_entre_fontes_s = _limitar("pausa_entre_fontes_s", a.pausa_entre_fontes_s, PAUSA_MIN_FONTES_S)

    nav_no = cru.get("navegador") or {}
    n = cfg.navegador
    n.headless = _bool(nav_no.get("headless", True), "navegador.headless")
    n.canal = nav_no.get("canal") or None
    n.timeout_ms = int(nav_no.get("timeout_ms", n.timeout_ms))
    n.proxy = nav_no.get("proxy") or None
    n.user_agent = nav_no.get("user_agent") or None
    return cfg


# ------------------------ gestao de rotas no YAML ------------------------

def _extrair_janela_dict(no: dict, chave_janela: str, chave_datas: str) -> dict | None:
    valor = no.get(chave_janela)
    if valor is None:
        valor = no.get(chave_datas)
    if valor is None:
        return None
    if isinstance(valor, dict):
        de = valor.get("de")
        if not de:
            return None
        ate = valor.get("ate", de)
        de_str = de.isoformat() if isinstance(de, (date, datetime)) else str(de).strip()
        ate_str = ate.isoformat() if isinstance(ate, (date, datetime)) else str(ate).strip()
        return {"de": de_str, "ate": ate_str}
    if isinstance(valor, list):
        if not valor:
            return None
        datas: list[str] = []
        for v in valor:
            if isinstance(v, (date, datetime)):
                datas.append(v.isoformat()[:10])
            else:
                datas.append(str(v).strip())
        datas.sort()
        return {"de": datas[0], "ate": datas[-1]}
    if isinstance(valor, (date, datetime)):
        d_str = valor.isoformat()[:10]
        return {"de": d_str, "ate": d_str}
    if isinstance(valor, str):
        s = valor.strip()
        return {"de": s, "ate": s}
    return None


def listar_rotas_dict(caminho: Path | str) -> list[dict]:
    """Retorna a lista de rotas configuradas como dicionarios."""
    p = _resolver_caminho(caminho)
    try:
        cru = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ErroConfig(f"YAML invalido em '{p}': {e}") from e
    except OSError as e:
        raise ErroConfig(f"Erro ao ler '{p}': {e}") from e

    if not isinstance(cru, dict):
        raise ErroConfig(f"Config '{p}' precisa ser um mapeamento YAML")

    rotas_raw = cru.get("rotas") or []
    if not isinstance(rotas_raw, list):
        raise ErroConfig(f"Secao 'rotas' em '{p}' deve ser uma lista")

    resultado: list[dict] = []
    for i, r in enumerate(rotas_raw):
        if not isinstance(r, dict):
            continue
        origem = str(r.get("origem", "")).strip().upper()
        destino = str(r.get("destino", "")).strip().upper()
        janela_ida = _extrair_janela_dict(r, "janela_ida", "datas_ida")
        janela_volta = _extrair_janela_dict(r, "janela_volta", "datas_volta")
        try:
            preco_maximo = float(r.get("preco_maximo", 0.0))
        except (TypeError, ValueError):
            preco_maximo = 0.0
        nome = str(r.get("nome", "") or "").strip()

        item: dict[str, Any] = {
            "indice": i,
            "id": f"{origem}-{destino}",
            "origem": origem,
            "destino": destino,
            "janela_ida": janela_ida,
            "janela_volta": janela_volta,
            "preco_maximo": preco_maximo,
            "nome": nome,
        }
        if "fontes" in r and isinstance(r["fontes"], list):
            item["fontes"] = [str(f).strip().lower() for f in r["fontes"]]
        resultado.append(item)
    return resultado


def _formatar_bloco_rotas(rotas: list[dict]) -> str:
    linhas = ["rotas:"]
    for r in rotas:
        origem = str(r.get("origem", "")).strip().upper()
        destino = str(r.get("destino", "")).strip().upper()
        linhas.append(f"  - origem: {origem}")
        linhas.append(f"    destino: {destino}")

        ji = _extrair_janela_dict(r, "janela_ida", "datas_ida")
        if ji:
            linhas.append(f"    janela_ida:   {{ de: {ji['de']}, ate: {ji['ate']} }}")

        jv = _extrair_janela_dict(r, "janela_volta", "datas_volta")
        if jv:
            linhas.append(f"    janela_volta: {{ de: {jv['de']}, ate: {jv['ate']} }}")

        try:
            pm = float(r.get("preco_maximo", 0.0))
            pm_str = str(int(pm)) if pm.is_integer() else f"{pm:.2f}"
        except (TypeError, ValueError):
            pm_str = "0"
        linhas.append(f"    preco_maximo: {pm_str}")

        nome = validar_nome_rota(r.get("nome", "") or "")
        if nome:
            # json.dumps gera uma string YAML valida (aspas, barra e unicode tratados)
            linhas.append(f"    nome: {json.dumps(nome, ensure_ascii=False)}")

        fontes = r.get("fontes")
        if fontes and isinstance(fontes, list):
            fontes_str = ", ".join(validar_nome_fonte(f) for f in fontes)
            linhas.append(f"    fontes: [{fontes_str}]")

        linhas.append("")
    return "\n".join(linhas).rstrip()


def _salvar_rotas_yaml(caminho: Path, rotas: list[dict], conteudo_original: str | None = None) -> None:
    if conteudo_original is None:
        conteudo_original = caminho.read_text(encoding="utf-8")

    bloco_rotas = _formatar_bloco_rotas(rotas)

    padrao_inicio = re.compile(r"^rotas\s*:", re.MULTILINE)
    m_inicio = padrao_inicio.search(conteudo_original)

    if m_inicio:
        inicio_rotas = m_inicio.start()
        padrao_proxima = re.compile(r"^[a-zA-Z0-9_-]+\s*:", re.MULTILINE)
        m_proxima = padrao_proxima.search(conteudo_original[m_inicio.end():])
        if m_proxima:
            fim_rotas = m_inicio.end() + m_proxima.start()
            trecho_entre = conteudo_original[m_inicio.end():fim_rotas]
            linhas_entre = trecho_entre.splitlines(keepends=True)
            idx_corte = len(linhas_entre)
            while idx_corte > 0 and (linhas_entre[idx_corte - 1].startswith("#") or linhas_entre[idx_corte - 1].strip() == ""):
                if linhas_entre[idx_corte - 1].strip() == "":
                    break
                idx_corte -= 1
            if 0 < idx_corte < len(linhas_entre):
                ajuste = sum(len(l) for l in linhas_entre[idx_corte:])
                fim_rotas -= ajuste
            prefixo = conteudo_original[:inicio_rotas].rstrip()
            sufixo = conteudo_original[fim_rotas:].lstrip("\r\n")
            novo_conteudo = f"{prefixo}\n\n{bloco_rotas}\n\n{sufixo}"
        else:
            prefixo = conteudo_original[:inicio_rotas].rstrip()
            novo_conteudo = f"{prefixo}\n\n{bloco_rotas}\n"
    else:
        novo_conteudo = f"{conteudo_original.rstrip()}\n\n{bloco_rotas}\n"

    caminho.write_text(novo_conteudo, encoding="utf-8")
    try:
        carregar_config(caminho)
    except Exception as e:
        caminho.write_text(conteudo_original, encoding="utf-8")
        raise ErroConfig(f"Falha ao validar configuracao apos atualizar rotas: {e}") from e


def _validar_e_montar_dict_rota(dados_rota: dict) -> dict[str, Any]:
    """Valida os dados de uma rota e retorna o dicionario pronto para salvar no YAML."""
    origem_raw = dados_rota.get("origem")
    if not isinstance(origem_raw, str) or not (2 <= len(origem_raw.strip()) <= 5) or not origem_raw.strip().isalnum():
        raise ErroConfig(f"Origem invalida: {origem_raw!r}. Deve ter entre 2 e 5 caracteres.")
    origem = origem_raw.strip().upper()

    destino_raw = dados_rota.get("destino")
    if not isinstance(destino_raw, str) or not (2 <= len(destino_raw.strip()) <= 5) or not destino_raw.strip().isalnum():
        raise ErroConfig(f"Destino invalido: {destino_raw!r}. Deve ter entre 2 e 5 caracteres.")
    destino = destino_raw.strip().upper()

    if origem == destino:
        raise ErroConfig(f"Origem e destino iguais ({origem})")

    ji = dados_rota.get("janela_ida")
    if ji is None and "ida_de" in dados_rota:
        ji = {"de": dados_rota.get("ida_de"), "ate": dados_rota.get("ida_ate")}
    if not isinstance(ji, dict):
        raise ErroConfig("Informe 'janela_ida' como {'de': 'AAAA-MM-DD', 'ate': 'AAAA-MM-DD'}")
    de_ida_val = ji.get("de")
    if not de_ida_val:
        raise ErroConfig("janela_ida precisa conter 'de'")
    d_ida = _data(de_ida_val, "janela_ida.de")
    ate_ida_val = ji.get("ate") or de_ida_val
    a_ida = _data(ate_ida_val, "janela_ida.ate")
    if a_ida < d_ida:
        raise ErroConfig(f"Janela de ida invertida: {d_ida} e posterior a {a_ida}")
    janela_ida_final = {"de": d_ida.isoformat(), "ate": a_ida.isoformat()}

    jv = dados_rota.get("janela_volta")
    if jv is None and dados_rota.get("volta_de"):
        jv = {"de": dados_rota.get("volta_de"), "ate": dados_rota.get("volta_ate")}
    janela_volta_final = None
    if jv is not None:
        if isinstance(jv, dict):
            de_volta_raw = str(jv.get("de") or "").strip()
            if de_volta_raw:
                d_volta = _data(de_volta_raw, "janela_volta.de")
                ate_volta_val = jv.get("ate") or de_volta_raw
                a_volta = _data(ate_volta_val, "janela_volta.ate")
                if d_volta < d_ida:
                    raise ErroConfig(f"Data de volta ({d_volta}) deve ser igual ou posterior a data de ida ({d_ida})")
                if a_volta < d_volta:
                    raise ErroConfig(f"Janela de volta invertida: {d_volta} e posterior a {a_volta}")
                janela_volta_final = {"de": d_volta.isoformat(), "ate": a_volta.isoformat()}
        elif str(jv).strip():
            d_volta = _data(jv, "janela_volta.de")
            if d_volta < d_ida:
                raise ErroConfig(f"Data de volta ({d_volta}) deve ser igual ou posterior a data de ida ({d_ida})")
            janela_volta_final = {"de": d_volta.isoformat(), "ate": d_volta.isoformat()}

    pm_val = dados_rota.get("preco_maximo")
    try:
        preco_maximo = float(pm_val)
    except (TypeError, ValueError):
        raise ErroConfig(f"Preco maximo invalido: {pm_val!r}")
    if preco_maximo <= 0:
        raise ErroConfig(f"Preco maximo deve ser maior que zero: {preco_maximo}")

    nome = validar_nome_rota(dados_rota.get("nome", "") or "")

    fontes = dados_rota.get("fontes")
    if fontes is not None:
        if not isinstance(fontes, list):
            raise ErroConfig("fontes deve ser uma lista")
        fontes = [validar_nome_fonte(f) for f in fontes]

    rota_dict: dict[str, Any] = {
        "origem": origem,
        "destino": destino,
        "janela_ida": janela_ida_final,
        "preco_maximo": preco_maximo,
    }
    if janela_volta_final:
        rota_dict["janela_volta"] = janela_volta_final
    if nome:
        rota_dict["nome"] = nome
    if fontes:
        rota_dict["fontes"] = fontes
    return rota_dict


def adicionar_rota_config(caminho: Path | str, nova_rota: dict) -> list[dict]:
    """Valida e adiciona nova rota ao config.yaml, preservando os demais comentarios."""
    p = _resolver_caminho(caminho)
    conteudo = p.read_text(encoding="utf-8")
    cru = yaml.safe_load(conteudo) or {}
    rotas_raw = cru.get("rotas") or []
    if not isinstance(rotas_raw, list):
        rotas_raw = []

    nova_rota_dict = _validar_e_montar_dict_rota(nova_rota)
    rotas_raw.append(nova_rota_dict)
    _salvar_rotas_yaml(p, rotas_raw, conteudo_original=conteudo)
    return listar_rotas_dict(p)


def atualizar_rota_config(caminho: Path | str, indice: int, dados_atualizados: dict) -> list[dict]:
    """Atualiza a rota indicada pelo indice no config.yaml e revalida."""
    p = _resolver_caminho(caminho)
    conteudo = p.read_text(encoding="utf-8")
    cru = yaml.safe_load(conteudo) or {}
    rotas_raw = cru.get("rotas") or []
    if not isinstance(rotas_raw, list):
        rotas_raw = []

    if not isinstance(indice, int) or indice < 0 or indice >= len(rotas_raw):
        raise IndexError(f"Indice de rota invalido: {indice} (total de rotas: {len(rotas_raw)})")

    rota_dict = _validar_e_montar_dict_rota(dados_atualizados)
    rotas_raw[indice] = rota_dict
    _salvar_rotas_yaml(p, rotas_raw, conteudo_original=conteudo)
    return listar_rotas_dict(p)


def remover_rota_config(caminho: Path | str, indice: int) -> list[dict]:
    """Remove a rota indicada pelo indice do config.yaml e revalida."""
    p = _resolver_caminho(caminho)
    conteudo = p.read_text(encoding="utf-8")
    cru = yaml.safe_load(conteudo) or {}
    rotas_raw = cru.get("rotas") or []
    if not isinstance(rotas_raw, list):
        rotas_raw = []

    if not isinstance(indice, int) or indice < 0 or indice >= len(rotas_raw):
        raise IndexError(f"Indice de rota invalido: {indice} (total de rotas: {len(rotas_raw)})")

    if len(rotas_raw) <= 1:
        raise ErroConfig("Nao e permitido remover a unica rota restante. O sistema precisa de ao menos uma rota.")

    rotas_raw.pop(indice)
    _salvar_rotas_yaml(p, rotas_raw, conteudo_original=conteudo)
    return listar_rotas_dict(p)


# Intervalos que o agendador aceita. Fontes como Google Flights, Skyscanner e Trip.com
# bloqueiam IPs que consultam com frequencia; abaixo de 8 h o risco de bloqueio sobe
# bastante e o usuario so descobre depois. Por isso nao ha opcao menor.
INTERVALOS_PERMITIDOS_H: tuple[float, ...] = (8.0, 12.0, 24.0, 168.0)   # 168 h = uma vez por semana
INTERVALO_MINIMO_MIN = int(INTERVALOS_PERMITIDOS_H[0] * 60)
_ROTULOS_INTERVALO = "8 horas, 12 horas, 24 horas ou semanal"
_AVISOS_INTERVALO: set[int] = set()

# Ritmo das consultas. Abaixo disto (ou com pausa 0, que desliga a espera) as fontes
# tratam o robo como bot e bloqueiam o IP. Valores menores no config.yaml sobem para o piso.
PAUSA_MIN_CONSULTAS_S = 8
PAUSA_MIN_FONTES_S = 20
MAX_COMBINACOES_TETO = 24
MAX_CONSULTAS_FONTE_TETO = 60
# Busca manual ("Buscar voos agora"): recusa abaixo disto e pede confirmacao ate o intervalo minimo
BUSCA_MANUAL_BLOQUEIO_MIN = 30
_AVISOS_LIMITES: set[str] = set()


def _limitar(campo: str, valor: int, minimo: int | None = None, maximo: int | None = None) -> int:
    """Mantem `valor` entre minimo e maximo; avisa uma vez por campo/valor quando ajusta."""
    novo = valor
    if minimo is not None and novo < minimo:
        novo = minimo
    if maximo is not None and novo > maximo:
        novo = maximo
    if novo != valor and f"{campo}={valor}" not in _AVISOS_LIMITES:
        _AVISOS_LIMITES.add(f"{campo}={valor}")
        log.warning(
            "agenda.%s=%d fora do limite seguro: usando %d (evita bloqueio de IP pelas fontes). "
            "Ajuste o config.yaml para silenciar este aviso.",
            campo, valor, novo,
        )
    return novo


def normalizar_intervalo_horas(horas: float) -> float:
    """Menor intervalo permitido que seja >= `horas` (valores antigos e curtos sobem para 8 h)."""
    for permitido in INTERVALOS_PERMITIDOS_H:
        if horas <= permitido + 1e-9:
            return permitido
    return INTERVALOS_PERMITIDOS_H[-1]


def validar_intervalo_horas(horas: Any) -> float:
    """Aceita so os intervalos permitidos; qualquer outro valor e erro (nao e ajustado em silencio)."""
    try:
        h = float(horas)
    except (TypeError, ValueError):
        raise ErroConfig(f"Intervalo invalido: {str(horas)[:20]!r}. Use {_ROTULOS_INTERVALO}.")
    for permitido in INTERVALOS_PERMITIDOS_H:
        if abs(h - permitido) < 1e-9:
            return permitido
    raise ErroConfig(
        f"Intervalo de {h:g} h nao permitido. Use {_ROTULOS_INTERVALO}: "
        "buscas mais frequentes fazem os sites bloquearem o seu IP."
    )


def obter_intervalo_cron(caminho: Path | str) -> float:
    """Le config.yaml via _resolver_caminho, extrai agenda.intervalo_minutos (padrao 60) e retorna float(minutos / 60)."""
    p = _resolver_caminho(caminho)
    conteudo = p.read_text(encoding="utf-8")
    cru = yaml.safe_load(conteudo) or {}
    agenda_no = cru.get("agenda") if isinstance(cru, dict) else {}
    minutos = INTERVALO_MINIMO_MIN
    if isinstance(agenda_no, dict) and "intervalo_minutos" in agenda_no:
        try:
            minutos = int(agenda_no["intervalo_minutos"])
        except (TypeError, ValueError):
            minutos = INTERVALO_MINIMO_MIN
    return normalizar_intervalo_horas(float(minutos / 60))


def salvar_intervalo_cron(caminho: Path | str, horas: float) -> float:
    """Converte horas para minutos = max(1, int(round(horas * 60))).
    Atualiza intervalo_minutos no config.yaml sob agenda: preservando comentarios e formatacao.
    Valida com carregar_config(caminho) e retorna horas.
    """
    p = _resolver_caminho(caminho)
    conteudo_original = p.read_text(encoding="utf-8")
    horas = validar_intervalo_horas(horas)
    minutos = int(round(horas * 60))

    padrao_agenda = re.compile(r"^agenda\s*:", re.MULTILINE)
    m_agenda = padrao_agenda.search(conteudo_original)

    if m_agenda:
        inicio_agenda = m_agenda.start()
        padrao_proxima = re.compile(r"^[a-zA-Z0-9_-]+\s*:", re.MULTILINE)
        m_proxima = padrao_proxima.search(conteudo_original[m_agenda.end():])
        if m_proxima:
            fim_agenda = m_agenda.end() + m_proxima.start()
        else:
            fim_agenda = len(conteudo_original)

        trecho_agenda = conteudo_original[inicio_agenda:fim_agenda]

        padrao_campo = re.compile(
            r"^([ \t]*intervalo_minutos\s*:\s*)[0-9]+(?:\.[0-9]+)?(.*)$",
            re.MULTILINE,
        )
        if padrao_campo.search(trecho_agenda):
            novo_trecho = padrao_campo.sub(rf"\g<1>{minutos}\2", trecho_agenda, count=1)
        else:
            linhas_agenda = trecho_agenda.splitlines(keepends=True)
            linhas_agenda.insert(1, f"  intervalo_minutos: {minutos}\n")
            novo_trecho = "".join(linhas_agenda)

        novo_conteudo = conteudo_original[:inicio_agenda] + novo_trecho + conteudo_original[fim_agenda:]
    else:
        novo_conteudo = f"{conteudo_original.rstrip()}\n\nagenda:\n  intervalo_minutos: {minutos}\n"

    p.write_text(novo_conteudo, encoding="utf-8")
    try:
        carregar_config(p)
    except Exception as e:
        p.write_text(conteudo_original, encoding="utf-8")
        raise ErroConfig(f"Falha ao validar configuracao apos atualizar intervalo cron: {e}") from e

    return float(horas)


def obter_configuracoes_gestao(caminho_config: Path | str, banco_path: Path | str) -> dict:
    """Le config.yaml e tabela configuracoes do SQLite, retornando estrutura unificada para a aba de gestao."""
    p = _resolver_caminho(caminho_config)
    conteudo = p.read_text(encoding="utf-8")
    cru = yaml.safe_load(conteudo) or {}
    email_no = cru.get("email") or {} if isinstance(cru, dict) else {}
    fontes_no = cru.get("fontes") or {} if isinstance(cru, dict) else {}

    # Email
    host = str(email_no.get("host", "smtp.gmail.com"))
    porta = int(email_no.get("porta", 587))
    tls = _bool(email_no.get("tls", True), "email.tls")
    de = str(email_no.get("de", "")).strip()
    para_cru = email_no.get("para") or []
    if isinstance(para_cru, list):
        para = [str(x).strip() for x in para_cru if str(x).strip()]
    elif isinstance(para_cru, str):
        para = [str(para_cru).strip()] if str(para_cru).strip() else []
    else:
        para = []

    # Senha
    from .seguranca import descriptografar_texto, mascarar_senha

    senha = os.getenv("SMTP_SENHA", "").strip()
    if not senha and banco_path:
        try:
            from .db import Banco

            pb = Path(banco_path)
            if not pb.is_absolute() and p.parent:
                pb_cand = p.parent / pb
                if pb_cand.exists():
                    pb = pb_cand
            if pb.exists():
                b = Banco(pb)
                token = b.obter_configuracao("smtp_senha", "")
                b.fechar()
                if token:
                    senha = descriptografar_texto(token, pasta=p.parent)
        except Exception:
            pass

    tem_senha = bool(senha)
    senha_mascarada = mascarar_senha(senha)
    # ha um token salvo, mas nao foi possivel ler (chave ausente/invalida/diferente)
    senha_ilegivel = False
    if not tem_senha and banco_path:
        try:
            from .db import Banco

            pb2 = Path(banco_path)
            if not pb2.is_absolute() and p.parent and (p.parent / pb2).exists():
                pb2 = p.parent / pb2
            if pb2.exists():
                b2 = Banco(pb2)
                senha_ilegivel = bool(b2.obter_configuracao("smtp_senha", ""))
                b2.fechar()
        except Exception:
            pass

    # Fontes
    fontes_dict = {
        nome: bool(fontes_no.get(nome, {}).get("ativo", False))
        if isinstance(fontes_no.get(nome), dict)
        else False
        for nome in ("google_flights", "trip_com", "skyscanner", "skiplagged", "latam", "gol", "azul")
    }

    # Cron
    intervalo_h = obter_intervalo_cron(p)

    return {
        "email": {
            "host": host,
            "porta": porta,
            "tls": tls,
            "de": de,
            "para": para,
            "tem_senha": tem_senha,
            "senha_ilegivel": senha_ilegivel,
            "senha_mascarada": senha_mascarada,
        },
        "fontes": fontes_dict,
        "cron": {
            "intervalo_horas": intervalo_h,
        },
    }


def salvar_configuracoes_gestao(
    caminho_config: Path | str, banco_path: Path | str, dados: dict
) -> dict:
    """Atualiza secoes de email, fontes e cron no config.yaml preservando comentarios,
    e armazena credenciais SMTP criptografadas com Fernet no SQLite.
    """
    p = _resolver_caminho(caminho_config)
    conteudo_original = p.read_text(encoding="utf-8")
    conteudo = conteudo_original

    if isinstance(dados.get("cron"), dict) and "intervalo_horas" in dados["cron"]:
        validar_intervalo_horas(dados["cron"]["intervalo_horas"])   # falha cedo, antes de gravar e-mail/fontes

    # 1. Tratar Email
    if "email" in dados and isinstance(dados["email"], dict):
        email_dados = dados["email"]

        # Se senha fornecida e nao for mascarada
        senha_raw = email_dados.get("senha")
        if senha_raw and isinstance(senha_raw, str):
            senha_limpa = senha_raw.strip()
            if senha_limpa and not senha_limpa.startswith("•"):
                from .seguranca import criptografar_texto
                from .db import Banco

                tok = criptografar_texto(senha_limpa, pasta=p.parent)
                pb = Path(banco_path)
                if not pb.is_absolute() and p.parent:
                    pb = p.parent / pb
                b = Banco(pb)
                b.salvar_configuracao("smtp_senha", tok)
                b.fechar()
                os.environ["SMTP_SENHA"] = senha_limpa

        # Atualizar campos no YAML sob email:
        padrao_email = re.compile(r"^email\s*:", re.MULTILINE)
        m_email = padrao_email.search(conteudo)
        if m_email:
            inicio_email = m_email.start()
            padrao_proxima = re.compile(r"^[a-zA-Z0-9_-]+\s*:", re.MULTILINE)
            m_prox = padrao_proxima.search(conteudo[m_email.end():])
            fim_email = (m_email.end() + m_prox.start()) if m_prox else len(conteudo)
            trecho_email = conteudo[inicio_email:fim_email]

            if "host" in email_dados:
                novo_h = validar_host_smtp(email_dados["host"])
                patt = re.compile(r"^([ \t]*host\s*:\s*)\S+(.*)$", re.MULTILINE)
                if patt.search(trecho_email):
                    trecho_email = patt.sub(lambda m: m.group(1) + novo_h + m.group(2), trecho_email, count=1)
                else:
                    trecho_email += f"  host: {novo_h}\n"

            if "porta" in email_dados:
                nova_porta = validar_porta_smtp(email_dados["porta"])
                patt = re.compile(r"^([ \t]*porta\s*:\s*)\d+(.*)$", re.MULTILINE)
                if patt.search(trecho_email):
                    trecho_email = patt.sub(lambda m: m.group(1) + str(nova_porta) + m.group(2), trecho_email, count=1)
                else:
                    trecho_email += f"  porta: {nova_porta}\n"

            if "tls" in email_dados:
                novo_tls = "true" if _bool(email_dados["tls"], "email.tls") else "false"
                patt = re.compile(
                    r"^([ \t]*tls\s*:\s*)(?:true|false|sim|nao|yes|no)(.*)$",
                    re.IGNORECASE | re.MULTILINE,
                )
                if patt.search(trecho_email):
                    trecho_email = patt.sub(lambda m: m.group(1) + novo_tls + m.group(2), trecho_email, count=1)
                else:
                    trecho_email += f"  tls: {novo_tls}\n"

            if "de" in email_dados:
                novo_de = validar_email(email_dados["de"], "E-mail remetente") if str(email_dados["de"] or "").strip() else ""
                patt = re.compile(r"^([ \t]*de\s*:\s*)\S+(.*)$", re.MULTILINE)
                if patt.search(trecho_email):
                    trecho_email = patt.sub(lambda m: m.group(1) + novo_de + m.group(2), trecho_email, count=1)
                else:
                    trecho_email += f"  de: {novo_de}\n"

            if "para" in email_dados:
                lista_p = validar_lista_emails(email_dados["para"], "Destinatarios")
                para_fmt = "[" + ", ".join(lista_p) + "]"
                patt = re.compile(r"^([ \t]*para\s*:\s*)\[.*?\](.*)$", re.MULTILINE)
                if patt.search(trecho_email):
                    trecho_email = patt.sub(lambda m: m.group(1) + para_fmt + m.group(2), trecho_email, count=1)
                else:
                    trecho_email += f"  para: {para_fmt}\n"

            conteudo = conteudo[:inicio_email] + trecho_email + conteudo[fim_email:]

    # 2. Tratar Fontes
    if "fontes" in dados and isinstance(dados["fontes"], dict):
        fontes_dados = dados["fontes"]
        padrao_fontes = re.compile(r"^fontes\s*:", re.MULTILINE)
        m_fontes = padrao_fontes.search(conteudo)
        if m_fontes:
            inicio_fontes = m_fontes.start()
            padrao_proxima = re.compile(r"^[a-zA-Z0-9_-]+\s*:", re.MULTILINE)
            m_prox = padrao_proxima.search(conteudo[m_fontes.end():])
            fim_fontes = (m_fontes.end() + m_prox.start()) if m_prox else len(conteudo)
            trecho_fontes = conteudo[inicio_fontes:fim_fontes]

            for nome_fonte, ativo_val in fontes_dados.items():
                nome_fonte = validar_nome_fonte(nome_fonte)
                ativo_str = "true" if _bool(ativo_val, f"fontes.{nome_fonte}") else "false"
                patt_inline = re.compile(
                    rf"^([ \t]*{re.escape(nome_fonte)}\s*:\s*\{{\s*ativo\s*:\s*)(?:true|false)(\s*\}}.*)$",
                    re.IGNORECASE | re.MULTILINE,
                )
                patt_sub = re.compile(
                    rf"^([ \t]*{re.escape(nome_fonte)}\s*:\s*\r?\n[ \t]*ativo\s*:\s*)(?:true|false)(.*)$",
                    re.IGNORECASE | re.MULTILINE,
                )
                if patt_inline.search(trecho_fontes):
                    trecho_fontes = patt_inline.sub(lambda m: m.group(1) + ativo_str + m.group(2), trecho_fontes, count=1)
                elif patt_sub.search(trecho_fontes):
                    trecho_fontes = patt_sub.sub(lambda m: m.group(1) + ativo_str + m.group(2), trecho_fontes, count=1)
                else:
                    trecho_fontes += f"  {nome_fonte}: {{ ativo: {ativo_str} }}\n"

            conteudo = conteudo[:inicio_fontes] + trecho_fontes + conteudo[fim_fontes:]

    # Escrever YAML temporario e validar
    p.write_text(conteudo, encoding="utf-8")
    try:
        carregar_config(p)
    except Exception as e:
        p.write_text(conteudo_original, encoding="utf-8")
        raise ErroConfig(f"Falha ao validar configuracao apos atualizacao: {e}") from e

    # 3. Tratar Cron
    if "cron" in dados and isinstance(dados["cron"], dict):
        if "intervalo_horas" in dados["cron"]:
            salvar_intervalo_cron(p, dados["cron"]["intervalo_horas"])

    return obter_configuracoes_gestao(p, banco_path)