"""
OCG to Code Generator Integration Tests
Tests for FASE 5: Integrating high-quality OCG with Code Generator
"""
import pytest
import json
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Questionnaire, OCG
from app.models.onboarding import ProjectRequest
from app.services.ocg_service import OCGService
from app.services.code_generation_service import CodeGenerationService
from app.services.llm_service import LLMProvider
from app.tests.factories import create_test_user, create_test_organization, create_test_project


@pytest.mark.asyncio
class TestOCGCodeGenIntegration:
    """Test OCG integration with Code Generator"""

    async def test_codegen_accepts_ocg_id(self, db_session: AsyncSession):
        """Test that Code Generator accepts ocg_id parameter"""
        # Create test project
        org = await create_test_organization(db_session)
        project = await create_test_project(db_session, organization_id=org.id)

        # Create service
        codegen_service = CodeGenerationService(
            db_session,
            llm_provider=LLMProvider.ANTHROPIC
        )

        # Verify method signature accepts ocg_id
        import inspect
        sig = inspect.signature(codegen_service.generate_project_code)
        assert "ocg_id" in sig.parameters
        assert sig.parameters["ocg_id"].default is None  # Should be optional

    async def test_ocg_context_loading(self, db_session: AsyncSession):
        """Test that OCG context is properly loaded"""
        from unittest.mock import AsyncMock, patch

        # Create mock OCG data
        ocg_id = uuid4()
        questionnaire_id = uuid4()
        project_id = uuid4()

        ocg_data = {
            "ocg_id": str(ocg_id),
            "questionnaire_id": str(questionnaire_id),
            "project_id": str(project_id),
            "CRITICAL_FINDINGS": [
                {
                    "pillar": "P7_Security",
                    "severity": "critical",
                    "finding": "Custom JWT implementation",
                    "action_required": "Switch to Auth0"
                }
            ],
            "TESTING_REQUIREMENTS": {
                "unit_tests": {"coverage_target": "80%"},
                "integration_tests": {"coverage_target": "60%"},
                "security_tests": {"coverage_target": "OWASP Top 10"}
            },
            "COMPLIANCE_CHECKLIST": [
                {
                    "requirement": "LGPD compliance",
                    "status": "REQUIRED"
                }
            ],
            "PILLAR_SCORES": {
                "P7_Security": {"score": 68}
            }
        }

        # Create mock OCG object
        mock_ocg = AsyncMock()
        mock_ocg.ocg_data = json.dumps(ocg_data)

        # Mock the database get call
        codegen_service = CodeGenerationService(db_session)
        with patch.object(db_session, 'get', new_callable=AsyncMock, return_value=mock_ocg):
            context = await codegen_service._load_ocg_context(ocg_id)

        # Verify context loaded correctly
        assert context is not None
        assert "critical_findings" in context
        assert len(context["critical_findings"]) > 0
        assert context["critical_findings"][0]["finding"] == "Custom JWT implementation"
        assert "testing_requirements" in context
        assert "compliance_checklist" in context

    async def test_prompt_builder_with_ocg_context(self):
        """Test that prompt builder properly enriches prompt with OCG data"""
        from app.services.code_generation_service import CodeGenerationPromptBuilder

        # Create mock project and artifacts
        class MockProject:
            project_name = "E-Commerce API"
            project_slug = "ecommerce-api"
            description = "Platform for online shopping"

        class MockArtifact:
            name = "Requirements"
            type = "REQUIREMENTS"
            content = "Build secure payment processing system"

        # Create OCG context
        ocg_context = {
            "critical_findings": [
                {
                    "severity": "critical",
                    "finding": "Authentication uses custom JWT",
                    "action_required": "Implement OAuth2 with Auth0"
                }
            ],
            "testing_requirements": {
                "unit_tests": {"coverage_target": "80%"},
                "security_tests": {"coverage_target": "OWASP"}
            },
            "compliance_checklist": [
                {"requirement": "LGPD compliance", "status": "REQUIRED"}
            ]
        }

        # Build prompt without OCG (baseline)
        prompt_without_ocg = CodeGenerationPromptBuilder.build_project_context_prompt(
            project=MockProject(),
            artifacts=[MockArtifact()],
            stack_recommendations={"stack": {"backend": "Python"}},
            ocg_context=None
        )

        # Build prompt with OCG
        prompt_with_ocg = CodeGenerationPromptBuilder.build_project_context_prompt(
            project=MockProject(),
            artifacts=[MockArtifact()],
            stack_recommendations={"stack": {"backend": "Python"}},
            ocg_context=ocg_context
        )

        # Verify OCG context is included
        assert len(prompt_with_ocg) > len(prompt_without_ocg)
        assert "CRITICAL REQUIREMENTS" in prompt_with_ocg
        assert "custom JWT" in prompt_with_ocg.lower() or "Authentication uses custom JWT" in prompt_with_ocg
        assert "Auth0" in prompt_with_ocg
        assert "TESTING STRATEGY" in prompt_with_ocg
        assert "80%" in prompt_with_ocg  # Coverage target
        assert "COMPLIANCE REQUIREMENTS" in prompt_with_ocg
        assert "LGPD" in prompt_with_ocg

    async def test_ocg_context_backward_compatibility(self, db_session: AsyncSession):
        """Test that Code Generator works without OCG (ocg_id=None)"""
        # This is a structural test - verify the method can be called without ocg_id
        org = await create_test_organization(db_session)
        project = await create_test_project(db_session, organization_id=org.id)

        codegen_service = CodeGenerationService(db_session)

        # Should not raise error when ocg_id is not provided
        try:
            # We're not actually calling with LLM, just testing the method accepts None
            import inspect
            sig = inspect.signature(codegen_service.generate_project_code)
            # Call method signature validation
            bound = sig.bind(
                project_id=project.id,
                gp_id=uuid4(),
                language="python",
                architecture="microservices",
                api_key=None,
                ocg_id=None  # Explicitly pass None
            )
            assert bound.arguments["ocg_id"] is None
        except TypeError as e:
            pytest.fail(f"generate_project_code should accept ocg_id=None: {str(e)}")

    async def test_ocg_not_found_handling(self, db_session: AsyncSession):
        """Test that invalid OCG ID is handled gracefully"""
        codegen_service = CodeGenerationService(db_session)

        # Try to load non-existent OCG
        fake_ocg_id = uuid4()
        context = await codegen_service._load_ocg_context(fake_ocg_id)

        # Should return None, not raise error
        assert context is None
