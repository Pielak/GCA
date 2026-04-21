"""
OCG Service - Orchestrates 8-agent pipeline for questionnaire analysis
Coordinates: Analyzer → Pillar Specialists (parallel) → Consolidator
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.models.base import Questionnaire, OCG, OCGDeltaLog
from app.schemas.ocg import (
    AnalyzerRequest,
    PillarAgentRequest,
    ConsolidatorRequest,
    OCGResponse,
)
from app.services.agent_service import AgentService

logger = structlog.get_logger(__name__)


class OCGService:
    """Service to orchestrate 8-agent OCG generation pipeline"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.agent_service = AgentService(db)

    async def generate_ocg_from_questionnaire(
        self,
        questionnaire_id: UUID,
        project_id: Optional[UUID] = None,
    ) -> OCGResponse:
        """
        Generate complete OCG from questionnaire ID.

        Pipeline:
        1. Fetch questionnaire from database
        2. Agent 0: Classify by pillar + extract metadata
        3. Agents 1-7: Analyze each pillar in parallel
        4. Agent 8: Consolidate into final OCG

        Args:
            questionnaire_id: UUID of questionnaire to analyze
            project_id: Optional project UUID

        Returns:
            OCGResponse with complete OCG
        """
        try:
            logger.info(
                "ocg.generate_starting",
                questionnaire_id=str(questionnaire_id),
            )

            # Step 1: Fetch questionnaire
            stmt = select(Questionnaire).where(Questionnaire.id == questionnaire_id)
            result = await self.db.execute(stmt)
            questionnaire = result.scalar_one_or_none()

            if not questionnaire:
                raise ValueError(f"Questionnaire {questionnaire_id} not found")

            # Parse questionnaire data
            responses_data = json.loads(questionnaire.responses) if questionnaire.responses else {}

            # Extract answers from responses
            answers = [
                {"question_id": qid, "text": response_text}
                for qid, response_text in responses_data.items()
            ]

            # Project metadata extraído das respostas do questionário
            r = responses_data
            project_metadata = {
                "project_name": r.get("1", f"Project {questionnaire_id}"),
                "project_slug": r.get("2", ""),
                "submitted_by": questionnaire.gp_email,
                "project_type": r.get("4", []),
                "criticality": r.get("5", ""),
                "classification": r.get("6", ""),
                # Stack definida pelo GP no questionário
                "deliverables": r.get("15", r.get("22", [])),
                "architecture": r.get("16", []),
                "execution_model": r.get("17", []),
                "multi_tenant": r.get("18", ""),
                "high_availability": r.get("19", ""),
                "async_processing": r.get("20", ""),
                "has_frontend": r.get("21", ""),
                "frontend_type": r.get("22", []),
                "frontend_stack": r.get("23", []),
                "frontend_language": r.get("24", ""),
                "frontend_requirements": r.get("25", []),
                "has_backend": r.get("26", ""),
                "backend_language": r.get("27", ""),
                "backend_framework": r.get("28", []),
                "backend_type": r.get("29", []),
                "backend_requirements": r.get("30", []),
                "database": r.get("31", ""),
                "database_profile": r.get("32", []),
                "uses_redis": r.get("33", ""),
                "redis_purpose": r.get("34", []),
                "uses_messaging": r.get("35", ""),
                "messaging_purpose": r.get("36", []),
                "uses_ai": r.get("39", ""),
                "ai_purpose": r.get("40", []),
                "ai_provider": r.get("41", []),
                "ai_restrictions": r.get("42", []),
                "security_controls": r.get("43", []),
                "observability": r.get("44", []),
                "test_types": r.get("45", []),
                "quality_gate": r.get("46", ""),
                "formal_qa": r.get("47", ""),
                "expected_deliverables": r.get("48", []),
            }

            logger.info(
                "ocg.questionnaire_loaded",
                questionnaire_id=str(questionnaire_id),
                num_answers=len(answers),
            )

            # Step 2: Agent 0 - Analyzer
            analyzer_req = AnalyzerRequest(
                questionnaire_id=questionnaire_id,
                answers=answers,
                project_metadata=project_metadata,
            )

            analyzer_result = await self.agent_service.analyze_questionnaire(analyzer_req)

            logger.info(
                "ocg.analyzer_complete",
                questionnaire_id=str(questionnaire_id),
                pillars_classified=len(analyzer_result.classification),
            )

            # Step 3: Agents 1-7 - Pillar Specialists (parallel)
            # Create questions list from response keys
            questions_data = [
                {"question_id": qid, "text": f"Question {qid}"}
                for qid in responses_data.keys()
            ]

            pillar_req = PillarAgentRequest(
                pillar_id=0,  # Will be overridden in analyze_pillar
                questionnaire_id=questionnaire_id,
                questions=questions_data,
                responses=responses_data,
                project_metadata=analyzer_result.extracted_info,  # Use extracted info from analyzer
            )

            pillar_results = await self.agent_service.analyze_all_pillars(
                analyzer_result,
                pillar_req,
            )

            logger.info(
                "ocg.pillars_complete",
                questionnaire_id=str(questionnaire_id),
                num_pillars=len(pillar_results),
            )

            # Step 4: Agent 8 - Consolidator
            consolidator_req = ConsolidatorRequest(
                questionnaire_id=questionnaire_id,
                project_id=project_id,
                analyzer_output=analyzer_result,
                pillar_results=pillar_results,
                project_metadata=analyzer_result.extracted_info,
            )

            ocg_response = await self.agent_service.consolidate_ocg(consolidator_req)

            logger.info(
                "ocg.generate_complete",
                questionnaire_id=str(questionnaire_id),
                ocg_id=str(ocg_response.ocg_id),
                overall_score=ocg_response.COMPOSITE_SCORE.get("overall", 0),
            )

            return ocg_response

        except Exception as e:
            logger.error(
                "ocg.generate_error",
                questionnaire_id=str(questionnaire_id),
                error=str(e),
            )
            raise

    async def rollback_to_version(
        self,
        project_id: UUID,
        version_to: int,
        actor_id: Optional[UUID] = None,
    ) -> dict:
        """MVP 14 Fase 14.7 — rollback formal do OCG para versão anterior.

        Lê snapshot de `OCGDeltaLog.ocg_snapshot` da versão alvo, grava
        nova versão no OCG (`version_from + 1`), registra delta de
        rollback e emite evento canônico `OCG_ROLLED_BACK`.
        """
        from app.services.audit_service import AuditService, AuditEvents

        snap_result = await self.db.execute(
            select(OCGDeltaLog)
            .where(
                OCGDeltaLog.project_id == project_id,
                OCGDeltaLog.ocg_version_to == version_to,
            )
            .order_by(OCGDeltaLog.created_at.desc())
            .limit(1)
        )
        delta = snap_result.scalar_one_or_none()
        if not delta or not delta.ocg_snapshot:
            raise ValueError(f"Snapshot não disponível para versão {version_to}")

        snapshot = json.loads(delta.ocg_snapshot)

        ocg_result = await self.db.execute(
            select(OCG)
            .where(OCG.project_id == project_id)
            .order_by(OCG.created_at.desc())
            .limit(1)
        )
        ocg = ocg_result.scalar_one_or_none()
        if not ocg:
            raise ValueError("OCG do projeto não encontrado")

        version_from = ocg.version
        new_version = version_from + 1

        ocg.ocg_data = json.dumps(snapshot, ensure_ascii=False)
        ocg.version = new_version
        ocg.updated_at = datetime.now(timezone.utc)
        self.db.add(ocg)

        rollback_delta = OCGDeltaLog(
            project_id=project_id,
            document_id=None,
            ocg_version_from=version_from,
            ocg_version_to=new_version,
            fields_changed=json.dumps(
                {"__rollback__": {"restored_from_version": version_to}},
                ensure_ascii=False,
            ),
            change_summary=f"Rollback para versão {version_to}",
            changed_by=actor_id,
            trigger_source="rollback",
            ocg_snapshot=json.dumps(snapshot, ensure_ascii=False),
        )
        self.db.add(rollback_delta)
        await self.db.flush()

        await AuditService(self.db).log_ocg_event(
            event_type=AuditEvents.OCG_ROLLED_BACK,
            actor_id=actor_id,
            project_id=project_id,
            version_from=version_from,
            version_to=new_version,
            restored_from=version_to,
        )

        await self.db.commit()

        logger.info(
            "ocg.rolled_back",
            project_id=str(project_id),
            version_from=version_from,
            version_to=new_version,
            restored_from=version_to,
        )

        return {
            "previous_version": version_from,
            "new_version": new_version,
            "restored_from": version_to,
        }

    async def consolidate_ocg(
        self,
        project_id: UUID,
        actor_id: Optional[UUID] = None,
    ) -> dict:
        """MVP 14 Fase 14.8 — consolidação explícita do OCG.

        Lê o OCG atual do projeto, recalcula `overall_score` e `status`
        a partir do bloco `PILLAR_SCORES`, aplicando as regras canônicas
        do contrato §5 (BLOCKED se P7<70 ou P2<70; READY≥90; NEEDS_REVIEW≥75;
        AT_RISK caso contrário).

        Se houver mudança, grava nova versão + delta `trigger_source=
        'consolidation'` + emite `OCG_CONSOLIDATED`. Se não houver mudança,
        é no-op e retorna `changed=False`.
        """
        from app.services.audit_service import AuditService, AuditEvents

        ocg_result = await self.db.execute(
            select(OCG)
            .where(OCG.project_id == project_id)
            .order_by(OCG.created_at.desc())
            .limit(1)
        )
        ocg = ocg_result.scalar_one_or_none()
        if not ocg:
            raise ValueError("OCG do projeto não encontrado")

        data = json.loads(ocg.ocg_data) if ocg.ocg_data else {}
        pillar_scores = data.get("PILLAR_SCORES") or {}
        scores: list[float] = []
        p2_score: Optional[float] = None
        p7_score: Optional[float] = None
        for key, value in pillar_scores.items():
            score = None
            if isinstance(value, dict):
                score = value.get("score")
            elif isinstance(value, (int, float)):
                score = value
            if score is None:
                continue
            scores.append(float(score))
            if key.upper() == "P2":
                p2_score = float(score)
            elif key.upper() == "P7":
                p7_score = float(score)

        overall = round(sum(scores) / len(scores), 1) if scores else 0.0
        is_blocking = (p2_score is not None and p2_score < 70) or (
            p7_score is not None and p7_score < 70
        )
        if is_blocking:
            status = "BLOCKED"
        elif overall >= 90:
            status = "READY"
        elif overall >= 75:
            status = "NEEDS_REVIEW"
        else:
            status = "AT_RISK"

        composite_before = data.get("COMPOSITE_SCORE") or {}
        status_before = ocg.status
        score_before = ocg.overall_score
        composite_after = {
            "overall": overall,
            "is_blocking": is_blocking,
            "status": status,
        }
        unchanged = (
            (score_before or 0.0) == overall
            and status_before == status
            and composite_before.get("overall") == overall
            and composite_before.get("status") == status
        )
        if unchanged:
            return {"changed": False, "version": ocg.version}

        version_from = ocg.version
        new_version = version_from + 1

        data["COMPOSITE_SCORE"] = composite_after
        ocg.ocg_data = json.dumps(data, ensure_ascii=False)
        ocg.overall_score = overall
        ocg.status = status
        ocg.is_blocking = is_blocking
        ocg.version = new_version
        ocg.updated_at = datetime.now(timezone.utc)
        self.db.add(ocg)

        delta = OCGDeltaLog(
            project_id=project_id,
            document_id=None,
            ocg_version_from=version_from,
            ocg_version_to=new_version,
            fields_changed=json.dumps(
                {
                    "COMPOSITE_SCORE": {
                        "old": composite_before,
                        "new": composite_after,
                    }
                },
                ensure_ascii=False,
            ),
            change_summary=f"Consolidação v{version_from}→v{new_version}",
            changed_by=actor_id,
            trigger_source="consolidation",
            ocg_snapshot=json.dumps(data, ensure_ascii=False),
        )
        self.db.add(delta)
        await self.db.flush()

        await AuditService(self.db).log_ocg_event(
            event_type=AuditEvents.OCG_CONSOLIDATED,
            actor_id=actor_id,
            project_id=project_id,
            version_from=version_from,
            version_to=new_version,
            extra={
                "composite_before": composite_before,
                "composite_after": composite_after,
                "status_before": status_before,
                "status_after": status,
            },
        )

        await self.db.commit()

        logger.info(
            "ocg.consolidated",
            project_id=str(project_id),
            version_from=version_from,
            version_to=new_version,
            overall_score=overall,
            status=status,
        )

        return {
            "changed": True,
            "previous_version": version_from,
            "new_version": new_version,
            "overall_score": overall,
            "status": status,
            "is_blocking": is_blocking,
        }

    async def get_next_version(self, project_id: UUID) -> int:
        """Retorna a próxima versão do OCG para o projeto"""
        result = await self.db.execute(
            select(OCG.version)
            .where(OCG.project_id == project_id)
            .order_by(OCG.version.desc())
            .limit(1)
        )
        current = result.scalar_one_or_none()
        return (current or 0) + 1

    async def log_delta(
        self,
        project_id: UUID,
        document_id: UUID,
        version_from: int,
        version_to: int,
        fields_changed: dict,
    ):
        """Registra mudança no OCG causada por ingestão"""
        delta = OCGDeltaLog(
            project_id=project_id,
            document_id=document_id,
            ocg_version_from=version_from,
            ocg_version_to=version_to,
            fields_changed=json.dumps(fields_changed, default=str),
            change_summary=f"OCG v{version_from} → v{version_to}",
        )
        self.db.add(delta)
        await self.db.commit()

        logger.info("ocg.delta_logged",
                    project_id=str(project_id),
                    version_from=version_from,
                    version_to=version_to)

    async def send_ocg_notification(
        self,
        ocg_id: UUID,
        recipient_email: Optional[str] = None,
    ) -> bool:
        """
        Send OCG notification (email, webhook, etc.)

        Args:
            ocg_id: UUID of OCG to notify about
            recipient_email: Optional email to send to

        Returns:
            True if successful
        """
        try:
            logger.info(
                "ocg.notification_sending",
                ocg_id=str(ocg_id),
                recipient=recipient_email,
            )

            # TODO: Implement email notification
            # For now, just log
            logger.info(
                "ocg.notification_sent",
                ocg_id=str(ocg_id),
            )
            return True

        except Exception as e:
            logger.error(
                "ocg.notification_error",
                ocg_id=str(ocg_id),
                error=str(e),
            )
            return False
