"""
Teste de Integração - FASE 3 GCA
Valida: Evaluation Engine, Piloter Service, Scoring Algorithm
"""
import asyncio
import sys
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import uuid4

# Adiciona app ao path
sys.path.insert(0, '/app')

from app.db.database import AsyncSessionLocal
from app.models.tenant import Artifact, ArtifactEvaluation, ArtifactType
from app.models.base import User
from app.services.evaluation_service import EvaluationService
from app.services.piloter_service import PiloterService
from app.core.security import hash_password


class EvaluationIntegrationTester:
    """Suite de testes de integração para Fase 3"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests_result = []
        self.project_id = None
        self.artifact_id = None
        self.user_id = None

    async def test_setup_data(self):
        """Setup: Create test user and artifact"""
        try:
            timestamp = int(time.time() * 1000)

            async with AsyncSessionLocal() as session:
                # Create user
                user = User(
                    id=uuid4(),
                    email=f"evaluator_{timestamp}@test.com",
                    password_hash=hash_password("password"),
                    full_name="Evaluator",
                    is_active=True
                )
                session.add(user)
                self.user_id = user.id

                # Create artifact (note: in real usage, this would be in tenant schema)
                artifact = Artifact(
                    id=uuid4(),
                    name="Test Artifact",
                    type=ArtifactType.REQUIREMENTS,
                    content="Test requirements document",
                    description="Test artifact for evaluation",
                    created_by=user.id
                )
                session.add(artifact)
                self.artifact_id = artifact.id

                await session.commit()

                self._log_pass("Setup: Test user and artifact created")

        except Exception as e:
            self._log_fail(f"Setup: {str(e)}")

    async def test_evaluation_service_init(self):
        """✓ Test 1: EvaluationService inicializa corretamente"""
        try:
            async with AsyncSessionLocal() as session:
                service = EvaluationService(session)
                assert service is not None
                assert service.db is not None

                self._log_pass("EvaluationService initializes correctly")

        except Exception as e:
            self._log_fail(f"EvaluationService init: {str(e)}")

    async def test_piloter_service_init(self):
        """✓ Test 2: PiloterService inicializa corretamente"""
        try:
            async with AsyncSessionLocal() as session:
                service = PiloterService(session)
                assert service is not None
                assert service.api_key is not None
                assert service.api_endpoint is not None

                self._log_pass("PiloterService initializes correctly")

        except Exception as e:
            self._log_fail(f"PiloterService init: {str(e)}")

    async def test_evaluate_artifact_approved(self):
        """✓ Test 3: Avaliação de artefato - Aprovado"""
        try:
            if not self.artifact_id or not self.user_id:
                raise ValueError("Test data not setup")

            async with AsyncSessionLocal() as session:
                service = EvaluationService(session)

                # High scores = approved
                evaluation_data = {
                    "p1_score": 85,
                    "p2_score": 80,
                    "p3_score": 90,
                    "p4_score": 85,
                    "p5_score": 80,
                    "p6_score": 85,
                    "p7_score": 80,  # >= 70, not blocked
                    "details": {
                        "strengths": ["Clear requirements", "Good documentation"],
                        "weaknesses": [],
                        "recommendations": []
                    },
                    "feedback": "Well-structured requirements"
                }

                evaluation = await service.evaluate_artifact(
                    artifact_id=self.artifact_id,
                    evaluator_id=self.user_id,
                    evaluation_data=evaluation_data
                )

                assert evaluation is not None
                assert evaluation.final_status == "approved"
                assert evaluation.p7_blocked is False
                assert evaluation.code_generation_allowed is True
                assert evaluation.final_score > 80

                self._log_pass("Artifact evaluation - Approved")

        except Exception as e:
            self._log_fail(f"Artifact evaluation (approved): {str(e)}")

    async def test_evaluate_artifact_needs_review(self):
        """✓ Test 4: Avaliação de artefato - Precisa Revisão"""
        try:
            timestamp = int(time.time() * 1000)
            artifact_id = uuid4()

            async with AsyncSessionLocal() as session:
                # Create artifact
                artifact = Artifact(
                    id=artifact_id,
                    name=f"Review Artifact {timestamp}",
                    type=ArtifactType.REQUIREMENTS,
                    content="Incomplete requirements",
                    created_by=self.user_id
                )
                session.add(artifact)
                await session.commit()

            async with AsyncSessionLocal() as session:
                service = EvaluationService(session)

                # Medium scores = needs review
                evaluation_data = {
                    "p1_score": 65,
                    "p2_score": 70,
                    "p3_score": 60,
                    "p4_score": 65,
                    "p5_score": 70,
                    "p6_score": 60,
                    "p7_score": 75,  # >= 70, not blocked
                    "details": {
                        "strengths": ["Basic structure"],
                        "weaknesses": ["Missing details"],
                        "recommendations": ["Add more details"]
                    },
                    "feedback": "Needs more work"
                }

                evaluation = await service.evaluate_artifact(
                    artifact_id=artifact_id,
                    evaluator_id=self.user_id,
                    evaluation_data=evaluation_data
                )

                assert evaluation.final_status == "needs_review"
                assert evaluation.p7_blocked is False
                assert evaluation.final_score >= 60 and evaluation.final_score < 80

                self._log_pass("Artifact evaluation - Needs Review")

        except Exception as e:
            self._log_fail(f"Artifact evaluation (review): {str(e)}")

    async def test_evaluate_artifact_p7_blocked(self):
        """✓ Test 5: Avaliação de artefato - P7 Bloqueado"""
        try:
            timestamp = int(time.time() * 1000)
            artifact_id = uuid4()

            async with AsyncSessionLocal() as session:
                # Create artifact
                artifact = Artifact(
                    id=artifact_id,
                    name=f"Blocked Artifact {timestamp}",
                    type=ArtifactType.REQUIREMENTS,
                    content="Security issues",
                    created_by=self.user_id
                )
                session.add(artifact)
                await session.commit()

            async with AsyncSessionLocal() as session:
                service = EvaluationService(session)

                # Good scores but P7 < 70 = blocked
                evaluation_data = {
                    "p1_score": 85,
                    "p2_score": 85,
                    "p3_score": 90,
                    "p4_score": 85,
                    "p5_score": 85,
                    "p6_score": 85,
                    "p7_score": 50,  # < 70, BLOCKED
                    "details": {
                        "strengths": [],
                        "weaknesses": ["Security vulnerabilities"],
                        "recommendations": []
                    },
                    "feedback": "Critical security issues"
                }

                evaluation = await service.evaluate_artifact(
                    artifact_id=artifact_id,
                    evaluator_id=self.user_id,
                    evaluation_data=evaluation_data
                )

                assert evaluation.p7_blocked is True
                assert evaluation.final_status == "blocked"
                assert evaluation.code_generation_allowed is False

                self._log_pass("Artifact evaluation - P7 Blocked")

        except Exception as e:
            self._log_fail(f"Artifact evaluation (blocked): {str(e)}")

    async def test_score_calculation_accuracy(self):
        """✓ Test 6: Cálculo de scores está correto"""
        try:
            service = EvaluationService(None)

            # Test weighted score calculation
            scores = {
                "p1": 80,
                "p2": 90,
                "p3": 70,
                "p4": 80,
                "p5": 85,
                "p6": 75,
                "p7": 80
            }

            weights = {
                f"P{i}": 1.0 for i in range(1, 8)
            }

            final_score, p7_blocked = service._calculate_final_score(scores, weights)

            # With equal weights, should be average of all scores
            expected = sum(scores.values()) / len(scores)

            assert abs(final_score - expected) < 1, f"Expected ~{expected}, got {final_score}"
            assert p7_blocked is False

            self._log_pass("Score calculation is accurate")

        except Exception as e:
            self._log_fail(f"Score calculation: {str(e)}")

    async def test_p7_blocker_threshold(self):
        """✓ Test 7: P7 blocker threshold (70) funciona corretamente"""
        try:
            service = EvaluationService(None)

            # Test P7 exactly at 70 (should not be blocked)
            scores_at_threshold = {"p" + str(i): 80 for i in range(1, 7)}
            scores_at_threshold["p7"] = 70.0

            _, blocked_at = service._calculate_final_score(scores_at_threshold, {f"P{i}": 1.0 for i in range(1, 8)})
            assert blocked_at is False, "P7=70 should NOT be blocked"

            # Test P7 just below 70 (should be blocked)
            scores_below = {"p" + str(i): 80 for i in range(1, 7)}
            scores_below["p7"] = 69.9

            _, blocked_below = service._calculate_final_score(scores_below, {f"P{i}": 1.0 for i in range(1, 8)})
            assert blocked_below is True, "P7<70 should be blocked"

            self._log_pass("P7 blocker threshold (70) is correct")

        except Exception as e:
            self._log_fail(f"P7 blocker threshold: {str(e)}")

    def _log_pass(self, test_name: str):
        """Log test passed"""
        self.passed += 1
        self.tests_result.append(f"✅ {test_name}")
        print(f"✅ {test_name}")

    def _log_fail(self, test_name: str):
        """Log test failed"""
        self.failed += 1
        self.tests_result.append(f"❌ {test_name}")
        print(f"❌ {test_name}")

    async def run_all_tests(self):
        """Executa todos os testes"""
        print("\n╔════════════════════════════════════════════════════════════════╗")
        print("║      TESTE DE INTEGRAÇÃO - FASE 3 GCA (Evaluation Engine)    ║")
        print("╚════════════════════════════════════════════════════════════════╝\n")

        # Setup first
        await self.test_setup_data()

        # Service initialization
        await self.test_evaluation_service_init()
        await self.test_piloter_service_init()

        # Evaluation tests
        await self.test_evaluate_artifact_approved()
        await self.test_evaluate_artifact_needs_review()
        await self.test_evaluate_artifact_p7_blocked()

        # Algorithm tests
        await self.test_score_calculation_accuracy()
        await self.test_p7_blocker_threshold()

        return self.print_results()

    def print_results(self):
        """Imprime resultados finais"""
        total = self.passed + self.failed
        percentage = (self.passed / total * 100) if total > 0 else 0

        print("\n" + "="*70)
        print("RESULTADOS DOS TESTES DE INTEGRAÇÃO - FASE 3")
        print("="*70)
        print(f"\n✅ Passou: {self.passed}/{total}")
        print(f"❌ Falhou: {self.failed}/{total}")
        print(f"📊 Taxa de sucesso: {percentage:.1f}%\n")

        if self.failed == 0:
            print("🎉 TODOS OS TESTES DE INTEGRAÇÃO PASSARAM!")
            print("\n✨ FASE 3 APROVADA - PRONTO PARA FASE 4 (Code Generation)")
            return True
        else:
            print("⚠️  ALGUNS TESTES DE INTEGRAÇÃO FALHARAM")
            print("\n❌ FASE 3 NÃO APROVADA - REVISAR ERROS")
            return False


async def main():
    tester = EvaluationIntegrationTester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
