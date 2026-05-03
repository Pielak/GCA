"""
Testes do Module CodeGen — Fase 3
Testa geração de código, mapeamento de frameworks e classificação de testes.

DT-085 (2026-05-03): testes que exercitam `generate_module_from_candidate`
agora mockam `check_ocg_maturity_gate` para passar pelo gate (introduzido
pelo MVP 31). Sem o mock, o gate levanta HTTPException 404 antes da lógica
sob teste — resultando em retry × 3 e fail genérico.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.module_codegen_service import ModuleCodegenService, TEST_FRAMEWORK_MAP


class TestFrameworkMap:
    """Testes do mapeamento linguagem → framework de teste."""

    def test_framework_map_has_python(self):
        """Python deve mapear para pytest."""
        assert TEST_FRAMEWORK_MAP["python"] == "pytest"

    def test_framework_map_has_typescript(self):
        """TypeScript deve mapear para jest."""
        assert TEST_FRAMEWORK_MAP["typescript"] == "jest"

    def test_framework_map_has_javascript(self):
        """JavaScript deve mapear para jest."""
        assert TEST_FRAMEWORK_MAP["javascript"] == "jest"

    def test_framework_map_has_java(self):
        """Java deve mapear para junit5."""
        assert TEST_FRAMEWORK_MAP["java"] == "junit5"

    def test_framework_map_has_go(self):
        """Go deve mapear para go_test."""
        assert TEST_FRAMEWORK_MAP["go"] == "go_test"

    def test_framework_map_has_rust(self):
        """Rust deve mapear para cargo_test."""
        assert TEST_FRAMEWORK_MAP["rust"] == "cargo_test"

    def test_framework_map_has_csharp(self):
        """C# deve mapear para xunit."""
        assert TEST_FRAMEWORK_MAP["csharp"] == "xunit"

    def test_framework_map_has_expected_keys(self):
        """Verifica que todas as linguagens principais estão mapeadas."""
        expected_keys = {"python", "typescript", "javascript", "java", "go", "rust", "csharp", "ruby", "php"}
        assert expected_keys.issubset(set(TEST_FRAMEWORK_MAP.keys()))


class TestModuleCodegenService:
    """Testes do serviço de geração de código."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_generate_with_missing_candidate_returns_none(self, mock_db):
        """Geração com candidato inexistente deve retornar None.

        DT-085: mocka gate de OCG (MVP 31) para que o teste exercite a
        lógica de "candidato inexistente" e não falhe no gate antes.
        """
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch(
            "app.services.module_codegen_service.check_ocg_maturity_gate",
            new=AsyncMock(return_value=None),  # gate liberado
        ):
            service = ModuleCodegenService(mock_db)
            result = await service.generate_module_from_candidate(
                project_id=uuid4(),
                module_candidate_id=uuid4(),
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_with_unapproved_candidate_returns_none(self, mock_db):
        """Geração com candidato não aprovado deve retornar None.

        DT-085: mocka gate de OCG (MVP 31).
        """
        candidate = MagicMock()
        candidate.status = "suggested"
        candidate.name = "TestModule"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = candidate
        mock_db.execute.return_value = mock_result

        with patch(
            "app.services.module_codegen_service.check_ocg_maturity_gate",
            new=AsyncMock(return_value=None),  # gate liberado
        ):
            service = ModuleCodegenService(mock_db)
            result = await service.generate_module_from_candidate(
                project_id=uuid4(),
                module_candidate_id=uuid4(),
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_module_status_not_found(self, mock_db):
        """Status de módulo inexistente deve retornar None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = ModuleCodegenService(mock_db)
        result = await service.get_module_status(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_module_status_returns_dict(self, mock_db):
        """Status de módulo existente retorna dict com campos corretos."""
        module = MagicMock()
        module.id = uuid4()
        module.name = "AuthModule"
        module.status = "generating"
        module.error_message = None
        module.generation_latency_ms = None
        module.generated_at = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = module
        mock_db.execute.return_value = mock_result

        service = ModuleCodegenService(mock_db)
        result = await service.get_module_status(module.id)

        assert result is not None
        assert result["status"] == "generating"
        assert result["name"] == "AuthModule"

    @pytest.mark.asyncio
    async def test_list_modules_empty(self, mock_db):
        """Lista de módulos vazia retorna lista vazia."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        service = ModuleCodegenService(mock_db)
        result = await service.list_modules(uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_list_tests_empty(self, mock_db):
        """Lista de testes vazia retorna lista vazia."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        service = ModuleCodegenService(mock_db)
        result = await service.list_tests(uuid4())
        assert result == []


class TestTestTypeClassification:
    """Testes de classificação de tipo de teste."""

    def test_unit_test_classification(self):
        """Caminho com 'unit' deve ser classificado como unit."""
        result = ModuleCodegenService.classify_test_type("tests/unit/test_auth.py")
        assert result == "unit"

    def test_integration_test_classification(self):
        """Caminho com 'integration' deve ser classificado como integration."""
        result = ModuleCodegenService.classify_test_type("tests/integration/test_auth_db.py")
        assert result == "integration"

    def test_uat_test_classification(self):
        """Caminho com 'uat' deve ser classificado como uat."""
        result = ModuleCodegenService.classify_test_type("tests/uat/test_login_flow.py")
        assert result == "uat"

    def test_e2e_classified_as_uat(self):
        """Caminho com 'e2e' deve ser classificado como uat."""
        result = ModuleCodegenService.classify_test_type("tests/e2e/test_full_flow.py")
        assert result == "uat"

    def test_acceptance_classified_as_uat(self):
        """Caminho com 'acceptance' deve ser classificado como uat."""
        result = ModuleCodegenService.classify_test_type("tests/acceptance/test_user_journey.py")
        assert result == "uat"

    def test_unknown_path_defaults_to_unit(self):
        """Caminho sem indicação clara deve ser classificado como unit."""
        result = ModuleCodegenService.classify_test_type("tests/test_something.py")
        assert result == "unit"

    def test_integracao_classified_as_integration(self):
        """Caminho com 'integracao' (PT-BR) deve ser classificado como integration."""
        result = ModuleCodegenService.classify_test_type("tests/integracao/test_api.py")
        assert result == "integration"
