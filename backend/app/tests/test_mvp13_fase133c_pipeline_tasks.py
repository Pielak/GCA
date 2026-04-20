"""MVP 13 Fase 13.3c — 3 pontos finais de asyncio.create_task migrados.

Pontos cobertos:
- ocg_updater_service.py:369 → `auto_generate_task`.
- external_repos_router.py:199,205 → `external_repo_fallback_task`.

Pós-13.3c: pipeline Arguider + OCG Updater + auto-CodeGen = 100%
Celery dentro do escopo §7 MVP 13 Fase 13.3. Questionnaire e
Gatekeeper ficam fora por design (cobertos por watchdog DT-073 até
decisão explícita do stakeholder expandir escopo).
"""
import pytest

import app.tasks.pipeline  # noqa: F401 — registra tasks


@pytest.mark.parametrize("task_name", [
    "app.tasks.pipeline.auto_generate_task",
    "app.tasks.pipeline.external_repo_fallback_task",
])
def test_task_registrada(task_name):
    from app.celery_app import celery_app
    assert task_name in celery_app.tasks


@pytest.mark.parametrize("task_name,delay", [
    ("app.tasks.pipeline.auto_generate_task", 30),
    ("app.tasks.pipeline.external_repo_fallback_task", 60),
])
def test_retry_policy_bounded(task_name, delay):
    from app.celery_app import celery_app
    task = celery_app.tasks[task_name]
    assert task.max_retries == 2
    assert task.default_retry_delay == delay


def test_ocg_updater_service_sem_asyncio_create_task():
    import inspect
    from app.services import ocg_updater_service

    src = inspect.getsource(ocg_updater_service)
    active = [
        line for line in src.splitlines()
        if "asyncio.create_task" in line and not line.strip().startswith("#")
    ]
    assert active == [], f"create_task ativo em ocg_updater_service: {active}"


def test_external_repos_router_sem_asyncio_create_task():
    import inspect
    from app.routers import external_repos_router

    src = inspect.getsource(external_repos_router)
    active = [
        line for line in src.splitlines()
        if "asyncio.create_task" in line and not line.strip().startswith("#")
    ]
    assert active == [], f"create_task ativo em external_repos_router: {active}"


def test_ocg_updater_usa_auto_generate_task():
    import inspect
    from app.services import ocg_updater_service
    src = inspect.getsource(ocg_updater_service)
    assert "auto_generate_task.delay" in src


def test_external_repos_usa_fallback_task():
    import inspect
    from app.routers import external_repos_router
    src = inspect.getsource(external_repos_router)
    assert "external_repo_fallback_task.delay" in src


def test_auto_generate_task_forwards_args(monkeypatch):
    """.apply() síncrono — task chama _auto_generate_in_background com args."""
    captured = {}

    async def fake_auto(project_id, updated_ocg):
        captured["project_id"] = project_id
        captured["updated_ocg"] = updated_ocg

    monkeypatch.setattr("app.services.ocg_updater_service._auto_generate_in_background", fake_auto)

    from app.tasks.pipeline import auto_generate_task
    result = auto_generate_task.apply(args=[
        "00000000-0000-0000-0000-000000000099",
        {"STACK_RECOMMENDATION": {"backend": "FastAPI"}, "version": 3},
    ])
    assert result.result["status"] == "ok"
    from uuid import UUID
    assert captured["project_id"] == UUID("00000000-0000-0000-0000-000000000099")
    assert captured["updated_ocg"]["version"] == 3


def test_external_fallback_task_forwards_args(monkeypatch):
    captured = {}

    async def fake_fallback(project_id, repo_id):
        captured["project_id"] = project_id
        captured["repo_id"] = repo_id

    monkeypatch.setattr("app.routers.external_repos_router._run_analysis_fallback", fake_fallback)

    from app.tasks.pipeline import external_repo_fallback_task
    result = external_repo_fallback_task.apply(args=[
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
    ])
    assert result.result["status"] == "ok"
    from uuid import UUID
    assert captured["project_id"] == UUID("00000000-0000-0000-0000-000000000001")
    assert captured["repo_id"] == UUID("00000000-0000-0000-0000-000000000002")


def test_fase133_escopo_completo_zero_create_task_no_pipeline():
    """Confirma que os 4 arquivos do escopo Fase 13.3 (Arguider + OCG +
    external_repos + router ingestion) estão 100% Celery."""
    import inspect
    from app.services import ingestion_service, ocg_updater_service
    from app.routers import external_repos_router, ingestion_router

    for mod in (ingestion_service, ocg_updater_service, external_repos_router, ingestion_router):
        src = inspect.getsource(mod)
        active = [
            line for line in src.splitlines()
            if "asyncio.create_task" in line and not line.strip().startswith("#")
        ]
        assert active == [], f"create_task ativo em {mod.__name__}: {active}"
