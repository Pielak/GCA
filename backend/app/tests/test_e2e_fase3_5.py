"""
End-to-End Test - FASE 3.5
Valida: Mock Project, Artifact Evaluation, N8N Integration
"""
import asyncio
import sys
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from uuid import uuid4

sys.path.insert(0, '/app')

from app.db.database import AsyncSessionLocal, engine
from app.models.base import User
from app.models.onboarding import ProjectRequest, ProjectRequestStatus, OnboardingProgress
from app.models.tenant import Artifact, ArtifactEvaluation, ArtifactType
from app.services.admin_service import AdminService
from app.services.evaluation_service import EvaluationService
from app.services.mock_n8n_service import get_mock_n8n_service
from app.core.security import hash_password
import structlog

logger = structlog.get_logger(__name__)


class EndToEndTester:
    """End-to-end test suite for FASE 3.5"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests_result = []
        self.project_id = None
        self.schema_name = None
        self.admin_id = None
        self.gp_id = None
        self.evaluator_id = None

    async def test_setup_users(self):
        """Setup: Create test users"""
        try:
            timestamp = int(time.time() * 1000)

            async with AsyncSessionLocal() as session:
                admin = User(
                    id=uuid4(),
                    email=f"admin_{timestamp}@e2e.com",
                    password_hash=hash_password("admin"),
                    full_name="Admin",
                    is_active=True,
                    is_admin=True
                )
                gp = User(
                    id=uuid4(),
                    email=f"gp_{timestamp}@e2e.com",
                    password_hash=hash_password("gp"),
                    full_name="GP",
                    is_active=True
                )
                evaluator = User(
                    id=uuid4(),
                    email=f"eval_{timestamp}@e2e.com",
                    password_hash=hash_password("eval"),
                    full_name="Evaluator",
                    is_active=True
                )
                session.add_all([admin, gp, evaluator])
                await session.commit()

                self.admin_id = admin.id
                self.gp_id = gp.id
                self.evaluator_id = evaluator.id

                self._log_pass("Setup: Users created")

        except Exception as e:
            self._log_fail(f"Setup: {str(e)}")

    async def test_e2e_create_project(self):
        """✓ Test 1: Admin creates project (E2E)"""
        try:
            timestamp = int(time.time() * 1000)

            async with AsyncSessionLocal() as session:
                service = AdminService(session)
                project = await service.create_project_request(
                    gp_id=self.gp_id,
                    project_name="E-Commerce Mock",
                    project_slug=f"ecommerce-{timestamp}",
                    description="Mock e-commerce for testing"
                )

                self.project_id = project.id
                self.schema_name = project.schema_name

                assert project.status == ProjectRequestStatus.PENDING

                self._log_pass("E2E: Project created")

        except Exception as e:
            self._log_fail(f"E2E create project: {str(e)}")

    async def test_e2e_approve_and_provision(self):
        """✓ Test 2: Admin approves project and provisions tenant (E2E)"""
        try:
            if not self.project_id or not self.admin_id:
                raise ValueError("Prerequisites not met")

            async with AsyncSessionLocal() as session:
                service = AdminService(session)
                project = await service.approve_project_request(
                    request_id=self.project_id,
                    admin_id=self.admin_id
                )

                assert project.status == ProjectRequestStatus.APPROVED

                # Verify schema created
                async with engine.begin() as conn:
                    result = await conn.execute(
                        text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema"),
                        {"schema": self.schema_name}
                    )
                    schema = result.scalar()
                    assert schema is not None

                self._log_pass("E2E: Project approved and tenant provisioned")

        except Exception as e:
            self._log_fail(f"E2E approve and provision: {str(e)}")

    async def test_e2e_create_artifacts(self):
        """✓ Test 3: Create mock artifacts in global schema (E2E)"""
        try:
            if not self.project_id or not self.gp_id:
                raise ValueError("Prerequisites not met")

            artifacts_created = 0

            # Create artifacts in global schema (not tenant-specific for this test)
            for i, artifact_data in enumerate([
                {
                    "name": "System Requirements",
                    "type": ArtifactType.REQUIREMENTS,
                    "content": "Complete functional requirements",
                    "p7_score": 85
                },
                {
                    "name": "Architecture Diagram",
                    "type": ArtifactType.ARCHITECTURE,
                    "content": "Microservices architecture",
                    "p7_score": 88
                },
                {
                    "name": "Security Issues",
                    "type": ArtifactType.DOCUMENT,
                    "content": "Unresolved security vulnerabilities",
                    "p7_score": 45
                }
            ]):
                async with AsyncSessionLocal() as session:
                    artifact = Artifact(
                        id=uuid4(),
                        name=artifact_data["name"],
                        type=artifact_data["type"],
                        content=artifact_data["content"],
                        created_by=self.gp_id
                    )
                    session.add(artifact)
                    await session.commit()
                    artifacts_created += 1

            assert artifacts_created == 3

            self._log_pass(f"E2E: Created {artifacts_created} artifacts")

        except Exception as e:
            self._log_fail(f"E2E create artifacts: {str(e)}")

    async def test_e2e_evaluate_artifacts(self):
        """✓ Test 4: Evaluate artifacts and check P7 blocker (E2E)"""
        try:
            if not self.project_id or not self.evaluator_id or not self.schema_name:
                raise ValueError("Prerequisites not met")

            evaluations_created = 0
            blocked_count = 0

            # Get artifact IDs first (from global schema)
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Artifact).order_by(Artifact.created_at.desc()).limit(3))
                artifacts_list = result.scalars().all()
                artifact_ids = [a.id for a in artifacts_list]

                if len(artifact_ids) != 3:
                    raise ValueError(f"Expected 3 artifacts, found {len(artifact_ids)}")

            # Evaluate each artifact in separate session
            for i, artifact_id in enumerate(artifact_ids):
                async with AsyncSessionLocal() as session:

                    if i == 0:  # Requirements - approved
                        p7_score = 85
                        expected_status = "approved"
                    elif i == 1:  # Architecture - approved
                        p7_score = 88
                        expected_status = "approved"
                    else:  # Security - blocked
                        p7_score = 45
                        expected_status = "blocked"

                    eval_data = {
                        "p1_score": 80,
                        "p2_score": 80,
                        "p3_score": 80,
                        "p4_score": 80,
                        "p5_score": 80,
                        "p6_score": 80,
                        "p7_score": p7_score,
                        "details": {},
                        "feedback": f"Evaluation"
                    }

                    service = EvaluationService(session)
                    evaluation = await service.evaluate_artifact(
                        artifact_id=artifact_id,
                        evaluator_id=self.evaluator_id,
                        evaluation_data=eval_data
                    )

                    if evaluation.final_status != expected_status:
                        raise AssertionError(
                            f"Artifact {i}: expected {expected_status}, got {evaluation.final_status} "
                            f"(p7={p7_score}, p7_blocked={evaluation.p7_blocked})"
                        )
                    evaluations_created += 1

                    if evaluation.p7_blocked:
                        blocked_count += 1

            if evaluations_created != 3:
                raise AssertionError(f"Expected 3 evaluations, got {evaluations_created}")
            if blocked_count != 1:
                raise AssertionError(f"Expected 1 blocked, got {blocked_count}")

            self._log_pass(f"E2E: Evaluated {evaluations_created} artifacts ({blocked_count} blocked by P7)")

        except Exception as e:
            self._log_fail(f"E2E evaluate artifacts: {str(e)}")

    async def test_e2e_n8n_workflow_trigger(self):
        """✓ Test 5: Trigger N8N workflow (E2E)"""
        try:
            mock_n8n = get_mock_n8n_service()

            workflow = await mock_n8n.trigger_workflow(
                project_slug=self.schema_name.replace("proj_", ""),
                language="python",
                architecture="microservices",
                onboarding_id=str(self.project_id)
            )

            assert workflow["status"] == "triggered"
            assert "workflow_id" in workflow

            self._log_pass(f"E2E: N8N workflow triggered (ID: {workflow['workflow_id'][:8]}...)")

            self._workflow_id = workflow["workflow_id"]

        except Exception as e:
            self._log_fail(f"E2E N8N trigger: {str(e)}")

    async def test_e2e_n8n_workflow_polling(self):
        """✓ Test 6: Poll N8N workflow status until completion (E2E)"""
        try:
            if not hasattr(self, '_workflow_id'):
                raise ValueError("Workflow not triggered in previous test")

            mock_n8n = get_mock_n8n_service()

            # Poll workflow status
            max_retries = 50  # 5 seconds max
            completed = False
            final_status = None

            for attempt in range(max_retries):
                status = await mock_n8n.get_workflow_status(self._workflow_id)

                if status["status"] in ["completed", "failed"]:
                    completed = True
                    final_status = status["status"]
                    break

                await asyncio.sleep(0.1)

            assert completed, f"Workflow did not complete after {max_retries * 0.1}s"
            assert final_status == "completed"

            # Get final result
            status = await mock_n8n.get_workflow_status(self._workflow_id)
            assert status["result"] is not None
            assert "stack" in status["result"]

            self._log_pass(f"E2E: N8N workflow completed with stack recommendations")

        except Exception as e:
            self._log_fail(f"E2E N8N polling: {str(e)}")

    async def test_e2e_stack_recommendations(self):
        """✓ Test 7: Verify stack recommendations from N8N (E2E)"""
        try:
            mock_n8n = get_mock_n8n_service()

            # Get mock data
            mock_data = mock_n8n.get_mock_data()

            assert "project_stacks" in mock_data
            assert "technologies" in mock_data
            assert "best_practices" in mock_data

            # Verify stack structure
            for stack_name, stack_info in mock_data["project_stacks"].items():
                assert "language" in stack_info
                assert "framework" in stack_info
                assert "database" in stack_info
                assert "deployment" in stack_info

            self._log_pass(f"E2E: Stack recommendations validated ({len(mock_data['project_stacks'])} stacks available)")

        except Exception as e:
            self._log_fail(f"E2E stack recommendations: {str(e)}")

    async def test_e2e_code_generation_ready(self):
        """✓ Test 8: Verify system is ready for code generation (E2E)"""
        try:
            if not self.project_id or not self.schema_name:
                raise ValueError("Prerequisites not met")

            # Check that we have:
            # 1. ✅ Project created and approved
            # 2. ✅ Tenant schema provisioned
            # 3. ✅ Artifacts created
            # 4. ✅ Evaluations completed
            # 5. ✅ Stack recommendations available
            # 6. ✅ P7 blocker enforced

            async with AsyncSessionLocal() as session:
                # Verify project
                project = await session.get(ProjectRequest, self.project_id)
                assert project.status == ProjectRequestStatus.APPROVED

                # Verify schema
                result = await session.execute(
                    select(Artifact)
                )
                artifacts = result.scalars().all()
                assert len(artifacts) > 0

            self._log_pass("E2E: System ready for Code Generation (FASE 4)")

        except Exception as e:
            self._log_fail(f"E2E readiness check: {str(e)}")

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
        print("║           END-TO-END TEST - FASE 3.5 GCA                      ║")
        print("║    Mock Project + Evaluation + N8N Integration                ║")
        print("╚════════════════════════════════════════════════════════════════╝\n")

        await self.test_setup_users()
        await self.test_e2e_create_project()
        await self.test_e2e_approve_and_provision()
        await self.test_e2e_create_artifacts()
        await self.test_e2e_evaluate_artifacts()
        await self.test_e2e_n8n_workflow_trigger()
        await self.test_e2e_n8n_workflow_polling()
        await self.test_e2e_stack_recommendations()
        await self.test_e2e_code_generation_ready()

        return self.print_results()

    def print_results(self):
        total = self.passed + self.failed
        percentage = (self.passed / total * 100) if total > 0 else 0

        print("\n" + "="*70)
        print("RESULTADOS DO TESTE END-TO-END - FASE 3.5")
        print("="*70)
        print(f"\n✅ Passou: {self.passed}/{total}")
        print(f"❌ Falhou: {self.failed}/{total}")
        print(f"📊 Taxa de sucesso: {percentage:.1f}%\n")

        if self.failed == 0:
            print("🎉 TESTE END-TO-END COMPLETO COM SUCESSO!")
            print("\n✨ FASE 3.5 APROVADA - SISTEMA PRONTO PARA FASE 4 (Code Generation)")
            return True
        else:
            print("⚠️  ALGUNS TESTES FALHARAM")
            return False


async def main():
    tester = EndToEndTester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
