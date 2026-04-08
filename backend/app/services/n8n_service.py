"""n8n Integration Service — Qwen AI Enhanced Analysis"""
import aiohttp
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import structlog
import json

from app.core.config import settings

logger = structlog.get_logger(__name__)


class N8nService:
    """Service for triggering n8n workflows with Qwen AI analysis"""

    @staticmethod
    async def trigger_questionnaire_analysis(
        questionnaire_id: str,
        project_id: str,
        gp_email: str,
        responses: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """
        Trigger n8n webhook for enhanced questionnaire analysis using Qwen AI.

        This is called asynchronously AFTER the built-in analysis.
        n8n will:
        1. Receive questionnaire data
        2. Run Qwen AI analysis for deeper insights
        3. Call back to /api/v1/webhooks/questionnaire-result with enhanced results

        Args:
            questionnaire_id: UUID of questionnaire
            project_id: Project UUID
            gp_email: Project manager email
            responses: Original questionnaire responses

        Returns:
            (success, error_message)
        """
        if not settings.N8N_WEBHOOK_URL:
            logger.info("n8n.disabled", reason="N8N_WEBHOOK_URL not configured")
            return True, None  # Don't fail if n8n is not configured

        try:
            payload = {
                "questionnaire_id": questionnaire_id,
                "project_id": str(project_id),
                "gp_email": gp_email,
                "responses": responses,
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            }

            logger.info(
                "n8n.webhook_triggering",
                questionnaire_id=questionnaire_id,
                project_id=str(project_id),
                url=settings.N8N_WEBHOOK_URL,
            )

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    settings.N8N_WEBHOOK_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                    headers={"Content-Type": "application/json"},
                ) as response:
                    if response.status in (200, 201, 202):
                        logger.info(
                            "n8n.webhook_triggered",
                            questionnaire_id=questionnaire_id,
                            status=response.status,
                        )
                        return True, None
                    else:
                        error_text = await response.text()
                        logger.warning(
                            "n8n.webhook_failed",
                            questionnaire_id=questionnaire_id,
                            status=response.status,
                            error=error_text[:200],
                        )
                        return False, f"n8n webhook returned {response.status}"

        except aiohttp.ClientConnectorError as e:
            logger.warning(
                "n8n.connection_failed",
                questionnaire_id=questionnaire_id,
                error=str(e),
            )
            return False, f"Failed to connect to n8n: {str(e)}"
        except asyncio.TimeoutError:
            logger.warning(
                "n8n.timeout",
                questionnaire_id=questionnaire_id,
            )
            return False, "n8n webhook timed out"
        except Exception as e:
            logger.error(
                "n8n.webhook_error",
                questionnaire_id=questionnaire_id,
                error=str(e),
            )
            return False, str(e)

    @staticmethod
    async def update_questionnaire_with_n8n_results(
        db,
        questionnaire_id: str,
        n8n_results: Dict[str, Any],
    ) -> bool:
        """
        Update questionnaire with enhanced results from n8n/Qwen AI.

        Called by n8n webhook when analysis is complete.
        """
        try:
            from uuid import UUID
            from sqlalchemy import select, update
            from app.models.base import Questionnaire

            q_uuid = UUID(questionnaire_id)

            # Prepare update data
            update_data = {
                "analyzed_at": datetime.now(timezone.utc),
            }

            # Update score if provided
            if "adherenceScore" in n8n_results:
                update_data["adherence_score"] = n8n_results["adherenceScore"]
                update_data["approved"] = n8n_results.get("approved", False)

            # Update validations if provided
            if "validations" in n8n_results:
                update_data["validations"] = json.dumps(n8n_results["validations"])

            # Update observations and restrictions
            if "observations" in n8n_results:
                update_data["observations"] = n8n_results["observations"]
            if "restrictions" in n8n_results:
                update_data["restrictions"] = n8n_results["restrictions"]
            if "highlightedFields" in n8n_results:
                update_data["highlighted_fields"] = json.dumps(n8n_results["highlightedFields"])

            # Execute update
            stmt = update(Questionnaire).where(Questionnaire.id == q_uuid).values(**update_data)
            await db.execute(stmt)
            await db.commit()

            logger.info(
                "n8n.questionnaire_updated",
                questionnaire_id=questionnaire_id,
                score=update_data.get("adherence_score"),
            )
            return True

        except Exception as e:
            logger.error(
                "n8n.update_failed",
                questionnaire_id=questionnaire_id,
                error=str(e),
            )
            return False


# Import asyncio at module level
import asyncio
