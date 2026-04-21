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
from app.routers.metrics_router import router as metrics_router, project_router as metrics_project_router
from app.routers.backup_router import (
    router as backup_project_router,
    admin_router as backup_admin_router,
    status_router as backup_status_router,
)
from app.routers.help_router import router as help_router
from app.routers.incident_ticket_router import (
    router as incident_project_router,
    ticket_router as incident_ticket_router,
    admin_router as incident_admin_router,
    support_router as incident_support_router,
)
from app.routers.release_router import (
    admin_router as release_admin_router,
    user_router as release_user_router,
)

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

    # Backup-4: scheduler diário 12:00 BRT + catch-up no startup.
    # Pula em test environment pra não disparar backups durante pytest.
    import os as _os
    if "PYTEST_CURRENT_TEST" not in _os.environ:
        try:
            from app.services.backup_scheduler import start_scheduler
            start_scheduler()
        except Exception as e:
            logger.error("gca.scheduler_start_failed", error=str(e))

    # MVP 7: sincroniza releases declaradas (backend/releases/*.yaml) com
    # a tabela `releases` e aplica as não-destrutivas automaticamente.
    # Releases destrutivas ficam pending até Admin confirmar.
    if "PYTEST_CURRENT_TEST" not in _os.environ:
        try:
            from app.db.database import AsyncSessionLocal
            from app.services import release_service as _rel_svc
            async with AsyncSessionLocal() as _db:
                created = await _rel_svc.sync_declared_releases(_db)
                if created:
                    logger.info("release.declared_synced", count=len(created),
                                tags=[r.tag for r in created])
                applied = await _rel_svc.apply_nondestructive_pending(_db)
                if applied:
                    logger.info("release.auto_applied", count=len(applied),
                                tags=[r.tag for r in applied])
        except Exception as e:
            logger.error("release.startup_sync_failed", error=str(e))

    # DT-3 dogfood: watchdog limpa docs presos em 'processing' por
    # reinício de backend (asyncio.create_task morre com o processo).
    # Também resolve sintoma operacional da DT-5 (sem fila persistente).
    if "PYTEST_CURRENT_TEST" not in _os.environ:
        try:
            from app.services.ingestion_watchdog import recover_zombie_documents
            summary = await recover_zombie_documents()
            if summary["recovered"]:
                logger.warning(
                    "ingestion.startup_watchdog_recovered",
                    recovered=summary["recovered"],
                    threshold_minutes=summary["threshold_minutes"],
                )
        except Exception as e:
            logger.error("ingestion.startup_watchdog_failed", error=str(e))

    # MVP 13 Fase 13.2: smoke do broker Celery no startup.
    # Worker roda em processo separado (gca-celery-worker). Aqui só
    # checamos conectividade do broker. Falha de broker é aviso, não
    # fatal — backend continua operacional para endpoints que não
    # dependem de fila.
    if "PYTEST_CURRENT_TEST" not in _os.environ:
        try:
            from app.celery_app import check_broker_connection
            broker_status = check_broker_connection(timeout=2.0)
            if broker_status["reachable"]:
                logger.info("celery.broker_reachable", broker=broker_status["broker"])
            else:
                logger.warning(
                    "celery.broker_unreachable",
                    broker=broker_status["broker"],
                    error=broker_status["error"],
                )
        except Exception as e:
            logger.error("celery.broker_check_failed", error=str(e))

    yield

    # Shutdown
    try:
        from app.services.backup_scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    logger.info("gca.shutdown")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# MVP 12 Fase 12.1 — Rate limit (slowapi) anti-abuse em endpoints públicos.
# Limiter fica acessível globalmente via `app.state.limiter` e os routers
# usam `@limiter.limit(...)` nos endpoints que decidirem aplicar. Key
# function default (`get_remote_address`) é por IP do cliente.
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS Middleware
# DT-066: expõe X-Access-Token-Renewed pro frontend poder ler o header
# e fazer sliding refresh silencioso. Sem expose_headers, navegador esconde.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
    expose_headers=["X-Access-Token-Renewed"],
)

# DT-066: Sliding session — renova token quando próximo do vencimento
# em respostas 2xx/3xx autenticadas. Deve ser adicionado DEPOIS do CORS
# (Starlette executa na ordem inversa da adição; CORS fica mais externo).
from app.middleware.sliding_session import SlidingSessionMiddleware
app.add_middleware(SlidingSessionMiddleware)

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
app.include_router(metrics_router, prefix=f"{settings.API_PREFIX}", tags=["metrics"])
app.include_router(metrics_project_router, prefix=f"{settings.API_PREFIX}", tags=["project-metrics"])
app.include_router(backup_project_router, prefix=f"{settings.API_PREFIX}", tags=["backups"])
app.include_router(backup_admin_router, prefix=f"{settings.API_PREFIX}", tags=["admin-backups"])
app.include_router(backup_status_router, prefix=f"{settings.API_PREFIX}", tags=["backups"])
app.include_router(help_router, prefix=f"{settings.API_PREFIX}", tags=["help"])
app.include_router(incident_project_router, prefix=f"{settings.API_PREFIX}", tags=["incident-tickets"])
app.include_router(incident_ticket_router, prefix=f"{settings.API_PREFIX}", tags=["incident-tickets"])
app.include_router(incident_admin_router, prefix=f"{settings.API_PREFIX}", tags=["admin-incidents"])
app.include_router(incident_support_router, prefix=f"{settings.API_PREFIX}", tags=["admin-support"])
app.include_router(release_admin_router, prefix=f"{settings.API_PREFIX}", tags=["admin-releases"])
app.include_router(release_user_router, prefix=f"{settings.API_PREFIX}", tags=["releases"])


@app.get("/health")
async def health_check():
    """Health check endpoint.

    MVP 13 Fase 13.2 — inclui status do broker Celery e contagem de
    workers online. Se o broker estiver fora, o backend segue respondendo
    (status="ok") mas `celery.broker.reachable=False` sinaliza a
    degradação para LB/Prometheus/uptime monitor.
    """
    from app.celery_app import check_broker_connection, check_workers_alive

    broker = check_broker_connection(timeout=1.0)
    workers_info = (
        check_workers_alive(timeout=1.0) if broker["reachable"]
        else {"workers": 0, "nodes": [], "error": "broker_unreachable"}
    )
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "celery": {
            "broker": broker,
            "workers": workers_info,
        },
    }


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
