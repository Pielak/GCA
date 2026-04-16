"""Testes integrados do DeliverableRegistry (Fase A.4).

Usa DB real (sessão isolada) — testa sync_from_ocg + verify_all +
attest_manual + export_status criando projeto+OCG fixture mínimo.
"""
from datetime import datetime
from uuid import uuid4

import pytest

from app.db.database import AsyncSessionLocal
from app.models.base import (
    OCG,
    Organization,
    Project,
    ProjectDeliverable,
    Questionnaire,
    User,
)
from app.core.security import hash_password
from app.services.deliverable_registry import DeliverableRegistry


async def _make_project_fixture():
    """Cria User + Org + Project + Questionnaire + OCG, retorna ids."""
    uid = uuid4()
    org_id = uuid4()
    project_id = uuid4()
    questionnaire_id = uuid4()
    ocg_id = uuid4()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(User(
                id=uid,
                email=f"deliv-{uid.hex[:6]}@test.com",
                password_hash=hash_password("Test@1234"),
                full_name="Deliverable Tester",
                is_active=True,
                is_admin=True,
                created_at=datetime.utcnow(),
            ))
            session.add(Organization(
                id=org_id,
                name=f"Org {uid.hex[:6]}",
                slug=f"org-{uid.hex[:6]}",
                owner_id=uid,
                is_active=True,
                created_at=datetime.utcnow(),
            ))
            await session.flush()
            session.add(Project(
                id=project_id,
                organization_id=org_id,
                name=f"P {uid.hex[:6]}",
                slug=f"p-{uid.hex[:6]}",
                status="active",
                deliverable_type="new_system",
                created_at=datetime.utcnow(),
            ))
            await session.flush()
            session.add(Questionnaire(
                id=questionnaire_id,
                project_id=project_id,
                gp_email=f"deliv-{uid.hex[:6]}@test.com",
                responses="{}",
                status="pending",
            ))
            await session.flush()
            session.add(OCG(
                id=ocg_id,
                project_id=project_id,
                questionnaire_id=questionnaire_id,
                version=1,
                status="READY",
                ocg_data="{}",
            ))
    return uid, org_id, project_id, questionnaire_id, ocg_id


async def _cleanup_project_fixture(uid, org_id, project_id, questionnaire_id, ocg_id):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                ProjectDeliverable.__table__.delete().where(
                    ProjectDeliverable.project_id == project_id
                )
            )
            await session.execute(OCG.__table__.delete().where(OCG.id == ocg_id))
            await session.execute(Questionnaire.__table__.delete().where(Questionnaire.id == questionnaire_id))
            await session.execute(Project.__table__.delete().where(Project.id == project_id))
            await session.execute(Organization.__table__.delete().where(Organization.id == org_id))
            await session.execute(User.__table__.delete().where(User.id == uid))


# ─────────────────────────── sync_from_ocg ───────────────────────────

@pytest.mark.asyncio
async def test_sync_inserts_new_deliverables_from_empty():
    uid, org_id, pid, qid, ocg_id = await _make_project_fixture()
    try:
        async with AsyncSessionLocal() as db:
            registry = DeliverableRegistry(db)
            counters = await registry.sync_from_ocg(pid, {
                "DELIVERABLES": [
                    "Documento de Caso de Negócio e ROI",
                    "SBOM (Software Bill of Materials) inicial",
                    "Algum entregável customizado sem padrão",
                ],
            })
        assert counters["inserted"] == 3
        assert counters["waived"] == 0

        # Verifica state
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            res = await db.execute(
                select(ProjectDeliverable).where(ProjectDeliverable.project_id == pid)
            )
            rows = list(res.scalars().all())
        kinds = {r.kind for r in rows}
        assert "business_case" in kinds
        assert "sbom" in kinds
        assert "other_manual" in kinds
        for r in rows:
            assert r.status == "declared"
    finally:
        await _cleanup_project_fixture(uid, org_id, pid, qid, ocg_id)


@pytest.mark.asyncio
async def test_sync_waives_removed_deliverables():
    uid, org_id, pid, qid, ocg_id = await _make_project_fixture()
    try:
        # Round 1: 2 itens
        async with AsyncSessionLocal() as db:
            await DeliverableRegistry(db).sync_from_ocg(pid, {
                "DELIVERABLES": ["Documento de Caso de Negócio e ROI", "SBOM inicial"],
            })

        # Round 2: só 1 (o outro deve virar waived)
        async with AsyncSessionLocal() as db:
            counters = await DeliverableRegistry(db).sync_from_ocg(pid, {
                "DELIVERABLES": ["Documento de Caso de Negócio e ROI"],
            })
        assert counters["inserted"] == 0
        assert counters["kept"] == 1
        assert counters["waived"] == 1

        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            res = await db.execute(
                select(ProjectDeliverable).where(ProjectDeliverable.project_id == pid)
            )
            rows = list(res.scalars().all())
        statuses = {r.kind: r.status for r in rows}
        assert statuses["business_case"] == "declared"
        assert statuses["sbom"] == "waived"
    finally:
        await _cleanup_project_fixture(uid, org_id, pid, qid, ocg_id)


