"""DeliverableRegistry — orquestra classifier + verifiers + persistência.

Responsabilidades:
    - sync_from_ocg(project_id, ocg_data): materializa OCG.DELIVERABLES
      em rows da tabela project_deliverables (insert novos, waive removidos).
    - verify_all(project_id): roda todos verifiers, atualiza status.
    - attest_manual(project_id, deliverable_id, user_id, note, evidence_ref):
      atestação humana (para business_case, etc).
    - export_status(project_id): payload para Readiness page.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models.base import ProjectDeliverable
from app.services.deliverable_classifier import (
    classify_deliverable,
    is_auto_verifiable,
    normalize_name,
)
from app.services.deliverable_verifiers import (
    VerificationResult,
    verify_kind,
)

logger = structlog.get_logger(__name__)


class DeliverableRegistry:
    """Registro de Definition of Done por projeto."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ──────────────────────────── sync ──────────────────────────────

    async def sync_from_ocg(
        self,
        project_id: UUID,
        ocg_data: Dict[str, Any],
    ) -> Dict[str, int]:
        """Sincroniza project_deliverables com OCG.DELIVERABLES.

        Estratégia:
            1. Lê DELIVERABLES do OCG (lista de strings).
            2. Carrega rows existentes do projeto, indexa por normalized_name.
            3. Para cada string do OCG:
                - Se normalized_name não existe: INSERT novo, status='declared'.
                - Se existe e está 'waived': reativa para 'declared'.
                - Caso contrário: mantém (não toca status).
            4. Para cada row existente cujo normalized_name NÃO está no OCG:
                - Marca status='waived' (preserva histórico).

        Returns:
            Contadores: ``{"inserted": N, "reactivated": N, "waived": N, "kept": N}``
        """
        deliverables_list = ocg_data.get("DELIVERABLES", []) or []
        if not isinstance(deliverables_list, list):
            return {"inserted": 0, "reactivated": 0, "waived": 0, "kept": 0}

        # Existing rows
        result = await self.db.execute(
            select(ProjectDeliverable).where(ProjectDeliverable.project_id == project_id)
        )
        existing = {row.normalized_name: row for row in result.scalars().all()}
        ocg_normalized = set()

        counters = {"inserted": 0, "reactivated": 0, "waived": 0, "kept": 0}

        for raw in deliverables_list:
            if not isinstance(raw, str) or not raw.strip():
                continue
            norm = normalize_name(raw)
            ocg_normalized.add(norm)

            if norm in existing:
                row = existing[norm]
                if row.status == "waived":
                    row.status = "declared"
                    row.notes = (row.notes or "") + " | reativado: voltou ao OCG"
                    counters["reactivated"] += 1
                else:
                    counters["kept"] += 1
                continue

            kind, category = classify_deliverable(raw)
            new_row = ProjectDeliverable(
                project_id=project_id,
                name=raw[:500],
                normalized_name=norm[:500],
                category=category,
                kind=kind,
                status="declared",
            )
            self.db.add(new_row)
            counters["inserted"] += 1

        # Waive os que sumiram do OCG
        for norm, row in existing.items():
            if norm not in ocg_normalized and row.status != "waived":
                row.status = "waived"
                row.notes = (row.notes or "") + " | waived: removido do OCG"
                counters["waived"] += 1

        await self.db.commit()
        logger.info(
            "deliverable_registry.sync_from_ocg",
            project_id=str(project_id),
            **counters,
        )
        return counters

    # ──────────────────────────── verify ────────────────────────────

    async def verify_all(self, project_id: UUID) -> Dict[str, int]:
        """Roda verify_kind() em todos deliverables não-waived do projeto.

        Atualiza status, evidence_*, last_verified_at por linha.

        Returns:
            ``{"verified": N, "present": N, "missing": N, "manual_only": N, "error": N}``
        """
        result = await self.db.execute(
            select(ProjectDeliverable).where(
                ProjectDeliverable.project_id == project_id,
                ProjectDeliverable.status != "waived",
            )
        )
        deliverables = list(result.scalars().all())

        counters = {"verified": 0, "present": 0, "missing": 0, "manual_only": 0, "error": 0}
        now = datetime.now(timezone.utc)

        for d in deliverables:
            res: VerificationResult = await verify_kind(d.kind, project_id, self.db)
            d.status = res.status if res.status in counters else "error"
            d.evidence_type = res.evidence_type
            d.evidence_ref = res.evidence_ref
            d.verification_method = res.method
            d.last_verified_at = now
            if res.notes:
                d.notes = res.notes
            counters[d.status] = counters.get(d.status, 0) + 1

        await self.db.commit()
        logger.info(
            "deliverable_registry.verify_all",
            project_id=str(project_id),
            **counters,
        )
        return counters

    # ──────────────────────────── attest manual ─────────────────────

    async def attest_manual(
        self,
        project_id: UUID,
        deliverable_id: UUID,
        user_id: UUID,
        note: str,
        evidence_ref: Optional[str] = None,
    ) -> Optional[ProjectDeliverable]:
        """Atestação humana — para business_case ou outros que não têm verifier.

        Marca status='verified', evidence_type='manual', registra usuário.
        Note obrigatório.
        """
        if not note or not note.strip():
            return None

        result = await self.db.execute(
            select(ProjectDeliverable).where(
                ProjectDeliverable.id == deliverable_id,
                ProjectDeliverable.project_id == project_id,
            )
        )
        d = result.scalar_one_or_none()
        if not d:
            return None

        d.status = "verified"
        d.evidence_type = "manual"
        d.evidence_ref = evidence_ref
        d.verification_method = "manual_attestation"
        d.last_verified_at = datetime.now(timezone.utc)
        d.verified_by = user_id
        d.notes = note.strip()[:2000]
        await self.db.commit()

        logger.info(
            "deliverable_registry.manual_attest",
            project_id=str(project_id),
            deliverable_id=str(deliverable_id),
            kind=d.kind,
            user_id=str(user_id),
        )
        return d

    # ──────────────────────────── export status ──────────────────────

    async def export_status(self, project_id: UUID) -> Dict[str, Any]:
        """Payload para Readiness page: lista + agregados por status/categoria."""
        result = await self.db.execute(
            select(ProjectDeliverable).where(ProjectDeliverable.project_id == project_id)
        )
        rows = list(result.scalars().all())

        items: List[Dict[str, Any]] = [
            {
                "id": str(r.id),
                "name": r.name,
                "category": r.category,
                "kind": r.kind,
                "status": r.status,
                "evidence_type": r.evidence_type,
                "evidence_ref": r.evidence_ref,
                "verification_method": r.verification_method,
                "last_verified_at": r.last_verified_at.isoformat() if r.last_verified_at else None,
                "verified_by": str(r.verified_by) if r.verified_by else None,
                "notes": r.notes,
                "auto_verifiable": is_auto_verifiable(r.kind),
            }
            for r in rows
        ]

        # Agregados (excluindo waived do total)
        active = [i for i in items if i["status"] != "waived"]
        total = len(active)
        by_status: Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        for i in active:
            by_status[i["status"]] = by_status.get(i["status"], 0) + 1
            by_category[i["category"]] = by_category.get(i["category"], 0) + 1

        verified = by_status.get("verified", 0)
        readiness_pct = round((verified / total) * 100, 1) if total > 0 else 0.0

        return {
            "deliverables": items,
            "summary": {
                "total_active": total,
                "total_with_waived": len(items),
                "verified": verified,
                "by_status": by_status,
                "by_category": by_category,
                "readiness_pct": readiness_pct,
            },
        }
