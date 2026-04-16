"""Criptografia simétrica para secrets de projeto (PATs, etc.).

Usa **Fernet** (AES-128-CBC + HMAC-SHA256, do pacote `cryptography`) com
chave derivada determinística de ``settings.GCA_MASTER_KEY``.

Por que Fernet:
    - Padrão da indústria, audited.
    - Pequeno: dependência única (`cryptography`, já presente).
    - Token autenticado (detecta tampering).
    - Formato visível (``gAAAAAB...``), facilitando detecção de
      legacy-plaintext.

Backward-compat:
    ``decrypt_pat`` aceita tanto ciphertext Fernet (decripta) quanto
    plaintext legacy (devolve como está). Isso permite migração gradual:
    valores plaintext existentes continuam funcionando até o próximo
    UPDATE, quando ``encrypt_pat`` os converte para ciphertext.
"""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

# Prefixo de Fernet tokens (padrão definido em cryptography.fernet:
# version byte 0x80 → base64 'gAAAAA').
_FERNET_PREFIX = "gAAAAA"


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """Deriva chave Fernet (32 bytes base64) de ``GCA_MASTER_KEY`` via SHA-256.

    Cached: a derivação é determinística e idempotente, mas a Fernet instance
    é reutilizada para evitar re-criação em loops quentes.
    """
    master = (settings.GCA_MASTER_KEY or "").strip()
    if not master:
        raise RuntimeError(
            "GCA_MASTER_KEY não configurada — necessária para criptografar PATs."
        )
    digest = hashlib.sha256(master.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_pat(plaintext: str) -> str:
    """Criptografa um PAT (ou qualquer secret) usando Fernet.

    Idempotente: se ``plaintext`` já parece ciphertext Fernet (prefixo
    ``gAAAAA``), devolve como está — evita re-encriptar valor já criptografado
    quando a aplicação salva o objeto sem alteração real do PAT.
    """
    if not plaintext:
        return plaintext
    if plaintext.startswith(_FERNET_PREFIX):
        return plaintext  # já criptografado
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_pat(stored: str) -> str:
    """Decripta um PAT armazenado.

    - Se for ciphertext Fernet válido: decripta e devolve plaintext.
    - Se for plaintext legacy (não começa com ``gAAAAA``): devolve como
      está. Isso preserva backward-compat com PATs antigos não-criptografados.
    - Se começa com prefixo Fernet mas decripta falha (token corrompido):
      levanta InvalidToken — caller deve tratar (logar + considerar PAT
      comprometido / pedir reconfigurar).
    """
    if not stored:
        return stored
    if not stored.startswith(_FERNET_PREFIX):
        return stored  # plaintext legacy
    return _get_fernet().decrypt(stored.encode("ascii")).decode("utf-8")


def is_encrypted(stored: str) -> bool:
    """True se ``stored`` parece ser um Fernet ciphertext válido."""
    if not stored or not stored.startswith(_FERNET_PREFIX):
        return False
    try:
        _get_fernet().decrypt(stored.encode("ascii"))
        return True
    except InvalidToken:
        return False
