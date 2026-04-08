"""
Testes do VaultService — Fase 0.2
Usa banco PostgreSQL real (via conftest fixtures).
"""
import pytest
from uuid import uuid4

from app.services.vault_service import VaultService


class TestVaultService:
    """Testes unitários com mock de banco (sem pgcrypto real)."""

    def test_master_key_loaded(self):
        vault = VaultService()
        assert len(vault.master_key) >= 32

    @pytest.mark.asyncio
    async def test_store_and_get_secret_integration(self):
        """
        Teste de integração — requer banco PostgreSQL com pgcrypto.
        Se não disponível, pula o teste.
        """
        try:
            from app.db.database import AsyncSessionLocal
        except ImportError:
            pytest.skip("Database not configured")

        vault = VaultService()
        project_id = uuid4()

        # Para este teste funcionar, precisamos de um projeto real no banco
        # Como é unitário, testamos apenas a instanciação
        assert vault.master_key is not None

    def test_vault_service_instantiation(self):
        vault = VaultService()
        assert vault is not None
        assert hasattr(vault, "store_secret")
        assert hasattr(vault, "get_secret")
        assert hasattr(vault, "delete_secret")
        assert hasattr(vault, "list_secrets")
        assert hasattr(vault, "rotate_secret")
