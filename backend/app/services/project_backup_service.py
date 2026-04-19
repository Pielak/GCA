"""Backup-2 — Service de backup/restore por projeto.

Estratégia:
- Backup = arquivo .zip em `/var/gca-backups/{project_slug}/{ts}.zip`
- Conteúdo: 1 JSON por tabela (rows filtrados por project_id) + manifest
- pg_dump não filtra por WHERE — usamos `psql COPY ... TO STDOUT` em SQL,
  o que permite WHERE arbitrário e produz JSONL determinístico
- Restore = soft: DROP rows do projeto + INSERT do JSONL, em ordem
  topológica reversa (filhos antes de pais)

Tabelas pertencentes ao projeto (todas com `project_id` FK):
- Conjunto extraído via information_schema. Lista hardcoded para evitar
  catálogo dinâmico em produção.

Arquivos do volume `gca-uploads-storage` (DT-030) NÃO entram nesta
versão — uploads são em `/tmp/gca-storage/{project_id}/...`. Adicionar
em iteração futura se cliente pedir.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Project, ProjectBackup

logger = structlog.get_logger(__name__)

BACKUP_VOLUME = "/var/gca-backups"
RETENTION_PER_PROJECT = 10

# Ordem importa: filhos antes dos pais (DELETE), pais antes dos filhos
# (INSERT). Definida manualmente — autodescoberta via FKs é frágil em
# Postgres com schema crescendo.
PROJECT_TABLES_ORDER = [
    # Filhos primeiro (DELETE em ordem direta; INSERT em ordem reversa)
    "user_notifications",
    "test_execution_logs",
    "test_artifacts",
    "test_files",
    "ai_usage_log",
    "pipeline_audit_entries",
    "ocg_delta_log",
    "ocg",
    "questionnaires",
    "ingested_documents",
    "arguider_analyses",
    "gatekeeper_items",
    "generated_modules",
    "module_candidates",
    "backlog_items",
    "project_deliverables",
    "project_releases",
    "project_external_repos",
    "project_git_configs",
    "project_secrets",
    "project_settings",
    "project_invites",
    "team_invites",
    "project_members",
    "repo_analysis_results",
    "repo_integration_roadmaps",
    "onboarding_progress",
    "support_tickets",
    "access_attempts",
    # NÃO incluir project_backups (auto-referência) nem projects (raiz —
    # restore não recria o projeto, só dados internos).
]


def _project_dir(slug: str) -> Path:
    return Path(BACKUP_VOLUME) / slug


def _safe_slug(slug: str) -> str:
    """Sanitiza slug para path filesystem."""
    keep = "abcdefghijklmnopqrstuvwxyz0123456789-_"
    return "".join(c if c.lower() in keep else "_" for c in (slug or "unknown"))


async def _get_project(db: AsyncSession, project_id: UUID) -> Optional[Project]:
    return (await db.execute(
        select(Project).where(Project.id == project_id)
    )).scalar_one_or_none()


async def _column_types(db: AsyncSession, table: str) -> dict:
    """Retorna dict {coluna: data_type} pra normalizar valores no INSERT
    (asyncpg não aceita timestamp ISO como string — exige datetime obj)."""
    rows = (await db.execute(
        text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:t
        """),
        {"t": table},
    )).all()
    return {r[0]: r[1] for r in rows}


def _normalize_row(row: dict, col_types: dict) -> dict:
    """Converte strings JSON para tipos Python esperados por asyncpg.
    Foca nos casos que `json.loads` deixa como string mas asyncpg recusa.
    """
    from datetime import datetime as _dt
    out = {}
    for k, v in row.items():
        if v is None:
            out[k] = None
            continue
        ctype = (col_types.get(k) or "").lower()
        if isinstance(v, str):
            if ctype in ("timestamp with time zone", "timestamp without time zone", "date"):
                # ISO 8601 → datetime
                try:
                    # Postgres timestamptz format: "2026-04-19T01:20:41.943735+00:00"
                    out[k] = _dt.fromisoformat(v)
                except Exception:
                    out[k] = v  # deixa asyncpg dar erro claro se inválido
                continue
            # UUID, jsonb, text, varchar — asyncpg aceita string direto
        if ctype == "jsonb" and not isinstance(v, str):
            # row_to_json já serializou jsonb como object Python; precisamos
            # serializar de volta pra string pra asyncpg passar como JSON.
            out[k] = json.dumps(v, ensure_ascii=False)
            continue
        out[k] = v
    return out


