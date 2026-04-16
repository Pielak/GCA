"""
GCA - Gerenciador Central de Arquiteturas
API Principal
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import structlog
from app.core.config import settings
from app.db.database import init_db
from app.routers import auth, projects, onboarding, admin, evaluation, code_generation, dashboard, validation, github, questionnaires, webhooks, agents, git_router, settings_router, ingestion_router, gatekeeper_router, module_router, livedocs_router, roadmap_router, admin_gca_router, setup, qa_router, external_repos_router, notifications_router, deliverables_router, public_requests_router
from app.routers.admin_gp_router import router as admin_gp_router
from app.routers.project_setup_router import router as project_setup_router
from app.routers.member_roles_router import router as member_roles_router
from app.routers.pipeline_quality_router import router as pipeline_quality_router
from app.routers.pipeline_audit_router import router as pipeline_audit_router
from app.routers.pipeline_orchestration_router import router as pipeline_orchestration_router
from app.routers.questionnaire_pdf_router import router as questionnaire_pdf_router

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle management for the application
    """
    # Startup
    logger.info("gca.startup", version=settings.APP_VERSION)

    # Initialize database
    try:
        await init_db()
        logger.info("gca.database_ready")
    except Exception as e:
        logger.error("gca.database_initialization_failed", error=str(e))
        raise

    # Archival de tokens expirados é feito via endpoint POST /questionnaires/archive-expired
    # e não mais no startup para evitar timeout de conexão

    yield

    # Shutdown
    logger.info("gca.shutdown")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# Routes
app.include_router(auth.router, prefix=f"{settings.API_PREFIX}/auth", tags=["auth"])
app.include_router(projects.router, prefix=f"{settings.API_PREFIX}/projects", tags=["projects"])
app.include_router(admin.router, prefix=f"{settings.API_PREFIX}/admin", tags=["admin"])
app.include_router(onboarding.router, prefix=f"{settings.API_PREFIX}/onboarding", tags=["onboarding"])
app.include_router(evaluation.router, prefix=f"{settings.API_PREFIX}", tags=["evaluation"])
app.include_router(code_generation.router)
app.include_router(dashboard.router)
app.include_router(validation.router)
app.include_router(github.router)
app.include_router(questionnaires.router, prefix=f"{settings.API_PREFIX}/questionnaires", tags=["questionnaires"])
app.include_router(webhooks.router, prefix=f"{settings.API_PREFIX}", tags=["webhooks"])
app.include_router(agents.router, prefix=f"{settings.API_PREFIX}", tags=["agents"])
app.include_router(git_router.router, prefix=f"{settings.API_PREFIX}", tags=["git"])
app.include_router(settings_router.router, prefix=f"{settings.API_PREFIX}", tags=["settings"])
app.include_router(ingestion_router.router, prefix=f"{settings.API_PREFIX}", tags=["ingestion"])
app.include_router(gatekeeper_router.router, prefix=f"{settings.API_PREFIX}", tags=["gatekeeper"])
app.include_router(module_router.router, prefix=f"{settings.API_PREFIX}", tags=["modules"])
app.include_router(livedocs_router.router, prefix=f"{settings.API_PREFIX}", tags=["livedocs"])
app.include_router(roadmap_router.router, prefix=f"{settings.API_PREFIX}", tags=["roadmap"])
app.include_router(admin_gca_router.router, prefix=f"{settings.API_PREFIX}", tags=["admin-gca"])
app.include_router(setup.router, prefix=f"{settings.API_PREFIX}", tags=["setup"])
app.include_router(qa_router.router, prefix=f"{settings.API_PREFIX}", tags=["qa"])
app.include_router(external_repos_router.router, prefix=f"{settings.API_PREFIX}", tags=["external-repos"])
app.include_router(notifications_router.router, prefix=f"{settings.API_PREFIX}", tags=["notifications"])
app.include_router(deliverables_router.router, prefix=f"{settings.API_PREFIX}", tags=["deliverables"])
app.include_router(public_requests_router.router, prefix=f"{settings.API_PREFIX}", tags=["public"])
app.include_router(admin_gp_router, prefix=f"{settings.API_PREFIX}", tags=["admin-gp"])
app.include_router(project_setup_router, prefix=f"{settings.API_PREFIX}")
app.include_router(member_roles_router, prefix=f"{settings.API_PREFIX}")
app.include_router(pipeline_quality_router, prefix=f"{settings.API_PREFIX}")
app.include_router(pipeline_audit_router, prefix=f"{settings.API_PREFIX}")
app.include_router(pipeline_orchestration_router, prefix=f"{settings.API_PREFIX}")
app.include_router(questionnaire_pdf_router, prefix=f"{settings.API_PREFIX}", tags=["questionnaire-pdf"])


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": f"{settings.API_PREFIX}/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
