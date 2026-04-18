"""
Pytest configuration and fixtures for GCA Admin Dashboard tests.

DT-034: forçar DATABASE_URL pra `gca_test` **antes** de qualquer import de
`app.*`. Pydantic Settings lê env na hora do import de `app.core.config`;
services que importam `AsyncSessionLocal`/`engine` de `app.db.database`
são bindados ao objeto criado com a URL vigente naquele momento. Por isso
o override precisa rodar no topo do conftest, antes de `from app.main`.

Guard adicional: se por qualquer motivo a URL resolver pra `gca`
(produção/dogfood), levanta RuntimeError — pytest **não pode** tocar prod.
"""
import os as _os
import re as _re

# ---------------------------------------------------------------------------
# DT-034: isolamento duro de DB antes de carregar `app.*`
# ---------------------------------------------------------------------------
# Sobrescreve DATABASE_URL pra apontar pra `gca_test` (schema clonado de
# produção mas sem dados). Pydantic Settings lê env no primeiro import de
# `app.core.config`, então esta atribuição precisa ser a primeira coisa do
# conftest — antes de qualquer `from app...`.
_default_test_url = "postgresql+asyncpg://gca:gca_secret@localhost:5432/gca_test"
_os.environ["DATABASE_URL"] = _os.environ.get("TEST_DATABASE_URL", _default_test_url)
_os.environ.setdefault("TESTING", "1")

import pytest
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx

from app.main import app
from app.db.database import Base, get_db, AsyncSessionLocal
from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.base import User, Organization, Project

# Safety fuse: se settings.DATABASE_URL for a DB de produção (`/gca`), aborta
# antes de qualquer fixture rodar. Evita que factories/services que fazem
# `async with AsyncSessionLocal() as db` contaminem o dogfood.
_prod_db_pattern = _re.compile(r"/gca(\?|$)")
if _prod_db_pattern.search(settings.DATABASE_URL):
    raise RuntimeError(
        f"DT-034 BLOCK: DATABASE_URL aponta pra DB de produção ({settings.DATABASE_URL}). "
        "pytest não pode rodar contra `gca`. Defina TEST_DATABASE_URL pra `gca_test` "
        "ou confirme que o conftest está sendo carregado antes dos imports de app.*"
    )
