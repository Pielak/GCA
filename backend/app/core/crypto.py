"""Criptografia simétrica para secrets de projeto (PATs, etc.).

Usa **Fernet** (AES-128-CBC + HMAC-SHA256, do pacote `cryptography`) com
chave derivada determinística de ``settings.GCA_MASTER_KEY``.

Por que Fernet:
    - Padrão da indústria, auditado.
    - Pequeno: dependência única (`cryptography`, já presente).
    - Token autenticado (detecta tampering).
    - Formato visível (``gAAAAAB...``), facilitando detecção de valor
      em texto plano inadvertido no banco.

Regra dura (contrato canônico):
    ``decrypt_pat`` NÃO aceita plaintext. Se o valor armazenado não for um
    ciphertext Fernet (não começa com ``gAAAAAB``), levanta ``RuntimeError``.
    Isso impede vazamento silencioso de credencial em claro — toda linha
    existente deve ter sido cifrada por ``encrypt_pat`` antes da persistência.
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


class PatNotEncryptedError(RuntimeError):
    """Levantada quando ``decrypt_pat`` recebe um valor que não é ciphertext
    Fernet. Indica credencial em plaintext inadvertido no banco — caller deve
    tratar como configuração inválida (pedir reconfiguração, não usar a
    credencial)."""


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
    - Se NÃO começa com ``gAAAAA``: levanta ``PatNotEncryptedError``.
      **Não há mais fallback silencioso para plaintext legado** — a política
      canônica (contrato §6.4 / §8 MVP 5) exige que secrets nunca trafeguem
      em claro. Caller deve tratar como configuração inválida.
    - Se começa com prefixo Fernet mas decripta falha (token corrompido ou
      chave master trocada): propaga ``InvalidToken`` — caller loga e pede
      reconfiguração.
    """
    if not stored:
        return stored
    if not stored.startswith(_FERNET_PREFIX):
        raise PatNotEncryptedError(
            "PAT armazenado não está criptografado (Fernet). "
            "Configure o repositório novamente via /projects/{id}/git para "
            "que o valor seja persistido cifrado."
        )
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
