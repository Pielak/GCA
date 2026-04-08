"""
Testes do GitService — Fase 0.1
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.services.git_service import GitService, _parse_github_url, _parse_gitlab_url, _parse_bitbucket_url


# ============================================================================
# Testes de URL parsing
# ============================================================================

class TestUrlParsing:
    def test_parse_github_https(self):
        result = _parse_github_url("https://github.com/Pielak/GCA.git")
        assert result == ("Pielak", "GCA")

    def test_parse_github_https_no_git(self):
        result = _parse_github_url("https://github.com/Pielak/GCA")
        assert result == ("Pielak", "GCA")

    def test_parse_github_ssh(self):
        result = _parse_github_url("git@github.com:Pielak/GCA.git")
        assert result == ("Pielak", "GCA")

    def test_parse_github_invalid(self):
        result = _parse_github_url("https://example.com/repo")
        assert result is None

    def test_parse_gitlab_url(self):
        result = _parse_gitlab_url("https://gitlab.com/group/project.git")
        assert result == ("group", "project")

    def test_parse_bitbucket_url(self):
        result = _parse_bitbucket_url("https://bitbucket.org/workspace/repo")
        assert result == ("workspace", "repo")


# ============================================================================
# Testes do GitService com mocks
# ============================================================================

class TestGitServiceConnect:
    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_connect_invalid_provider(self, mock_db):
        service = GitService(mock_db)
        result = await service.connect_repository(
            project_id=uuid4(),
            provider="invalid",
            repository_url="https://github.com/test/repo",
            pat="fake-pat",
        )
        assert result["success"] is False
        assert "Provider inválido" in result["message"]

    @pytest.mark.asyncio
    async def test_verify_connection_no_config(self, mock_db):
        # Simula nenhuma config encontrada
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = GitService(mock_db)
        result = await service.verify_connection(uuid4())
        assert result["connected"] is False

    @pytest.mark.asyncio
    async def test_commit_file_no_config(self, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = GitService(mock_db)
        result = await service.commit_file(
            project_id=uuid4(),
            file_path="test.md",
            content="hello",
            commit_message="test",
        )
        assert result["success"] is False
        assert "não configurado" in result["message"]

    @pytest.mark.asyncio
    async def test_get_file_content_no_config(self, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = GitService(mock_db)
        result = await service.get_file_content(uuid4(), "test.md")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_files_no_config(self, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = GitService(mock_db)
        result = await service.list_files(uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_initialize_structure_no_config(self, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = GitService(mock_db)
        result = await service.initialize_repository_structure(uuid4())
        assert result is False
