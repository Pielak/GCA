"""MVP 14 Fase 14.1 — Celery em questionnaire_service.

Contrato §7 MVP 14 Fase 14.1:
- 4 asyncio.create_task em `QuestionnaireService.submit_questionnaire`
  migrados para Celery tasks seguindo padrão 13.3.
- Tasks: notify_admins_submitted_task, send_analysis_email_task,
  trigger_n8n_analysis_task, generate_ocg_task.
- `questionnaire_service.py` agora com zero asyncio.create_task.
"""
import inspect

import pytest

import app.tasks.questionnaire  # noqa: F401 — registra tasks


# ─── Registro + retry policy ──────────────────────────────────────────


@pytest.mark.parametrize("task_name", [
    "app.tasks.questionnaire.notify_admins_submitted_task",
    "app.tasks.questionnaire.send_analysis_email_task",
    "app.tasks.questionnaire.trigger_n8n_analysis_task",
    "app.tasks.questionnaire.generate_ocg_task",
])
def test_task_registrada(task_name):
    from app.celery_app import celery_app
    assert task_name in celery_app.tasks


@pytest.mark.parametrize("task_name,delay", [
    ("app.tasks.questionnaire.notify_admins_submitted_task", 30),
    ("app.tasks.questionnaire.send_analysis_email_task", 30),
    ("app.tasks.questionnaire.trigger_n8n_analysis_task", 60),
    ("app.tasks.questionnaire.generate_ocg_task", 60),
])
def test_retry_policy_bounded(task_name, delay):
    from app.celery_app import celery_app
    task = celery_app.tasks[task_name]
    assert task.max_retries == 2
    assert task.default_retry_delay == delay


# ─── questionnaire_service zero create_task ───────────────────────────


def test_questionnaire_service_sem_asyncio_create_task():
    from app.services import questionnaire_service
    src = inspect.getsource(questionnaire_service)
    active = [
        line for line in src.splitlines()
        if "asyncio.create_task" in line and not line.strip().startswith("#")
    ]
    assert active == [], f"create_task ativo em questionnaire_service: {active}"


def test_questionnaire_service_usa_celery_tasks():
    from app.services import questionnaire_service
    src = inspect.getsource(questionnaire_service)
    assert "notify_admins_submitted_task.delay" in src
    assert "send_analysis_email_task.delay" in src
    assert "trigger_n8n_analysis_task.delay" in src
    assert "generate_ocg_task.delay" in src


# ─── Tasks encaminham args corretamente (.apply síncrono) ────────────


def test_notify_admins_submitted_task_forwards_args(monkeypatch):
    captured = {}

    async def fake_notify(*, gp_email, project_name, questionnaire_id, project_id):
        captured.update(
            gp_email=gp_email,
            project_name=project_name,
            questionnaire_id=questionnaire_id,
            project_id=project_id,
        )

    monkeypatch.setattr(
        "app.services.questionnaire_service.QuestionnaireService._notify_admins_questionnaire_submitted",
        fake_notify,
    )

    from app.tasks.questionnaire import notify_admins_submitted_task
    result = notify_admins_submitted_task.apply(args=[
        "gp@test.com",
        "Projeto Foo",
        "q-123",
        "00000000-0000-0000-0000-000000000001",
    ])
    assert result.result == {"status": "ok", "questionnaire_id": "q-123"}
    assert captured["gp_email"] == "gp@test.com"
    assert captured["project_name"] == "Projeto Foo"
    assert captured["questionnaire_id"] == "q-123"
    from uuid import UUID
    assert captured["project_id"] == UUID("00000000-0000-0000-0000-000000000001")


def test_notify_admins_task_com_project_id_none(monkeypatch):
    """Externo (sem project_id) deve passar project_id=None ao handler."""
    captured = {}

    async def fake_notify(*, gp_email, project_name, questionnaire_id, project_id):
        captured["project_id"] = project_id

    monkeypatch.setattr(
        "app.services.questionnaire_service.QuestionnaireService._notify_admins_questionnaire_submitted",
        fake_notify,
    )

    from app.tasks.questionnaire import notify_admins_submitted_task
    result = notify_admins_submitted_task.apply(args=["gp@test.com", "P", "q", None])
    assert result.result["status"] == "ok"
    assert captured["project_id"] is None


def test_send_analysis_email_task_forwards_args(monkeypatch):
    captured = {}

    async def fake_send(*, gp_email, project_id, questionnaire_id, notification_type, analysis_result):
        captured.update(
            gp_email=gp_email, project_id=project_id,
            questionnaire_id=questionnaire_id,
            notification_type=notification_type,
            analysis_result=analysis_result,
        )

    monkeypatch.setattr(
        "app.services.questionnaire_service.QuestionnaireService._send_analysis_email",
        fake_send,
    )

    from app.tasks.questionnaire import send_analysis_email_task
    result = send_analysis_email_task.apply(args=[
        "gp@x", "p-1", "q-1", "approved", {"score": 95},
    ])
    assert result.result["status"] == "ok"
    assert captured["notification_type"] == "approved"
    assert captured["analysis_result"]["score"] == 95


def test_trigger_n8n_analysis_task_forwards_args(monkeypatch):
    captured = {}

    async def fake_n8n(*, questionnaire_id, project_id, gp_email, responses):
        captured.update(
            questionnaire_id=questionnaire_id, project_id=project_id,
            gp_email=gp_email, responses=responses,
        )

    monkeypatch.setattr(
        "app.services.questionnaire_service.QuestionnaireService._trigger_n8n_analysis",
        fake_n8n,
    )

    from app.tasks.questionnaire import trigger_n8n_analysis_task
    result = trigger_n8n_analysis_task.apply(args=[
        "q-7", "p-7", "x@y.com", {"Q1": "a", "Q2": "b"},
    ])
    assert result.result["status"] == "ok"
    assert captured["responses"] == {"Q1": "a", "Q2": "b"}


def test_generate_ocg_task_forwards_args(monkeypatch):
    captured = {}

    async def fake_gen(*, questionnaire_id, project_id, gp_email):
        captured.update(
            questionnaire_id=questionnaire_id,
            project_id=project_id, gp_email=gp_email,
        )

    monkeypatch.setattr(
        "app.services.questionnaire_service.QuestionnaireService._generate_ocg",
        fake_gen,
    )

    from app.tasks.questionnaire import generate_ocg_task
    result = generate_ocg_task.apply(args=[
        "00000000-0000-0000-0000-000000000002",
        "00000000-0000-0000-0000-000000000003",
        "gp@test.com",
    ])
    assert result.result["status"] == "ok"
    from uuid import UUID
    assert captured["questionnaire_id"] == UUID("00000000-0000-0000-0000-000000000002")
    assert captured["project_id"] == UUID("00000000-0000-0000-0000-000000000003")
    assert captured["gp_email"] == "gp@test.com"
