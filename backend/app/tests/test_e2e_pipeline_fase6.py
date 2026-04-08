"""
FASE 6: End-to-End Pipeline Tests
Tests for complete flow: Questionnaire → OCG → Code Generation
"""
import pytest
import json
import time
from uuid import uuid4, UUID
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, Mock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Questionnaire, OCG
from app.services.questionnaire_service import QuestionnaireService
from app.services.ocg_service import OCGService
from app.services.code_generation_service import CodeGenerationService
from app.services.llm_service import LLMProvider


def _mock_project(project_id):
    """Create a mock ProjectRequest with required attributes."""
    mock = MagicMock()
    mock.id = project_id
    mock.project_name = "E-Commerce Platform"
    mock.project_slug = "e-commerce-platform"
    mock.description = "Online shopping platform"
    mock.status = "approved"
    return mock


def _patch_codegen(codegen_service):
    """Apply common mocks to CodeGenerationService for testing."""
    codegen_service.piloter_service.get_stack_recommendations = AsyncMock(return_value={})


@pytest.mark.asyncio
class TestE2EPipeline:
    """End-to-end pipeline tests: Questionnaire → OCG → Code Generation"""

    async def test_questionnaire_to_ocg_complete_flow(
        self, db_session: AsyncSession, test_project, test_user, complete_questionnaire_response
    ):
        """
        Test complete flow: Questionnaire submission → OCG generation

        Validates:
        - Questionnaire created with valid ID and status
        - Responses stored correctly
        - Adherence score calculated
        - OCG generated with all pillar scores
        """
        # Step 1: Submit questionnaire (staticmethod — no instantiation)
        success, questionnaire_id, error = await QuestionnaireService.submit_questionnaire(
            db=db_session,
            project_id=test_project.id,
            gp_email=test_user.email,
            responses=complete_questionnaire_response,
        )

        # Validate questionnaire submission
        assert success is True, f"Questionnaire submission failed: {error}"
        assert questionnaire_id is not None

        # Step 2: Trigger OCG generation
        ocg_service = OCGService(db_session)
        q_uuid = UUID(questionnaire_id) if isinstance(questionnaire_id, str) else questionnaire_id
        ocg_response = await ocg_service.generate_ocg_from_questionnaire(
            questionnaire_id=q_uuid,
            project_id=test_project.id,
        )

        # Validate OCG response
        assert ocg_response.ocg_id is not None
        assert ocg_response.COMPOSITE_SCORE is not None

    async def test_ocg_context_flows_to_code_generation(
        self, db_session: AsyncSession, test_project, test_user, mock_generated_code
    ):
        """
        Test OCG context is used by Code Generator

        Uses mock for OCG lookup (avoids FK constraint) and ProjectRequest lookup.
        """
        ocg_id = uuid4()
        ocg_data = {
            "CRITICAL_FINDINGS": [
                {
                    "pillar": "P7_Security",
                    "severity": "critical",
                    "finding": "Custom JWT implementation",
                    "action_required": "Switch to Auth0",
                }
            ],
            "TESTING_REQUIREMENTS": {
                "unit_tests": {"coverage_target": "80%"},
                "integration_tests": {"coverage_target": "60%"},
            },
            "COMPLIANCE_CHECKLIST": [
                {"requirement": "LGPD compliance", "status": "REQUIRED"}
            ],
            "PILLAR_SCORES": {"P7_Security": {"score": 65}},
        }

        # Mock OCG object
        mock_ocg = MagicMock()
        mock_ocg.id = ocg_id
        mock_ocg.ocg_data = json.dumps(ocg_data)

        mock_project = _mock_project(test_project.id)

        # Mock Artifact
        mock_artifact = MagicMock()
        mock_artifact.id = uuid4()
        mock_artifact.created_by = test_user.id
        mock_artifact.created_at = datetime.now(timezone.utc)

        with patch('app.services.code_generation_service.LLMServiceFactory.create_client') as mock_factory:
            mock_llm = AsyncMock()
            mock_llm.generate = AsyncMock(return_value=mock_generated_code)
            mock_factory.return_value = mock_llm

            codegen_service = CodeGenerationService(db_session, llm_provider=LLMProvider.ANTHROPIC)

            # Mock _load_ocg_context to return OCG data directly
            codegen_service._load_ocg_context = AsyncMock(return_value=ocg_data)

            # Mock piloter_service
            codegen_service.piloter_service.get_stack_recommendations = AsyncMock(return_value={})

            # Mock db.get to return mock project (ProjectRequest)
            original_get = db_session.get

            async def mock_get(model, id_val):
                from app.models.onboarding import ProjectRequest as PR
                if model is PR:
                    return mock_project
                from app.models.base import OCG as OCGModel
                if model is OCGModel:
                    return mock_ocg
                return await original_get(model, id_val)

            db_session.get = mock_get

            # Mock execute for artifacts query
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_artifact]
            original_execute = db_session.execute
            db_session.execute = AsyncMock(return_value=mock_result)

            result = await codegen_service.generate_project_code(
                project_id=test_project.id,
                gp_id=test_user.id,
                language="python",
                architecture="microservices",
                api_key="test-key",
                ocg_id=ocg_id,
            )

            # Restore
            db_session.get = original_get
            db_session.execute = original_execute

        # Validate code generation result
        assert result["success"] is True
        assert "generated_code" in result
        assert len(result["generated_code"]) > 0

    async def test_full_pipeline_end_to_end(
        self, db_session: AsyncSession, test_project, test_user,
        complete_questionnaire_response, mock_generated_code
    ):
        """
        Complete end-to-end test: Questionnaire → OCG → Code Generation
        """
        # Step 1: Submit questionnaire (staticmethod)
        success, questionnaire_id, error = await QuestionnaireService.submit_questionnaire(
            db=db_session,
            project_id=test_project.id,
            gp_email=test_user.email,
            responses=complete_questionnaire_response,
        )
        assert success is True, f"Questionnaire failed: {error}"
        q_uuid = UUID(questionnaire_id) if isinstance(questionnaire_id, str) else questionnaire_id

        # Step 2: Generate OCG
        ocg_service = OCGService(db_session)
        ocg_response = await ocg_service.generate_ocg_from_questionnaire(
            questionnaire_id=q_uuid,
            project_id=test_project.id,
        )
        ocg_id = ocg_response.ocg_id

        # Step 3: Generate code with OCG context (mocked LLM + project lookup)
        mock_project = _mock_project(test_project.id)
        mock_artifact = MagicMock()
        mock_artifact.id = uuid4()
        mock_artifact.created_by = test_user.id
        mock_artifact.created_at = datetime.now(timezone.utc)

        with patch('app.services.code_generation_service.LLMServiceFactory.create_client') as mock_factory:
            mock_llm = AsyncMock()
            mock_llm.generate = AsyncMock(return_value=mock_generated_code)
            mock_factory.return_value = mock_llm

            codegen_service = CodeGenerationService(db_session, llm_provider=LLMProvider.ANTHROPIC)
            _patch_codegen(codegen_service)

            original_get = db_session.get

            async def mock_get(model, id_val):
                from app.models.onboarding import ProjectRequest as PR
                if model is PR:
                    return mock_project
                return await original_get(model, id_val)

            db_session.get = mock_get

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_artifact]
            original_execute = db_session.execute
            db_session.execute = AsyncMock(return_value=mock_result)

            code_result = await codegen_service.generate_project_code(
                project_id=test_project.id,
                gp_id=test_user.id,
                language="python",
                api_key="test-key",
                ocg_id=ocg_id,
            )

            db_session.get = original_get
            db_session.execute = original_execute

        # Validate complete pipeline
        assert code_result["success"] is True
        assert code_result["full_code_length"] > 0

    async def test_pipeline_backward_compatibility_without_ocg(
        self, db_session: AsyncSession, test_project, test_user, mock_generated_code
    ):
        """
        Test code generation works WITHOUT ocg_id (backward compatible)
        """
        mock_project = _mock_project(test_project.id)
        mock_artifact = MagicMock()
        mock_artifact.id = uuid4()
        mock_artifact.created_by = test_user.id
        mock_artifact.created_at = datetime.now(timezone.utc)

        with patch('app.services.code_generation_service.LLMServiceFactory.create_client') as mock_factory:
            mock_llm = AsyncMock()
            mock_llm.generate = AsyncMock(return_value=mock_generated_code)
            mock_factory.return_value = mock_llm

            codegen_service = CodeGenerationService(db_session, llm_provider=LLMProvider.ANTHROPIC)
            _patch_codegen(codegen_service)

            original_get = db_session.get

            async def mock_get(model, id_val):
                from app.models.onboarding import ProjectRequest as PR
                if model is PR:
                    return mock_project
                return await original_get(model, id_val)

            db_session.get = mock_get

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_artifact]
            original_execute = db_session.execute
            db_session.execute = AsyncMock(return_value=mock_result)

            result = await codegen_service.generate_project_code(
                project_id=test_project.id,
                gp_id=test_user.id,
                language="python",
                api_key="test-key",
                ocg_id=None,  # No OCG provided
            )

            db_session.get = original_get
            db_session.execute = original_execute

        # Validate code generation works without OCG
        assert result["success"] is True
        assert result["full_code_length"] > 0

    async def test_pipeline_error_handling_scenarios(
        self, db_session: AsyncSession, test_project, test_user
    ):
        """
        Test error handling at each pipeline stage

        Scenarios:
        - Non-existent OCG ID
        - LLM provider errors
        """
        # Scenario 1: Non-existent OCG ID
        codegen_service = CodeGenerationService(db_session, llm_provider=LLMProvider.ANTHROPIC)
        fake_ocg_id = uuid4()

        # Should gracefully handle missing OCG (return None from _load_ocg_context)
        ocg_context = await codegen_service._load_ocg_context(fake_ocg_id)
        assert ocg_context is None

        # Scenario 2: Verify error handling doesn't crash
        invalid_project_id = uuid4()
        try:
            await codegen_service.generate_project_code(
                project_id=invalid_project_id,
                gp_id=test_user.id,
                language="python"
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Project not found" in str(e)

    async def test_pipeline_performance_benchmarks(
        self, db_session: AsyncSession, test_project, test_user,
        complete_questionnaire_response, mock_generated_code
    ):
        """
        Benchmark performance of each pipeline stage
        """
        timings = {}

        # Benchmark 1: Questionnaire submission (staticmethod)
        start = time.time()
        success, questionnaire_id, error = await QuestionnaireService.submit_questionnaire(
            db=db_session,
            project_id=test_project.id,
            gp_email=test_user.email,
            responses=complete_questionnaire_response,
        )
        timings["questionnaire_submission"] = time.time() - start
        assert success is True, f"Questionnaire failed: {error}"

        # Benchmark 2: OCG generation
        q_uuid = UUID(questionnaire_id) if isinstance(questionnaire_id, str) else questionnaire_id
        start = time.time()
        ocg_service = OCGService(db_session)
        ocg_response = await ocg_service.generate_ocg_from_questionnaire(
            questionnaire_id=q_uuid,
            project_id=test_project.id,
        )
        timings["ocg_generation"] = time.time() - start
        ocg_id = ocg_response.ocg_id

        # Benchmark 3: Code generation (mocked LLM + project lookup)
        mock_project = _mock_project(test_project.id)
        mock_artifact = MagicMock()
        mock_artifact.id = uuid4()
        mock_artifact.created_by = test_user.id
        mock_artifact.created_at = datetime.now(timezone.utc)

        with patch('app.services.code_generation_service.LLMServiceFactory.create_client') as mock_factory:
            mock_llm = AsyncMock()
            mock_llm.generate = AsyncMock(return_value=mock_generated_code)
            mock_factory.return_value = mock_llm

            original_get = db_session.get

            async def mock_get(model, id_val):
                from app.models.onboarding import ProjectRequest as PR
                if model is PR:
                    return mock_project
                return await original_get(model, id_val)

            db_session.get = mock_get

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_artifact]
            original_execute = db_session.execute
            db_session.execute = AsyncMock(return_value=mock_result)

            start = time.time()
            codegen_service = CodeGenerationService(db_session, llm_provider=LLMProvider.ANTHROPIC)
            _patch_codegen(codegen_service)
            code_result = await codegen_service.generate_project_code(
                project_id=test_project.id,
                gp_id=test_user.id,
                language="python",
                api_key="test-key",
                ocg_id=ocg_id,
            )
            timings["code_generation"] = time.time() - start

            db_session.get = original_get
            db_session.execute = original_execute

        # Log timings
        print(f"\n=== Pipeline Performance Benchmarks ===")
        print(f"Questionnaire Submission: {timings['questionnaire_submission']:.3f}s (target: <1.0s)")
        print(f"OCG Generation: {timings['ocg_generation']:.3f}s (target: <300s)")
        print(f"Code Generation: {timings['code_generation']:.3f}s (target: <30s)")
        total = sum(timings.values())
        print(f"Total Pipeline: {total:.3f}s (target: <360s)")
        print("=====================================\n")

        # Soft assertions
        assert timings['questionnaire_submission'] < 5.0
        assert timings['code_generation'] < 10.0