if "gca_test" not in settings.DATABASE_URL:
    raise RuntimeError(
        f"DT-034 BLOCK: DATABASE_URL inesperada pra testes ({settings.DATABASE_URL}). "
        "Esperado conter `gca_test`."
    )


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()

    yield loop

    try:
        loop.close()
    except:
        pass


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a test database session with auto-rollback.
    Wraps in a transaction and replaces commit/rollback with
    savepoint operations so service-level commits don't persist.
    """
    from sqlalchemy.ext.asyncio import AsyncSession as _AS

    async with AsyncSessionLocal() as session:
        trans = await session.begin()

        # Replace commit with flush (keeps data visible in session
        # but doesn't commit the outer transaction)
        _original_commit = session.commit
        _original_rollback = session.rollback

        async def _fake_commit():
            await session.flush()

        async def _fake_rollback():
            pass  # ignore service rollbacks

        session.commit = _fake_commit  # type: ignore
        session.rollback = _fake_rollback  # type: ignore

        try:
            yield session
        finally:
            session.commit = _original_commit  # type: ignore
            session.rollback = _original_rollback  # type: ignore
            # DT-040: teardown silencioso. asyncpg + NullPool + TestClient
            # (que usa loop próprio) dispara `RuntimeError: Event loop is
            # closed` ao cancelar tasks pendentes no close da conexão. O
            # rollback em si já ocorreu no fluxo do teste; suprimir o
            # ruído de cancelamento evita falsos errors em testes que só
            # fazem request GET via sync_client (test_setup_wizard).
            try:
                await trans.rollback()
            except RuntimeError as e:
                if "Event loop is closed" not in str(e):
                    raise


# ============================================================================
# User & Authentication Fixtures
# ============================================================================

@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user in the database."""
    uid = uuid4()
    user = User(
        id=uid,
        email=f"testuser-{uid.hex[:8]}@example.com",
        password_hash=hash_password("testpassword123"),
        full_name="Test User",
        is_active=True,
        is_admin=True,
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def test_non_admin_user(db_session: AsyncSession) -> User:
    """Create a test non-admin user in the database."""
    uid = uuid4()
    user = User(
        id=uid,
        email=f"regularuser-{uid.hex[:8]}@example.com",
        password_hash=hash_password("testpassword123"),
        full_name="Regular User",
        is_active=True,
        is_admin=False,
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def test_organization(db_session: AsyncSession, test_user: User):
    """Create a test organization in the database."""
    org = Organization(
        id=uuid4(),
        name=f"Test Organization {uuid4().hex[:8]}",
        slug=f"test-org-{uuid4().hex[:8]}",
        description="A test organization",
        owner_id=test_user.id,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest.fixture
async def test_project(db_session: AsyncSession, test_user: User, test_organization: Organization):
    """Create a test project in the database."""
    project = Project(
        id=uuid4(),
        organization_id=test_organization.id,
        name="Test Project",
        slug=f"test-project-{uuid4().hex[:8]}",
        description="A test project",
        # DT-040: `deliverable_type` é NOT NULL desde DT-015. Fixture default
        # pra "new_system" — testes que precisarem de outro tipo criam
        # Project(...) manualmente.
        deliverable_type="new_system",
        status="active",
        created_at=datetime.utcnow(),
    )
    db_session.add(project)
    await db_session.flush()
    return project


@pytest.fixture
def auth_token(test_user: User) -> str:
    """Generate a valid JWT token for the test admin user."""
    return create_access_token(data={"sub": str(test_user.id)})


@pytest.fixture
def non_admin_token(test_non_admin_user: User) -> str:
    """Generate a valid JWT token for the test non-admin user."""
    return create_access_token(data={"sub": str(test_non_admin_user.id)})


@pytest.fixture
def invalid_token() -> str:
    """Return an invalid JWT token."""
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.invalid"


# ============================================================================
# FastAPI Client Fixtures
# ============================================================================

@pytest.fixture
def test_app(db_session: AsyncSession) -> FastAPI:
    """Create a test FastAPI app with database dependency overridden."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def sync_client(test_app: FastAPI) -> TestClient:
    """Synchronous test client for FastAPI."""
    return TestClient(test_app)


@pytest.fixture
def async_client(test_app: FastAPI) -> TestClient:
    """Alias for sync_client (all tests use sync TestClient)"""
    return TestClient(test_app)


# ============================================================================
# Request Header Fixtures
# ============================================================================

@pytest.fixture
def auth_headers(auth_token: str) -> dict:
    """Return authorization headers with admin token."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def non_admin_auth_headers(non_admin_token: str) -> dict:
    """Return authorization headers with non-admin token."""
    return {"Authorization": f"Bearer {non_admin_token}"}


@pytest.fixture
def invalid_auth_headers(invalid_token: str) -> dict:
    """Return authorization headers with invalid token."""
    return {"Authorization": f"Bearer {invalid_token}"}


# ============================================================================
# E2E Pipeline Fixtures (FASE 6)
# ============================================================================

@pytest.fixture
async def test_gp_user(db_session: AsyncSession) -> User:
    """Create a test GP (Gestor de Projeto) user for questionnaire submission."""
    uid = uuid4()
    user = User(
        id=uid,
        email=f"gp-{uid.hex[:8]}@example.com",
        password_hash=hash_password("gppassword123"),
        full_name="Test GP User",
        is_active=True,
        is_admin=False,
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def complete_questionnaire_response() -> dict:
    """
    Complete questionnaire response — 49 perguntas (Q1–Q49), 8 blocos (A.1–A.8).
    Chaves numéricas como strings. Retorna um questionário válido e aprovável (score >= 85).
    """
    return {
        # A.1 — Informações gerais do projeto
        "1": "E-Commerce Platform",                        # project_name
        "2": "e-commerce-platform",                        # project_slug
        "3": "Não",                                        # is_existing_project
        "4": ["Novo sistema"],                             # initiative_type
        "5": "Alta",                                       # criticality
        "6": "Confidencial",                               # information_classification
        # A.2 — Projetos existentes (não aplicável, Q3 = Não)
        # "7"-"14" omitidos
        # A.3 — Perfil de entrega e arquitetura alvo
        "15": ["Aplicação web", "API"],                    # main_deliverable
        "16": ["Monólito modular"],                        # architectural_profile
        "17": "Cloud",                                     # execution_model
        "18": "Não",                                       # multi_tenant
        "19": "Sim",                                       # high_availability
        "20": "Sim",                                       # async_processing
        # A.4 — Frontend
        "21": "Sim",                                       # has_frontend
        "22": ["Web SPA", "Portal autenticado"],           # frontend_type
        "23": ["React", "Vite + React"],                   # frontend_stack
        "24": "TypeScript",                                # frontend_language
        "25": ["Responsividade", "Dark theme",
               "Formulários complexos", "Gráficos"],       # frontend_requirements
        # A.5 — Backend e APIs
        "26": "Sim",                                       # has_backend
        "27": "Python",                                    # backend_language
        "28": ["FastAPI"],                                 # backend_framework
        "29": ["REST API", "WebSocket"],                   # backend_type
        "30": ["Autenticação", "RBAC", "Webhooks",
               "Jobs", "Auditoria", "Observabilidade",
               "Integração com IA"],                       # backend_requirements
        # A.6 — Dados, cache, mensageria e automação
        "31": "PostgreSQL",                                # primary_database
        "32": ["Transacional", "Misto"],                   # database_usage_profile
        "33": "Sim",                                       # needs_redis
        "34": ["Cache de leitura", "Sessões",
               "Rate limiting"],                           # redis_purpose
        "35": "Sim",                                       # needs_messaging
        "36": ["Eventos de domínio",
               "Processamento em background"],             # messaging_purpose
        "37": "Sim",                                       # uses_n8n
        "38": ["Automação de integrações",
               "Notificações"],                            # n8n_purpose
        # A.7 — IA, segurança e observabilidade
        "39": "Sim",                                       # uses_ai
        "40": ["Análise de requisitos", "Geração de código",
               "Revisão de código"],                       # ai_purpose
        "41": ["Anthropic"],                               # ai_provider
        "42": ["Mascaramento",
               "Avaliação por tipo de dado"],              # ai_restrictions
        "43": ["JWT", "OAuth2", "MFA",
               "Criptografia em trânsito",
               "Criptografia em repouso",
               "Vault de segredos",
               "Trilhas de auditoria"],                    # security_controls
        "44": ["Logs estruturados", "Métricas",
               "Tracing", "Health checks", "Alertas"],     # observability
        # A.8 — Testes, validação e entregáveis
        "45": ["Unitários", "Integração", "E2E",
               "Segurança", "SAST/SCA",
               "Performance/Carga", "Regressão"],          # test_types
        "46": "Sim",                                       # automated_quality_gate
        "47": "Sim",                                       # formal_qa_evidence
        "48": ["Sugestão de arquitetura",
               "Sugestão de stack",
               "Documento técnico consolidado",
               "Gap analysis", "Plano de testes",
               "Plano de segurança"],                      # pipeline_deliverables
        "49": ["Painel no GCA", "JSON estruturado"],       # output_format
    }


@pytest.fixture
def complete_questionnaire_response_named() -> dict:
    """
    Formato legado com campos nomeados (retrocompatibilidade).
    """
    return {
        "project_name": "E-Commerce Platform",
        "has_frontend": "Sim",
        "has_backend": "Sim",
        "frontend_stack": ["React", "Vite + React"],
        "backend_language": "Python",
        "backend_framework": ["FastAPI"],
        "primary_database": "PostgreSQL",
        "architectural_profile": ["Monólito modular"],
        "execution_model": "Cloud",
        "uses_ai": "Sim",
        "ai_provider": ["Anthropic"],
        "security_controls": ["JWT", "OAuth2", "Criptografia em trânsito",
                              "Criptografia em repouso"],
        "test_types": ["Unitários", "Integração", "E2E"],
        "main_deliverable": ["Aplicação web", "API"],
        "criticality": "Alta",
        "information_classification": "Confidencial",
        "observability": ["Health checks", "Métricas", "Alertas"],
    }


@pytest.fixture
def mock_generated_code() -> str:
    """Mock generated code response from LLM."""
    return '''
"""
Generated Python microservice for E-Commerce Platform
"""
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="E-Commerce API")

# ============================================================================
# Models
# ============================================================================

class Product(BaseModel):
    """Product model with security considerations"""
    id: str
    name: str
    price: float
    description: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "id": "prod_123",
                "name": "Wireless Headphones",
                "price": 99.99,
                "description": "Premium wireless headphones"
            }
        }


class Order(BaseModel):
    """Order model with compliance requirements (LGPD)"""
    id: str
    customer_id: str  # PII - handle according to LGPD
    products: List[str]
    total: float
    status: str


# ============================================================================
# Authentication & Security
# ============================================================================

async def verify_auth_token(token: str) -> str:
    """
    Verify JWT token - CRITICAL: This is a critical security finding.
    Ensure OAuth2/Auth0 integration for production.
    """
    # TODO: Replace with Auth0 integration
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return "user_id"


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/products", response_model=List[Product])
async def list_products():
    """Get all products - Unit test required (80% coverage target)"""
    return []


@app.post("/orders", response_model=Order)
async def create_order(order: Order):
    """Create order - Security test required (OWASP Top 10)"""
    # LGPD Compliance: Log order creation with customer PII protection
    return order


# ============================================================================
# Testing Fixtures
# ============================================================================

@pytest.fixture
def test_client():
    """Test client for integration tests"""
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def sample_product():
    """Sample product for testing"""
    return Product(
        id="test_prod_1",
        name="Test Product",
        price=29.99
    )


# ============================================================================
# Compliance & LDGP
# ============================================================================

class ComplianceHandler:
    """Handle LGPD compliance requirements"""

    @staticmethod
    async def redact_pii(data: dict) -> dict:
        """Redact personally identifiable information per LGPD"""
        if "customer_id" in data:
            data["customer_id"] = "***REDACTED***"
        return data


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
'''


# ============================================================================
# Markers
# ============================================================================

def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line("markers", "asyncio: mark test as async")
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "unit: mark test as unit test")
