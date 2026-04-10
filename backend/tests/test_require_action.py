import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from fastapi import HTTPException

from app.dependencies.require_action import resolve_user_role_in_project


@pytest.mark.asyncio
class TestResolveUserRole:

    async def test_member_with_role_returns_role(self):
        db = AsyncMock()
        user_id = uuid4()
        project_id = uuid4()

        with patch("app.dependencies.require_action.get_user_project_role", return_value="gp"), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=False):
            role = await resolve_user_role_in_project(user_id, project_id, db)
            assert role == "gp"

    async def test_admin_without_membership_returns_admin_viewer(self):
        db = AsyncMock()
        user_id = uuid4()
        project_id = uuid4()

        with patch("app.dependencies.require_action.get_user_project_role", return_value=None), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=True):
            role = await resolve_user_role_in_project(user_id, project_id, db)
            assert role == "admin_viewer"

    async def test_admin_with_membership_returns_member_role(self):
        db = AsyncMock()
        user_id = uuid4()
        project_id = uuid4()

        with patch("app.dependencies.require_action.get_user_project_role", return_value="gp"), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=True):
            role = await resolve_user_role_in_project(user_id, project_id, db)
            assert role == "gp"

    async def test_non_member_non_admin_raises_403(self):
        db = AsyncMock()
        user_id = uuid4()
        project_id = uuid4()

        with patch("app.dependencies.require_action.get_user_project_role", return_value=None), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await resolve_user_role_in_project(user_id, project_id, db)
            assert exc_info.value.status_code == 403
