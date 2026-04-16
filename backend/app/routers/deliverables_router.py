"""Router de Definition of Done por projeto (Fase B.1).

Expõe operações do DeliverableRegistry como REST:
    GET    /projects/{id}/deliverables                 → status + lista
    POST   /projects/{id}/deliverables/verify-all      → re-verifica todos
    POST   /projects/{id}/deliverables/{did}/verify    → re-verifica um
    POST   /projects/{id}/deliverables/{did}/attest    → atestação manual
    POST   /projects/{id}/deliverables/sync            → re-sync do OCG atual

Acesso: qualquer membro autenticado do projeto pode LER (GET).
        Verify e attest exigem GP/admin do projeto (RBAC futuro; por
        ora aceita qualquer member, audit log captura quem foi).
"""
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.base import OCG, ProjectDeliverable
from app.services.deliverable_registry import DeliverableRegistry
from app.services.deliverable_verifiers import verify_kind

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["deliverables"])


# ──────────────────────────── Request models ─────────────────────────

class AttestRequest(BaseModel):
    """Atestação manual de um entregável."""
    note: str = Field(..., min_length=1, max_length=2000)
    evidence_ref: Optional[str] = Field(None, max_length=2000)


# ──────────────────────────── Endpoints ──────────────────────────────

@router.get("/projects/{project_id}/deliverables")
async def get_deliverables_status(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Payload completo: lista + agregados por status/categoria + readiness%.

    Não roda verificadores — devolve estado persistido (rápido). Para
    re-verificar, chame /verify-all.
    """
    registry = DeliverableRegistry(db)
    payload = await registry.export_status(project_id)
    return payload


@router.post("/projects/{project_id}/deliverables/verify-all")
async def verify_all_deliverables(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Roda todos verifiers; atualiza status de cada deliverable; commita.

    Operação potencialmente lenta (N × tempo do verifier mais lento;
    paralelizada em camada inferior). UI deve mostrar spinner.
    """
    registry = DeliverableRegistry(db)
    counters = await registry.verify_all(project_id)
    await db.commit()
    logger.info(
        "deliverables_router.verify_all",
        project_id=str(project_id),
        actor=str(current_user_id),
        **counters,
    )
    return {"counters": counters, "actor": str(current_user_id)}


@router.post("/projects/{project_id}/deliverables/{deliverable_id}/verify")
async def verify_one_deliverable(
    project_id: UUID,
    deliverable_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Re-verifica UM deliverable específico (mais rápido que verify-all)."""
    result = await db.execute(
        select(ProjectDeliverable).where(
            ProjectDeliverable.id == deliverable_id,
            ProjectDeliverable.project_id == project_id,
        )
    )
    d = result.scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Entregável não encontrado")

    if d.status == "waived":
        return {"id": str(d.id), "status": "waived", "message": "Entregável marcado como waived; não verificado."}

    res = await verify_kind(d.kind, project_id, db)
    new_status = res.status if res.status in {"verified", "present", "missing", "manual_only", "error"} else "error"

    if new_status == "error":
        # Preserva evidência prévia; só atualiza nota (mesmo padrão de verify_all)
        d.status = "error"
        if res.notes:
            d.notes = res.notes
    else:
        d.status = new_status
        d.evidence_type = res.evidence_type
        d.evidence_ref = res.evidence_ref
        d.verification_method = res.method
        d.last_verified_at = datetime.now(timezone.utc)
        if res.notes:
            d.notes = res.notes
    await db.commit()

    return {
        "id": str(d.id),
        "kind": d.kind,
        "status": d.status,
        "evidence_type": d.evidence_type,
        "evidence_ref": d.evidence_ref,
        "verification_method": d.verification_method,
        "notes": d.notes,
        "last_verified_at": d.last_verified_at.isoformat() if d.last_verified_at else None,
    }


@router.post("/projects/{project_id}/deliverables/{deliverable_id}/attest")
async def attest_manual(
    project_id: UUID,
    deliverable_id: UUID,
    req: AttestRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Atestação humana — para business_case e outros sem verifier auto."""
    registry = DeliverableRegistry(db)
    updated = await registry.attest_manual(
        project_id=project_id,
        deliverable_id=deliverable_id,
        user_id=current_user_id,
        note=req.note,
        evidence_ref=req.evidence_ref,
    )
    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Entregável não encontrado ou note inválida",
        )
    await db.commit()
    return {
        "id": str(updated.id),
        "status": updated.status,
        "verified_by": str(updated.verified_by) if updated.verified_by else None,
        "evidence_ref": updated.evidence_ref,
        "notes": updated.notes,
    }


@router.post("/projects/{project_id}/deliverables/sync")
async def resync_from_ocg(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Força re-sync do OCG atual (caso projeto tenha rodado migration sem
    o hook ainda ativo, ou divergência manual).

    Caso normal: sync acontece automaticamente após qualquer update do OCG.
    """
    result = await db.execute(
        select(OCG).where(OCG.project_id == project_id).order_by(OCG.version.desc()).limit(1)
    )
    ocg = result.scalar_one_or_none()
    if not ocg:
        raise HTTPException(status_code=404, detail="OCG não encontrado para o projeto")

    registry = DeliverableRegistry(db)
    counters = await registry.sync_from_ocg(project_id, ocg.ocg_data)
    await db.commit()
    return {"counters": counters, "ocg_version": ocg.version}


# ────────────────────────── Release Bundle (Fase D) ──────────────────

from fastapi.responses import FileResponse


@router.post("/projects/{project_id}/releases")
async def create_release_bundle(
    project_id: UUID,
    threshold: float = 90.0,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Cria um Release Bundle (zip + MANIFEST + RELEASE_NOTES + docs).

    Pré-condição: readiness do projeto >= ``threshold`` (default 90%).
    Falha o pré-check → 412 Precondition Failed com diagnóstico.
    """
    from app.services.release_bundle_service import ReleaseBundleService
    svc = ReleaseBundleService(db)
    result = await svc.create_bundle(project_id, actor_id=current_user_id, threshold=threshold)
    if result.get("error") == "readiness_below_threshold":
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={
                "message": f"Readiness {result['readiness_pct']}% abaixo do threshold {result['threshold']}%.",
                "readiness_pct": result["readiness_pct"],
                "threshold": result["threshold"],
                "missing": result.get("missing_count"),
                "manual_only": result.get("manual_only_count"),
            },
        )
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result.get("message") or result["error"])
    return result


@router.get("/projects/{project_id}/releases")
async def list_releases(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Lista todas as releases do projeto (mais recentes primeiro)."""
    from app.services.release_bundle_service import ReleaseBundleService
    svc = ReleaseBundleService(db)
    releases = await svc.list_releases(project_id)
    return {"releases": releases, "count": len(releases)}


@router.get("/projects/{project_id}/releases/{version}/download")
async def download_release(
    project_id: UUID,
    version: int,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Baixa o zip de um release específico.

    Retorna 404 se release não existe, status != 'ready', ou arquivo
    sumiu do filesystem.
    """
    from app.services.release_bundle_service import ReleaseBundleService
    svc = ReleaseBundleService(db)
    file_path = await svc.get_release_path(project_id, version)
    if not file_path:
        raise HTTPException(
            status_code=404,
            detail=f"Release v{version} não encontrada ou indisponível",
        )
    return FileResponse(
        path=file_path,
        media_type="application/zip",
        filename=f"release-v{version}.zip",
    )
