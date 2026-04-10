import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from app.services.gp_management_service import GPManagementService


@pytest.mark.asyncio
class TestGPManagement:

    async def test_add_gp_creates_member(self):
        db = AsyncMock()
        service = GPManagementService()
        project_id = uuid4()

        with patch.object(service, "_get_or_create_user", return_value=(uuid4(), False)), \
             patch.object(service, "_check_existing_membership", return_value=None), \
             patch.object(service, "_create_gp_member", return_value=MagicMock()):
            db.get = AsyncMock(return_value=MagicMock(name="Test Project"))
            result = await service.add_gp(db, project_id, "novo@gp.com", uuid4())
            assert result["success"] is True

    async def test_remove_last_gp_fails(self):
        db = AsyncMock()
        service = GPManagementService()

        with patch.object(service, "_count_active_gps", return_value=1):
            result = await service.remove_gp(db, uuid4(), uuid4(), uuid4())
            assert result["success"] is False
            assert "ultimo" in result["error"].lower()

    async def test_remove_gp_with_multiple_succeeds(self):
        db = AsyncMock()
        service = GPManagementService()

        with patch.object(service, "_count_active_gps", return_value=2), \
             patch.object(service, "_deactivate_member", return_value=None):
            result = await service.remove_gp(db, uuid4(), uuid4(), uuid4())
            assert result["success"] is True

    async def test_replace_gp_atomic(self):
        db = AsyncMock()
        service = GPManagementService()

        with patch.object(service, "_get_or_create_user", return_value=(uuid4(), False)), \
             patch.object(service, "_check_existing_membership", return_value=None), \
             patch.object(service, "_deactivate_member", return_value=None), \
             patch.object(service, "_create_gp_member", return_value=MagicMock()):
            result = await service.replace_gp(db, uuid4(), uuid4(), "novo@gp.com", uuid4())
            assert result["success"] is True
