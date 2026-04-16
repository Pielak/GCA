"""Verifiers determinísticos para Definition of Done (Fase A.3).

Cada verifier checa a presença de um tipo específico de entregável
(``kind``) usando fontes deterministas (Git, DB, OCG, LiveDocs). NÃO usa
LLM — resultado é reproduzível e auditável.

Cada verifier devolve um ``VerificationResult`` com:
    - status: 'verified' | 'present' | 'missing' | 'manual_only' | 'error'
    - evidence_type: 'file' | 'git_commit' | 'db_query' | 'ocg_field' | None
    - evidence_ref: caminho/uuid/url da evidência
    - method: nome do verifier (para audit log)
    - notes: detalhes opcionais

Dispatcher: ``verify_kind(kind, project_id, db)`` roteia para o verifier
correto. Kinds desconhecidos ou marcados como manual retornam
``status='manual_only'`` (não falha — só sinaliza que precisa atestação).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class VerificationResult:
    """Resultado de uma verificação. Imutável; serializável para o registry."""
    status: str
    method: str
    evidence_type: Optional[str] = None
    evidence_ref: Optional[str] = None
    notes: Optional[str] = None


# ──────────────────────────── Helpers Git ────────────────────────────

async def _git_file_exists(project_id: UUID, db: AsyncSession, *paths: str) -> Optional[str]:
    """True (path) se algum dos paths existe no repo Git do projeto.

    Usa GitService.get_file_content — retorna None se o arquivo não
    existir. Catch genérico em exceptions: se o repo nem está configurado
    ou GitHub fora do ar, retornamos None (=não encontrado), não exception.
    """
    try:
        from app.services.git_service import GitService
        gs = GitService(db)
        for path in paths:
            try:
                content = await gs.get_file_content(project_id, path)
                if content is not None:
                    return path
            except Exception:  # noqa: BLE001
                continue
        return None
    except Exception:  # noqa: BLE001
        return None


async def _git_dir_count(project_id: UUID, db: AsyncSession, dir_path: str) -> int:
    """Conta arquivos no diretório (não-recursivo) ou retorna 0."""
    try:
        from app.services.git_service import GitService
        gs = GitService(db)
        items = await gs.list_files(project_id, dir_path)
        if not items:
            return 0
        return sum(1 for it in items if it.get("type") == "file")
    except Exception:  # noqa: BLE001
        return 0


# ──────────────────────────── Verifiers por kind ─────────────────────

async def _verify_dockerfile(project_id: UUID, db: AsyncSession) -> VerificationResult:
    found = await _git_file_exists(project_id, db, "Dockerfile", "docker/Dockerfile", ".docker/Dockerfile")
    if found:
        return VerificationResult(
            status="verified",
            method="git_file_exists",
            evidence_type="file",
            evidence_ref=found,
        )
    return VerificationResult(status="missing", method="git_file_exists")


async def _verify_openapi(project_id: UUID, db: AsyncSession) -> VerificationResult:
    found = await _git_file_exists(
        project_id, db,
        "openapi.yaml", "openapi.json",
        "docs/openapi.yaml", "docs/openapi.json",
        "api/openapi.yaml",
    )
    if found:
        return VerificationResult(
            status="verified",
            method="git_file_exists",
            evidence_type="file",
            evidence_ref=found,
        )
    # Fallback: FastAPI gera /openapi.json em runtime — se houver um app
    # FastAPI rodando, considera "present" (não verified — não temos como
    # provar sem subir o app).
    found_app = await _git_file_exists(project_id, db, "app/main.py", "src/main.py", "main.py")
    if found_app:
        return VerificationResult(
            status="present",
            method="git_file_exists+fastapi_inferred",
            evidence_type="file",
            evidence_ref=found_app,
            notes="FastAPI app detectado — assume /openapi.json em runtime",
        )
    return VerificationResult(status="missing", method="git_file_exists")


async def _verify_manifests(project_id: UUID, db: AsyncSession) -> VerificationResult:
    found = await _git_file_exists(
        project_id, db,
        "pyproject.toml", "package.json",
        "backend/pyproject.toml", "frontend/package.json",
    )
    if found:
        return VerificationResult(
            status="verified",
            method="git_file_exists",
            evidence_type="file",
            evidence_ref=found,
        )
    return VerificationResult(status="missing", method="git_file_exists")


async def _verify_database_design(project_id: UUID, db: AsyncSession) -> VerificationResult:
    """DDL = arquivos de migração ou schema SQL."""
    count = await _git_dir_count(project_id, db, "migrations")
    if count > 0:
        return VerificationResult(
            status="verified",
            method="git_dir_count",
            evidence_type="file",
            evidence_ref=f"migrations/ ({count} arquivos)",
        )
    count2 = await _git_dir_count(project_id, db, "backend/migrations")
    if count2 > 0:
        return VerificationResult(
            status="verified",
            method="git_dir_count",
            evidence_type="file",
            evidence_ref=f"backend/migrations/ ({count2} arquivos)",
        )
    found = await _git_file_exists(project_id, db, "schema.sql", "db/schema.sql")
    if found:
        return VerificationResult(
            status="verified",
            method="git_file_exists",
            evidence_type="file",
            evidence_ref=found,
        )
    return VerificationResult(status="missing", method="git_dir_count")


async def _verify_adr(project_id: UUID, db: AsyncSession) -> VerificationResult:
    count = await _git_dir_count(project_id, db, "docs/adr")
    if count > 0:
        return VerificationResult(
            status="verified",
            method="git_dir_count",
            evidence_type="file",
            evidence_ref=f"docs/adr/ ({count} ADRs)",
        )
    return VerificationResult(status="missing", method="git_dir_count")


async def _verify_sbom(project_id: UUID, db: AsyncSession) -> VerificationResult:
    found = await _git_file_exists(
        project_id, db,
        "sbom.json", "sbom.xml", "docs/sbom.json", "bom.json",
    )
    if found:
        return VerificationResult(
            status="verified",
            method="git_file_exists",
            evidence_type="file",
            evidence_ref=found,
        )
    return VerificationResult(status="missing", method="git_file_exists")


async def _verify_ci_pipeline(project_id: UUID, db: AsyncSession) -> VerificationResult:
    count_gh = await _git_dir_count(project_id, db, ".github/workflows")
    if count_gh > 0:
        return VerificationResult(
            status="verified",
            method="git_dir_count",
            evidence_type="file",
            evidence_ref=f".github/workflows/ ({count_gh} jobs)",
        )
    found = await _git_file_exists(project_id, db, ".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml")
    if found:
        return VerificationResult(
            status="verified",
            method="git_file_exists",
            evidence_type="file",
            evidence_ref=found,
        )
    return VerificationResult(status="missing", method="git_dir_count")


async def _verify_compliance_checklist(project_id: UUID, db: AsyncSession) -> VerificationResult:
    """% de items resolvidos no OCG.COMPLIANCE_CHECKLIST."""
    from app.models.base import OCG
    result = await db.execute(
        select(OCG).where(OCG.project_id == project_id).order_by(OCG.version.desc()).limit(1)
    )
    ocg = result.scalar_one_or_none()
    if not ocg or not ocg.ocg_data:
        return VerificationResult(status="missing", method="ocg_field_count", notes="OCG não encontrado")
    try:
        ocg_data = json.loads(ocg.ocg_data) if isinstance(ocg.ocg_data, str) else ocg.ocg_data
        items = ocg_data.get("COMPLIANCE_CHECKLIST", []) or []
        total = len(items)
        if total == 0:
            return VerificationResult(status="missing", method="ocg_field_count", notes="checklist vazio")
        resolved = sum(1 for i in items if str(i.get("status", "")).upper() != "PENDENTE")
        if resolved == total:
            return VerificationResult(
                status="verified", method="ocg_field_count",
                evidence_type="ocg_field",
                evidence_ref=f"COMPLIANCE_CHECKLIST: {resolved}/{total} resolvidos",
            )
        return VerificationResult(
            status="present", method="ocg_field_count",
            evidence_type="ocg_field",
            evidence_ref=f"COMPLIANCE_CHECKLIST: {resolved}/{total} resolvidos",
            notes=f"{total - resolved} pendentes",
        )
    except (json.JSONDecodeError, TypeError):
        return VerificationResult(status="error", method="ocg_field_count", notes="ocg_data corrompido")


async def _verify_test_plan(project_id: UUID, db: AsyncSession) -> VerificationResult:
    """Plano de testes: prioriza doc no Git, fallback em TestArtifact rows.

    O generator de test_plan produz docs/test_plan.md a partir de
    OCG.TESTING_REQUIREMENTS. Verifier deve detectar tanto o doc quanto
    a existência de execução real (TestArtifact)."""
    # Primeiro: doc gerado automaticamente
    found = await _git_file_exists(
        project_id, db,
        "docs/test_plan.md", "docs/TEST_PLAN.md", "TEST_PLAN.md", "test_plan.md",
    )
    if found:
        return VerificationResult(
            status="verified", method="git_file_exists",
            evidence_type="file", evidence_ref=found,
        )

    # Fallback: TestArtifact rows (execução real existente)
    from app.models.base import TestArtifact
    result = await db.execute(
        select(func.count(TestArtifact.id)).where(TestArtifact.project_id == project_id)
    )
    count = result.scalar() or 0
    if count > 0:
        return VerificationResult(
            status="verified", method="qa_artifacts_count",
            evidence_type="db_query",
            evidence_ref=f"test_artifacts: {count} rows",
        )
    return VerificationResult(status="missing", method="git_file_exists+qa_artifacts_count")


async def _verify_backlog(project_id: UUID, db: AsyncSession) -> VerificationResult:
    from app.models.base import BacklogItem
    result = await db.execute(
        select(func.count(BacklogItem.id)).where(BacklogItem.project_id == project_id)
    )
    count = result.scalar() or 0
    if count > 0:
        return VerificationResult(
            status="verified", method="db_count",
            evidence_type="db_query",
            evidence_ref=f"backlog_items: {count} rows",
        )
    return VerificationResult(status="missing", method="db_count")


async def _verify_observability_dashboard(project_id: UUID, db: AsyncSession) -> VerificationResult:
    """Procura config de observability no repo."""
    found = await _git_file_exists(
        project_id, db,
        "docker-compose.observability.yml",
        "infra/grafana", "infra/prometheus.yml",
        "observability/grafana", "monitoring/grafana",
    )
    if found:
        return VerificationResult(
            status="verified", method="git_file_exists",
            evidence_type="file", evidence_ref=found,
        )
    return VerificationResult(status="missing", method="git_file_exists")


async def _verify_dev_environment(project_id: UUID, db: AsyncSession) -> VerificationResult:
    """docker-compose ou devcontainer count."""
    found = await _git_file_exists(
        project_id, db,
        "docker-compose.yml", "docker-compose.yaml",
        ".devcontainer/devcontainer.json",
    )
    if found:
        return VerificationResult(
            status="verified", method="git_file_exists",
            evidence_type="file", evidence_ref=found,
        )
    return VerificationResult(status="missing", method="git_file_exists")


async def _verify_manual_only(project_id: UUID, db: AsyncSession) -> VerificationResult:
    """Para kinds que SEMPRE precisam atestação humana (business_case, etc.)."""
    return VerificationResult(
        status="manual_only", method="manual_only",
        notes="Requer atestação manual pelo GP",
    )


# ──────────────────────────── Dispatcher ─────────────────────────────

_VERIFIERS: Dict[str, Callable[..., Any]] = {
    "dockerfile": _verify_dockerfile,
    "openapi": _verify_openapi,
    "manifests": _verify_manifests,
    "database_design": _verify_database_design,
    "adr": _verify_adr,
    "sbom": _verify_sbom,
    "ci_pipeline": _verify_ci_pipeline,
    "compliance_checklist": _verify_compliance_checklist,
    "compliance_doc": _verify_compliance_checklist,  # mesmo verifier por enquanto
    "test_plan": _verify_test_plan,
    "test_implementation": _verify_test_plan,
    "backlog": _verify_backlog,
    "observability_dashboard": _verify_observability_dashboard,
    "dev_environment": _verify_dev_environment,
    # Manuais
    "business_case": _verify_manual_only,
    "justification_record": _verify_manual_only,
    "architecture_doc": _verify_manual_only,  # parcial via LiveDocs, mas precisa atestar
    "architecture_diagram": _verify_manual_only,
    "user_manual": _verify_manual_only,
    "data_retention_policy": _verify_manual_only,
    "dependency_policy": _verify_manual_only,
    "code_repository": _verify_manual_only,  # presença implícita do PAT
    "logging_setup": _verify_manual_only,
    "roadmap": _verify_manual_only,
}


async def verify_kind(
    kind: str,
    project_id: UUID,
    db: AsyncSession,
) -> VerificationResult:
    """Dispatcher: roteia kind para o verifier apropriado.

    Kinds desconhecidos retornam ``status='manual_only'`` — não falha,
    só sinaliza que o registry precisa atestação humana.
    """
    handler = _VERIFIERS.get(kind, _verify_manual_only)
    try:
        return await handler(project_id, db)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "deliverable_verifier.error",
            kind=kind,
            project_id=str(project_id),
            error=str(exc),
        )
        return VerificationResult(
            status="error",
            method=f"verifier:{kind}",
            notes=f"erro durante verificação: {type(exc).__name__}",
        )
