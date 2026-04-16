"""DeliverableRegistry — orquestra classifier + verifiers + persistência.

Responsabilidades:
    - sync_from_ocg(project_id, ocg_data): materializa OCG.DELIVERABLES
      em rows da tabela project_deliverables (insert novos, waive removidos).
    - verify_all(project_id): roda todos verifiers em paralelo (semáforo
      de 5 in flight para não saturar GitHub API), atualiza status.
    - attest_manual(project_id, deliverable_id, user_id, note, evidence_ref):
      atestação humana (para business_case, etc).
    - export_status(project_id): payload para Readiness page.

**Contrato de transação**: nenhum método aqui dá `commit()`. Todos usam
`flush()` para tornar mudanças visíveis dentro da sessão. O CALLER é
responsável por commitar (ou rollback em caso de erro). Isso preserva
atomicidade — sync + outras operações do caller terminam juntas ou
rollback juntas.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
from app.services.deliverable_generators import (
    GeneratorResult,
    generate_kind,
    has_generator,
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
        ocg_data: Any,
    ) -> Dict[str, int]:
        """Sincroniza project_deliverables com OCG.DELIVERABLES.

        Estratégia:
            1. Aceita ``ocg_data`` como dict OU string JSON (parseia).
            2. Lê DELIVERABLES do OCG (lista de strings).
            3. Carrega rows existentes do projeto, indexa por normalized_name.
            4. Para cada string do OCG:
                - Se normalized_name não existe: INSERT (com ON CONFLICT
                  DO NOTHING para tolerar race condition entre 2 syncs
                  concorrentes do mesmo projeto). Status='declared'.
                - Se existe e está 'waived': reativa para 'declared' E
                  re-classifica kind/category (LLM pode ter renomeado
                  semanticamente; reativação é boa hora pra atualizar).
                - Caso contrário: mantém (não toca status).
            5. Para cada row existente cujo normalized_name NÃO está no OCG:
                - Marca status='waived' (preserva histórico).

        Truncagem: name e normalized_name são limitados a 500 chars (limite
        da coluna). Truncamento de normalized_name pode causar colisão
        entre nomes longos quase iguais — ON CONFLICT DO NOTHING evita
        IntegrityError nesses casos (item duplicado é ignorado).

        Não dá commit — caller controla a transação.

        Returns:
            Contadores: ``{"inserted": N, "reactivated": N, "waived": N,
                          "kept": N, "skipped": N}``
        """
        # Normalizar input: aceitar string JSON também
        if isinstance(ocg_data, str):
            try:
                ocg_data = json.loads(ocg_data)
            except (json.JSONDecodeError, ValueError):
                logger.warning("deliverable_registry.invalid_ocg_string", project_id=str(project_id))
                return {"inserted": 0, "reactivated": 0, "waived": 0, "kept": 0, "skipped": 0}
        if not isinstance(ocg_data, dict):
            return {"inserted": 0, "reactivated": 0, "waived": 0, "kept": 0, "skipped": 0}

        deliverables_list = ocg_data.get("DELIVERABLES", []) or []
        if not isinstance(deliverables_list, list):
            return {"inserted": 0, "reactivated": 0, "waived": 0, "kept": 0, "skipped": 0}

        # Existing rows
        result = await self.db.execute(
            select(ProjectDeliverable).where(ProjectDeliverable.project_id == project_id)
        )
        existing = {row.normalized_name: row for row in result.scalars().all()}
        ocg_normalized = set()

        counters = {"inserted": 0, "reactivated": 0, "waived": 0, "kept": 0, "skipped": 0}

        for raw in deliverables_list:
            if not isinstance(raw, str) or not raw.strip():
                counters["skipped"] += 1
                continue
            norm = normalize_name(raw)[:500]  # truncate consistente com coluna
            if not norm:
                counters["skipped"] += 1
                continue
            ocg_normalized.add(norm)

            if norm in existing:
                row = existing[norm]
                if row.status == "waived":
                    # Reativar + re-classificar (kind pode ter mudado se LLM
                    # ressignificou o item; reaproveitamos a oportunidade)
                    new_kind, new_category = classify_deliverable(raw)
                    row.status = "declared"
                    row.kind = new_kind
                    row.category = new_category
                    row.notes = (row.notes or "") + " | reativado: voltou ao OCG"
                    counters["reactivated"] += 1
                else:
                    counters["kept"] += 1
                continue

            # INSERT com ON CONFLICT DO NOTHING — tolera race condition
            # (2 syncs concorrentes do mesmo projeto). Se conflito, conta
            # como skipped, não inserted.
            kind, category = classify_deliverable(raw)
            stmt = (
                pg_insert(ProjectDeliverable)
                .values(
                    project_id=project_id,
                    name=raw[:500],
                    normalized_name=norm,
                    category=category,
                    kind=kind,
                    status="declared",
                )
                .on_conflict_do_nothing(
                    index_elements=["project_id", "normalized_name"]
                )
                .returning(ProjectDeliverable.id)
            )
            res = await self.db.execute(stmt)
            inserted_id = res.scalar_one_or_none()
            if inserted_id:
                counters["inserted"] += 1
            else:
                # Conflict — outra task inseriu primeiro (ou colisão por
                # truncamento). Skipped, mas não-fatal.
                counters["skipped"] += 1

        # Waive os que sumiram do OCG
        for norm, row in existing.items():
            if norm not in ocg_normalized and row.status != "waived":
                row.status = "waived"
                row.notes = (row.notes or "") + " | waived: removido do OCG"
                counters["waived"] += 1

        await self.db.flush()
        logger.info(
            "deliverable_registry.sync_from_ocg",
            project_id=str(project_id),
            **counters,
        )
        return counters

    # ──────────────────────────── verify ────────────────────────────

    # Concorrência máxima de verifiers em paralelo. Cada verifier tipicamente
    # faz 1 HTTP call ao GitHub API. Limite é conservador para não estourar
    # rate-limit (GitHub: 5000 req/h autenticado = 1.4/s sustentado).
    _VERIFY_CONCURRENCY = 5

    async def verify_all(self, project_id: UUID) -> Dict[str, int]:
        """Roda verify_kind() em todos deliverables não-waived do projeto.

        Paraleliza com semáforo (até ``_VERIFY_CONCURRENCY`` verifiers em
        flight simultâneos). Para 30 deliverables × 1s/verifier:
            - serial:   ~30s
            - paralelo: ~6s

        Atualiza status, evidence_*, last_verified_at por linha.

        Em caso de status='error' (verifier levantou exception), preserva
        evidência anterior (não apaga last_verified_at/evidence_ref) — o
        registro fica com last_verified_at antigo + nota de erro nova.

        Não dá commit — caller controla a transação.

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

        if not deliverables:
            return {"verified": 0, "present": 0, "missing": 0, "manual_only": 0, "error": 0}

        # Paralelizar verifiers com semáforo
        sem = asyncio.Semaphore(self._VERIFY_CONCURRENCY)

        async def _run(d: ProjectDeliverable):
            async with sem:
                return d, await verify_kind(d.kind, project_id, self.db)

        results = await asyncio.gather(*[_run(d) for d in deliverables])

        # Aplicar resultados (sequencial para não conflitar com sessão SQLA)
        counters = {"verified": 0, "present": 0, "missing": 0, "manual_only": 0, "error": 0}
        now = datetime.now(timezone.utc)
        for d, res in results:
            new_status = res.status if res.status in counters else "error"

            if new_status == "error":
                # Preservar evidência anterior; só atualizar nota.
                d.status = "error"
                if res.notes:
                    d.notes = res.notes
                # NÃO apaga evidence_*, verification_method, last_verified_at
            else:
                d.status = new_status
                d.evidence_type = res.evidence_type
                d.evidence_ref = res.evidence_ref
                d.verification_method = res.method
                d.last_verified_at = now
                if res.notes:
                    d.notes = res.notes

            counters[d.status] = counters.get(d.status, 0) + 1

        await self.db.flush()
        logger.info(
            "deliverable_registry.verify_all",
            project_id=str(project_id),
            concurrency=self._VERIFY_CONCURRENCY,
            **counters,
        )
        return counters

    # ──────────────────────────── auto-generate ──────────────────────

    async def auto_generate_pending(
        self,
        project_id: UUID,
        ocg_data: Any,
        re_verify: bool = True,
    ) -> Dict[str, Any]:
        """Roda generators para deliverables 'declared' ou 'missing' que têm
        generator registrado. Após gerar, opcionalmente re-verifica o kind
        (que detecta o arquivo no Git e marca 'verified').

        Idempotente: deliverables 'verified', 'present', 'manual_only',
        'waived' são pulados. Generator não-existente para o kind = pulado.

        Args:
            project_id: id do projeto.
            ocg_data: dict OCG (ou string JSON; é normalizado).
            re_verify: se True, roda verify_kind no kind logo após gerar.

        Returns:
            ``{"generated": [{kind, path, bytes}], "skipped": [{kind, reason}],
               "errors": [{kind, error}], "re_verified": [{kind, status}]}``
        """
        # Normaliza ocg_data
        if isinstance(ocg_data, str):
            try:
                ocg_data = json.loads(ocg_data)
            except (json.JSONDecodeError, ValueError):
                ocg_data = {}
        if not isinstance(ocg_data, dict):
            ocg_data = {}

        # Carrega deliverables candidatos a geração
        result = await self.db.execute(
            select(ProjectDeliverable).where(
                ProjectDeliverable.project_id == project_id,
                ProjectDeliverable.status.in_(["declared", "missing"]),
            )
        )
        deliverables = list(result.scalars().all())

        # Dedup: cada KIND roda só 1x mesmo se tem múltiplos deliverables
        # do mesmo kind (raro mas possível).
        seen_kinds: set[str] = set()
        generated: list[dict] = []
        skipped: list[dict] = []
        errors: list[dict] = []
        re_verified: list[dict] = []

        for d in deliverables:
            if d.kind in seen_kinds:
                skipped.append({"kind": d.kind, "reason": "dedup (já processado neste batch)"})
                continue
            seen_kinds.add(d.kind)

            if not has_generator(d.kind):
                skipped.append({"kind": d.kind, "reason": "sem generator registrado"})
                continue

            try:
                # Marca como 'generating' enquanto roda (UI pode mostrar spinner)
                d.status = "generating"
                await self.db.flush()

                res: GeneratorResult = await generate_kind(d.kind, project_id, self.db, ocg_data)

                if res.committed:
                    generated.append({
                        "kind": d.kind,
                        "path": res.path,
                        "bytes": res.bytes_written,
                        "notes": res.notes,
                    })
                    if re_verify:
                        v = await verify_kind(d.kind, project_id, self.db)
                        new_status = v.status if v.status in {"verified", "present", "missing", "manual_only", "error"} else "error"
                        d.status = new_status
                        d.evidence_type = v.evidence_type
                        d.evidence_ref = v.evidence_ref
                        d.verification_method = v.method
                        d.last_verified_at = datetime.now(timezone.utc)
                        if v.notes:
                            d.notes = v.notes
                        re_verified.append({"kind": d.kind, "status": new_status})
                    else:
                        # Sem re-verify: marca como 'present' (arquivo gerado mas
                        # status final será atualizado no próximo verify_all).
                        d.status = "present"
                        d.evidence_type = "file"
                        d.evidence_ref = res.path
                        d.verification_method = "auto_generator"
                        d.last_verified_at = datetime.now(timezone.utc)
                else:
                    # Generator decidiu pular (OCG sem dados, etc.) — volta
                    # para 'declared' e registra motivo na nota.
                    d.status = "declared"
                    d.notes = f"auto_generator skipped: {res.skipped_reason}"
                    skipped.append({"kind": d.kind, "reason": res.skipped_reason})
            except Exception as exc:  # noqa: BLE001
                # Volta para status anterior e registra erro
                d.status = "declared"
                d.notes = f"auto_generator error: {type(exc).__name__}: {exc}"
                errors.append({"kind": d.kind, "error": str(exc)})
                logger.warning(
                    "deliverable_registry.auto_generate_failed",
                    project_id=str(project_id),
                    kind=d.kind,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

        await self.db.flush()
        logger.info(
            "deliverable_registry.auto_generate_pending",
            project_id=str(project_id),
            generated=len(generated),
            skipped=len(skipped),
            errors=len(errors),
        )
        return {
            "generated": generated,
            "skipped": skipped,
            "errors": errors,
            "re_verified": re_verified,
        }

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

        Não dá commit — caller controla a transação.
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
        await self.db.flush()

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
