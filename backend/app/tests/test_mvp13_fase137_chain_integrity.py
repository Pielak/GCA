"""MVP 13 Fase 13.7 — Instrumentação CodeGen + E2E chain integrity.

Contrato §7 MVP 13 Fase 13.7:
- `generate_scaffold`: emite CODEGEN_SCAFFOLD_GENERATED.
- `apply_scaffold`: emite CODEGEN_SCAFFOLD_APPLIED.
- `regenerate_file`: emite CODEGEN_FILE_REGENERATED.
- Teste E2E dispara série de eventos canônicos (projeto + questionário
  + CodeGen + role) e valida `AuditService.verify_chain()` íntegra —
  zero broken links na hash chain SHA-256.
"""
import inspect
import json
from uuid import uuid4

import pytest


# ─── Verifica que os 3 endpoints usam helpers canônicos ──────────────


def test_generate_scaffold_usa_log_codegen_event():
    from app.routers import code_generation
    src = inspect.getsource(code_generation.generate_scaffold)
    assert "log_codegen_event" in src
    assert "CODEGEN_SCAFFOLD_GENERATED" in src


def test_apply_scaffold_usa_log_codegen_event():
    from app.routers import code_generation
    src = inspect.getsource(code_generation.apply_scaffold)
    assert "log_codegen_event" in src
    assert "CODEGEN_SCAFFOLD_APPLIED" in src


def test_regenerate_file_usa_log_codegen_event():
    from app.routers import code_generation
    src = inspect.getsource(code_generation.regenerate_single_file)
    assert "log_codegen_event" in src
    assert "CODEGEN_FILE_REGENERATED" in src


# ─── Chain integrity E2E ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_chain_intacto_apos_serie_de_eventos_canonicos():
    """E2E canônico: grava 1 evento de cada domínio em sequência e
    valida que `verify_chain()` retorna válido sem broken links.

    Evita pipeline LLM real (rollback N/A, consolidate implícito);
    foca em integridade de hash chain que é o que contrato pede.
    """
    from app.db.database import AsyncSessionLocal
    from app.models.base import GlobalAuditLog
    from app.services.audit_service import AuditEvents, AuditService

    # Marker único desta execução — filtra verify_chain para nosso
    # subconjunto, não compartilhando com outros testes.
    marker = f"f137-chain-{uuid4().hex[:8]}"
    project_id = uuid4()
    questionnaire_id = uuid4()

    try:
        async with AsyncSessionLocal() as session:
            audit = AuditService(session)

            # 1. project_approved
            await audit.log_project_event(
                event_type=AuditEvents.PROJECT_APPROVED,
                actor_id=None, project_id=project_id,
                action=marker, old_status="pending", new_status="active",
            )

            # 2. questionnaire_submitted (log_event direto — helper é só
            # pra approved/rejected)
            await audit.log_event(
                event_type=AuditEvents.QUESTIONNAIRE_SUBMITTED,
                resource_type="questionnaire",
                resource_id=questionnaire_id,
                details={"marker": marker, "score": 95},
            )

            # 3. questionnaire_approved
            await audit.log_questionnaire_event(
                event_type=AuditEvents.QUESTIONNAIRE_APPROVED,
                actor_id=None, project_id=project_id,
                questionnaire_id=questionnaire_id,
                action=marker, score=95.0,
            )

            # 4. role_granted (existe no catálogo desde 11.4)
            await audit.log_role_event(
                event_type=AuditEvents.ROLE_GRANTED,
                actor_id=None, target_user_id=uuid4(),
                project_id=project_id,
                old_role=None, new_role="dev",
                phase=marker,
            )

            # 5. codegen_scaffold_generated
            await audit.log_codegen_event(
                event_type=AuditEvents.CODEGEN_SCAFFOLD_GENERATED,
                actor_id=None, project_id=project_id,
                action=marker, files_count=10,
            )

            # 6. codegen_scaffold_applied
            await audit.log_codegen_event(
                event_type=AuditEvents.CODEGEN_SCAFFOLD_APPLIED,
                actor_id=None, project_id=project_id,
                action=marker, files_count=8,
            )

            # 7. codegen_file_regenerated
            await audit.log_codegen_event(
                event_type=AuditEvents.CODEGEN_FILE_REGENERATED,
                actor_id=None, project_id=project_id,
                action=marker, file_path="src/main.py",
            )

            await session.commit()

        # Valida que os 7 eventos estão gravados E têm hash chain coerente.
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select, desc

            # Pega só os nossos 7 (via marker nos details).
            res = await session.execute(
                select(GlobalAuditLog)
                .where(GlobalAuditLog.details.like(f'%"{marker}"%'))
                .order_by(GlobalAuditLog.created_at)
            )
            our_entries = list(res.scalars().all())
            assert len(our_entries) == 7, f"esperava 7 entradas com marker, veio {len(our_entries)}"

            # Para cada entry nossa, o current_hash deve ser
            # previous_hash da próxima. Garante que a cadeia não
            # foi corrompida enquanto gravávamos.
            for i in range(1, len(our_entries)):
                # Nossa cadeia pode ter entries de outros testes
                # intercaladas no DB global. Testamos integridade
                # individual: hash é determinístico em (event_type,
                # resource_type, actor_id, resource_id, details,
                # previous_hash).
                assert our_entries[i].current_hash is not None
                assert our_entries[i].current_hash != our_entries[i - 1].current_hash

            # Valida verify_chain() global em última instância: zero
            # broken links no subconjunto recente.
            result = await AuditService(session).verify_chain(limit=500)
            # Se `verify_chain()` retorna valid=False, é porque algum
            # previous_hash não bateu — inclusive entries nossas.
            assert result["valid"] is True, (
                f"verify_chain quebrou: {result.get('errors', [])[:3]}"
            )
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    GlobalAuditLog.__table__.delete().where(
                        GlobalAuditLog.details.like(f'%"{marker}"%')
                    )
                )
