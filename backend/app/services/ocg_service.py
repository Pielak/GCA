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

from app.models.base import Questionnaire
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

            # Project metadata from questionnaire context
            project_metadata = {
                "project_name": f"Project {questionnaire_id}",
                "submitted_by": questionnaire.gp_email,
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
