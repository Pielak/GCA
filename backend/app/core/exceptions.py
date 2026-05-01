"""Hierarquia canônica de exceções do GCA.

Toda exceção lançada por código de domínio do GCA DEVE ser subclasse de
GCAException. Exceções de bibliotecas externas (SQLAlchemy, httpx, anthropic, etc)
devem ser capturadas e re-lançadas como subclasse apropriada via `raise ... from e`.
"""
from __future__ import annotations
from typing import Any


class GCAException(Exception):
    """Raiz de toda exceção de domínio do GCA."""

    code: str = "GCA_INTERNAL_ERROR"
    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}
        if cause is not None:
            self.__cause__ = cause

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "context": self.context,
        }


class ValidationError(GCAException):
    """Dados de entrada inválidos (formato, tipo, schema)."""
    code = "GCA_VALIDATION_ERROR"
    http_status = 400


class AuthenticationError(GCAException):
    """Credenciais ausentes ou inválidas."""
    code = "GCA_AUTH_ERROR"
    http_status = 401


class AuthorizationError(GCAException):
    """Usuário autenticado mas sem permissão para o recurso."""
    code = "GCA_FORBIDDEN"
    http_status = 403


class NotFoundError(GCAException):
    """Recurso não encontrado."""
    code = "GCA_NOT_FOUND"
    http_status = 404


class ConflictError(GCAException):
    """Conflito de estado (ex: unique violation, optimistic lock)."""
    code = "GCA_CONFLICT"
    http_status = 409


class DomainError(GCAException):
    """Regra de negócio violada."""
    code = "GCA_DOMAIN_ERROR"
    http_status = 422


class ExternalServiceError(GCAException):
    """Falha em serviço externo (HTTP, DB, fila, etc)."""
    code = "GCA_EXTERNAL_SERVICE"
    http_status = 502


class ConfigurationError(GCAException):
    """Configuração ausente ou inválida (env var, secret, settings)."""
    code = "GCA_CONFIG_ERROR"
    http_status = 500


class LLMError(ExternalServiceError):
    """Falha em chamada a provedor LLM (Anthropic, OpenAI, Gemini)."""
    code = "GCA_LLM_ERROR"


class CryptoError(GCAException):
    """Falha em operação criptográfica (Fernet, RSA, hash)."""
    code = "GCA_CRYPTO_ERROR"
    http_status = 500


class GatekeeperError(DomainError):
    """Código gerado reprovado pelo Gatekeeper."""
    code = "GCA_GATEKEEPER_REJECTED"
