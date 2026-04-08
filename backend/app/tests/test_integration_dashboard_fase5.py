"""
Integration Tests - FASE 5 Dashboard & Monitoring
Valida: Monitoring Service, Dashboard Endpoints, Metrics Aggregation
"""
import asyncio
import sys
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import uuid4
from datetime import datetime, timezone, timedelta

sys.path.insert(0, '/app')

from app.db.database import AsyncSessionLocal
from app.models.base import User
from app.models.onboarding import ProjectRequest, ProjectRequestStatus
from app.models.tenant import Artifact, ArtifactEvaluation, ArtifactType, ArtifactStatus
from app.services.monitoring_service import MonitoringService
from app.core.security import hash_password
import structlog

logger = structlog.get_logger(__name__)


class DashboardTester:
    """Integration test suite for FASE 5"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests_result = []
        self.project_id = None
        self.gp_id = None
        self.admin_id = None

    async def test_setup(self):
        """Setup: Create test data"""
        try:
            timestamp = int(time.time() * 1000)

            async with AsyncSessionLocal() as session:
                # Create users
                admin = User(
                    id=uuid4(),
                    email=f"admin_{timestamp}@dashboard.com",
                    password_hash=hash_password("admin"),
                    full_name="Admin",
                    is_active=True,
                    is_admin=True
                )
                gp = User(
                    id=uuid4(),
                    email=f"gp_{timestamp}@dashboard.com",
                    password_hash=hash_password("gp"),
                    full_name="GP",
                    is_active=True
                )
                session.add_all([admin, gp])
                await session.commit()

                self.admin_id = admin.id
                self.gp_id = gp.id

                # Create project
                project = ProjectRequest(
                    id=uuid4(),
                    gp_id=gp.id,
                    project_name="Dashboard Test Project",
                    project_slug=f"dashboard-test-{timestamp}",
                    description="Test project for monitoring",
                    schema_name=f"proj_dashboard_{timestamp}",
                    status=ProjectRequestStatus.APPROVED,
                    approved_by=admin.id,
                    approved_at=datetime.now(timezone.utc)
                )
                session.add(project)
                await session.commit()

                self.project_id = project.id

                # Create test artifacts
                for i in range(3):
                    artifact = Artifact(
                        id=uuid4(),
                        name=f"Test Artifact {i+1}",
                        type=ArtifactType.DOCUMENT,
                        content=f"Test content {i+1}",
                        status=ArtifactStatus.APPROVED,
                        created_by=gp.id
                    )
                    session.add(artifact)
                    await session.commit()

                    # Create evaluation
                    evaluation = ArtifactEvaluation(
                        id=uuid4(),
                        artifact_id=artifact.id,
                        p1_business_score=80 + i,
                        p2_rules_score=82 + i,
                        p3_functional_score=85 + i,
                        p4_nonfunctional_score=80 + i,
                        p5_architecture_score=88 + i,
                        p6_data_score=85 + i,
                        p7_security_score=75 + i,
                        final_score=82.5 + i,
                        final_status="approved",
                        code_generation_allowed=True,
                        evaluated_by=admin.id
                    )
                    session.add(evaluation)

                await session.commit()

                self._log_pass("Setup: Test data created")

        except Exception as e:
            self._log_fail(f"Setup: {str(e)}")

    async def test_monitoring_service_init(self):
        """Test 1: MonitoringService initializes correctly"""
        try:
            async with AsyncSessionLocal() as session:
                service = MonitoringService(db=session)
                assert service.db is not None
                self._log_pass("Test 1: MonitoringService initializes correctly")

        except Exception as e:
            self._log_fail(f"Test 1: {str(e)}")

    async def test_track_generation(self):
        """Test 2: Track generation event"""
        try:
            async with AsyncSessionLocal() as session:
                service = MonitoringService(db=session)
                event = await service.track_generation(
                    project_id=self.project_id,
                    provider="anthropic",
                    tokens_generated=1500,
                    generation_time_ms=3500.0,
                    status="success"
                )

                assert event["project_id"] == str(self.project_id)
                assert event["provider"] == "anthropic"
                assert event["tokens_generated"] == 1500
                assert event["generation_time_ms"] == 3500.0
                assert event["status"] == "success"
                assert event["estimated_cost_usd"] > 0

                self._log_pass(f"Test 2: Track generation (cost: ${event['estimated_cost_usd']})")

        except Exception as e:
            self._log_fail(f"Test 2: {str(e)}")

    async def test_project_metrics(self):
        """Test 3: Get project metrics"""
        try:
            async with AsyncSessionLocal() as session:
                service = MonitoringService(db=session)
                metrics = await service.get_project_metrics(self.project_id)

                assert metrics["project_id"] == str(self.project_id)
                assert metrics["project_name"] == "Dashboard Test Project"
                # Just verify that evaluations were counted (there are evaluations from setup)
                assert metrics["evaluations"]["total"] >= 3
                assert metrics["evaluations"]["avg_score"] > 0
                assert "max_score" in metrics["evaluations"]
                assert "min_score" in metrics["evaluations"]

                self._log_pass(f"Test 3: Project metrics (evaluations: {metrics['evaluations']['total']}, avg_score: {metrics['evaluations']['avg_score']})")

        except Exception as e:
            self._log_fail(f"Test 3: {str(e)}")

    async def test_provider_statistics(self):
        """Test 4: Get provider statistics"""
        try:
            async with AsyncSessionLocal() as session:
                service = MonitoringService(db=session)
                stats = await service.get_provider_statistics()

                providers = ["anthropic", "openai", "grok", "deepseek"]
                for provider in providers:
                    assert provider in stats["providers"]
                    assert "cost_per_1k_tokens" in stats["providers"][provider]
                    assert "estimated_latency_ms" in stats["providers"][provider]
                    assert "recommended_for" in stats["providers"][provider]

                self._log_pass("Test 4: Provider statistics (4 providers available)")

        except Exception as e:
            self._log_fail(f"Test 4: {str(e)}")

    async def test_dashboard_summary(self):
        """Test 5: Get dashboard summary"""
        try:
            async with AsyncSessionLocal() as session:
                service = MonitoringService(db=session)
                summary = await service.get_dashboard_summary()

                assert "timestamp" in summary
                assert summary["projects"]["total"] > 0
                assert summary["artifacts"]["total"] > 0
                assert summary["evaluations"]["total"] > 0
                assert summary["system_health"]["status"] in ["healthy", "initializing", "degraded"]

                self._log_pass(f"Test 5: Dashboard summary (projects: {summary['projects']['total']}, evaluations: {summary['evaluations']['total']})")

        except Exception as e:
            self._log_fail(f"Test 5: {str(e)}")

    async def test_generation_timeline(self):
        """Test 6: Get generation timeline"""
        try:
            async with AsyncSessionLocal() as session:
                service = MonitoringService(db=session)
                timeline = await service.get_generation_timeline(days=7)

                assert timeline["period_days"] == 7
                assert "start_date" in timeline
                assert "end_date" in timeline
                assert isinstance(timeline["timeline"], dict)
                assert timeline["total_in_period"] > 0

                self._log_pass(f"Test 6: Generation timeline ({timeline['total_in_period']} artifacts in period)")

        except Exception as e:
            self._log_fail(f"Test 6: {str(e)}")

    async def test_quality_metrics(self):
        """Test 7: Get quality metrics"""
        try:
            async with AsyncSessionLocal() as session:
                service = MonitoringService(db=session)
                metrics = await service.get_quality_metrics()

                assert "timestamp" in metrics
                assert "evaluation_status" in metrics
                assert "pillar_averages" in metrics
                assert "quality_assessment" in metrics

                pillars = metrics["pillar_averages"]
                assert "P1_Business" in pillars
                assert "P7_Security" in pillars

                self._log_pass(f"Test 7: Quality metrics (assessment: {metrics['quality_assessment']})")

        except Exception as e:
            self._log_fail(f"Test 7: {str(e)}")

    async def test_cost_calculation(self):
        """Test 8: Cost calculation for different providers"""
        try:
            async with AsyncSessionLocal() as session:
                service = MonitoringService(db=session)

                costs = {}
                providers = ["anthropic", "openai", "grok", "deepseek"]
                tokens = 1000

                for provider in providers:
                    cost = service._calculate_cost(provider, tokens)
                    costs[provider] = cost
                    assert cost >= 0

                # Verify cost comparison
                assert costs["grok"] < costs["openai"]  # Grok cheapest
                assert costs["deepseek"] < costs["anthropic"]  # DeepSeek cheaper than Anthropic

                self._log_pass(f"Test 8: Cost calculation (1000 tokens) - DeepSeek: ${costs['deepseek']}, Anthropic: ${costs['anthropic']}")

        except Exception as e:
            self._log_fail(f"Test 8: {str(e)}")

    async def test_quality_assessment(self):
        """Test 9: Quality assessment logic"""
        try:
            async with AsyncSessionLocal() as session:
                service = MonitoringService(db=session)

                # Test high quality
                high_scores = {
                    "P1_Business": 90, "P2_Rules": 90,
                    "P3_Functional": 90, "P4_NonFunctional": 90,
                    "P5_Architecture": 90, "P6_Data": 90,
                    "P7_Security": 90
                }
                assessment = service._assess_quality(high_scores)
                assert "Excellent" in assessment

                # Test low quality
                low_scores = {
                    "P1_Business": 50, "P2_Rules": 50,
                    "P3_Functional": 50, "P4_NonFunctional": 50,
                    "P5_Architecture": 50, "P6_Data": 50,
                    "P7_Security": 50
                }
                assessment = service._assess_quality(low_scores)
                assert "Needs Review" in assessment

                self._log_pass("Test 9: Quality assessment logic works correctly")

        except Exception as e:
            self._log_fail(f"Test 9: {str(e)}")

    async def test_provider_recommendations(self):
        """Test 10: Provider recommendations"""
        try:
            async with AsyncSessionLocal() as session:
                service = MonitoringService(db=session)

                providers = ["anthropic", "openai", "grok", "deepseek"]
                recommendations = {}
                for provider in providers:
                    rec = service._get_provider_recommendation(provider)
                    assert len(rec) > 0
                    recommendations[provider] = rec

                # Verify we got recommendations for all providers
                assert len(recommendations) == 4
                # Verify recommendations contain meaningful content
                for provider, rec in recommendations.items():
                    assert isinstance(rec, str)
                    assert len(rec) > 10  # Should be detailed

                self._log_pass("Test 10: Provider recommendations available for all providers")

        except Exception as e:
            self._log_fail(f"Test 10: {str(e)}")

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
        print("║           INTEGRATION TEST - FASE 5 DASHBOARD                 ║")
        print("║    Monitoring Service, Dashboard Endpoints, Metrics           ║")
        print("╚════════════════════════════════════════════════════════════════╝\n")

        await self.test_setup()
        await self.test_monitoring_service_init()
        await self.test_track_generation()
        await self.test_project_metrics()
        await self.test_provider_statistics()
        await self.test_dashboard_summary()
        await self.test_generation_timeline()
        await self.test_quality_metrics()
        await self.test_cost_calculation()
        await self.test_quality_assessment()
        await self.test_provider_recommendations()

        return self.print_results()

    def print_results(self):
        total = self.passed + self.failed
        percentage = (self.passed / total * 100) if total > 0 else 0

        print("\n" + "="*70)
        print("RESULTADOS DO TESTE - FASE 5 DASHBOARD")
        print("="*70)
        print(f"\n✅ Passou: {self.passed}/{total}")
        print(f"❌ Falhou: {self.failed}/{total}")
        print(f"📊 Taxa de sucesso: {percentage:.1f}%\n")

        if self.failed == 0:
            print("🎉 TESTES DE DASHBOARD COMPLETOS COM SUCESSO!")
            print("\n✨ FASE 5 APROVADA - MONITORING & DASHBOARD READY")
            return True
        else:
            print("⚠️  ALGUNS TESTES FALHARAM")
            return False


async def main():
    tester = DashboardTester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
