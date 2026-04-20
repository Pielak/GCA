"""MVP 12 Fase 12.2 — Timezone configurável em BackupScheduler.

Contrato §7 MVP 12 Fase 12.2:
- Env `BACKUP_TIMEZONE` define timezone do scheduler.
- Default `America/Sao_Paulo` (compat retrógrada).
- Valor inválido → fallback silencioso para default + warning.
- Valor válido → scheduler usa esse tz.
"""
import os

import pytest


def _reload_backup_scheduler():
    """Recarrega o módulo para pegar a env var atual."""
    import importlib
    import app.services.backup_scheduler as bs
    importlib.reload(bs)
    return bs


def test_default_is_sao_paulo_when_env_unset(monkeypatch):
    monkeypatch.delenv("BACKUP_TIMEZONE", raising=False)
    bs = _reload_backup_scheduler()
    assert bs._resolve_backup_timezone() == "America/Sao_Paulo"


def test_valid_env_is_honored(monkeypatch):
    monkeypatch.setenv("BACKUP_TIMEZONE", "America/New_York")
    bs = _reload_backup_scheduler()
    assert bs._resolve_backup_timezone() == "America/New_York"


def test_empty_string_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("BACKUP_TIMEZONE", "   ")
    bs = _reload_backup_scheduler()
    assert bs._resolve_backup_timezone() == "America/Sao_Paulo"


def test_invalid_tz_falls_back_with_warning(monkeypatch, caplog):
    monkeypatch.setenv("BACKUP_TIMEZONE", "Not/A_Real_Zone_xxx")
    bs = _reload_backup_scheduler()
    assert bs._resolve_backup_timezone() == "America/Sao_Paulo"


@pytest.mark.parametrize("tz", [
    "UTC",
    "Europe/London",
    "Asia/Tokyo",
    "America/Los_Angeles",
    "Australia/Sydney",
])
def test_multiple_valid_zones_accepted(monkeypatch, tz):
    monkeypatch.setenv("BACKUP_TIMEZONE", tz)
    bs = _reload_backup_scheduler()
    assert bs._resolve_backup_timezone() == tz


@pytest.mark.asyncio
async def test_scheduler_uses_configured_tz(monkeypatch):
    """start_scheduler recebe timezone resolvida (AsyncIOScheduler exige loop ativo)."""
    monkeypatch.setenv("BACKUP_TIMEZONE", "UTC")
    bs = _reload_backup_scheduler()

    # Força estado limpo do global _scheduler
    if bs._scheduler is not None:
        try:
            bs._scheduler.shutdown(wait=False)
        except Exception:
            pass
        bs._scheduler = None

    bs.start_scheduler()
    try:
        assert bs._scheduler is not None
        assert str(bs._scheduler.timezone) == "UTC"
    finally:
        bs.stop_scheduler()
