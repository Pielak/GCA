"""
AI Billing Service — Registra custo de cada chamada LLM por projeto.
"""
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import structlog

from app.models.base import AIUsageLog

logger = structlog.get_logger(__name__)

AI_PRICING = {
    "deepseek": {"deepseek-chat": {"input": 0.14, "output": 0.28}},
    "anthropic": {
        "claude-opus-4-6": {"input": 15.0, "output": 75.0},
        "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    },
    "openai": {"gpt-4o": {"input": 2.50, "output": 10.0}},
    "grok": {"grok-3-mini": {"input": 0.30, "output": 0.50}},
    "gemini": {"gemini-2.0-pro": {"input": 1.25, "output": 5.0}},
}


class AIBillingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_usage(
        self,
        project_id: Optional[UUID],
        provider: str,
        model: str,
        operation: str,
        tokens_input: int,
        tokens_output: int,
        actor_id: Optional[UUID] = None,
        metadata: Optional[dict] = None,
    ) -> AIUsageLog:
        cost = self._calculate_cost(provider, model, tokens_input, tokens_output)
        entry = AIUsageLog(
            project_id=project_id,
            provider=provider,
            model=model,
            operation=operation,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=cost,
            actor_id=actor_id,
            metadata_json=json.dumps(metadata, default=str) if metadata else None,
        )
        self.db.add(entry)
        await self.db.flush()
        logger.info("billing.usage_logged",
                    project_id=str(project_id) if project_id else "global",
                    provider=provider, operation=operation,
                    tokens=tokens_input + tokens_output, cost_usd=f"{cost:.6f}")
        return entry

    def _calculate_cost(self, provider: str, model: str, tokens_in: int, tokens_out: int) -> float:
        prices = AI_PRICING.get(provider, {}).get(model)
        if not prices:
            return (tokens_in / 1_000_000 * 1.0) + (tokens_out / 1_000_000 * 3.0)
        return (tokens_in / 1_000_000 * prices["input"]) + (tokens_out / 1_000_000 * prices["output"])

    async def get_project_summary(self, project_id: UUID) -> dict:
        result = await self.db.execute(
            select(
                func.sum(AIUsageLog.cost_usd).label("total_cost"),
                func.sum(AIUsageLog.tokens_input + AIUsageLog.tokens_output).label("total_tokens"),
                func.count(AIUsageLog.id).label("total_calls"),
            ).where(AIUsageLog.project_id == project_id)
        )
        row = result.first()
        op_result = await self.db.execute(
            select(
                AIUsageLog.operation,
                func.sum(AIUsageLog.cost_usd).label("cost"),
                func.sum(AIUsageLog.tokens_input + AIUsageLog.tokens_output).label("tokens"),
                func.count(AIUsageLog.id).label("calls"),
            ).where(AIUsageLog.project_id == project_id).group_by(AIUsageLog.operation)
        )
        prov_result = await self.db.execute(
            select(
                AIUsageLog.provider,
                func.sum(AIUsageLog.cost_usd).label("cost"),
                func.count(AIUsageLog.id).label("calls"),
            ).where(AIUsageLog.project_id == project_id).group_by(AIUsageLog.provider)
        )
        return {
            "total_cost_usd": float(row.total_cost or 0),
            "total_tokens": int(row.total_tokens or 0),
            "total_calls": int(row.total_calls or 0),
            "by_operation": [
                {"operation": r.operation, "cost_usd": float(r.cost or 0), "tokens": int(r.tokens or 0), "calls": int(r.calls or 0)}
                for r in op_result
            ],
            "by_provider": [
                {"provider": r.provider, "cost_usd": float(r.cost or 0), "calls": int(r.calls or 0)}
                for r in prov_result
            ],
        }

    async def get_project_detail(self, project_id: UUID, limit: int = 50) -> list[dict]:
        result = await self.db.execute(
            select(AIUsageLog).where(AIUsageLog.project_id == project_id)
            .order_by(AIUsageLog.created_at.desc()).limit(limit)
        )
        return [
            {
                "id": str(e.id), "provider": e.provider, "model": e.model,
                "operation": e.operation, "tokens_input": e.tokens_input,
                "tokens_output": e.tokens_output, "cost_usd": float(e.cost_usd),
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in result.scalars().all()
        ]
