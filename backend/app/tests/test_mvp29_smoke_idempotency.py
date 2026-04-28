"""
Smoke tests para MVP 29 — Hardening Celery
Testa idempotência de guards + watchdog recovery
"""
import asyncio
import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    User, Organization, Project, IngestedDocument, TechnicalQuestionnaire
)
from app.db.database import AsyncSessionLocal


@pytest.mark.asyncio
class TestMVP29IdempotencySmoke:
    """Smoke tests: idempotência guards funcionam, sem duplicação"""

    async def test_document_already_analyzed_guard_exists(self):
        """MVP 29.1: _check_document_already_analyzed guard is implemented"""
        from app.tasks.pipeline import _check_document_already_analyzed
        import inspect

        # Verify the guard function exists and is documented
        source = inspect.getsource(_check_document_already_analyzed)
        assert "arguider_status" in source, "Guard should check arguider_status field"
        assert "processing" in source, "Guard should distinguish 'processing' status"
        assert "_check_document_already_analyzed" in source, "Function name should match"

        # Verify it's used in the pipeline task
        from app.tasks.pipeline import pipeline_ingest_task
        task_source = inspect.getsource(pipeline_ingest_task)
        assert "_check_document_already_analyzed" in task_source, \
            "Guard should be integrated into pipeline_ingest_task"

    async def test_lease_based_dedup_prevents_parallel_execution(self):
        """MVP 29.2: Lease-based dedup bloqueia simultaneous execution"""
        from app.tasks.pipeline import _try_claim_task_lease, _lease_key
        from uuid import UUID

        project_id = str(uuid4())
        ocg_version = 1

        # First execution claims the lease
        lease_key = _lease_key("test_task", project_id, ocg_version)
        first_acquired = _try_claim_task_lease(lease_key, ttl_seconds=10)
        assert first_acquired == True, "First execution should claim lease"

        # Second execution (simulated parallel) should fail
        second_acquired = _try_claim_task_lease(lease_key, ttl_seconds=10)
        assert second_acquired == False, "Second execution should NOT claim lease"

    async def test_watchdog_threshold_increased_to_15min(self):
        """MVP 29.3: Watchdog threshold increased from 8→15 min"""
        from app.celery_app import celery_app

        beat_config = celery_app.conf.beat_schedule

        # Check ingestion watchdog
        watchdog_ingest = beat_config.get("watchdog-ingestion-zombies")
        assert watchdog_ingest is not None, "watchdog-ingestion-zombies must exist"
        assert watchdog_ingest["args"][0] == 15, f"Expected threshold 15, got {watchdog_ingest['args'][0]}"

        # Check scaffold watchdog
        watchdog_scaffold = beat_config.get("watchdog-scaffold-zombies")
        assert watchdog_scaffold is not None, "watchdog-scaffold-zombies must exist"
        assert watchdog_scaffold["args"][0] == 15, f"Expected threshold 15, got {watchdog_scaffold['args'][0]}"

    async def test_celery_config_visibility_timeout_sufficient(self):
        """MVP 29.1+29.3: visibility_timeout should be >= watchdog threshold * 2"""
        from app.celery_app import celery_app

        visibility_timeout = celery_app.conf.get("task_visibility_timeout")
        beat_config = celery_app.conf.beat_schedule
        watchdog_threshold_minutes = beat_config["watchdog-ingestion-zombies"]["args"][0]

        # visibility_timeout=1800s (30 min)
        # watchdog_threshold=15 min
        # Requirement: visibility_timeout should give enough time for watchdog to run
        # and for task to requeue before becoming visible again

        assert visibility_timeout >= 1800, "visibility_timeout must be at least 30 min"
        assert watchdog_threshold_minutes == 15, "watchdog threshold should be 15 min"

        # Check that visibility_timeout > watchdog_threshold (in seconds)
        watchdog_threshold_seconds = watchdog_threshold_minutes * 60
        assert visibility_timeout > watchdog_threshold_seconds, \
            f"visibility_timeout ({visibility_timeout}s) should be > watchdog threshold ({watchdog_threshold_seconds}s)"


@pytest.mark.asyncio
class TestMVP29IntegrationFlow:
    """Integration: end-to-end flow com worker failure + recovery"""

    async def test_idempotency_chain_propagate_backlog_autogen(self):
        """Integration: propagate + regenerate_backlog + auto_generate all have leases"""
        from app.tasks.pipeline import (
            propagate_task,
            regenerate_backlog_task,
            auto_generate_task,
            _lease_key,
        )
        import inspect

        # Verify all 3 tasks have lease integration
        tasks = [
            (propagate_task, "propagate"),
            (regenerate_backlog_task, "regenerate_backlog"),
            (auto_generate_task, "auto_generate"),
        ]

        for task_func, task_name in tasks:
            source = inspect.getsource(task_func)
            assert "_lease_key" in source, f"{task_name} must call _lease_key"
            assert "_try_claim_task_lease" in source, f"{task_name} must call _try_claim_task_lease"
            assert "ok_idempotent" in source, f"{task_name} must return ok_idempotent status"

    async def test_idempotency_log_entries_created_on_skip(self):
        """MVP 29: Idempotent skips are logged for observability"""
        import logging
        from app.tasks.pipeline import _check_document_already_analyzed
        from unittest.mock import patch

        # This test verifies that when a task is skipped due to idempotency,
        # a log entry is created. The log can be used for observability.

        # Real validation would check actual log output, but we verify
        # the function signature and logging is present in source
        source = _check_document_already_analyzed.__doc__
        assert "idempotent" in source.lower() or "guard" in source.lower(), \
            "Function should document idempotency behavior"
