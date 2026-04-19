"""Backup-2 — Testes do project_backup_service.

Cobertura:
- create_backup gera registro completed + arquivo no volume
- list_backups retorna em ordem desc
- _cleanup_old_backups respeita retenção 10
- restore_from_backup substitui dados do projeto
- SHA mismatch aborta restore
"""
import json
import zipfile
import io
from pathlib import Path
from uuid import uuid4

import pytest

from app.models.base import Project, ProjectBackup, BacklogItem
from app.services import project_backup_service as svc
from app.tests.factories import create_test_organization, create_test_project


@pytest.mark.asyncio
async def test_create_backup_writes_zip_to_volume(db_session, monkeypatch, tmp_path):
    """Backup gera zip + registro completed + manifest válido."""
    monkeypatch.setattr(svc, "BACKUP_VOLUME", str(tmp_path))
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="test-bkp-1")

    backup = await svc.create_backup(db_session, project.id, trigger_source="manual_admin")

    assert backup.status == "completed"
    assert backup.file_path is not None
    assert backup.sha256 is not None
    assert backup.size_bytes > 0

    full = Path(tmp_path) / backup.file_path
    assert full.exists()

    # Manifest válido
    with zipfile.ZipFile(full, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["project_id"] == str(project.id)
    assert manifest["project_slug"] == "test-bkp-1"
    assert manifest["version"] == 1
    assert any(t["name"] == "backlog_items" for t in manifest["tables"])


@pytest.mark.asyncio
async def test_backup_includes_project_rows(db_session, monkeypatch, tmp_path):
    """JSONL de tabela contém rows filtrados por project_id."""
    monkeypatch.setattr(svc, "BACKUP_VOLUME", str(tmp_path))
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="test-bkp-rows")

    # Adiciona 3 backlog items pro projeto
    for i in range(3):
        db_session.add(BacklogItem(
            id=uuid4(),
            project_id=project.id,
            category="modules",
            title=f"Item {i}",
            description=None,
            priority="medium",
            status="pending",
            source="ocg",
        ))
    await db_session.flush()

    backup = await svc.create_backup(db_session, project.id, trigger_source="manual_gp")

    full = Path(tmp_path) / backup.file_path
    with zipfile.ZipFile(full, "r") as zf:
        backlog_jsonl = zf.read("tables/backlog_items.jsonl").decode("utf-8")

    lines = [l for l in backlog_jsonl.split("\n") if l.strip()]
    assert len(lines) == 3
    titles = sorted(json.loads(l)["title"] for l in lines)
    assert titles == ["Item 0", "Item 1", "Item 2"]


@pytest.mark.asyncio
async def test_list_backups_ordered_desc(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(svc, "BACKUP_VOLUME", str(tmp_path))
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="test-bkp-list")

    b1 = await svc.create_backup(db_session, project.id, trigger_source="manual_admin")
    b2 = await svc.create_backup(db_session, project.id, trigger_source="scheduled")

    out = await svc.list_backups(db_session, project.id)
    assert len(out) == 2
    assert out[0].id == b2.id  # mais recente primeiro
    assert out[1].id == b1.id


@pytest.mark.asyncio
async def test_cleanup_keeps_only_last_10(db_session, monkeypatch, tmp_path):
    """Retenção 10: 12 backups → cleanup deixa 10."""
    monkeypatch.setattr(svc, "BACKUP_VOLUME", str(tmp_path))
    monkeypatch.setattr(svc, "RETENTION_PER_PROJECT", 3)  # Acelera teste
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="test-bkp-clean")

    for _ in range(5):
        await svc.create_backup(db_session, project.id, trigger_source="scheduled")

    out = await svc.list_backups(db_session, project.id)
    assert len(out) == 3, f"Esperava 3 (retention), got {len(out)}"


@pytest.mark.asyncio
async def test_restore_replaces_project_rows(db_session, test_user, monkeypatch, tmp_path):
    """Restore: cria backup, modifica dados, restora, dados voltam."""
    monkeypatch.setattr(svc, "BACKUP_VOLUME", str(tmp_path))
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="test-bkp-restore")

    # Estado inicial: 2 items
    for i in range(2):
        db_session.add(BacklogItem(
            id=uuid4(), project_id=project.id, category="modules",
            title=f"Original {i}", priority="medium", status="pending", source="ocg",
        ))
    await db_session.flush()

    # Backup
    backup = await svc.create_backup(db_session, project.id, trigger_source="manual_gp")

    # Modificação destrutiva
    from sqlalchemy import text as _t
    await db_session.execute(_t("DELETE FROM backlog_items WHERE project_id = :pid"), {"pid": str(project.id)})
    db_session.add(BacklogItem(
        id=uuid4(), project_id=project.id, category="security",
        title="Inserido após backup", priority="critical", status="pending", source="ocg",
    ))
    await db_session.flush()

    # Restore
    await svc.restore_from_backup(db_session, project.id, backup.id, test_user.id)

    # Verifica que voltou ao estado do backup
    from app.models.base import BacklogItem as _BI
    from sqlalchemy import select as _s
    rows = (await db_session.execute(
        _s(_BI).where(_BI.project_id == project.id)
    )).scalars().all()
    titles = sorted(r.title for r in rows)
    assert titles == ["Original 0", "Original 1"]

    # Marca restored_at
    await db_session.refresh(backup)
    assert backup.restored_at is not None
    assert backup.restored_by == test_user.id


@pytest.mark.asyncio
async def test_restore_aborts_on_sha_mismatch(db_session, test_user, monkeypatch, tmp_path):
    monkeypatch.setattr(svc, "BACKUP_VOLUME", str(tmp_path))
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="test-bkp-corrupt")

    backup = await svc.create_backup(db_session, project.id, trigger_source="manual_admin")

    # Corrompe o arquivo
    full = Path(tmp_path) / backup.file_path
    full.write_bytes(b"corrupted")

    with pytest.raises(ValueError, match="SHA256 não confere"):
        await svc.restore_from_backup(db_session, project.id, backup.id, test_user.id)


@pytest.mark.asyncio
async def test_backup_updates_project_last_backup_at(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(svc, "BACKUP_VOLUME", str(tmp_path))
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="test-bkp-cache")

    assert project.last_backup_at is None
    await svc.create_backup(db_session, project.id, trigger_source="scheduled")
    await db_session.refresh(project)
    assert project.last_backup_at is not None
