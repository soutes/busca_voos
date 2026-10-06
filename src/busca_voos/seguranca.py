"""Modulo de seguranca e criptografia simetrica (Fernet / AES-128-CBC + HMAC-SHA256)."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("busca_voos")

CHAVE_ARQUIVO = Path(".segredo.key")


class ErroChave(Exception):
    """A chave mestra esta ausente ou invalida. Nunca e regenerada em silencio."""


def _caminho_chave(pasta: Path | None) -> Path:
    return (Path(pasta) if pasta else Path(".")) / CHAVE_ARQUIVO.name


def obter_chave_mestra(pasta: Path | None = None, criar: bool = True) -> bytes:
    """Carrega a chave mestra (Fernet) de ``.segredo.key``; cria se nao existir e ``criar=True``.

    * Arquivo existente mas invalido: levanta ``ErroChave``. NAO gera outra chave,
      porque isso sobrescreveria a original e tornaria a senha salva irrecuperavel.
    * Criacao atomica (O_EXCL) ja com permissao 0600: sem janela em que o arquivo
      exista legivel por outros usuarios e sem corrida entre dois processos.
    """
    caminho = _caminho_chave(pasta)
    if caminho.is_file():
        chave = caminho.read_bytes().strip()
        try:
            Fernet(chave)
        except Exception as e:
            raise ErroChave(
                f"A chave mestra '{caminho}' existe, mas e invalida ({e}). "
                "Nao vou sobrescreve-la: restaure o arquivo do seu backup. "
                "Se nao houver backup, apague-o e cadastre a senha de e-mail de novo."
            ) from e
        return chave

    if not criar:
        raise ErroChave(
            f"Chave mestra '{caminho}' nao encontrada: a senha salva nao pode ser lida. "
            "Cadastre a senha de e-mail de novo."
        )

    chave = Fernet.generate_key()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(caminho, flags, 0o600)
    except FileExistsError:  # outro processo criou entre o is_file() e agora
        return obter_chave_mestra(pasta, criar=False)
    with os.fdopen(fd, "wb") as f:
        f.write(chave)
    return chave


def criptografar_texto(texto: str, pasta: Path | None = None) -> str:
    """Criptografa o texto usando Fernet e retorna a string de token base64.

    Levanta ``ErroChave`` se a chave existente for invalida.
    """
    if not texto:
        return ""
    f = Fernet(obter_chave_mestra(pasta))
    return f.encrypt(texto.encode("utf-8")).decode("utf-8")


def descriptografar_texto(token: str, pasta: Path | None = None) -> str:
    """Descriptografa o token de volta para texto puro. Retorna vazio se nao for possivel.

    Nunca cria nem altera a chave: ler nao pode ter efeito colateral.
    """
    if not token or not isinstance(token, str):
        return ""
    try:
        f = Fernet(obter_chave_mestra(pasta, criar=False))
        return f.decrypt(token.strip().encode("utf-8")).decode("utf-8")
    except ErroChave as e:
        log.error("%s", e)
        return ""
    except (InvalidToken, ValueError) as e:
        log.warning("Falha ao descriptografar token (chave diferente da usada ao salvar?): %s", type(e).__name__)
        return ""


def mascarar_senha(senha: str) -> str:
    """Retorna mascara de senha ou string vazia se senha ausente."""
    if not senha or not senha.strip():
        return ""
    return "••••••••••••"
