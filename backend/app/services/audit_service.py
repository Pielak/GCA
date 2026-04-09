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
