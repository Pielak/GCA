"""
Teste de Regressão - Fase 1 GCA
Valida: Database, Models, Configuration, Encryption, Pilares, Routes
"""
import asyncio
import sys
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from uuid import uuid4

# Adiciona app ao path
sys.path.insert(0, '/app')

from app.db.database import AsyncSessionLocal, engine
from app.models.pillar import PillarTemplate, CompanyPolicy
from app.models.onboarding import (
    ProjectRequest, OnboardingProgress, TeamInvite,
    StackCache, PiloterQuery, PiloterQuotaHistory
)
from app.models.tenant import (
    PillarConfiguration, OGCVersion, Artifact, ArtifactEvaluation, AuditLog
)
from app.models.base import User
from app.core.config import settings
from app.core.security import hash_password, encrypt_token, decrypt_token
from app.services.onboarding_service import OnboardingService


class RegressionTester:
    """Suite de testes de regressão para Fase 1"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests_result = []

    async def test_backend_health(self):
        """✓ Test 1: Health check do backend"""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://localhost:8000/health",
                    timeout=5.0
                )
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "ok"
                assert data["version"] == "0.1.0"
                self._log_pass("Backend health check")
        except Exception as e:
            self._log_fail(f"Backend health check: {str(e)}")

    async def test_database_connection(self):
        """✓ Test 2: Conexão com banco de dados"""
        try:
            async with engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                assert result.scalar() == 1
                self._log_pass("Database connection")
        except Exception as e:
            self._log_fail(f"Database connection: {str(e)}")

    async def test_pillars_seeded(self):
        """✓ Test 3: 7 Pilares foram criados"""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(PillarTemplate)
                )
                pillars = result.scalars().all()

                assert len(pillars) == 7, f"Expected 7 pillars, got {len(pillars)}"

                pillar_codes = [p.code for p in pillars]
                expected_codes = ["P1", "P2", "P3", "P4", "P5", "P6", "P7"]
                assert set(pillar_codes) == set(expected_codes), f"Missing pillars: {set(expected_codes) - set(pillar_codes)}"

                # Valida P7 como bloqueante
                p7 = next((p for p in pillars if p.code == "P7"), None)
                assert p7 is not None, "P7 not found"
                assert p7.is_blocking is True, "P7 should be blocking"
                assert p7.blocking_threshold == 70.0, "P7 threshold should be 70.0"

                self._log_pass(f"7 Pillars seeded (P1-P7 com P7 bloqueante)")

        except Exception as e:
            self._log_fail(f"Pillars seeded: {str(e)}")

    async def test_orm_models_import(self):
        """✓ Test 4: Todos os ORM models importam corretamente"""
        try:
            # Valida que models podem ser instanciados
            pillar = PillarTemplate(
                id=uuid4(),
                code="TEST",
                name="Test Pillar",
                is_blocking=False
            )
            assert pillar is not None

            project_req = ProjectRequest(
                id=uuid4(),
                gp_id=uuid4(),
                project_name="Test Project",
                project_slug="test-project"
            )
            assert project_req is not None

            artifact = Artifact(
                id=uuid4(),
                name="Test Artifact"
            )
            assert artifact is not None

            self._log_pass("ORM models import successfully")

        except Exception as e:
            self._log_fail(f"ORM models import: {str(e)}")

    async def test_encryption_security(self):
        """✓ Test 5: Encryption/Decryption de tokens"""
        try:
            token = "ghp_testtoken123456"
            encrypted = encrypt_token(token)
            assert encrypted != token, "Token should be encrypted"
            assert len(encrypted) > len(token), "Encrypted should be longer"

            decrypted = decrypt_token(encrypted)
            assert decrypted == token, "Decrypted token should match original"

            self._log_pass("Token encryption/decryption working")

        except Exception as e:
            self._log_fail(f"Token encryption: {str(e)}")

    async def test_password_hashing(self):
        """✓ Test 6: Password hashing com bcrypt"""
        try:
            password = "TestPassword@123"
            hashed = hash_password(password)

            assert hashed != password, "Hash should differ from password"
            assert len(hashed) > 20, "Hash should be long enough"
            assert "$2b$" in hashed or "$2a$" in hashed, "Should be bcrypt format"

            self._log_pass("Password hashing working")

        except Exception as e:
            self._log_fail(f"Password hashing: {str(e)}")

    async def test_configuration_settings(self):
        """✓ Test 7: Configurações carregadas do .env"""
        try:
            assert settings.APP_NAME == "GCA - Gerenciador Central de Arquiteturas"
            assert settings.APP_VERSION == "0.1.0"
            assert settings.PILOTER_API_KEY == "4179f4fb-cf46-4d2b-b55c-930278e8fdc5"
            assert settings.PILOTER_API_ENDPOINT == "https://api.piloterr.com/v2"
            assert "http://localhost:5678/webhook" in settings.N8N_WEBHOOK_URL or settings.N8N_WEBHOOK_URL
            assert settings.ONBOARDING_INVITE_EXPIRES_DAYS == 7
            assert settings.STACK_CACHE_DURATION_DAYS == 30

            self._log_pass("Configuration settings loaded correctly")

        except Exception as e:
            self._log_fail(f"Configuration settings: {str(e)}")

    async def test_onboarding_service_init(self):
        """✓ Test 8: OnboardingService pode ser inicializado"""
        try:
            async with AsyncSessionLocal() as session:
                service = OnboardingService(session)
                assert service is not None
                assert service.db is not None

                self._log_pass("OnboardingService initializes correctly")

        except Exception as e:
            self._log_fail(f"OnboardingService init: {str(e)}")

    async def test_pillar_criteria(self):
        """✓ Test 9: Pilares tem critérios detalhados"""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(PillarTemplate).where(PillarTemplate.code == "P7")
                )
                p7 = result.scalar_one()

                assert p7.default_criteria is not None, "P7 should have criteria"
                assert isinstance(p7.default_criteria, dict), "Criteria should be dict"
                assert "compliance" in p7.default_criteria or "security" in p7.default_criteria
                assert len(p7.default_criteria) >= 3, "P7 should have multiple criteria"

                self._log_pass("Pillar criteria properly configured")

        except Exception as e:
            self._log_fail(f"Pillar criteria: {str(e)}")

    async def test_async_sqlalchemy(self):
        """✓ Test 10: Async SQLAlchemy operations"""
        try:
            async with AsyncSessionLocal() as session:
                # Testa SELECT
                result = await session.execute(
                    select(PillarTemplate).limit(1)
                )
                pillar = result.scalar()
                assert pillar is not None, "Should find at least one pillar"

                # Testa contagem
                result = await session.execute(
                    select(PillarTemplate)
                )
                count = len(result.scalars().all())
                assert count == 7, f"Should have 7 pillars, got {count}"

                self._log_pass("Async SQLAlchemy operations working")

        except Exception as e:
            self._log_fail(f"Async SQLAlchemy: {str(e)}")

    async def test_routes_registration(self):
        """✓ Test 11: Rotas de onboarding registradas"""
        try:
            import httpx
            from uuid import uuid4
            test_id = uuid4()
            async with httpx.AsyncClient() as client:
                # Testa que endpoint existe (vai dar erro 422 pois falta body, mas endpoint existe)
                response = await client.post(
                    f"http://localhost:8000/api/v1/onboarding/{test_id}/step-1/repository",
                    json={},
                    timeout=5.0
                )
                # 422 = Unprocessable Entity (validação falhou, mas rota existe)
                assert response.status_code in [422, 400], f"Expected validation error, got {response.status_code}"

                self._log_pass("Onboarding routes registered")

        except Exception as e:
            self._log_fail(f"Routes registration: {str(e)}")

    async def test_cors_configuration(self):
        """✓ Test 12: CORS configurado para produção"""
        try:
            assert "https://gca.code-auditor.com.br" in settings.CORS_ORIGINS
            assert "https://api.code-auditor.com.br" in settings.CORS_ORIGINS
            assert "http://localhost:5173" in settings.CORS_ORIGINS
            assert settings.CORS_ALLOW_CREDENTIALS is True

            self._log_pass("CORS configuration correct")

        except Exception as e:
            self._log_fail(f"CORS configuration: {str(e)}")

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
        print("║         TESTE DE REGRESSÃO - FASE 1 GCA                       ║")
        print("╚════════════════════════════════════════════════════════════════╝\n")

        await self.test_backend_health()
        await self.test_database_connection()
        await self.test_pillars_seeded()
        await self.test_orm_models_import()
        await self.test_encryption_security()
        await self.test_password_hashing()
        await self.test_configuration_settings()
        await self.test_onboarding_service_init()
        await self.test_pillar_criteria()
        await self.test_async_sqlalchemy()
        await self.test_routes_registration()
        await self.test_cors_configuration()

        return self.print_results()

    def print_results(self):
        """Imprime resultados finais"""
        total = self.passed + self.failed
        percentage = (self.passed / total * 100) if total > 0 else 0

        print("\n" + "="*70)
        print("RESULTADOS DOS TESTES")
        print("="*70)
        print(f"\n✅ Passou: {self.passed}/{total}")
        print(f"❌ Falhou: {self.failed}/{total}")
        print(f"📊 Taxa de sucesso: {percentage:.1f}%\n")

        if self.failed == 0:
            print("🎉 TODOS OS TESTES PASSARAM!")
            print("\n✨ FASE 1 APROVADA - PRONTO PARA FASE 2")
            return True
        else:
            print("⚠️  ALGUNS TESTES FALHARAM")
            print("\n❌ FASE 1 NÃO APROVADA - REVISAR ERROS")
            return False


async def main():
    tester = RegressionTester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
