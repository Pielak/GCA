"""
Audit Service — Trilha de auditoria encadeada com hash chain
Toda ação crítica deve ser registrada via este serviço.
"""
import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import structlog

from app.models.base import GlobalAuditLog


# Catálogo de eventos internos (spec seção 10.1)
class AuditEvents:
    # Eventos 1-9: Projeto e questionário
    PROJECT_REQUEST_CREATED = "PROJECT_REQUEST_CREATED"
    PROJECT_PROVISIONING_STARTED = "PROJECT_PROVISIONING_STARTED"
    PROJECT_PROVISIONED = "PROJECT_PROVISIONED"
    QUESTIONNAIRE_SUBMITTED = "QUESTIONNAIRE_SUBMITTED"
    QUESTIONNAIRE_APPROVED = "QUESTIONNAIRE_APPROVED"
    DOCUMENT_INGESTED = "DOCUMENT_INGESTED"
    DOCUMENT_QUARANTINED = "DOCUMENT_QUARANTINED"
    MASTER_DOCUMENT_MERGED = "MASTER_DOCUMENT_MERGED"
    GATEKEEPER_EVALUATED = "GATEKEEPER_EVALUATED"
    OCG_UPDATED = "OCG_UPDATED"

    # Eventos 10-18: Agentes e geração
    ARGUIDER_QUESTION_OPENED = "ARGUIDER_QUESTION_OPENED"
    ARGUIDER_RESPONSE_REGISTERED = "ARGUIDER_RESPONSE_REGISTERED"
    CODEGEN_REQUESTED = "CODEGEN_REQUESTED"
    CODEGEN_COMPLETED = "CODEGEN_COMPLETED"
    CODE_VALIDATION_COMPLETED = "CODE_VALIDATION_COMPLETED"
    QA_EXECUTION_REQUESTED = "QA_EXECUTION_REQUESTED"
    QA_EXECUTION_COMPLETED = "QA_EXECUTION_COMPLETED"
    LIVEDOCS_UPDATED = "LIVEDOCS_UPDATED"
    WEBHOOK_HEALTH_CHANGED = "WEBHOOK_HEALTH_CHANGED"

    # Eventos 19-26: Usuários e memberships
    CREDENTIAL_STATUS_CHANGED = "CREDENTIAL_STATUS_CHANGED"
    GP_USER_CREATED = "GP_USER_CREATED"
    PROJECT_MEMBERSHIP_CREATED = "PROJECT_MEMBERSHIP_CREATED"
    PROJECT_INVITE_CREATED = "PROJECT_INVITE_CREATED"
    PROJECT_INVITE_EMAIL_SENT = "PROJECT_INVITE_EMAIL_SENT"
    PROJECT_INVITE_ACCEPTED = "PROJECT_INVITE_ACCEPTED"
    PROJECT_CONTEXT_ACTIVATED = "PROJECT_CONTEXT_ACTIVATED"
    BACKLOG_REGENERATED = "BACKLOG_REGENERATED"
    AUDIT_CHAIN_VERIFIED = "AUDIT_CHAIN_VERIFIED"

    # Extra: emails e sistema
    PROJECT_APPROVAL_EMAIL_SENT = "PROJECT_APPROVAL_EMAIL_SENT"
    SYSTEM_SETUP_COMPLETED = "system.setup_completed"

    # MVP 11 Fase 11.4 — Eventos canônicos de papel
    # Payload em details: {actor_id, target_user_id, project_id (nullable),
    # old_role, new_role, phase, timestamp}. Cobertura obrigatória: convite
    # emitido, convite aceito, convite revogado, promoção/rebaixamento de
    # Admin, transferência de soberania de GP, desativação de user/member.
    ROLE_GRANTED = "role_granted"
    ROLE_REVOKED = "role_revoked"
    ROLE_TRANSFERRED = "role_transferred"

    # MVP 13 Fase 13.5 — Eventos canônicos de projeto
    # Payload em details: {actor_id, project_id, action, old_status,
    # new_status, timestamp, extra?}. Fase 13.6 instrumenta os pontos.
    PROJECT_APPROVED = "project_approved"
    PROJECT_REJECTED = "project_rejected"
    PROJECT_STATUS_CHANGED = "project_status_changed"

    # MVP 13 Fase 13.5 — Eventos canônicos de questionário
    # Payload em details: {actor_id, project_id, questionnaire_id, action,
    # score?, timestamp, extra?}. Fase 13.6 instrumenta os pontos.
    QUESTIONNAIRE_APPROVED = "questionnaire_approved"
    QUESTIONNAIRE_REJECTED = "questionnaire_rejected"

    # MVP 13 Fase 13.5 — Eventos canônicos de CodeGen
    # Payload em details: {actor_id, project_id, action, file_path?,
    # files_count?, commit_sha?, timestamp, extra?}. Fase 13.7 instrumenta.
    CODEGEN_SCAFFOLD_GENERATED = "codegen_scaffold_generated"
    CODEGEN_SCAFFOLD_APPLIED = "codegen_scaffold_applied"
    CODEGEN_FILE_REGENERATED = "codegen_file_regenerated"

    # MVP 14 Fase 14.7 — Evento canônico de rollback de OCG
    # Payload em details: {actor_id, project_id, version_from, version_to,
    # restored_from, timestamp}. Emitido por OCGService.rollback_to_version.
    OCG_ROLLED_BACK = "ocg_rolled_back"

