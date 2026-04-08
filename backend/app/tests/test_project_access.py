"""
Testes de verify_project_access — Fase 0.3
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from app.dependencies.project_access import verify_project_access, get_user_project_role


class TestVerifyProjectAccess:

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_admin_without_role_gets_403(self, mock_db):
        """Admin sem papel no projeto recebe 403."""
        admin_user = MagicMock()
        admin_user.is_admin = True
        admin_user.id = uuid4()

        # Mock: user found, but no role in project
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = admin_user
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[user_result, role_result])

        with pytest.raises(HTTPException) as exc_info:
            await verify_project_access(uuid4(), admin_user.id, mock_db)

        assert exc_info.value.status_code == 403
        assert "log de auditoria" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_admin_with_role_succeeds(self, mock_db):
        """Admin com papel no projeto acessa normalmente."""
        admin_user = MagicMock()
        admin_user.is_admin = True
        admin_user.id = uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = admin_user
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = "developer"

        mock_db.execute = AsyncMock(side_effect=[user_result, role_result])

        role = await verify_project_access(uuid4(), admin_user.id, mock_db)
        assert role == "developer"

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self, mock_db):
        """Usuário sem papel no projeto recebe 403."""
        regular_user = MagicMock()
        regular_user.is_admin = False
        regular_user.id = uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = regular_user
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[user_result, role_result])

        with pytest.raises(HTTPException) as exc_info:
            await verify_project_access(uuid4(), regular_user.id, mock_db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_wrong_role_gets_403(self, mock_db):
        """Usuário com papel errado recebe 403."""
        regular_user = MagicMock()
        regular_user.is_admin = False
        regular_user.id = uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = regular_user
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = "viewer"

        mock_db.execute = AsyncMock(side_effect=[user_result, role_result])

        with pytest.raises(HTTPException) as exc_info:
            await verify_project_access(uuid4(), regular_user.id, mock_db, required_roles=["gp"])
        assert exc_info.value.status_code == 403
        assert "viewer" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_gp_accesses_own_project(self, mock_db):
        """GP acessa projeto normalmente."""
        gp_user = MagicMock()
        gp_user.is_admin = False
        gp_user.id = uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = gp_user
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = "gp"

        mock_db.execute = AsyncMock(side_effect=[user_result, role_result])

        role = await verify_project_access(uuid4(), gp_user.id, mock_db, required_roles=["gp"])
        assert role == "gp"

    @pytest.mark.asyncio
    async def test_user_not_found_gets_401(self, mock_db):
        """Usuário inexistente recebe 401."""
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(return_value=user_result)

        with pytest.raises(HTTPException) as exc_info:
            await verify_project_access(uuid4(), uuid4(), mock_db)
        assert exc_info.value.status_code == 401
