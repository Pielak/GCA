"""
Testes do LiveDocs — Fase 4
Testa geração de changelog, índice de documentação e seções.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.livedocs_service import LiveDocsService


class TestChangelogEntry:
    """Testes de geração de entradas de changelog."""

    def test_changelog_entry_format(self):
        """Entrada de changelog deve conter timestamp, event_type, label e formatted."""
        entry = LiveDocsService.generate_changelog_entry(
            "document_ingested",
            {"summary": "Documento requisitos.pdf ingerido"},
        )
        assert "timestamp" in entry
        assert entry["event_type"] == "document_ingested"
        assert entry["label"] == "Documento ingerido"
        assert "formatted" in entry
        assert "Documento ingerido" in entry["formatted"]

    def test_changelog_entry_module_generated(self):
        """Entrada de módulo gerado deve ter label correto."""
        entry = LiveDocsService.generate_changelog_entry(
            "module_generated",
            {"summary": "Módulo AuthService gerado"},
        )
        assert entry["label"] == "Módulo gerado"

    def test_changelog_entry_unknown_event(self):
        """Evento desconhecido deve usar event_type como label."""
        entry = LiveDocsService.generate_changelog_entry(
            "custom_event",
            {"summary": "Algo aconteceu"},
        )
        assert entry["label"] == "custom_event"
        assert entry["event_type"] == "custom_event"

    def test_changelog_entry_has_details(self):
        """Entrada deve preservar detalhes originais."""
        details = {"summary": "Teste", "extra": "info"}
        entry = LiveDocsService.generate_changelog_entry("ocg_updated", details)
        assert entry["details"] == details

    def test_changelog_all_known_events(self):
        """Todos os eventos conhecidos devem ter labels em português-BR."""
        known_events = [
            "document_ingested", "module_generated", "ocg_updated",
            "test_generated", "docs_refreshed",
            "gatekeeper_approved", "gatekeeper_rejected",
        ]
        for event in known_events:
            entry = LiveDocsService.generate_changelog_entry(event, {"summary": "teste"})
            # Label não deve ser igual ao event_type (deve ser traduzido)
            assert entry["label"] != event


class TestLiveDocsService:
    """Testes do serviço de documentação viva."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_doc_index_returns_list(self, mock_db):
        """Índice de docs deve retornar uma lista."""
        # GitService.list_files retorna lista vazia quando sem config
        git_result = MagicMock()
        git_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = git_result

        service = LiveDocsService(mock_db)
        result = await service.get_doc_index(uuid4())
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_doc_section_not_found_returns_none(self, mock_db):
        """Seção inexistente deve retornar None."""
        git_result = MagicMock()
        git_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = git_result

        service = LiveDocsService(mock_db)
        result = await service.get_doc_section(uuid4(), "docs/NONEXISTENT.md")
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_initial_without_ocg(self, mock_db):
        """Geração inicial sem OCG deve retornar erro."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = LiveDocsService(mock_db)
        result = await service.generate_initial_documentation(uuid4())
        assert "error" in result
        assert result["sections"] == []

    @pytest.mark.asyncio
    async def test_update_on_document_not_found(self, mock_db):
        """Atualização com documento inexistente deve retornar updated=False."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = LiveDocsService(mock_db)
        result = await service.update_on_document_ingested(uuid4(), uuid4())
        assert result["updated"] is False

    @pytest.mark.asyncio
    async def test_update_on_module_not_found(self, mock_db):
        """Atualização com módulo inexistente deve retornar updated=False."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = LiveDocsService(mock_db)
        result = await service.update_on_module_generated(uuid4(), uuid4())
        assert result["updated"] is False

    @pytest.mark.asyncio
    async def test_refresh_without_ocg(self, mock_db):
        """Refresh sem OCG deve retornar refreshed=False."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = LiveDocsService(mock_db)
        result = await service.refresh_ocg_documentation(uuid4())
        assert result["refreshed"] is False
