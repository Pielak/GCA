"""Dramatiq app configuration — task queue para migração de Celery.

Usa Redis DB 3 (DBs 1-2 reservados para Celery/beat durante transição).
Middleware: retries + time limit + age limit (padrão Dramatiq).

Ativação via:
  docker-compose run dramatiq-worker python -m dramatiq app.tasks.pipeline --processes 2 --threads 4

Tasks migradas de Celery para Dramatiq (Fase 2):
- pipeline_ingest_task
- process_ingestion_complete_ocg
- propagate_task, regenerate_backlog_task, reevaluate_gatekeeper_task
- auto_generate_task, external_repo_fallback_task
- propagate_questionnaire_impact_task, revert_document_propagation_task

Detalhe: task.send(args) retorna Message object, não AsyncResult.
Não há result backend — jobs são fire-and-forget com retry via middleware.
"""
from __future__ import annotations

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import (
    AgeLimit,
    CurrentMessage,
    Retries,
    TimeLimit,
)

# Broker configurado em Redis DB 3 (isolado de Celery DBs 1-2)
# Middleware padrão (retries, time limit, age limit) já incluído por RedisBroker.
broker = RedisBroker(url="redis://redis:6379/3")

# Set global broker
dramatiq.set_broker(broker)
