"""Testes de _check_setup_status — 3 pré-requisitos canônicos.

Alinhado a GCA_CANONICAL_CONTRACT.md §7 (MVP 1) e Task 1 do plano
2026-04-17-project-setup-gate-complete: ready_to_activate exige
repo + llm + questionnaire.
"""
import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4


@pytest.mark.asyncio
class TestSetupStatus:

    async def test_all_three_configured_returns_ready(self):
        from app.routers.project_setup_router import _check_setup_status
        db = AsyncMock()
        project_id = uuid4()
        with patch("app.routers.project_setup_router._has_repo_configured", return_value=True), \
             patch("app.routers.project_setup_router._has_llm_configured", return_value=True), \
             patch("app.routers.project_setup_router._has_questionnaire_submitted", return_value=True):
            result = await _check_setup_status(db, project_id)
            assert result["repo_configured"] is True
            assert result["llm_configured"] is True
            assert result["questionnaire_submitted"] is True
            assert result["ready_to_activate"] is True

    async def test_missing_repo_not_ready(self):
        from app.routers.project_setup_router import _check_setup_status
        db = AsyncMock()
        project_id = uuid4()
        with patch("app.routers.project_setup_router._has_repo_configured", return_value=False), \
             patch("app.routers.project_setup_router._has_llm_configured", return_value=True), \
             patch("app.routers.project_setup_router._has_questionnaire_submitted", return_value=True):
            result = await _check_setup_status(db, project_id)
            assert result["repo_configured"] is False
            assert result["ready_to_activate"] is False

    async def test_missing_llm_not_ready(self):
        from app.routers.project_setup_router import _check_setup_status
        db = AsyncMock()
        project_id = uuid4()
        with patch("app.routers.project_setup_router._has_repo_configured", return_value=True), \
             patch("app.routers.project_setup_router._has_llm_configured", return_value=False), \
             patch("app.routers.project_setup_router._has_questionnaire_submitted", return_value=True):
            result = await _check_setup_status(db, project_id)
            assert result["llm_configured"] is False
            assert result["ready_to_activate"] is False

    async def test_missing_questionnaire_not_ready(self):
        from app.routers.project_setup_router import _check_setup_status
        db = AsyncMock()
        project_id = uuid4()
        with patch("app.routers.project_setup_router._has_repo_configured", return_value=True), \
             patch("app.routers.project_setup_router._has_llm_configured", return_value=True), \
             patch("app.routers.project_setup_router._has_questionnaire_submitted", return_value=False):
            result = await _check_setup_status(db, project_id)
            assert result["questionnaire_submitted"] is False
            assert result["ready_to_activate"] is False
