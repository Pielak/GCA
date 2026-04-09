"""
QA Service — Orquestração de execução de testes e gravação de logs.

Responsabilidades:
- Executar testes isolados (subprocess)
- Gravar logs em test_execution_logs (banco) + JSONL (arquivo)
- Consolidar resultados e cobertura por categoria
"""
import asyncio
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models.base import TestArtifact, TestExecutionLog, User, Project

logger = structlog.get_logger(__name__)

LOGS_DIR = Path(os.getenv("TEST_LOGS_DIR", "logs/test_executions"))


class QAService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute_test_plan(
        self,
        project_id: UUID,
        user_id: UUID,
        test_types: Optional[List[str]] = None,
    ) -> dict:
        """Dispara execução de todos os testes de um projeto por categoria."""
        query = select(TestArtifact).where(
            TestArtifact.project_id == project_id,
            TestArtifact.status.in_(["approved", "edited", "pending_review"]),
        )
        if test_types:
            query = query.where(TestArtifact.test_type.in_(test_types))

        result = await self.db.execute(query)
        artifacts = result.scalars().all()

        results = []
        for artifact in artifacts:
            exec_result = await self.execute_single_test(artifact.id, user_id)
            results.append(exec_result)

        passed = sum(1 for r in results if r.get("status") == "passed")
        failed = sum(1 for r in results if r.get("status") == "failed")
        errors = sum(1 for r in results if r.get("status") == "error")

        return {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "results": results,
        }

    async def execute_single_test(self, test_artifact_id: UUID, user_id: UUID) -> dict:
        """Executa um teste individual e grava log em banco + JSONL."""
        artifact = await self.db.get(TestArtifact, test_artifact_id)
        if not artifact:
            return {"error": "Teste não encontrado", "status_code": 404}

        start = datetime.now(timezone.utc)
        exec_result = await self._run_isolated(artifact.content, artifact.test_type)
        end = datetime.now(timezone.utc)
        duration_ms = int((end - start).total_seconds() * 1000)

        # Buscar contexto do projeto para desnormalizar no log
        project = await self.db.get(Project, artifact.project_id)

        # Calcular aderência (passed = 100%, failed = 0%)
        adherence = 100.0 if exec_result["status"] == "passed" else 0.0

        # Gravar log no banco — REGRA: sempre, independente da vontade do usuário
        log_entry = TestExecutionLog(
            test_artifact_id=artifact.id,
            project_id=artifact.project_id,
            executed_at=end,
            executed_by=user_id,
            status=exec_result["status"],
            duration_ms=duration_ms,
            output=exec_result.get("output", ""),
            module_name=artifact.title.split("_")[0] if "_" in artifact.title else artifact.title,
            function_name=artifact.title,
            test_created_by=artifact.created_by,
            test_edited_by=artifact.last_edited_by,
            test_version_at_run=artifact.version,
            # Contexto do projeto (desnormalizado)
            project_code=str(project.id)[:8] if project else None,
            project_name=project.name if project else None,
            project_slug=project.slug if project else None,
            test_type=artifact.test_type,
            adherence_percent=adherence,
        )
        self.db.add(log_entry)
        await self.db.commit()

        # Gravar log em arquivo JSONL
        await self._write_jsonl_log(artifact, log_entry, user_id)

        logger.info(
            "qa.test_executed",
            test_id=str(artifact.id),
            status=exec_result["status"],
            duration_ms=duration_ms,
        )

        return {
            "test_id": str(artifact.id),
            "title": artifact.title,
            "test_type": artifact.test_type,
            "status": exec_result["status"],
            "duration_ms": duration_ms,
            "output": exec_result.get("output", "")[:500],
        }

    async def get_execution_results(self, project_id: UUID) -> List[dict]:
        """Retorna resultados consolidados das execuções mais recentes."""
        result = await self.db.execute(
            select(TestExecutionLog)
            .where(TestExecutionLog.project_id == project_id)
            .order_by(TestExecutionLog.executed_at.desc())
            .limit(100)
        )
        logs = result.scalars().all()
        return [
            {
                "id": str(log.id),
                "test_artifact_id": str(log.test_artifact_id),
                "executed_at": log.executed_at.isoformat() if log.executed_at else None,
                "executed_by": str(log.executed_by),
                "status": log.status,
                "duration_ms": log.duration_ms,
                "module_name": log.module_name,
                "function_name": log.function_name,
                "test_version_at_run": log.test_version_at_run,
                "project_code": log.project_code,
                "project_name": log.project_name,
                "project_slug": log.project_slug,
                "test_type": log.test_type,
                "adherence_percent": log.adherence_percent,
            }
            for log in logs
        ]

    async def get_coverage_by_type(self, project_id: UUID) -> dict:
        """Retorna cobertura por categoria de teste."""
        # Total de testes por tipo
        total_q = await self.db.execute(
            select(TestArtifact.test_type, func.count(TestArtifact.id))
            .where(TestArtifact.project_id == project_id)
            .group_by(TestArtifact.test_type)
        )
        totals = {row[0]: row[1] for row in total_q.all()}

        # Últimas execuções passando por tipo
        passed_q = await self.db.execute(
            select(TestExecutionLog.status, func.count(TestExecutionLog.id))
            .join(TestArtifact, TestExecutionLog.test_artifact_id == TestArtifact.id)
            .where(TestArtifact.project_id == project_id)
            .group_by(TestExecutionLog.status)
        )
        status_counts = {row[0]: row[1] for row in passed_q.all()}

        categories = ["unit", "integration", "e2e", "regression", "load", "security"]
        coverage = {}
        for cat in categories:
            total = totals.get(cat, 0)
            coverage[cat] = {"total": total, "label": cat}

        return {
            "coverage": coverage,
            "summary": {
                "total_tests": sum(totals.values()),
                "total_passed": status_counts.get("passed", 0),
                "total_failed": status_counts.get("failed", 0),
                "total_errors": status_counts.get("error", 0),
            },
        }

    async def get_logs(
        self,
        project_id: UUID,
        test_artifact_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[dict]:
        """Retorna logs de execução paginados."""
        query = (
            select(TestExecutionLog)
            .where(TestExecutionLog.project_id == project_id)
        )
        if test_artifact_id:
            query = query.where(TestExecutionLog.test_artifact_id == test_artifact_id)
        query = query.order_by(TestExecutionLog.executed_at.desc()).limit(limit).offset(offset)

        result = await self.db.execute(query)
        logs = result.scalars().all()
        return [
            {
                "id": str(log.id),
                "test_artifact_id": str(log.test_artifact_id),
                "executed_at": log.executed_at.isoformat() if log.executed_at else None,
                "executed_by": str(log.executed_by),
                "status": log.status,
                "duration_ms": log.duration_ms,
                "output": log.output,
                "module_name": log.module_name,
                "function_name": log.function_name,
                "test_version_at_run": log.test_version_at_run,
                "project_code": log.project_code,
                "project_name": log.project_name,
                "project_slug": log.project_slug,
                "test_type": log.test_type,
                "adherence_percent": log.adherence_percent,
            }
            for log in logs
        ]

    async def _run_isolated(self, content: str, test_type: str) -> dict:
        """Executa código de teste em subprocess isolado."""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, prefix=f"gca_test_{test_type}_"
            ) as f:
                f.write(content)
                f.flush()
                temp_path = f.name

            proc = await asyncio.create_subprocess_exec(
                "python", "-m", "pytest", temp_path, "-v", "--tb=short", "--no-header",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            output = stdout.decode("utf-8", errors="replace") + stderr.decode("utf-8", errors="replace")
            status = "passed" if proc.returncode == 0 else "failed"

            return {"status": status, "output": output}

        except asyncio.TimeoutError:
            return {"status": "error", "output": "Timeout: execução excedeu 60 segundos"}
        except Exception as e:
            return {"status": "error", "output": str(e)}
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    async def _write_jsonl_log(
        self,
        artifact: TestArtifact,
        log: TestExecutionLog,
        user_id: UUID,
    ) -> None:
        """Grava log em arquivo JSONL diário."""
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = LOGS_DIR / f"{today}.jsonl"

        # Buscar nomes de usuários
        executor = await self.db.get(User, user_id)
        creator = await self.db.get(User, artifact.created_by)
        editor = await self.db.get(User, artifact.last_edited_by) if artifact.last_edited_by else None

        entry = {
            "timestamp": log.executed_at.isoformat() if log.executed_at else None,
            "test_id": str(artifact.id),
            "test_title": artifact.title,
            "test_type": artifact.test_type,
            "module_name": log.module_name,
            "function_name": log.function_name,
            "status": log.status,
            "duration_ms": log.duration_ms,
            "executed_by": {
                "id": str(user_id),
                "name": executor.full_name if executor else "unknown",
            },
            "test_created_by": {
                "id": str(artifact.created_by),
                "name": creator.full_name if creator else "unknown",
            },
            "test_edited_by": {
                "id": str(artifact.last_edited_by),
                "name": editor.full_name if editor else None,
            } if artifact.last_edited_by else None,
            "test_version": artifact.version,
            "project_id": str(artifact.project_id),
            "project_code": log.project_code,
            "project_name": log.project_name,
            "project_slug": log.project_slug,
            "adherence_percent": log.adherence_percent,
            "output_summary": (log.output or "")[:200],
        }

        with open(log_file, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
