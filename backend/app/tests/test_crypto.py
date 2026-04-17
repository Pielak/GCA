"""Testes do helper de cripto Fernet para PATs (camada base F1)."""
import pytest
from cryptography.fernet import InvalidToken

from app.core.crypto import (
    decrypt_pat,
    encrypt_pat,
    is_encrypted,
    PatNotEncryptedError,
)


# ─────────────────────────── ciclo round-trip ────────────────────────────

def test_encrypt_then_decrypt_returns_original():
    plaintext = "ghp_xRjGTdL3hVo5pH4qABcD123"
    cipher = encrypt_pat(plaintext)
    assert cipher != plaintext
    assert cipher.startswith("gAAAAA")
    assert decrypt_pat(cipher) == plaintext


def test_encrypt_different_plaintexts_produces_different_ciphers():
    """Fernet adiciona IV aleatório — duas encripções do mesmo plaintext
    devolvem ciphers diferentes, ambas decriptáveis para o mesmo valor."""
    plaintext = "secret-token"
    c1 = encrypt_pat(plaintext)
    c2 = encrypt_pat(plaintext)
    assert c1 != c2
    assert decrypt_pat(c1) == plaintext
    assert decrypt_pat(c2) == plaintext


def test_encrypt_idempotent_on_already_encrypted():
    """Re-encriptar valor já cifrado é no-op — evita corromper objeto que
    foi salvo sem modificação real do PAT."""
    plaintext = "my-pat-123"
    cipher = encrypt_pat(plaintext)
    cipher_twice = encrypt_pat(cipher)
    assert cipher == cipher_twice
    # E ainda decripta para o original (não duplo-encriptou)
    assert decrypt_pat(cipher_twice) == plaintext


# ─────────────────────────── política de plaintext ─────────────────────

def test_decrypt_raises_on_legacy_plaintext():
    """PAT plaintext legado (sem prefixo gAAAAA) agora levanta
    PatNotEncryptedError — contrato §6.4 / §8 MVP 5 proíbe secrets em claro
    no banco. Nenhum fallback silencioso."""
    legacy = "ghp_legacyTokenSemFernet123"
    with pytest.raises(PatNotEncryptedError):
        decrypt_pat(legacy)


def test_encrypt_empty_returns_empty():
    assert encrypt_pat("") == ""
    assert encrypt_pat(None) is None  # type: ignore[arg-type]


def test_decrypt_empty_returns_empty():
    assert decrypt_pat("") == ""
    assert decrypt_pat(None) is None  # type: ignore[arg-type]


# ─────────────────────────── detecção / robustez ─────────────────────────

def test_is_encrypted_true_for_real_cipher():
    cipher = encrypt_pat("xyz")
    assert is_encrypted(cipher) is True


def test_is_encrypted_false_for_plaintext():
    assert is_encrypted("plain-token") is False
    assert is_encrypted("") is False


def test_is_encrypted_false_for_corrupt_pseudo_cipher():
    """String que começa com prefixo Fernet mas é inválida → False."""
    fake = "gAAAAA" + "0" * 50  # parece Fernet mas é lixo
    assert is_encrypted(fake) is False


def test_decrypt_corrupt_token_raises():
    """Ciphertext corrompido com prefixo Fernet → InvalidToken (não silent)."""
    fake = "gAAAAA" + "x" * 80
    with pytest.raises(InvalidToken):
        decrypt_pat(fake)