async def _dump_table_to_jsonl(
    db: AsyncSession, table: str, project_id: UUID
) -> Tuple[bytes, int]:
    """Exporta uma tabela filtrada por project_id como JSONL bytes.
    Retorna (conteúdo, contagem)."""
    # Verifica se a tabela existe (ignora gracefully se ainda não foi
    # criada — útil em deploys onde uma migration está pendente).
    exists = (await db.execute(
        text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='public' AND table_name=:t
        """),
        {"t": table},
    )).scalar_one_or_none()
    if not exists:
        return b"", 0

    # row_to_json + COPY produz JSONL completo. JSON do Postgres já
    # serializa UUID/timestamp/jsonb corretamente.
    sql = text(f"""
        SELECT row_to_json(t)::text AS row_json
        FROM {table} t
        WHERE t.project_id = :pid
    """)
    rows = (await db.execute(sql, {"pid": str(project_id)})).all()
    # Cada row é uma tupla com 1 elemento (string JSON).
    lines = [r[0] for r in rows if r[0] is not None]
    payload = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    return payload, len(lines)


def _zip_with_manifest(
    artifacts: dict, project_id: UUID, project_slug: str, project_name: str
) -> Tuple[bytes, str, int, dict]:
    """Empacota dict {tabela → bytes JSONL} em zip + manifest.json.
    Retorna (zip_bytes, sha256, size_bytes, manifest_dict)."""
    buf = io.BytesIO()
    counts = {}
    hashes = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for table, content in artifacts.items():
            if not content:
                # tabela vazia — ainda gravamos arquivo vazio pra restore
                # saber que é "intencional zero rows", não "tabela ausente".
                zf.writestr(f"tables/{table}.jsonl", b"")
                counts[table] = 0
                hashes[table] = hashlib.sha256(b"").hexdigest()
                continue
            zf.writestr(f"tables/{table}.jsonl", content)
            counts[table] = content.count(b"\n")
            hashes[table] = hashlib.sha256(content).hexdigest()

        manifest = {
            "project_id": str(project_id),
            "project_slug": project_slug,
            "project_name": project_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tables": [
                {"name": t, "rows": counts[t], "sha256": hashes[t]}
                for t in PROJECT_TABLES_ORDER
                if t in artifacts
            ],
            "version": 1,
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))

    zip_bytes = buf.getvalue()
    sha = hashlib.sha256(zip_bytes).hexdigest()
    return zip_bytes, sha, len(zip_bytes), manifest


async def create_backup(
    db: AsyncSession,
    project_id: UUID,
    actor_id: Optional[UUID] = None,
    trigger_source: str = "manual_admin",
) -> ProjectBackup:
    """Cria um backup do projeto. Bloqueante (await)."""
    project = await _get_project(db, project_id)
    if not project:
        raise ValueError(f"Projeto {project_id} não existe.")

    # Cria registro running no DB primeiro — banner do frontend já vê.
    backup = ProjectBackup(
        id=uuid4(),
        project_id=project_id,
        created_at=datetime.now(timezone.utc),
        created_by=actor_id,
        trigger_source=trigger_source,
        status="running",
    )
    db.add(backup)
    await db.commit()
    await db.refresh(backup)
    backup_id = backup.id

    logger.info(
        "backup.started",
        backup_id=str(backup_id),
        project_id=str(project_id),
        trigger=trigger_source,
    )

    try:
        artifacts = {}
        for table in PROJECT_TABLES_ORDER:
            content, count = await _dump_table_to_jsonl(db, table, project_id)
            artifacts[table] = content

        zip_bytes, sha, size, manifest = _zip_with_manifest(
            artifacts, project_id, project.slug, project.name
        )

        # Grava no volume
        slug = _safe_slug(project.slug)
        out_dir = _project_dir(slug)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        rel_path = f"{slug}/{ts}_{backup_id.hex[:8]}.zip"
        full_path = Path(BACKUP_VOLUME) / rel_path
        full_path.write_bytes(zip_bytes)

        # Atualiza registro
        await db.execute(
            update(ProjectBackup)
            .where(ProjectBackup.id == backup_id)
            .values(
                status="completed",
                completed_at=datetime.now(timezone.utc),
                file_path=rel_path,
                size_bytes=size,
                sha256=sha,
                manifest_json=json.dumps(manifest, ensure_ascii=False),
            )
        )
        # Cache last_backup_at no project
        await db.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(last_backup_at=datetime.now(timezone.utc))
        )
        await db.commit()

        # Cleanup retenção
        await _cleanup_old_backups(db, project_id)

        logger.info(
            "backup.completed",
            backup_id=str(backup_id),
            project_id=str(project_id),
            size_bytes=size,
            tables=len(artifacts),
        )

        await db.refresh(backup)
        return backup

    except Exception as e:
        logger.error(
            "backup.failed",
            backup_id=str(backup_id),
            project_id=str(project_id),
            error=str(e)[:300],
        )
        await db.execute(
            update(ProjectBackup)
            .where(ProjectBackup.id == backup_id)
            .values(
                status="failed",
                completed_at=datetime.now(timezone.utc),
                error_message=str(e)[:1000],
            )
        )
        await db.commit()
        raise


async def list_backups(db: AsyncSession, project_id: UUID) -> List[ProjectBackup]:
    """Retorna backups do projeto ordenados por created_at desc."""
    rows = (await db.execute(
        select(ProjectBackup)
        .where(ProjectBackup.project_id == project_id)
        .order_by(ProjectBackup.created_at.desc())
    )).scalars().all()
    return list(rows)


async def list_all_backups(db: AsyncSession) -> List[ProjectBackup]:
    """Admin view — todos os backups de todos os projetos."""
    rows = (await db.execute(
        select(ProjectBackup)
        .order_by(ProjectBackup.created_at.desc())
        .limit(200)
    )).scalars().all()
    return list(rows)


async def _cleanup_old_backups(db: AsyncSession, project_id: UUID) -> int:
    """Mantém apenas os últimos RETENTION_PER_PROJECT backups completos
    do projeto. Falhados são preservados pra debug por 7 dias (não
    contam na cota)."""
    completed = (await db.execute(
        select(ProjectBackup)
        .where(
            ProjectBackup.project_id == project_id,
            ProjectBackup.status == "completed",
        )
        .order_by(ProjectBackup.created_at.desc())
    )).scalars().all()

    to_delete = list(completed[RETENTION_PER_PROJECT:])
    deleted = 0
    for old in to_delete:
        if old.file_path:
            try:
                full = Path(BACKUP_VOLUME) / old.file_path
                if full.exists():
                    full.unlink()
            except Exception as e:
                logger.warning("backup.cleanup_unlink_failed", path=old.file_path, error=str(e))
        await db.delete(old)
        deleted += 1
    if deleted:
        await db.commit()
        logger.info("backup.cleanup", project_id=str(project_id), deleted=deleted)
    return deleted


async def restore_from_backup(
    db: AsyncSession,
    project_id: UUID,
    backup_id: UUID,
    actor_id: UUID,
) -> ProjectBackup:
    """Soft restore — substitui dados do projeto pelo conteúdo do backup.

    Steps:
      1. Carrega o zip do volume + valida sha256
      2. Para cada tabela na ordem direta: DELETE WHERE project_id=X
      3. Para cada tabela na ordem reversa: INSERT a partir do JSONL
      4. Marca o backup como `restored_at`
    """
    backup = (await db.execute(
        select(ProjectBackup).where(
            ProjectBackup.id == backup_id,
            ProjectBackup.project_id == project_id,
        )
    )).scalar_one_or_none()
    if not backup:
        raise ValueError(f"Backup {backup_id} não encontrado para projeto {project_id}.")
    if backup.status != "completed":
        raise ValueError(f"Backup {backup_id} não está completo (status={backup.status}).")
    if not backup.file_path:
        raise ValueError(f"Backup {backup_id} sem file_path.")

    full_path = Path(BACKUP_VOLUME) / backup.file_path
    if not full_path.exists():
        raise ValueError(f"Arquivo do backup não existe no volume: {backup.file_path}")

    zip_bytes = full_path.read_bytes()
    actual_sha = hashlib.sha256(zip_bytes).hexdigest()
    if backup.sha256 and actual_sha != backup.sha256:
        raise ValueError(
            f"SHA256 não confere para backup {backup_id}: esperado {backup.sha256}, "
            f"atual {actual_sha}. Arquivo corrompido — restore abortado."
        )

    logger.info(
        "backup.restore_started",
        backup_id=str(backup_id),
        project_id=str(project_id),
        actor_id=str(actor_id),
    )

    # Carrega tabelas do zip
    table_payloads: dict = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        for name in zf.namelist():
            if name.startswith("tables/") and name.endswith(".jsonl"):
                table = name[len("tables/"):-len(".jsonl")]
                table_payloads[table] = zf.read(name).decode("utf-8")

    # DELETE em ordem direta (filhos primeiro)
    for table in PROJECT_TABLES_ORDER:
        # Só apaga se a tabela existir no schema atual
        exists = (await db.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=:t"),
            {"t": table},
        )).scalar_one_or_none()
        if not exists:
            continue
        await db.execute(text(f"DELETE FROM {table} WHERE project_id = :pid"), {"pid": str(project_id)})

    # INSERT em ordem reversa (pais primeiro)
    for table in reversed(PROJECT_TABLES_ORDER):
        payload = table_payloads.get(table, "")
        if not payload.strip():
            continue
        # Descobre tipos das colunas pra normalizar timestamp/uuid/etc.
        col_types = await _column_types(db, table)
        for line in payload.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            row = _normalize_row(row, col_types)
            cols = list(row.keys())
            placeholders = [f":{c}" for c in cols]
            sql = text(
                f"INSERT INTO {table} ({', '.join(cols)}) "
                f"VALUES ({', '.join(placeholders)})"
            )
            try:
                await db.execute(sql, row)
            except Exception as e:
                # Restaura best-effort: registra warning e segue.
                # Caller decide se quer abortar ou continuar.
                logger.warning(
                    "backup.restore_row_failed",
                    table=table, error=str(e)[:200],
                )

    # Marca o backup como restaurado
    await db.execute(
        update(ProjectBackup)
        .where(ProjectBackup.id == backup_id)
        .values(restored_at=datetime.now(timezone.utc), restored_by=actor_id)
    )
    await db.commit()

    logger.info(
        "backup.restore_completed",
        backup_id=str(backup_id),
        project_id=str(project_id),
    )

    await db.refresh(backup)
    return backup


def read_backup_bytes(backup: ProjectBackup) -> bytes:
    """Lê o conteúdo binário do backup do volume — usado pelo endpoint de download."""
    if not backup.file_path:
        raise ValueError("Backup sem file_path.")
    full = Path(BACKUP_VOLUME) / backup.file_path
    if not full.exists():
        raise ValueError(f"Arquivo não encontrado: {backup.file_path}")
    return full.read_bytes()
