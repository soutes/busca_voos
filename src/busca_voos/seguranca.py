"""Modulo de seguranca e criptografia simetrica (Fernet / AES-128-CBC + HMAC-SHA256)."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("busca_voos")

CHAVE_ARQUIVO = Path(".segredo.key")


def obter_chave_mestra(pasta: Path | None = None) -> bytes:
    """Carrega ou gera uma chave mestra url-safe de 32 bytes via Fernet.generate_key().
    Salva no arquivo .segredo.key com permissoes restritas.
    """
    caminho_chave = (Path(pasta) if pasta else Path(".")) / CHAVE_ARQUIVO.name
    if caminho_chave.is_file():
        try:
            chave = caminho_chave.read_bytes().strip()
            Fernet(chave)
            return chave
        except Exception as e:
            log.warning("Chave mestra existente invalida (%s), gerando nova chave.", e)

    chave = Fernet.generate_key()
    caminho_chave.parent.mkdir(parents=True, exist_ok=True)
    caminho_chave.write_bytes(chave)
    try:
        os.chmod(caminho_chave, 0o600)
    except OSError:
        pass
    return chave


def criptografar_texto(texto: str, pasta: Path | None = None) -> str:
    """Criptografa o texto usando Fernet e retorna a string de token base64."""
    if not texto:
        return ""
    chave = obter_chave_mestra(pasta)
    f = Fernet(chave)
    token = f.encrypt(texto.encode("utf-8"))
    return token.decode("utf-8")


def descriptografar_texto(token: str, pasta: Path | None = None) -> str:
    """Descriptografa o token de volta para texto puro. Retorna vazio se invalido."""
    if not token or not isinstance(token, str):
        return ""
    try:
        chave = obter_chave_mestra(pasta)
        f = Fernet(chave)
        return f.decrypt(token.strip().encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, Exception) as e:
        log.warning("Falha ao descriptografar token: %s", e)
        return ""


def mascarar_senha(senha: str) -> str:
    """Retorna mascara de senha ou string vazia se senha ausente."""
    if not senha or not senha.strip():
        return ""
    return "••••••••••••"