logger = structlog.get_logger(__name__)


class AuditService:
    """Serviço centralizado de auditoria com hash chain"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_event(
        self,
        event_type: str,
        resource_type: str,
        actor_id: Optional[UUID] = None,
        actor_email: Optional[str] = None,
        resource_id: Optional[UUID] = None,
        details: Optional[dict] = None,
        correlation_id: Optional[UUID] = None,
    ) -> GlobalAuditLog:
        """Registra evento com hash chain encadeado"""

        # Buscar hash do último registro para encadear
        previous_hash = await self._get_last_hash()

        # Gerar hash deste registro
        details_str = json.dumps(details, default=str, sort_keys=True) if details else ""
        payload = (
            f"{event_type}|{resource_type}|{str(actor_id or '')}|"
            f"{str(resource_id or '')}|{details_str}|{previous_hash or ''}"
        )
        current_hash = hashlib.sha256(payload.encode()).hexdigest()

        entry = GlobalAuditLog(
            event_type=event_type,
            actor_id=actor_id,
            actor_email=actor_email,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details_str if details else None,
            previous_hash=previous_hash,
            current_hash=current_hash,
            correlation_id=correlation_id,
        )

        self.db.add(entry)
        await self.db.flush()

        logger.info(
            "audit.event_logged",
            event_type=event_type,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            correlation_id=str(correlation_id) if correlation_id else None,
            hash=current_hash[:12],
        )

        return entry

    async def log_role_event(
        self,
        event_type: str,
        actor_id: Optional[UUID],
        target_user_id: UUID,
        project_id: Optional[UUID],
        old_role: Optional[str],
        new_role: Optional[str],
        phase: str,
        resource_type: str = "project_member",
        resource_id: Optional[UUID] = None,
        actor_email: Optional[str] = None,
        correlation_id: Optional[UUID] = None,
        extra: Optional[dict] = None,
    ) -> GlobalAuditLog:
        """MVP 11 Fase 11.4 — registra evento canônico de papel.

        Uso obrigatório nos 6 pontos de mudança de papel (contrato §7 MVP 11
        Fase 11.4): invite emitido, invite aceito, invite revogado, promoção/
        rebaixamento de admin, desativação de user ativa com papel. Payload
        canônico: actor_id + target_user_id + project_id (nullable na
        instância) + old_role + new_role + phase.

        `event_type` deve ser um de: AuditEvents.ROLE_GRANTED,
        AuditEvents.ROLE_REVOKED, AuditEvents.ROLE_TRANSFERRED.
        `phase` diferencia o momento da mudança ('invited', 'accepted',
        'revoked', 'admin_promoted', 'admin_demoted', 'transferred',
        'user_deactivated'). `project_id=None` sinaliza ação na instância
        (Admin). `extra` permite anexar metadados opcionais sem quebrar o
        schema canônico.
        """
        allowed = {AuditEvents.ROLE_GRANTED, AuditEvents.ROLE_REVOKED, AuditEvents.ROLE_TRANSFERRED}
        if event_type not in allowed:
            raise ValueError(f"event_type inválido para log_role_event: {event_type!r}")

        details: dict = {
            "target_user_id": str(target_user_id),
            "project_id": str(project_id) if project_id else None,
            "old_role": old_role,
            "new_role": new_role,
            "phase": phase,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            details["extra"] = extra

        return await self.log_event(
            event_type=event_type,
            resource_type=resource_type,
            actor_id=actor_id,
            actor_email=actor_email,
            resource_id=resource_id,
            details=details,
            correlation_id=correlation_id,
        )

    async def log_project_event(
        self,
        event_type: str,
        actor_id: Optional[UUID],
        project_id: UUID,
        action: str,
        old_status: Optional[str] = None,
        new_status: Optional[str] = None,
        actor_email: Optional[str] = None,
        correlation_id: Optional[UUID] = None,
        extra: Optional[dict] = None,
    ) -> GlobalAuditLog:
        """MVP 13 Fase 13.5 — registra evento canônico de projeto.

        `event_type` deve ser um de: PROJECT_APPROVED, PROJECT_REJECTED,
        PROJECT_STATUS_CHANGED. Payload canônico: actor_id + project_id
        + action + old_status + new_status + timestamp.
        """
        allowed = {
            AuditEvents.PROJECT_APPROVED,
            AuditEvents.PROJECT_REJECTED,
            AuditEvents.PROJECT_STATUS_CHANGED,
        }
        if event_type not in allowed:
            raise ValueError(f"event_type inválido para log_project_event: {event_type!r}")

        details: dict = {
            "project_id": str(project_id),
            "action": action,
            "old_status": old_status,
            "new_status": new_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            details["extra"] = extra

        return await self.log_event(
            event_type=event_type,
            resource_type="project",
            actor_id=actor_id,
            actor_email=actor_email,
            resource_id=project_id,
            details=details,
            correlation_id=correlation_id,
        )

    async def log_questionnaire_event(
        self,
        event_type: str,
        actor_id: Optional[UUID],
        project_id: UUID,
        questionnaire_id: UUID,
        action: str,
        score: Optional[float] = None,
        actor_email: Optional[str] = None,
        correlation_id: Optional[UUID] = None,
        extra: Optional[dict] = None,
    ) -> GlobalAuditLog:
        """MVP 13 Fase 13.5 — registra evento canônico de questionário.

        `event_type` deve ser um de: QUESTIONNAIRE_APPROVED,
        QUESTIONNAIRE_REJECTED. Para QUESTIONNAIRE_SUBMITTED (já existe
        no catálogo antigo) o caller usa `log_event` direto. Payload:
        actor_id + project_id + questionnaire_id + action + score +
        timestamp.
        """
        allowed = {
            AuditEvents.QUESTIONNAIRE_APPROVED,
            AuditEvents.QUESTIONNAIRE_REJECTED,
        }
        if event_type not in allowed:
            raise ValueError(f"event_type inválido para log_questionnaire_event: {event_type!r}")

        details: dict = {
            "project_id": str(project_id),
            "questionnaire_id": str(questionnaire_id),
            "action": action,
            "score": score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            details["extra"] = extra

        return await self.log_event(
            event_type=event_type,
            resource_type="questionnaire",
            actor_id=actor_id,
            actor_email=actor_email,
            resource_id=questionnaire_id,
            details=details,
            correlation_id=correlation_id,
        )

    async def log_codegen_event(
        self,
        event_type: str,
        actor_id: Optional[UUID],
        project_id: UUID,
        action: str,
        file_path: Optional[str] = None,
        files_count: Optional[int] = None,
        commit_sha: Optional[str] = None,
        actor_email: Optional[str] = None,
        correlation_id: Optional[UUID] = None,
        extra: Optional[dict] = None,
    ) -> GlobalAuditLog:
        """MVP 13 Fase 13.5 — registra evento canônico de CodeGen.

        `event_type` deve ser um de: CODEGEN_SCAFFOLD_GENERATED,
        CODEGEN_SCAFFOLD_APPLIED, CODEGEN_FILE_REGENERATED. Payload:
        actor_id + project_id + action + file_path + files_count +
        commit_sha + timestamp.
        """
        allowed = {
            AuditEvents.CODEGEN_SCAFFOLD_GENERATED,
            AuditEvents.CODEGEN_SCAFFOLD_APPLIED,
            AuditEvents.CODEGEN_FILE_REGENERATED,
        }
        if event_type not in allowed:
            raise ValueError(f"event_type inválido para log_codegen_event: {event_type!r}")

        details: dict = {
            "project_id": str(project_id),
            "action": action,
            "file_path": file_path,
            "files_count": files_count,
            "commit_sha": commit_sha,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            details["extra"] = extra

        return await self.log_event(
            event_type=event_type,
            resource_type="codegen",
            actor_id=actor_id,
            actor_email=actor_email,
            resource_id=project_id,
            details=details,
            correlation_id=correlation_id,
        )

    async def log_ocg_event(
        self,
        event_type: str,
        actor_id: Optional[UUID],
        project_id: UUID,
        version_from: int,
        version_to: int,
        restored_from: Optional[int] = None,
        actor_email: Optional[str] = None,
        correlation_id: Optional[UUID] = None,
        extra: Optional[dict] = None,
    ) -> GlobalAuditLog:
        """MVP 14 Fase 14.7 — registra evento canônico de OCG.

        Hoje cobre OCG_ROLLED_BACK. Payload: actor_id + project_id +
        version_from + version_to + restored_from + timestamp.
        """
        allowed = {AuditEvents.OCG_ROLLED_BACK}
        if event_type not in allowed:
            raise ValueError(f"event_type inválido para log_ocg_event: {event_type!r}")

        details: dict = {
            "project_id": str(project_id),
            "version_from": version_from,
            "version_to": version_to,
            "restored_from": restored_from,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            details["extra"] = extra

        return await self.log_event(
            event_type=event_type,
            resource_type="ocg",
            actor_id=actor_id,
            actor_email=actor_email,
            resource_id=project_id,
            details=details,
            correlation_id=correlation_id,
        )

    async def _get_last_hash(self) -> Optional[str]:
        """Busca hash do último registro da cadeia"""
        result = await self.db.execute(
            select(GlobalAuditLog.current_hash)
            .order_by(desc(GlobalAuditLog.created_at))
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row

    async def verify_chain(self, limit: int = 100) -> dict:
        """Verifica integridade da cadeia de auditoria"""
        result = await self.db.execute(
            select(GlobalAuditLog)
            .order_by(GlobalAuditLog.created_at.asc())
            .limit(limit)
        )
        entries = result.scalars().all()

        if not entries:
            return {"valid": True, "checked": 0, "errors": []}

        errors = []
        for i, entry in enumerate(entries):
            # Verificar se previous_hash bate com o current_hash do anterior
            if i == 0:
                if entry.previous_hash is not None:
                    errors.append({"index": 0, "id": str(entry.id), "error": "primeiro registro deveria ter previous_hash=null"})
            else:
                if entry.previous_hash != entries[i - 1].current_hash:
                    errors.append({
                        "index": i,
                        "id": str(entry.id),
                        "error": f"previous_hash não bate com current_hash do registro anterior",
                        "expected": entries[i - 1].current_hash[:12],
                        "got": (entry.previous_hash or "null")[:12],
                    })

        return {
            "valid": len(errors) == 0,
            "checked": len(entries),
            "errors": errors,
        }
