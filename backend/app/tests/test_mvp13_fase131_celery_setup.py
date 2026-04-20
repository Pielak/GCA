"""MVP 13 Fase 13.1 — Setup Celery + infraestrutura.

Contrato §7 MVP 13 Fase 13.1:
- `app.celery_app` expõe Celery app canônico, broker Redis DB 1,
  result backend Redis DB 2.
- Task `ping` serve de smoke/healthcheck: retorna "pong".
- Timezone alinhado à env `BACKUP_TIMEZONE` (default America/Sao_Paulo).
- Modo `CELERY_TASK_ALWAYS_EAGER` configurável via env para testes
  (será estabilizado na Fase 13.4).

Esta suite NÃO depende de worker rodando em background — usa
`ALWAYS_EAGER` por default quando `TEST_DATABASE_URL` isolada está
apontando para `gca_test`.
"""
import importlib
import os

import pytest


def _reload_celery():
    import app.celery_app as mod
    importlib.reload(mod)
    return mod


# ─── Config básica ────────────────────────────────────────────────────


def test_celery_app_tem_nome_gca():
    mod = _reload_celery()
    assert mod.celery_app.main == "gca"


def test_broker_aponta_para_redis_db_1_por_default(monkeypatch):
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    mod = _reload_celery()
    assert mod.celery_app.conf.broker_url == "redis://redis:6379/1"


def test_result_backend_aponta_para_redis_db_2_por_default(monkeypatch):
    monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    mod = _reload_celery()
    assert mod.celery_app.conf.result_backend == "redis://redis:6379/2"


def test_broker_respeita_env_explicita(monkeypatch):
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://custom:6380/7")
    mod = _reload_celery()
    assert mod.celery_app.conf.broker_url == "redis://custom:6380/7"


def test_broker_deriva_de_redis_url(monkeypatch):
    """Quando só REDIS_URL é setada, broker usa DB 1 dessa URL."""
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://myredis:6400/0")
    mod = _reload_celery()
    assert mod.celery_app.conf.broker_url == "redis://myredis:6400/1"


def test_result_backend_deriva_de_redis_url(monkeypatch):
    monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://myredis:6400/0")
    mod = _reload_celery()
    assert mod.celery_app.conf.result_backend == "redis://myredis:6400/2"


def test_timezone_default_sao_paulo(monkeypatch):
    monkeypatch.delenv("BACKUP_TIMEZONE", raising=False)
    mod = _reload_celery()
    assert mod.celery_app.conf.timezone == "America/Sao_Paulo"


def test_timezone_respeita_backup_timezone(monkeypatch):
    monkeypatch.setenv("BACKUP_TIMEZONE", "UTC")
    mod = _reload_celery()
    assert mod.celery_app.conf.timezone == "UTC"


def test_timezone_fallback_se_invalido(monkeypatch):
    monkeypatch.setenv("BACKUP_TIMEZONE", "Not/A_Real_Zone")
    mod = _reload_celery()
    assert mod.celery_app.conf.timezone == "America/Sao_Paulo"


def test_serializacao_json_apenas():
    mod = _reload_celery()
    conf = mod.celery_app.conf
    assert conf.task_serializer == "json"
    assert conf.result_serializer == "json"
    assert "json" in conf.accept_content
    # Pickle nunca — risco de segurança.
    assert "pickle" not in (conf.accept_content or [])


def test_retry_policy_default_bounded():
    mod = _reload_celery()
    conf = mod.celery_app.conf
    assert conf.task_default_max_retries == 3
    assert conf.task_default_retry_delay == 60
    # Retry infinito é proibido (contrato §7 MVP 13 regra dura).
    assert conf.task_default_max_retries is not None


def test_ack_late_preserva_tasks_em_worker_lost():
    mod = _reload_celery()
    conf = mod.celery_app.conf
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is True


def test_task_ping_esta_registrada():
    mod = _reload_celery()
    assert "app.celery_app.ping" in mod.celery_app.tasks


# ─── Ping em modo eager (sem depender de worker rodando) ──────────────


def test_ping_retorna_pong_em_eager_mode(monkeypatch):
    """Quando CELERY_TASK_ALWAYS_EAGER=true, task executa inline."""
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "true")
    mod = _reload_celery()
    assert mod.celery_app.conf.task_always_eager is True
    result = mod.ping.delay()
    # Em eager, result já vem resolvido.
    assert result.get(timeout=1) == "pong"


def test_eager_mode_desligado_por_default_em_producao(monkeypatch):
    monkeypatch.delenv("CELERY_TASK_ALWAYS_EAGER", raising=False)
    mod = _reload_celery()
    assert mod.celery_app.conf.task_always_eager is False
