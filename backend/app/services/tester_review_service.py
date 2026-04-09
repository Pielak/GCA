"""
Tester Review Service — CRUD de artefatos de teste com RBAC e versionamento.

Regras:
- Edição: apenas tester/admin
- Aprovação: tester/gestor/admin/qa
- Cada edição incrementa version e registra last_edited_by
"""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models.base import TestArtifact, TestExecutionLog, User, ProjectMember

logger = structlog.get_logger(__name__)

# RBAC — regras definitivas (08/04/2026)
# Admin NÃO atua em projeto, apenas administra plataforma
# GP NÃO edita testes
# Dev NÃO edita testes, NÃO aprova
# Tester: edita, aprova, rejeita, executa, exporta
# QA: executa, aprova resultados, exporta — NÃO edita conteúdo
EDIT_ROLES = {"tester"}
APPROVE_ROLES = {"tester", "qa"}
EXECUTE_ROLES = {"tester", "qa", "dev"}


class TesterReviewService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_user_project_role(self, user_id: UUID, project_id: UUID) -> Optional[str]:
        """Retorna o papel do usuário no projeto, ou 'admin' se is_admin."""
        user = await self.db.get(User, user_id)
        if user and user.is_admin:
            return "admin"
        result = await self.db.execute(
            select(ProjectMember.role)
            .where(ProjectMember.user_id == user_id, ProjectMember.project_id == project_id)
        )
        row = result.scalar_one_or_none()
        return row

    async def list_tests(
        self,
        project_id: UUID,
        test_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[dict]:
        query = select(TestArtifact).where(TestArtifact.project_id == project_id)
        if test_type:
            query = query.where(TestArtifact.test_type == test_type)
        if status:
            query = query.where(TestArtifact.status == status)
        query = query.order_by(TestArtifact.created_at.desc())
        result = await self.db.execute(query)
        artifacts = result.scalars().all()
        return [self._to_dict(a) for a in artifacts]

    async def get_test(self, test_id: UUID) -> Optional[dict]:
        artifact = await self.db.get(TestArtifact, test_id)
        return self._to_dict(artifact) if artifact else None

    async def update_test(
        self,
        test_id: UUID,
        user_id: UUID,
        content: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        artifact = await self.db.get(TestArtifact, test_id)
        if not artifact:
            return {"error": "Teste não encontrado", "status_code": 404}

        role = await self._get_user_project_role(user_id, artifact.project_id)
        if role not in EDIT_ROLES:
            return {"error": "Sem permissão para editar testes", "status_code": 403}

        if content is not None:
            artifact.content = content
        if title is not None:
            artifact.title = title
        if description is not None:
            artifact.description = description

        artifact.version += 1
        artifact.last_edited_by = user_id
        artifact.last_edited_at = datetime.now(timezone.utc)
        artifact.status = "edited"

        await self.db.commit()
        await self.db.refresh(artifact)

        logger.info(
            "tester_review.test_updated",
            test_id=str(test_id),
            user_id=str(user_id),
            version=artifact.version,
        )
        return self._to_dict(artifact)

    async def approve_test(self, test_id: UUID, user_id: UUID) -> dict:
        artifact = await self.db.get(TestArtifact, test_id)
        if not artifact:
            return {"error": "Teste não encontrado", "status_code": 404}

        role = await self._get_user_project_role(user_id, artifact.project_id)
        if role not in APPROVE_ROLES:
            return {"error": "Sem permissão para aprovar testes", "status_code": 403}

        artifact.status = "approved"
        await self.db.commit()
        await self.db.refresh(artifact)

        logger.info("tester_review.test_approved", test_id=str(test_id), user_id=str(user_id))
        return self._to_dict(artifact)

    async def reject_test(self, test_id: UUID, user_id: UUID, reason: str) -> dict:
        artifact = await self.db.get(TestArtifact, test_id)
        if not artifact:
            return {"error": "Teste não encontrado", "status_code": 404}

        role = await self._get_user_project_role(user_id, artifact.project_id)
        if role not in APPROVE_ROLES:
            return {"error": "Sem permissão para rejeitar testes", "status_code": 403}

        artifact.status = "rejected"
        artifact.description = (artifact.description or "") + f"\n\n[REJEITADO] {reason}"
        await self.db.commit()
        await self.db.refresh(artifact)

        logger.info("tester_review.test_rejected", test_id=str(test_id), reason=reason)
        return self._to_dict(artifact)

    async def get_execution_logs(self, test_id: UUID) -> List[dict]:
        result = await self.db.execute(
            select(TestExecutionLog)
            .where(TestExecutionLog.test_artifact_id == test_id)
            .order_by(TestExecutionLog.executed_at.desc())
        )
        logs = result.scalars().all()
        return [
            {
                "id": str(log.id),
                "executed_at": log.executed_at.isoformat() if log.executed_at else None,
                "executed_by": str(log.executed_by),
                "status": log.status,
                "duration_ms": log.duration_ms,
                "output": log.output,
                "module_name": log.module_name,
                "function_name": log.function_name,
                "test_version_at_run": log.test_version_at_run,
            }
            for log in logs
        ]

    def _to_dict(self, artifact: TestArtifact) -> dict:
        return {
            "id": str(artifact.id),
            "project_id": str(artifact.project_id),
            "module_id": str(artifact.module_id) if artifact.module_id else None,
            "test_type": artifact.test_type,
            "title": artifact.title,
            "description": artifact.description,
            "file_path": artifact.file_path,
            "content": artifact.content,
            "status": artifact.status,
            "created_by": str(artifact.created_by),
            "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
            "last_edited_by": str(artifact.last_edited_by) if artifact.last_edited_by else None,
            "last_edited_at": artifact.last_edited_at.isoformat() if artifact.last_edited_at else None,
            "version": artifact.version,
        }
