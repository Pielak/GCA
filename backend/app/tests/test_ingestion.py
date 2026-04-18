"""
Testes de Ingestão + Arguidor — Fase 1
"""
import pytest
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.ingestion_service import IngestionService, EXTENSION_MAP, MAX_FILE_SIZE
from app.services.arguider_service import DocumentExtractor, ArguiderService


# ============================================================================
# Testes do DocumentExtractor
# ============================================================================

class TestDocumentExtractor:
    @pytest.mark.asyncio
    async def test_extract_text_markdown(self):
        ext = DocumentExtractor()
        result = await ext.extract_text(b"# Hello World\nSome content", "markdown")
        assert "Hello World" in result

    @pytest.mark.asyncio
    async def test_extract_text_txt(self):
        ext = DocumentExtractor()
        result = await ext.extract_text(b"Plain text content", "txt")
        assert "Plain text" in result

    @pytest.mark.asyncio
    async def test_extract_text_code(self):
        ext = DocumentExtractor()
        result = await ext.extract_text(b"def hello():\n    print('world')", "code")
        assert "def hello" in result

    @pytest.mark.asyncio
    async def test_extract_text_unknown_binary(self):
        ext = DocumentExtractor()
        result = await ext.extract_text(b"\x00\x01\x02\x03", "other")
        assert result is not None


# ============================================================================
# Testes do IngestionService
# ============================================================================

class TestIngestionService:
    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.add = MagicMock()
        db.delete = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_upload_oversized_file(self, mock_db):
        service = IngestionService(mock_db)
        big_bytes = b"x" * (MAX_FILE_SIZE + 1)
        result = await service.upload_document(
            project_id=uuid4(), uploaded_by=uuid4(),
            file_bytes=big_bytes, original_filename="huge.pdf",
        )
        assert result["status_code"] == 413

    @pytest.mark.asyncio
    async def test_upload_unsupported_type(self, mock_db):
        service = IngestionService(mock_db)
        result = await service.upload_document(
            project_id=uuid4(), uploaded_by=uuid4(),
            file_bytes=b"content", original_filename="file.exe",
        )
        assert result["status_code"] == 400
        assert "não suportado" in result["error"]

    @pytest.mark.asyncio
    async def test_upload_duplicate_detected(self, mock_db):
        dup_doc = MagicMock()
        dup_doc.id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dup_doc
        mock_db.execute.return_value = mock_result

        service = IngestionService(mock_db)
        result = await service.upload_document(
            project_id=uuid4(), uploaded_by=uuid4(),
            file_bytes=b"content", original_filename="doc.pdf",
        )
        assert result.get("duplicate") is True
        assert result["status_code"] == 409

    def test_extension_map_coverage(self):
        """Verifica que todos os tipos mencionados estão mapeados."""
        expected = {"pdf", "docx", "doc", "md", "txt", "png", "jpg", "jpeg",
                    "gif", "webp", "xlsx", "xls", "csv", "py", "ts", "js",
                    "java", "cs", "go", "rs"}
        assert expected.issubset(set(EXTENSION_MAP.keys()))

    def test_max_file_size(self):
        assert MAX_FILE_SIZE == 50 * 1024 * 1024


# ============================================================================
# Testes do ArguiderService
# ============================================================================

class TestArguiderService:
    def test_build_prompt(self):
        # DT-040: DT-012 tornou ArguiderService exigente quanto à chave do
        # projeto (Arguidor é ALTA criticidade §6.2 — sem fallback pra chave
        # global do admin). Teste unitário passa chave fake.
        db = AsyncMock()
        service = ArguiderService(db, project_api_key="sk-test-dummy-key")
        prompt = service._build_prompt(
            doc_text="Conteúdo do documento",
            ocg={"PROJECT_PROFILE": {"name": "Test"}},
            prev=[],
        )
        assert "DOCUMENTO A ANALISAR" in prompt
        assert "OCG ATUAL" in prompt
        assert "Conteúdo do documento" in prompt

    def test_extract_json_valid(self):
        result = ArguiderService._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_extract_json_with_text(self):
        result = ArguiderService._extract_json('Some text before {"key": "value"} and after')
        assert result == {"key": "value"}

    def test_extract_json_invalid(self):
        result = ArguiderService._extract_json("not json at all")
        assert result == {}
