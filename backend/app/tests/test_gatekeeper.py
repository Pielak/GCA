"""
Testes do Gatekeeper — Fase 2
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.gatekeeper_service import GatekeeperService


class TestGatekeeperService:
    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_get_empty_gatekeeper(self, mock_db):
        """GET gatekeeper sem documentos → summary com zeros."""
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []
        modules_result = MagicMock()
        modules_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[items_result, modules_result])

        service = GatekeeperService(mock_db)
        result = await service.get_project_gatekeeper(uuid4())

        assert result["summary"]["total_gaps"] == 0
        assert result["summary"]["total_modules"] == 0
        assert result["summary"]["has_blockers"] is False

    @pytest.mark.asyncio
    async def test_ignore_item_without_reason_fails(self, mock_db):
        service = GatekeeperService(mock_db)
        result = await service.ignore_item(uuid4(), uuid4(), uuid4(), "")
        assert result["success"] is False
        assert result["status_code"] == 400

    @pytest.mark.asyncio
    async def test_reject_module_without_reason_fails(self, mock_db):
        service = GatekeeperService(mock_db)
        result = await service.reject_module(uuid4(), uuid4(), uuid4(), "")
        assert result["success"] is False
        assert result["status_code"] == 400

    @pytest.mark.asyncio
    async def test_resolve_item_not_found(self, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = GatekeeperService(mock_db)
        result = await service.resolve_item(uuid4(), uuid4(), uuid4(), "fixed")
        assert result is False

    @pytest.mark.asyncio
    async def test_approve_module_not_found(self, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = GatekeeperService(mock_db)
        result = await service.approve_module(uuid4(), uuid4(), uuid4())
        assert result["success"] is False
        assert result["status_code"] == 404

    @pytest.mark.asyncio
    async def test_approve_module_success(self, mock_db):
        module = MagicMock()
        module.id = uuid4()
        module.name = "AuthModule"
        module.status = "suggested"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = module
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        service = GatekeeperService(mock_db)
        result = await service.approve_module(uuid4(), module.id, uuid4())
        assert result["success"] is True
        assert module.status == "approved"

    @pytest.mark.asyncio
    async def test_generate_report_markdown(self, mock_db):
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []
        modules_result = MagicMock()
        modules_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[items_result, modules_result])

        service = GatekeeperService(mock_db)
        md = await service.generate_report_markdown(uuid4())
        assert "Relatório do Gatekeeper" in md
        assert "Gaps:" in md
