"""
Piloter Service
Integração com Piloter API para recomendações de stack e análise
"""
import httpx
import structlog
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.config import settings
from app.models.onboarding import StackCache, PiloterQuery, PiloterQuotaHistory
from app.core.security import decrypt_token, encrypt_token

logger = structlog.get_logger(__name__)


class PiloterService:
    """Service for Piloter API integration"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.api_key = settings.PILOTER_API_KEY
        self.api_endpoint = settings.PILOTER_API_ENDPOINT
        self.webhook_url = settings.N8N_WEBHOOK_URL

    async def get_stack_recommendations(
        self,
        project_id: UUID,
        language: str,
        architecture: str,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Get technology stack recommendations from Piloter API

        Returns:
            {
                "stack": {...},
                "recommendations": [...],
                "alternatives": [...],
                "cached": bool
            }
        """
        try:
            cache_key = f"{language}_{architecture}"

            # 1. Try to get from cache if enabled
            if use_cache:
                cached = await self._get_from_cache(cache_key)
                if cached:
                    logger.info("piloter.cache_hit",
                               project_id=str(project_id),
                               cache_key=cache_key)
                    return {
                        "stack": cached.stack_data,
                        "recommendations": cached.recommendations,
                        "alternatives": cached.alternatives,
                        "cached": True,
                        "cached_at": cached.created_at.isoformat()
                    }

            # 2. Call Piloter API
            logger.info("piloter.api_call_start",
                       project_id=str(project_id),
                       language=language,
                       architecture=architecture)

            stack_data = await self._call_piloter_api(language, architecture)

            # 3. Check quota before saving
            quota_ok = await self._check_quota(project_id)
            if not quota_ok:
                logger.warning("piloter.quota_exceeded",
                              project_id=str(project_id))
                return {
                    "error": "API quota exceeded",
                    "cached": False,
                    "stack": None
                }

            # 4. Save to cache
            await self._save_to_cache(
                cache_key=cache_key,
                stack_data=stack_data,
                recommendations=stack_data.get("recommendations", []),
                alternatives=stack_data.get("alternatives", [])
            )

            # 5. Log API call
            await self._log_api_call(
                project_id=project_id,
                language=language,
                architecture=architecture,
                success=True
            )

            logger.info("piloter.api_call_success",
                       project_id=str(project_id))

            return {
                "stack": stack_data,
                "recommendations": stack_data.get("recommendations", []),
                "alternatives": stack_data.get("alternatives", []),
                "cached": False
            }

        except Exception as e:
            logger.error("piloter.get_stack_error",
                        project_id=str(project_id),
                        error=str(e))
            raise ValueError(f"Failed to get stack recommendations: {str(e)}")

    async def _call_piloter_api(
        self,
        language: str,
        architecture: str
    ) -> Dict[str, Any]:
        """Call Piloter API directly"""

        payload = {
            "language": language,
            "architecture": architecture,
            "filters": {
                "stability": "stable",
                "maturity": "mature"
            }
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_endpoint}/recommendations",
                    json=payload,
                    headers=headers
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    raise ValueError("Piloter API authentication failed")
                elif response.status_code == 429:
                    raise ValueError("Piloter API rate limit exceeded")
                else:
                    raise ValueError(f"Piloter API error: {response.status_code}")

        except httpx.TimeoutException:
            raise ValueError("Piloter API request timeout")
        except httpx.RequestError as e:
            raise ValueError(f"Piloter API request error: {str(e)}")

    async def _get_from_cache(self, cache_key: str) -> Optional[StackCache]:
        """Get cached stack recommendations"""

        result = await self.db.execute(
            select(StackCache)
            .where(StackCache.cache_key == cache_key)
            .where(StackCache.expires_at > datetime.now(timezone.utc))
        )

        return result.scalar_one_or_none()

    async def _save_to_cache(
        self,
        cache_key: str,
        stack_data: Dict[str, Any],
        recommendations: List[Dict],
        alternatives: List[Dict]
    ) -> None:
        """Save stack recommendations to cache"""

        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.STACK_CACHE_DURATION_DAYS
        )

        cache_entry = StackCache(
            cache_key=cache_key,
            stack_data=stack_data,
            recommendations=recommendations,
            alternatives=alternatives,
            expires_at=expires_at
        )

        self.db.add(cache_entry)
        await self.db.commit()

        logger.info("piloter.cache_saved",
                   cache_key=cache_key,
                   expires_at=expires_at.isoformat())

    async def _check_quota(self, project_id: UUID) -> bool:
        """Check Piloter API quota usage"""

        result = await self.db.execute(
            select(PiloterQuotaHistory)
            .order_by(PiloterQuotaHistory.created_at.desc())
            .limit(1)
        )

        quota = result.scalar_one_or_none()

        if not quota:
            # First call, assume quota is available
            return True

        # Check alert level
        if quota.alert_level == "critical":
            logger.warning("piloter.quota_critical",
                          remaining=quota.credits_remaining)
            return False

        if quota.credits_remaining <= 0:
            logger.error("piloter.quota_exhausted")
            return False

        return True

    async def _log_api_call(
        self,
        project_id: UUID,
        language: str,
        architecture: str,
        success: bool
    ) -> None:
        """Log Piloter API call"""

        query_log = PiloterQuery(
            project_id=project_id,
            language=language,
            architecture=architecture,
            success=success,
            query_data={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "success" if success else "failed"
            }
        )

        self.db.add(query_log)
        await self.db.commit()

    async def trigger_n8n_workflow(
        self,
        onboarding_id: UUID,
        language: str,
        architecture: str,
        project_slug: str
    ) -> Dict[str, Any]:
        """
        Trigger N8N workflow to execute Piloter stack discovery

        Returns:
            {
                "workflow_id": str,
                "status": "triggered",
                "estimated_completion": str
            }
        """

        payload = {
            "onboarding_id": str(onboarding_id),
            "language": language,
            "architecture": architecture,
            "project_slug": project_slug,
            "triggered_at": datetime.now(timezone.utc).isoformat()
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload
                )

                if response.status_code in [200, 202]:
                    logger.info("piloter.n8n_triggered",
                               onboarding_id=str(onboarding_id),
                               project_slug=project_slug)
                    return {
                        "workflow_id": response.headers.get("X-Workflow-ID"),
                        "status": "triggered",
                        "estimated_completion": "30-60 seconds"
                    }
                else:
                    raise ValueError(f"N8N webhook failed: {response.status_code}")

        except Exception as e:
            logger.error("piloter.n8n_trigger_error",
                        onboarding_id=str(onboarding_id),
                        error=str(e))
            raise ValueError(f"Failed to trigger N8N workflow: {str(e)}")

    async def get_workflow_status(
        self,
        workflow_id: str
    ) -> Dict[str, Any]:
        """
        Poll N8N workflow status

        Returns:
            {
                "status": "running|completed|failed",
                "result": {...},
                "error": None|str
            }
        """

        try:
            headers = {
                "X-Workflow-ID": workflow_id
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.webhook_url}/status",
                    headers=headers
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "status": data.get("status", "unknown"),
                        "result": data.get("result"),
                        "error": data.get("error")
                    }
                else:
                    raise ValueError(f"Status check failed: {response.status_code}")

        except Exception as e:
            logger.error("piloter.status_check_error",
                        workflow_id=workflow_id,
                        error=str(e))
            return {
                "status": "error",
                "result": None,
                "error": str(e)
            }
