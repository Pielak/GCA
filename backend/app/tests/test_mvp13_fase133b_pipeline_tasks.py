"""MVP 13 Fase 13.3b — 6 pontos restantes de asyncio.create_task em
ingestion_service migrados para Celery.

Pontos cobertos:
- Linha ~247 (propagate após OCG update com changes) → propagate_task.
- Linha ~255 (regenerate_backlog sem changes) → regenerate_backlog_task.
- Linha ~263 (reevaluate_gatekeeper) → reevaluate_gatekeeper_task.
- Linha ~401 (upload_document dispara _analyze_with_timeout) →
  pipeline_ingest_task (reusado da 13.3a).
- Linhas ~1327, ~1338 (caminho OCG reactive) → propagate_task +
  reevaluate_gatekeeper_task.

Pós-13.3b: `ingestion_service.py` tem ZERO `asyncio.create_task`.
Restante fica em 13.3c (ocg_updater_service + external_repos_router).
"""
import pytest

# Garante registro das tasks no celery_app em pytest.
import app.tasks.pipeline  # noqa: F401


# ─── Registro das tasks ───────────────────────────────────────────────


@pytest.mark.parametrize("task_name", [
    "app.tasks.pipeline.pipeline_ingest_task",
    "app.tasks.pipeline.propagate_task",
    "app.tasks.pipeline.regenerate_backlog_task",
    "app.tasks.pipeline.reevaluate_gatekeeper_task",
])
def test_task_registrada(task_name):
    from app.celery_app import celery_app
    assert task_name in celery_app.tasks


@pytest.mark.parametrize("task_name", [
    "app.tasks.pipeline.propagate_task",
    "app.tasks.pipeline.regenerate_backlog_task",
    "app.tasks.pipeline.reevaluate_gatekeeper_task",
])
def test_retry_policy_bounded(task_name):
    from app.celery_app import celery_app
    task = celery_app.tasks[task_name]
    assert task.max_retries == 2
    assert task.default_retry_delay == 30


# ─── ingestion_service sem asyncio.create_task ────────────────────────


def test_ingestion_service_sem_asyncio_create_task():
    """Após 13.3b, todos os 6 pontos devem ter virado .delay()."""
    import inspect
    from app.services import ingestion_service

    src = inspect.getsource(ingestion_service)
    # Extrai apenas linhas ativas (sem comentários).
    active = [
        line for line in src.splitlines()
        if "asyncio.create_task" in line and not line.strip().startswith("#")
    ]
    assert active == [], f"create_task ativo em ingestion_service: {active}"


def test_ingestion_service_usa_pipeline_tasks():
    """Confirma que os nomes canônicos das tasks são invocados."""
    import inspect
    from app.services import ingestion_service

    src = inspect.getsource(ingestion_service)
    assert "pipeline_ingest_task.delay" in src
    assert "propagate_task.delay" in src
    assert "regenerate_backlog_task.delay" in src
    assert "reevaluate_gatekeeper_task.delay" in src


# ─── Tasks invocáveis via .apply() síncrono (sem tocar conf global) ──
#
# Não usamos CELERY_TASK_ALWAYS_EAGER aqui porque vaza pros testes
# subsequentes (celery_app é singleton). `.apply()` executa a task
# sincronamente sem depender da conf global.


def test_propagate_task_forwards_args(monkeypatch):
    captured = {}

    async def fake_propagate(*, project_id, changes, ocg_version):
        captured["project_id"] = project_id
        captured["changes"] = changes
        captured["ocg_version"] = ocg_version

    monkeypatch.setattr("app.services.ingestion_service._propagate_async", fake_propagate)

    from app.tasks.pipeline import propagate_task
    result = propagate_task.apply(args=[
        "00000000-0000-0000-0000-000000000001",
        [{"key": "PILLAR_SCORES", "op": "update"}],
        3,
    ])
    assert result.result == {"status": "ok", "project_id": "00000000-0000-0000-0000-000000000001"}
    from uuid import UUID
    assert captured["project_id"] == UUID("00000000-0000-0000-0000-000000000001")
    assert captured["changes"] == [{"key": "PILLAR_SCORES", "op": "update"}]
    assert captured["ocg_version"] == 3


def test_regenerate_backlog_task_forwards_args(monkeypatch):
    captured = {}

    async def fake_regen(*, project_id, ocg_version, trigger):
        captured["project_id"] = project_id
        captured["ocg_version"] = ocg_version
        captured["trigger"] = trigger

    monkeypatch.setattr("app.services.ingestion_service._regenerate_backlog_async", fake_regen)

    from app.tasks.pipeline import regenerate_backlog_task
    result = regenerate_backlog_task.apply(args=[
        "00000000-0000-0000-0000-000000000042",
        5,
        "document_ingestion",
    ])
    assert result.result["status"] == "ok"
    from uuid import UUID
    assert captured["project_id"] == UUID("00000000-0000-0000-0000-000000000042")
    assert captured["trigger"] == "document_ingestion"


def test_reevaluate_gatekeeper_task_forwards_args(monkeypatch):
    captured = {}

    async def fake_reeval(*, project_id, ocg_version, trigger):
        captured["project_id"] = project_id
        captured["ocg_version"] = ocg_version
        captured["trigger"] = trigger

    monkeypatch.setattr("app.services.ingestion_service._reevaluate_gatekeeper_async", fake_reeval)

    from app.tasks.pipeline import reevaluate_gatekeeper_task
    result = reevaluate_gatekeeper_task.apply(args=[
        "00000000-0000-0000-0000-000000000007",
        2,
        "manual",
    ])
    assert result.result["status"] == "ok"
    assert captured["trigger"] == "manual"