@pytest.mark.asyncio
async def test_sync_reactivates_waived_when_returns_to_ocg():
    uid, org_id, pid, qid, ocg_id = await _make_project_fixture()
    try:
        async with AsyncSessionLocal() as db:
            await DeliverableRegistry(db).sync_from_ocg(pid, {"DELIVERABLES": ["SBOM inicial"]})
        async with AsyncSessionLocal() as db:
            await DeliverableRegistry(db).sync_from_ocg(pid, {"DELIVERABLES": []})  # waive
        async with AsyncSessionLocal() as db:
            counters = await DeliverableRegistry(db).sync_from_ocg(pid, {"DELIVERABLES": ["SBOM inicial"]})
        assert counters["reactivated"] == 1

        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            res = await db.execute(
                select(ProjectDeliverable).where(ProjectDeliverable.project_id == pid)
            )
            rows = list(res.scalars().all())
        assert len(rows) == 1
        assert rows[0].status == "declared"
    finally:
        await _cleanup_project_fixture(uid, org_id, pid, qid, ocg_id)


# ─────────────────────────── attest_manual ───────────────────────────

@pytest.mark.asyncio
async def test_attest_manual_marks_verified():
    uid, org_id, pid, qid, ocg_id = await _make_project_fixture()
    try:
        async with AsyncSessionLocal() as db:
            await DeliverableRegistry(db).sync_from_ocg(pid, {
                "DELIVERABLES": ["Documento de Caso de Negócio e ROI"],
            })

        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            res = await db.execute(
                select(ProjectDeliverable).where(ProjectDeliverable.project_id == pid)
            )
            row = res.scalar_one()
            deliverable_id = row.id

        async with AsyncSessionLocal() as db:
            registry = DeliverableRegistry(db)
            updated = await registry.attest_manual(
                pid, deliverable_id, uid,
                note="Aprovado pelo board em 2026-04-15. Acta em #12345.",
                evidence_ref="https://wiki/acta-12345",
            )
            assert updated is not None
            assert updated.status == "verified"
            assert updated.evidence_type == "manual"
            assert updated.verified_by == uid
            assert "board" in updated.notes
    finally:
        await _cleanup_project_fixture(uid, org_id, pid, qid, ocg_id)


@pytest.mark.asyncio
async def test_attest_manual_rejects_empty_note():
    uid, org_id, pid, qid, ocg_id = await _make_project_fixture()
    try:
        async with AsyncSessionLocal() as db:
            await DeliverableRegistry(db).sync_from_ocg(pid, {"DELIVERABLES": ["A"]})
            from sqlalchemy import select
            res = await db.execute(
                select(ProjectDeliverable).where(ProjectDeliverable.project_id == pid)
            )
            deliverable_id = res.scalar_one().id

        async with AsyncSessionLocal() as db:
            r = await DeliverableRegistry(db).attest_manual(pid, deliverable_id, uid, note="")
            assert r is None
            r = await DeliverableRegistry(db).attest_manual(pid, deliverable_id, uid, note="   ")
            assert r is None
    finally:
        await _cleanup_project_fixture(uid, org_id, pid, qid, ocg_id)


# ─────────────────────────── export_status ───────────────────────────

@pytest.mark.asyncio
async def test_export_status_aggregates():
    uid, org_id, pid, qid, ocg_id = await _make_project_fixture()
    try:
        async with AsyncSessionLocal() as db:
            await DeliverableRegistry(db).sync_from_ocg(pid, {
                "DELIVERABLES": [
                    "Documento de Caso de Negócio e ROI",  # business_case (doc)
                    "SBOM inicial",  # sbom (code)
                    "Plano de Testes",  # test_plan (test)
                    "Algum coisa custom",  # other_manual (other)
                ],
            })

        async with AsyncSessionLocal() as db:
            payload = await DeliverableRegistry(db).export_status(pid)

        assert payload["summary"]["total_active"] == 4
        assert payload["summary"]["verified"] == 0
        assert payload["summary"]["readiness_pct"] == 0.0
        cats = payload["summary"]["by_category"]
        assert cats.get("doc") == 1
        assert cats.get("code") == 1
        assert cats.get("test") == 1
        assert cats.get("other") == 1
        # Cada item tem auto_verifiable correto
        items = {i["kind"]: i for i in payload["deliverables"]}
        assert items["sbom"]["auto_verifiable"] is True
        assert items["business_case"]["auto_verifiable"] is False
        assert items["other_manual"]["auto_verifiable"] is False
    finally:
        await _cleanup_project_fixture(uid, org_id, pid, qid, ocg_id)
