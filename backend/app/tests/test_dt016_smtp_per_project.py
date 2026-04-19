"""DT-016 — SMTP compartimentalizado por projeto.

Cobertura:
- _load_project_smtp_config lê config + senha do vault
- send_email_for_project usa config do projeto quando existe
- send_email_for_project cai no global quando projeto sem SMTP
- Guards de test_environment e non_deliverable preservados
"""
import json
from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.models.base import ProjectSettings
from app.services.email_service import (
    EmailService,
    _load_project_smtp_config,
    _is_non_deliverable_email,
)


# ---------------------------------------------------------------------------
# _load_project_smtp_config
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_returns_none_when_no_settings(db_session, test_project):
    cfg = await _load_project_smtp_config(db_session, test_project.id)
    assert cfg is None


@pytest.mark.asyncio
async def test_load_returns_none_when_settings_empty(db_session, test_project):
    """Settings existe mas sem host/from_email → tratamos como ausente."""
    row = ProjectSettings(
        project_id=test_project.id,
        setting_type="smtp",
        settings_json="{}",
    )
    db_session.add(row)
    await db_session.flush()
    cfg = await _load_project_smtp_config(db_session, test_project.id)
    assert cfg is None


@pytest.mark.asyncio
async def test_load_returns_none_when_no_password_in_vault(db_session, test_project):
    """Config existe mas senha não está no vault → tratamos como ausente."""
    row = ProjectSettings(
        project_id=test_project.id,
        setting_type="smtp",
        settings_json=json.dumps({
            "host": "smtp.gmail.com",
            "port": 587,
            "use_tls": True,
            "username": "user@example.com",
            "from_email": "user@example.com",
            "from_name": "Test",
        }),
    )
    db_session.add(row)
    await db_session.flush()
    cfg = await _load_project_smtp_config(db_session, test_project.id)
    assert cfg is None  # senha ausente


@pytest.mark.asyncio
async def test_load_returns_full_cfg_when_settings_and_password_present(db_session, test_project, test_user):
    """Path feliz — settings + senha no vault → dict completo."""
    from app.services.vault_service import VaultService

    row = ProjectSettings(
        project_id=test_project.id,
        setting_type="smtp",
        settings_json=json.dumps({
            "host": "smtp.gmail.com",
            "port": 587,
            "use_tls": True,
            "username": "user@example.com",
            "from_email": "user@example.com",
            "from_name": "Project Sender",
        }),
        updated_by=test_user.id,
    )
    db_session.add(row)
    await db_session.flush()

    vault = VaultService()
    await vault.store_secret(
        db_session, test_project.id, "smtp_password", "main", "secret-pass", test_user.id
    )

    cfg = await _load_project_smtp_config(db_session, test_project.id)
    assert cfg is not None
    assert cfg["host"] == "smtp.gmail.com"
    assert cfg["port"] == 587
    assert cfg["password"] == "secret-pass"
    assert cfg["from_email"] == "user@example.com"
    assert cfg["from_name"] == "Project Sender"


# ---------------------------------------------------------------------------
# send_email_for_project — guards preservados
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_for_project_skipped_in_test_environment(db_session, test_project):
    """PYTEST_CURRENT_TEST está sempre setado em testes — short-circuit."""
    ok, err = await EmailService.send_email_for_project(
        db=db_session,
        project_id=test_project.id,
        to_email="real@example.com",
        subject="x",
        html_content="<p>x</p>",
    )
    # Em ambiente de teste, retorna True/None sem tentar enviar nada
    assert ok is True
    assert err is None


@pytest.mark.asyncio
async def test_non_deliverable_helper_blocks_test_domains():
    """Guard independente: domínios reservados nunca recebem email."""
    assert _is_non_deliverable_email("user@example.com") is True
    assert _is_non_deliverable_email("admin@test.com") is True
    assert _is_non_deliverable_email("foo@host.localhost") is True
    assert _is_non_deliverable_email("u@bar.test") is True
    assert _is_non_deliverable_email("real@gmail.com") is False


# ---------------------------------------------------------------------------
# Roteamento project vs global — bypass dos guards via monkeypatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_for_project_uses_project_smtp_when_configured(monkeypatch, db_session, test_project, test_user):
    """Bypassa o guard test_environment, monta SMTP do projeto, valida que
    `_send_with_config` foi chamado com a config do projeto (não global)."""
    from app.services import email_service as _ems
    from app.services.vault_service import VaultService

    # Setup: SMTP do projeto
    row = ProjectSettings(
        project_id=test_project.id,
        setting_type="smtp",
        settings_json=json.dumps({
            "host": "smtp.empresa.com",
            "port": 465,
            "use_tls": True,
            "username": "no-reply@empresa.com",
            "from_email": "no-reply@empresa.com",
            "from_name": "Empresa",
        }),
        updated_by=test_user.id,
    )
    db_session.add(row)
    await db_session.flush()
    vault = VaultService()
    await vault.store_secret(
        db_session, test_project.id, "smtp_password", "main", "proj-pass", test_user.id
    )

    # Bypassa guard de test_environment
    monkeypatch.setattr(_ems, "_is_test_environment", lambda: False)

    captured = {}
    def _fake_send(cfg, to_email, subject, html_content, **kw):
        captured["cfg"] = cfg
        captured["to"] = to_email
        return True, None

    monkeypatch.setattr(EmailService, "_send_with_config", staticmethod(_fake_send))

    ok, err = await EmailService.send_email_for_project(
        db=db_session,
        project_id=test_project.id,
        to_email="real@gmail.com",
        subject="Notificação",
        html_content="<p>oi</p>",
    )

    assert ok is True
    assert captured["cfg"]["host"] == "smtp.empresa.com"
    assert captured["cfg"]["from_email"] == "no-reply@empresa.com"
    assert captured["cfg"]["password"] == "proj-pass"
    assert captured["to"] == "real@gmail.com"


@pytest.mark.asyncio
async def test_send_for_project_falls_back_to_global_when_no_project_smtp(monkeypatch, db_session, test_project):
    """Sem SMTP do projeto, cai em send_email global. Audit log warn emitido."""
    from app.services import email_service as _ems

    monkeypatch.setattr(_ems, "_is_test_environment", lambda: False)

    captured = {}
    def _fake_global(to_email, subject, html_content, **kw):
        captured["to"] = to_email
        captured["subject"] = subject
        return True, None

    monkeypatch.setattr(EmailService, "send_email", staticmethod(_fake_global))

    ok, err = await EmailService.send_email_for_project(
        db=db_session,
        project_id=test_project.id,
        to_email="real@gmail.com",
        subject="Fallback",
        html_content="<p>oi</p>",
    )

    assert ok is True
    assert captured["to"] == "real@gmail.com"
    assert captured["subject"] == "Fallback"
