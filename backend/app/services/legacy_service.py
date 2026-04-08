"""
Legacy Service — Análise de codebase legado existente.
Ingere código existente (zip ou URL de repositório) e analisa:
debt técnico, padrões, conflitos com OCG, módulos implementados.
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4, UUID

from sqlalchemy.ext.asyncio import AsyncSession
import structlog

logger = structlog.get_logger(__name__)


class LegacyService:
    """Serviço de análise de codebase legado."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def start_analysis(
        self,
        project_id: UUID,
        source_type: str,
        source: str,
        branch: str = "main",
    ) -> dict:
        """
        Inicia análise assíncrona de codebase legado.

        Args:
            project_id: ID do projeto
            source_type: 'zip' ou 'git_url'
            source: Arquivo ou URL do repositório
            branch: Branch para analisar (padrão: main)

        Returns:
            dict com job_id e status
        """
        if source_type not in ("zip", "git_url"):
            return {"error": "source_type deve ser 'zip' ou 'git_url'", "status": "failed"}

        job_id = str(uuid4())

        logger.info(
            "legacy.analise_iniciada",
            project_id=str(project_id),
            source_type=source_type,
            job_id=job_id,
        )

        # Em produção, dispararia job assíncrono (Celery/asyncio task)
        return {
            "job_id": job_id,
            "status": "analyzing",
            "source_type": source_type,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_analysis_status(
        self,
        project_id: UUID,
        job_id: str,
    ) -> dict:
        """Retorna status de um job de análise legado."""
        # Stub — em produção, consultaria fila/banco
        return {
            "job_id": job_id,
            "status": "pending",
            "progress_percent": 0,
            "current_step": "Aguardando processamento",
        }

    async def get_analysis_result(
        self,
        project_id: UUID,
        job_id: str,
    ) -> Optional[dict]:
        """Retorna resultado de análise legado completada."""
        # Stub — em produção, buscaria resultado processado
        return None
