import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4


@pytest.mark.asyncio
class TestSetupStatus:

    async def test_both_configured_returns_ready(self):
        from app.routers.project_setup_router import _check_setup_status
        db = AsyncMock()
        project_id = uuid4()
        with patch("app.routers.project_setup_router._has_repo_configured", return_value=True), \
             patch("app.routers.project_setup_router._has_llm_configured", return_value=True):
            result = await _check_setup_status(db, project_id)
            assert result["repo_configured"] is True
            assert result["llm_configured"] is True
            assert result["ready_to_activate"] is True

    async def test_missing_repo_not_ready(self):
        from app.routers.project_setup_router import _check_setup_status
        db = AsyncMock()
        project_id = uuid4()
        with patch("app.routers.project_setup_router._has_repo_configured", return_value=False), \
             patch("app.routers.project_setup_router._has_llm_configured", return_value=True):
            result = await _check_setup_status(db, project_id)
            assert result["repo_configured"] is False
            assert result["ready_to_activate"] is False

    async def test_missing_llm_not_ready(self):
        from app.routers.project_setup_router import _check_setup_status
        db = AsyncMock()
        project_id = uuid4()
        with patch("app.routers.project_setup_router._has_repo_configured", return_value=True), \
             patch("app.routers.project_setup_router._has_llm_configured", return_value=False):
            result = await _check_setup_status(db, project_id)
            assert result["llm_configured"] is False
            assert result["ready_to_activate"] is False
