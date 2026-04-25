"""Endpoints do Arguidor #2 (auditor pós-CodeGen, 2026-04-25).

4 endpoints:
  - POST /scaffold/runs/{run_id}/audit/start  → trigger manual da auditoria
  - GET  /projects/{project_id}/audit/findings → lista com filtros
  - POST /audit/findings/{finding_id}/dismiss  → owner descarta com nota
  - POST /audit/findings/{finding_id}/accept   → cria BacklogItem fix

A auditoria também roda automaticamente após apply_scaffold_run quando
há commits (ver code_generation.py).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.require_action import require_action
from app.middleware.auth import get_current_user_from_token
from app.models.base import (
    BacklogItem,
    CodeAuditFinding,
    Project,
    ScaffoldRun,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["code-audit"])


@router.post("/scaffold/runs/{run_id}/audit/start")
async def trigger_code_audit(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    """Dispara auditoria manualmente sobre uma ScaffoldRun aplicada.

    O fluxo automático já roda após apply_scaffold_run quando há commits.
    Este endpoint serve pra re-rodar (auditoria voluntária ou após dismiss
    de findings antigos).
    """
    run = await db.get(ScaffoldRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run não encontrada")
    # require_action pra project:edit no contexto do projeto da run
    project_id = run.project_id
    # Validação manual de permissão via project:edit pra esse projeto
    from app.dependencies.require_action import resolve_user_role_in_project
    role = await resolve_user_role_in_project(db, project_id, user_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem acesso ao projeto")

    if run.status not in ("applied", "completed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run em status {run.status!r} — só audita após applied/completed.",
        )

    from app.tasks.scaffold import code_audit_executor
    code_audit_executor.delay(str(run_id))
    logger.info(
        "code_audit.manual_trigger",
        run_id=str(run_id),
        project_id=str(project_id),
        triggered_by=str(user_id),
    )
    return {"status": "queued", "run_id": str(run_id)}


@router.get("/projects/{project_id}/audit/findings")
async def list_code_audit_findings(
    project_id: UUID,
    severity: Optional[str] = Query(None, description="info | warn | critical"),
    run_id: Optional[UUID] = Query(None),
    file_path: Optional[str] = Query(None),
    pending_only: bool = Query(False, description="Apenas findings sem ação do owner"),
    permissions: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Lista findings de auditoria com filtros opcionais."""
    from app.services.code_audit_service import list_findings
    items = await list_findings(
        db, project_id,
        severity=severity,
        run_id=run_id,
        file_path=file_path,
        pending_only=pending_only,
    )
    return {"items": items, "total": len(items)}


@router.post("/audit/findings/{finding_id}/dismiss")
async def dismiss_finding(
    finding_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    """Owner descarta finding com nota (justificativa)."""
    finding = await db.get(CodeAuditFinding, finding_id)
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding não encontrado")

    from app.dependencies.require_action import resolve_user_role_in_project
    role = await resolve_user_role_in_project(db, finding.project_id, user_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem acesso ao projeto")

    note = (body or {}).get("note") or ""
    finding.owner_action = "dismissed"
    finding.owner_note = str(note)[:1000] or None
    finding.owner_acted_by = user_id
    finding.owner_acted_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True, "id": str(finding.id), "owner_action": "dismissed"}


@router.post("/audit/findings/{finding_id}/accept")
async def accept_finding(
    finding_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    """Owner aceita finding. Se `create_fix=true`, gera BacklogItem categoria
    fix com fix_severity baseado em severity, vinculado ao finding."""
    finding = await db.get(CodeAuditFinding, finding_id)
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding não encontrado")

    from app.dependencies.require_action import resolve_user_role_in_project
    role = await resolve_user_role_in_project(db, finding.project_id, user_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem acesso ao projeto")

    create_fix = bool((body or {}).get("create_fix", False))
    note = str((body or {}).get("note") or "")[:1000]

    if create_fix:
        # Mapeia severity do finding pra fix_severity do BacklogItem
        sev_map = {"critical": "CRITICAL", "warn": "MEDIUM", "info": "LOW"}
        fix_item = BacklogItem(
            project_id=finding.project_id,
            category="modules",
            module_type="fix",
            title=f"Fix: {finding.finding[:120]}",
            description=(
                f"Origem: auditoria pós-CodeGen (Arguidor #2)\n"
                f"Arquivo: {finding.file_path}\n"
                f"Categoria: {finding.category}\n"
                f"Severidade: {finding.severity}\n\n"
                f"Achado:\n{finding.finding}\n\n"
                f"Sugestão de correção:\n{finding.suggested_fix or '(não fornecida)'}"
            ),
            priority="critical" if finding.severity == "critical" else "high" if finding.severity == "warn" else "medium",
            status="pending",
            source="audit",
            fix_severity=sev_map.get(finding.severity),
            fix_remediation=finding.suggested_fix,
        )
        db.add(fix_item)
        await db.flush()
        finding.backlog_fix_item_id = fix_item.id
        finding.owner_action = "fix_created"
    else:
        finding.owner_action = "accepted"

    finding.owner_note = note or None
    finding.owner_acted_by = user_id
    finding.owner_acted_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "ok": True,
        "id": str(finding.id),
        "owner_action": finding.owner_action,
        "backlog_fix_item_id": str(finding.backlog_fix_item_id) if finding.backlog_fix_item_id else None,
    }
