"""
Teste de Integração - Fase 2 GCA
Valida: Admin Project Creation, Project Approval, Tenant Provisioning
"""
import asyncio
import sys
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from uuid import uuid4

# Adiciona app ao path
sys.path.insert(0, '/app')

from app.db.database import AsyncSessionLocal, engine
from app.models.onboarding import ProjectRequest, ProjectRequestStatus
from app.models.pillar import PillarTemplate
from app.models.tenant import PillarConfiguration, OGCVersion
from app.models.base import User
from app.services.admin_service import AdminService
from app.core.config import settings
from app.core.security import hash_password


class AdminIntegrationTester:
    """Suite de testes de integração para Fase 2"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests_result = []
        self.created_project_id = None
        self.created_schema_name = None
        self.admin_user_id = None
        self.gp_user_id = None

    async def test_setup_users(self):
        """Setup: Create test users (admin and GP)"""
        try:
            import time
            timestamp = int(time.time() * 1000)

            async with AsyncSessionLocal() as session:
                # Create admin user with unique email
                admin_user = User(
                    id=uuid4(),
                    email=f"admin_{timestamp}@test.com",
                    password_hash=hash_password("admin_password"),
                    full_name="Admin User",
                    is_active=True
                )
                session.add(admin_user)
                self.admin_user_id = admin_user.id

                # Create GP user with unique email
                gp_user = User(
                    id=uuid4(),
                    email=f"gp_{timestamp}@test.com",
                    password_hash=hash_password("gp_password"),
                    full_name="GP User",
                    is_active=True
                )
                session.add(gp_user)
                self.gp_user_id = gp_user.id

                await session.commit()

                self._log_pass("Setup: Test users created")

        except Exception as e:
            self._log_fail(f"Setup: Create test users: {str(e)}")

    async def test_admin_create_project_request(self):
        """✓ Test 2: Admin cria solicitação de projeto"""
        try:
            if not self.gp_user_id:
                raise ValueError("GP user not created in setup")

            import time
            timestamp = int(time.time() * 1000)
            unique_slug = f"test-proj-{timestamp}"

            async with AsyncSessionLocal() as session:
                service = AdminService(session)

                project = await service.create_project_request(
                    gp_id=self.gp_user_id,
                    project_name="Test Project Fase 2",
                    project_slug=unique_slug,
                    description="Integration test for Phase 2"
                )

                assert project is not None
                assert project.project_name == "Test Project Fase 2"
                assert project.project_slug == unique_slug
                assert project.status == ProjectRequestStatus.PENDING
                assert project.schema_name == f"proj_{unique_slug}"

                self.created_project_id = project.id
                self.created_schema_name = project.schema_name

                self._log_pass("Admin create project request")

        except Exception as e:
            self._log_fail(f"Admin create project request: {str(e)}")

    async def test_admin_get_pending_projects(self):
        """✓ Test 3: Admin visualiza projetos pendentes"""
        try:
            if not self.created_project_id:
                raise ValueError("Project not created in previous test")

            async with AsyncSessionLocal() as session:
                service = AdminService(session)
                projects = await service.get_pending_projects()

                assert isinstance(projects, list)
                assert len(projects) >= 1
                # Check that our created project is in the pending list
                assert any(p.id == self.created_project_id for p in projects)

                self._log_pass("Admin get pending projects")

        except Exception as e:
            self._log_fail(f"Admin get pending projects: {str(e)}")

    async def test_admin_approve_project(self):
        """✓ Test 4: Admin aprova projeto e provisiona tenant"""
        try:
            if not self.created_project_id:
                raise ValueError("No project created in previous test")
            if not self.admin_user_id:
                raise ValueError("Admin user not created in setup")

            async with AsyncSessionLocal() as session:
                service = AdminService(session)

                # Approve the project
                approved_project = await service.approve_project_request(
                    request_id=self.created_project_id,
                    admin_id=self.admin_user_id
                )

                assert approved_project is not None
                assert approved_project.status == ProjectRequestStatus.APPROVED
                assert approved_project.approved_by == self.admin_user_id
                assert approved_project.approved_at is not None

                self._log_pass("Admin approve project")

        except Exception as e:
            self._log_fail(f"Admin approve project: {str(e)}")

    async def test_tenant_schema_created(self):
        """✓ Test 5: Schema do tenant foi criado"""
        try:
            if not self.created_schema_name:
                raise ValueError("No schema name available")

            async with engine.begin() as conn:
                # Verifica se schema existe
                result = await conn.execute(
                    text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema_name"),
                    {"schema_name": self.created_schema_name}
                )
                schema = result.scalar()
                assert schema is not None, f"Schema {self.created_schema_name} not found"

                self._log_pass(f"Tenant schema created: {self.created_schema_name}")

        except Exception as e:
            self._log_fail(f"Tenant schema created: {str(e)}")

    async def test_tenant_pillar_configurations_seeded(self):
        """✓ Test 6: Configurações de pilares foram seeded no tenant"""
        try:
            if not self.created_schema_name:
                raise ValueError("No schema name available")

            async with AsyncSessionLocal() as session:
                # Set search path to tenant schema
                await session.execute(text(f'SET search_path = "{self.created_schema_name}", public'))

                # Query pillar configurations in tenant schema
                result = await session.execute(select(PillarConfiguration))
                configs = result.scalars().all()

                assert len(configs) == 7, f"Expected 7 pillar configs, got {len(configs)}"

                pillar_codes = [c.pillar_code for c in configs]
                expected_codes = ["P1", "P2", "P3", "P4", "P5", "P6", "P7"]
                assert set(pillar_codes) == set(expected_codes), f"Missing pillars: {set(expected_codes) - set(pillar_codes)}"

                # Valida P7 como bloqueante
                p7_config = next((c for c in configs if c.pillar_code == "P7"), None)
                assert p7_config is not None, "P7 config not found"
                assert p7_config.importance == "high", "P7 should be high importance"

                self._log_pass("Tenant pillar configurations seeded")

        except Exception as e:
            self._log_fail(f"Tenant pillar configurations seeded: {str(e)}")

    async def test_tenant_initial_ogc_created(self):
        """✓ Test 7: OGC inicial foi criada no tenant"""
        try:
            if not self.created_schema_name:
                raise ValueError("No schema name available")

            async with AsyncSessionLocal() as session:
                # Set search path to tenant schema
                await session.execute(text(f'SET search_path = "{self.created_schema_name}", public'))

                # Query OGC versions in tenant schema
                result = await session.execute(select(OGCVersion))
                ogc_versions = result.scalars().all()

                assert len(ogc_versions) >= 1, "OGC v1 should be created"

                ogc_v1 = next((o for o in ogc_versions if o.version == 1), None)
                assert ogc_v1 is not None, "OGC v1 not found"
                assert ogc_v1.is_active is True
                assert ogc_v1.ogc_data is not None
                assert ogc_v1.ogc_data.get("status") == "initialization"

                self._log_pass("Tenant initial OGC created")

        except Exception as e:
            self._log_fail(f"Tenant initial OGC created: {str(e)}")

    async def test_tenant_tables_created(self):
        """✓ Test 8: Todas as tabelas foram criadas no tenant schema"""
        try:
            if not self.created_schema_name:
                raise ValueError("No schema name available")

            expected_tables = [
                "pillar_configuration",
                "ogc_versions",
                "artifacts",
                "artifact_evaluations",
                "audit_log"
            ]

            async with engine.begin() as conn:
                for table_name in expected_tables:
                    result = await conn.execute(
                        text(f"""
                            SELECT table_name FROM information_schema.tables
                            WHERE table_schema = :schema_name AND table_name = :table_name
                        """),
                        {"schema_name": self.created_schema_name, "table_name": table_name}
                    )
                    table = result.scalar()
                    assert table is not None, f"Table {table_name} not found in {self.created_schema_name}"

                self._log_pass(f"Tenant tables created (all {len(expected_tables)} tables present)")

        except Exception as e:
            self._log_fail(f"Tenant tables created: {str(e)}")

    async def test_admin_reject_project(self):
        """✓ Test 9: Admin rejeita projeto"""
        try:
            if not self.gp_user_id or not self.admin_user_id:
                raise ValueError("Users not created in setup")

            import time
            timestamp = int(time.time() * 1000)
            unique_slug = f"test-reject-{timestamp}"

            async with AsyncSessionLocal() as session:
                service = AdminService(session)

                # Create another project to reject
                project = await service.create_project_request(
                    gp_id=self.gp_user_id,
                    project_name="Test Project Reject",
                    project_slug=unique_slug,
                    description="Project to be rejected"
                )

                # Reject it
                rejected_project = await service.reject_project_request(
                    request_id=project.id,
                    admin_id=self.admin_user_id,
                    reason="Does not meet business requirements"
                )

                assert rejected_project.status == ProjectRequestStatus.REJECTED
                assert rejected_project.rejection_reason == "Does not meet business requirements"

                self._log_pass("Admin reject project")

        except Exception as e:
            self._log_fail(f"Admin reject project: {str(e)}")

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
        print("║      TESTE DE INTEGRAÇÃO - FASE 2 GCA (Admin & Provisioning) ║")
        print("╚════════════════════════════════════════════════════════════════╝\n")

        # Setup test users first
        await self.test_setup_users()

        # Admin project tests
        await self.test_admin_create_project_request()
        await self.test_admin_get_pending_projects()
        await self.test_admin_approve_project()

        # Tenant provisioning tests
        await self.test_tenant_schema_created()
        await self.test_tenant_pillar_configurations_seeded()
        await self.test_tenant_initial_ogc_created()
        await self.test_tenant_tables_created()

        # Admin rejection test
        await self.test_admin_reject_project()

        return self.print_results()

    def print_results(self):
        """Imprime resultados finais"""
        total = self.passed + self.failed
        percentage = (self.passed / total * 100) if total > 0 else 0

        print("\n" + "="*70)
        print("RESULTADOS DOS TESTES DE INTEGRAÇÃO - FASE 2")
        print("="*70)
        print(f"\n✅ Passou: {self.passed}/{total}")
        print(f"❌ Falhou: {self.failed}/{total}")
        print(f"📊 Taxa de sucesso: {percentage:.1f}%\n")

        if self.failed == 0:
            print("🎉 TODOS OS TESTES DE INTEGRAÇÃO PASSARAM!")
            print("\n✨ FASE 2 APROVADA - PRONTO PARA FASE 3 (Evaluation Engine)")
            return True
        else:
            print("⚠️  ALGUNS TESTES DE INTEGRAÇÃO FALHARAM")
            print("\n❌ FASE 2 NÃO APROVADA - REVISAR ERROS")
            return False


async def main():
    tester = AdminIntegrationTester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
