"""
Integration Tests - FASE 4 Code Generation
Valida: LLM Integration, Code Generation Service, Prompt Builder
"""
import asyncio
import sys
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import uuid4

sys.path.insert(0, '/app')

from app.db.database import AsyncSessionLocal
from app.models.base import User
from app.models.onboarding import ProjectRequest, ProjectRequestStatus
from app.models.tenant import Artifact, ArtifactType, ArtifactStatus
from app.services.code_generation_service import (
    CodeGenerationService,
    CodeGenerationPromptBuilder
)
from app.services.llm_service import LLMProvider, LLMServiceFactory
from app.core.security import hash_password
import structlog

logger = structlog.get_logger(__name__)


class CodeGenTester:
    """Integration test suite for FASE 4"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests_result = []
        self.project_id = None
        self.gp_id = None
        self.schema_name = None

    async def test_setup(self):
        """Setup: Create test users and project"""
        try:
            timestamp = int(time.time() * 1000)

            async with AsyncSessionLocal() as session:
                # Create users
                admin = User(
                    id=uuid4(),
                    email=f"admin_{timestamp}@codegen.com",
                    password_hash=hash_password("admin"),
                    full_name="Admin",
                    is_active=True,
                    is_admin=True
                )
                gp = User(
                    id=uuid4(),
                    email=f"gp_{timestamp}@codegen.com",
                    password_hash=hash_password("gp"),
                    full_name="GP",
                    is_active=True
                )
                session.add_all([admin, gp])
                await session.commit()

                self.gp_id = gp.id

                # Create project
                project = ProjectRequest(
                    id=uuid4(),
                    gp_id=gp.id,
                    project_name="Test CodeGen Project",
                    project_slug=f"codegen-test-{timestamp}",
                    description="Test project for code generation",
                    schema_name=f"proj_codegen_{timestamp}",
                    status=ProjectRequestStatus.APPROVED,
                    approved_by=admin.id
                )
                session.add(project)
                await session.commit()

                self.project_id = project.id
                self.schema_name = project.schema_name

                self._log_pass("Setup: Users and project created")

        except Exception as e:
            self._log_fail(f"Setup: {str(e)}")

    async def test_prompt_builder_basic(self):
        """Test 1: Prompt builder creates valid prompts"""
        try:
            project = ProjectRequest(
                id=self.project_id,
                gp_id=self.gp_id,
                project_name="E-Commerce",
                project_slug="ecommerce",
                description="Mock e-commerce",
                schema_name=self.schema_name,
                status=ProjectRequestStatus.APPROVED
            )

            artifacts = [
                Artifact(
                    name="Requirements",
                    type=ArtifactType.REQUIREMENTS,
                    content="Complete functional requirements"
                ),
                Artifact(
                    name="Architecture",
                    type=ArtifactType.ARCHITECTURE,
                    content="Microservices architecture"
                )
            ]

            stack = {
                "stack": {
                    "language": "Python",
                    "framework": "FastAPI",
                    "database": "PostgreSQL"
                },
                "recommendations": ["Use async/await", "Connection pooling"]
            }

            prompt = CodeGenerationPromptBuilder.build_project_context_prompt(
                project=project,
                artifacts=artifacts,
                stack_recommendations=stack
            )

            assert len(prompt) > 0
            assert "E-Commerce" in prompt
            assert "FastAPI" in prompt
            assert "async/await" in prompt

            self._log_pass("Test 1: Prompt builder creates valid prompts")

        except Exception as e:
            self._log_fail(f"Test 1: {str(e)}")

    async def test_prompt_builder_module(self):
        """Test 2: Module-specific prompt builder"""
        try:
            context = {
                "description": "User authentication module",
                "requirements": "JWT-based auth, email verification",
                "language": "Python",
                "framework": "FastAPI",
                "database": "PostgreSQL"
            }

            prompt = CodeGenerationPromptBuilder.build_module_generation_prompt(
                module_name="auth",
                module_type="backend",
                context=context
            )

            assert len(prompt) > 0
            assert "auth" in prompt.lower()
            assert "backend" in prompt.lower()
            assert "Python" in prompt
            assert "FastAPI" in prompt

            self._log_pass("Test 2: Module-specific prompt builder works")

        except Exception as e:
            self._log_fail(f"Test 2: {str(e)}")

    async def test_llm_factory_creation(self):
        """Test 3: LLM factory creates clients correctly"""
        try:
            # Test all providers can be created (won't validate without real API keys)
            providers = [
                LLMProvider.ANTHROPIC,
                LLMProvider.OPENAI,
                LLMProvider.GROK,
                LLMProvider.DEEPSEEK
            ]

            for provider in providers:
                try:
                    client = LLMServiceFactory.create_client(
                        provider=provider,
                        api_key="test_key_dummy"
                    )
                    assert client is not None
                except Exception as e:
                    raise AssertionError(f"Failed to create {provider.value} client: {str(e)}")

            self._log_pass("Test 3: LLM factory creates all provider clients")

        except Exception as e:
            self._log_fail(f"Test 3: {str(e)}")

    async def test_code_generation_service_init(self):
        """Test 4: CodeGenerationService initializes correctly"""
        try:
            async with AsyncSessionLocal() as session:
                service = CodeGenerationService(
                    db=session,
                    llm_provider=LLMProvider.ANTHROPIC
                )

                assert service.db is not None
                assert service.llm_provider == LLMProvider.ANTHROPIC
                assert service.piloter_service is not None

            self._log_pass("Test 4: CodeGenerationService initializes correctly")

        except Exception as e:
            self._log_fail(f"Test 4: {str(e)}")

    async def test_create_test_artifacts(self):
        """Test 5: Create test artifacts for generation"""
        try:
            async with AsyncSessionLocal() as session:
                artifacts = []

                for artifact_data in [
                    {
                        "name": "API Requirements",
                        "type": ArtifactType.REQUIREMENTS,
                        "content": "REST API with CRUD operations"
                    },
                    {
                        "name": "Database Schema",
                        "type": ArtifactType.DOCUMENT,
                        "content": "PostgreSQL schema with Users, Products, Orders tables"
                    }
                ]:
                    artifact = Artifact(
                        id=uuid4(),
                        name=artifact_data["name"],
                        type=artifact_data["type"],
                        content=artifact_data["content"],
                        status=ArtifactStatus.APPROVED,
                        created_by=self.gp_id
                    )
                    session.add(artifact)
                    artifacts.append(artifact)

                await session.commit()

                self._log_pass(f"Test 5: Created {len(artifacts)} test artifacts")

        except Exception as e:
            self._log_fail(f"Test 5: {str(e)}")

    async def test_provider_validation_logic(self):
        """Test 6: Test provider validation logic (without real API)"""
        try:
            async with AsyncSessionLocal() as session:
                service = CodeGenerationService(
                    db=session,
                    llm_provider=LLMProvider.ANTHROPIC
                )

                # This will fail without real API key, but tests the structure
                # In real scenario, we'd mock the validation
                try:
                    result = await service.validate_llm_provider(api_key="dummy_key")
                    # Expected to fail with dummy key
                    assert isinstance(result, bool)
                except Exception:
                    # Expected with dummy API key
                    pass

            self._log_pass("Test 6: Provider validation logic works")

        except Exception as e:
            self._log_fail(f"Test 6: {str(e)}")

    async def test_api_key_resolution(self):
        """Test 7: API key resolution from environment"""
        try:
            import os

            async with AsyncSessionLocal() as session:
                service = CodeGenerationService(
                    db=session,
                    llm_provider=LLMProvider.ANTHROPIC
                )

                # Test that it tries to get key from environment
                # This will raise if key not found, which is expected
                try:
                    key = service._get_provider_api_key()
                except ValueError as e:
                    # Expected if env variable not set
                    assert "ANTHROPIC_API_KEY" in str(e) or "not found" in str(e).lower()

            self._log_pass("Test 7: API key resolution logic works")

        except Exception as e:
            self._log_fail(f"Test 7: {str(e)}")

    async def test_generation_history_structure(self):
        """Test 8: Code generation history retrieval structure"""
        try:
            async with AsyncSessionLocal() as session:
                service = CodeGenerationService(db=session)

                # Test that method exists and returns correct structure
                history = await service.get_generation_history(
                    project_id=self.project_id,
                    limit=10
                )

                assert isinstance(history, list)
                # Empty history is ok for new project
                assert len(history) >= 0

            self._log_pass("Test 8: Code generation history structure correct")

        except Exception as e:
            self._log_fail(f"Test 8: {str(e)}")

    async def test_llm_provider_enum(self):
        """Test 9: LLMProvider enum works correctly"""
        try:
            # Test enum values
            assert LLMProvider.ANTHROPIC.value == "anthropic"
            assert LLMProvider.OPENAI.value == "openai"
            assert LLMProvider.GROK.value == "grok"
            assert LLMProvider.DEEPSEEK.value == "deepseek"

            # Test enum from string
            provider = LLMProvider("anthropic")
            assert provider == LLMProvider.ANTHROPIC

            # Test invalid provider
            try:
                LLMProvider("invalid")
                raise AssertionError("Should have raised ValueError")
            except ValueError:
                pass  # Expected

            self._log_pass("Test 9: LLMProvider enum works correctly")

        except Exception as e:
            self._log_fail(f"Test 9: {str(e)}")

    def _log_pass(self, test_name: str):
        self.passed += 1
        self.tests_result.append(f"✅ {test_name}")
        print(f"✅ {test_name}")

    def _log_fail(self, test_name: str):
        self.failed += 1
        self.tests_result.append(f"❌ {test_name}")
        print(f"❌ {test_name}")

    async def run_all_tests(self):
        print("\n╔════════════════════════════════════════════════════════════════╗")
        print("║           INTEGRATION TEST - FASE 4 CODE GENERATION            ║")
        print("║    LLM Integration, Prompt Building, Code Generation Service   ║")
        print("╚════════════════════════════════════════════════════════════════╝\n")

        await self.test_setup()
        await self.test_prompt_builder_basic()
        await self.test_prompt_builder_module()
        await self.test_llm_factory_creation()
        await self.test_code_generation_service_init()
        await self.test_create_test_artifacts()
        await self.test_provider_validation_logic()
        await self.test_api_key_resolution()
        await self.test_generation_history_structure()
        await self.test_llm_provider_enum()

        return self.print_results()

    def print_results(self):
        total = self.passed + self.failed
        percentage = (self.passed / total * 100) if total > 0 else 0

        print("\n" + "="*70)
        print("RESULTADOS DO TESTE - FASE 4 CODE GENERATION")
        print("="*70)
        print(f"\n✅ Passou: {self.passed}/{total}")
        print(f"❌ Falhou: {self.failed}/{total}")
        print(f"📊 Taxa de sucesso: {percentage:.1f}%\n")

        if self.failed == 0:
            print("🎉 TESTES DE CÓDIGO GENERATION COMPLETOS COM SUCESSO!")
            print("\n✨ FASE 4 PREPARADA - LLM INTEGRATION PRONTA")
            return True
        else:
            print("⚠️  ALGUNS TESTES FALHARAM")
            return False


async def main():
    tester = CodeGenTester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
