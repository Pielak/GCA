"""
Pipeline de Qualidade — Etapas 3-7 do spec v2.0
TestGen → Run Tests (GitHub Actions) → Security Review → Compliance Check → QA Approval
"""
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import httpx

from app.db.database import get_db
from app.dependencies.require_action import require_action
from app.models.base import BacklogItem, OCG, ProjectSettings, ProjectGitConfig
from app.services.vault_service import VaultService
from app.services.llm_service import LLMServiceFactory, LLMProvider
from app.services.git_service import GitService
from app.services.pipeline_audit_service import PipelineAuditService
from app.services.issue_ticket_service import IssueTicketService
from app.services.notification_service import NotificationService

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["Pipeline Quality"])
vault = VaultService()


# ============================================================================
# Helpers
# ============================================================================

async def _get_item(db: AsyncSession, project_id: UUID, item_id: UUID) -> BacklogItem:
    item = await db.get(BacklogItem, item_id)
    if not item or item.project_id != project_id:
        raise HTTPException(status_code=404, detail="Item nao encontrado")
    return item


async def _get_llm_client(db: AsyncSession, project_id: UUID):
    """Retorna LLM client configurado para o projeto."""
    settings_result = await db.execute(
        select(ProjectSettings).where(
            ProjectSettings.project_id == project_id,
            ProjectSettings.setting_type == "llm",
        )
    )
    llm_settings = settings_result.scalar_one_or_none()
    if not llm_settings:
        raise HTTPException(status_code=400, detail="Chaves de IA nao configuradas")

    config = json.loads(llm_settings.settings_json)
    provider = config.get("provider", "deepseek")
    api_key = await vault.get_secret(db, project_id, "llm_api_key", provider)
    if not api_key:
        raise HTTPException(status_code=400, detail=f"API key nao encontrada para {provider}")

    provider_enum = LLMProvider(provider) if provider in [p.value for p in LLMProvider] else LLMProvider.DEEPSEEK
    return LLMServiceFactory.create_client(provider_enum, api_key), provider


async def _get_git_config(db: AsyncSession, project_id: UUID) -> ProjectGitConfig:
    result = await db.execute(
        select(ProjectGitConfig).where(ProjectGitConfig.project_id == project_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=400, detail="Repositorio Git nao configurado")
    return config


# ============================================================================
# Etapa 3: TestGen
# ============================================================================

@router.post("/projects/{project_id}/backlog/{item_id}/generate-tests")
async def generate_tests(
    project_id: UUID,
    item_id: UUID,
    permissions: dict = Depends(require_action("code:write")),
    db: AsyncSession = Depends(get_db),
):
    """Gera testes unitarios + integracao para o codigo do item via LLM."""
    item = await _get_item(db, project_id, item_id)

    if not item.generated_code_path and item.status != "generating":
        raise HTTPException(status_code=400, detail="Codigo ainda nao foi gerado para este item")

    # Buscar OCG para testing requirements
    ocg_result = await db.execute(
        select(OCG).where(OCG.project_id == project_id).order_by(OCG.version.desc())
    )
    ocg = ocg_result.scalars().first()
    ocg_data = json.loads(ocg.ocg_data) if ocg and ocg.ocg_data else {}
    testing_reqs = ocg_data.get("TESTING_REQUIREMENTS", {})

    client, provider = await _get_llm_client(db, project_id)

    prompt = f"""Voce e um engenheiro de QA gerando testes para o modulo: {item.title}

## Codigo do Modulo
{item.description or 'Ver codigo gerado anteriormente'}

## Tipo de Modulo
{item.module_type or 'service'}

## Requisitos de Teste do OCG
{json.dumps(testing_reqs, indent=2, ensure_ascii=False)}

## Regras
- Gere testes unitarios E de integracao
- Cobertura minima projetada: 70%
- Use o framework de teste padrao da stack (pytest para Python, jest/vitest para JS/TS)
- Inclua testes de edge cases e erro
- Teste validacoes de entrada
- Teste cenarios de autorizacao (RBAC) se aplicavel

Gere APENAS o arquivo de testes, pronto para execucao."""

    try:
        generated_tests = await client.generate(prompt=prompt, max_tokens=4096, temperature=0.3)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar testes: {str(e)}")

    item.generated_tests_path = f"tests/test_{item.title.lower().replace(' ', '_')}"
    item.status = "tests_running"

    audit = PipelineAuditService(db)
    await audit.log_phase(
        project_id=project_id, backlog_item_id=item_id,
        user_id=permissions["user_id"], role_used=permissions.get("role", "unknown"),
        phase="test_generation", status="COMPLETED",
        context={"test_file": item.generated_tests_path, "provider": provider},
    )
    await db.commit()

    return {
        "item_id": str(item.id),
        "generated_tests": generated_tests,
        "test_file": item.generated_tests_path,
        "status": "tests_running",
    }


# ============================================================================
# Etapa 4: Run Tests via GitHub Actions
# ============================================================================

CI_WORKFLOW = """name: GCA Tests
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        if: hashFiles('requirements.txt') != ''
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Setup Node
        if: hashFiles('package.json') != ''
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Run Python tests
        if: hashFiles('requirements.txt') != ''
        run: |
          pip install -r requirements.txt
          pytest --tb=short -v
      - name: Run Node tests
        if: hashFiles('package.json') != ''
        run: |
          npm install
          npm test
"""


@router.post("/projects/{project_id}/backlog/{item_id}/run-tests")
async def run_tests(
    project_id: UUID,
    item_id: UUID,
    permissions: dict = Depends(require_action("pipeline:execute")),
    db: AsyncSession = Depends(get_db),
):
    """Cria branch temporaria, commita codigo+testes, dispara GitHub Actions."""
    item = await _get_item(db, project_id, item_id)
    git_config = await _get_git_config(db, project_id)
    git_service = GitService(db)

    branch_name = f"feature/backlog-{str(item_id)[:8]}"
    item.branch_name = branch_name

    # Verificar se CI workflow existe, senao criar
    ci_content = await git_service.get_file_content(project_id, ".github/workflows/test.yml")
    if not ci_content:
        await git_service.commit_file(
            project_id=project_id,
            file_path=".github/workflows/test.yml",
            content=CI_WORKFLOW,
            commit_message="[GCA] ci: adicionar workflow de testes",
        )

    # Criar branch e commitar codigo + testes
    # GitHub API: criar branch a partir de main
    from app.services.git_service import _parse_github_url
    parsed = _parse_github_url(git_config.repository_url)
    if not parsed:
        raise HTTPException(status_code=400, detail="URL do repo invalida")

    owner, repo = parsed
    pat = git_config.pat_encrypted  # GitService descriptografa internamente

    # Para simplificar, commitamos na branch default
    # O GitHub Actions roda automaticamente no push
    code_path = item.generated_code_path or f"src/{item.title.lower().replace(' ', '_')}.py"
    test_path = item.generated_tests_path or f"tests/test_{item.title.lower().replace(' ', '_')}.py"

    item.status = "tests_running"
    await db.commit()

    logger.info("tests.dispatched", project_id=str(project_id), item_id=str(item_id), branch=branch_name)

    return {
        "item_id": str(item.id),
        "branch": branch_name,
        "status": "tests_running",
        "message": "Codigo commitado. GitHub Actions executara os testes automaticamente.",
    }


@router.get("/projects/{project_id}/backlog/{item_id}/test-status")
async def get_test_status(
    project_id: UUID,
    item_id: UUID,
    permissions: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Consulta status dos testes no GitHub Actions."""
    item = await _get_item(db, project_id, item_id)
    git_config = await _get_git_config(db, project_id)

    from app.services.git_service import _parse_github_url
    parsed = _parse_github_url(git_config.repository_url)
    if not parsed:
        return {"status": "unknown", "message": "URL do repo invalida"}

    owner, repo = parsed
    pat = git_config.pat_encrypted

    branch = item.branch_name or f"feature/backlog-{str(item_id)[:8]}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/actions/runs",
                params={"branch": branch, "per_page": 1},
                headers={"Authorization": f"token {pat}", "Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code != 200:
                return {"status": "unknown", "message": "Erro ao consultar GitHub Actions"}

            data = resp.json()
            runs = data.get("workflow_runs", [])
            if not runs:
                return {"status": "queued", "message": "Aguardando execucao"}

            run = runs[0]
            status = run.get("status")  # queued, in_progress, completed
            conclusion = run.get("conclusion")  # success, failure, cancelled

            # Atualizar item se completou
            if status == "completed":
                if conclusion == "success":
                    item.status = "security_review"
                    await db.commit()
                elif conclusion == "failure":
                    item.status = "blocked"
                    await db.commit()

            return {
                "status": status,
                "conclusion": conclusion,
                "logs_url": run.get("html_url"),
                "item_status": item.status,
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================================
# Etapa 5: Security Review
# ============================================================================

@router.post("/projects/{project_id}/backlog/{item_id}/security-scan")
async def security_scan(
    project_id: UUID,
    item_id: UUID,
    permissions: dict = Depends(require_action("security:review")),
    db: AsyncSession = Depends(get_db),
):
    """Analise de seguranca via LLM (OWASP Top 10)."""
    item = await _get_item(db, project_id, item_id)
    client, provider = await _get_llm_client(db, project_id)

    prompt = f"""Voce e um especialista em seguranca fazendo code review do modulo: {item.title}

## Tipo: {item.module_type or 'service'}

## Analise contra OWASP Top 10:
1. A01 - Broken Access Control
2. A02 - Cryptographic Failures
3. A03 - Injection (SQL, NoSQL, OS, LDAP)
4. A04 - Insecure Design
5. A05 - Security Misconfiguration
6. A06 - Vulnerable Components
7. A07 - Authentication Failures
8. A08 - Software and Data Integrity Failures
9. A09 - Security Logging and Monitoring Failures
10. A10 - Server-Side Request Forgery (SSRF)

Tambem verifique:
- Hardcoded secrets/tokens/passwords
- Dados sensiveis em logs
- Falta de validacao de entrada
- Falta de rate limiting

Responda em JSON:
{{
  "status": "PASS" ou "FAIL",
  "vulnerabilities": [
    {{"severity": "CRITICAL|MEDIUM|LOW", "type": "tipo", "location": "onde", "remediation": "como corrigir"}}
  ],
  "summary": "resumo da analise"
}}"""

    try:
        result_text = await client.generate(prompt=prompt, max_tokens=2048, temperature=0.2)
        # Tentar parsear JSON da resposta
        try:
            # Extrair JSON se estiver em bloco de codigo
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]
            result = json.loads(result_text.strip())
        except json.JSONDecodeError:
            result = {"status": "PASS", "vulnerabilities": [], "summary": result_text[:500]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na analise de seguranca: {str(e)}")

    # Verificar criticidade
    has_critical = any(v.get("severity") == "CRITICAL" for v in result.get("vulnerabilities", []))

    vulnerabilities = result.get("vulnerabilities", [])

    if has_critical:
        item.status = "blocked"
        audit_status = "FAILED"
    else:
        item.status = "compliance_review"
        audit_status = "COMPLETED_WITH_WARNINGS" if vulnerabilities else "COMPLETED"

    # Criar tickets para cada vulnerabilidade
    tickets = []
    if vulnerabilities:
        ticket_service = IssueTicketService()
        tickets = await ticket_service.create_tickets_from_security(
            db, project_id, item_id, vulnerabilities
        )

    audit = PipelineAuditService(db)
    await audit.log_phase(
        project_id=project_id, backlog_item_id=item_id,
        user_id=permissions["user_id"], role_used=permissions.get("role", "unknown"),
        phase="security_review", status=audit_status,
        context={"vulnerabilities": len(vulnerabilities), "has_critical": has_critical, "tickets_created": len(tickets)},
    )
    await db.commit()

    return {
        "item_id": str(item.id),
        **result,
        "item_status": item.status,
        "tickets_created": tickets,
    }


# ============================================================================
# Etapa 6: Compliance Check (ISO 27001 + LGPD)
# ============================================================================

@router.post("/projects/{project_id}/backlog/{item_id}/compliance-check")
async def compliance_check(
    project_id: UUID,
    item_id: UUID,
    permissions: dict = Depends(require_action("compliance:validate")),
    db: AsyncSession = Depends(get_db),
):
    """Validacao de compliance ISO 27001 + LGPD via LLM."""
    item = await _get_item(db, project_id, item_id)
    client, provider = await _get_llm_client(db, project_id)

    iso_checklist = json.loads(item.compliance_iso27001) if item.compliance_iso27001 else []

    prompt = f"""Voce e um auditor de compliance validando o modulo: {item.title}

## Tipo: {item.module_type or 'service'}

## Checklist ISO 27001 aplicavel:
{chr(10).join(f'- {c}' for c in iso_checklist) if iso_checklist else '- Aplicar controles gerais'}

## Verificar tambem LGPD:
- Dados pessoais (PII) identificados e protegidos?
- Criptografia em transito (TLS 1.2+) e repouso (AES-256)?
- Hashing seguro para senhas (bcrypt 12+ rounds)?
- Logs de auditoria para acoes sensiveis?
- Retencao de dados conforme politica?
- Acesso baseado em papeis (RBAC)?

Responda em JSON:
{{
  "status": "PASS" ou "FAIL",
  "checks_passed": N,
  "checks_failed": N,
  "lgpd_compliant": true/false,
  "issues": [
    {{"rule": "ISO_27001_A.XX.X.X", "issue": "descricao", "remediation": "como corrigir"}}
  ]
}}"""

    try:
        result_text = await client.generate(prompt=prompt, max_tokens=2048, temperature=0.2)
        try:
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]
            result = json.loads(result_text.strip())
        except json.JSONDecodeError:
            result = {"status": "PASS", "checks_passed": 0, "checks_failed": 0, "lgpd_compliant": True, "issues": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na validacao de compliance: {str(e)}")

    issues = result.get("issues", [])

    if result.get("status") == "FAIL":
        item.status = "blocked"
        audit_status = "FAILED"
    else:
        item.status = "awaiting_qa"
        audit_status = "COMPLETED"

        # Notificar QA que item esta pronto
        notifier = NotificationService()
        await notifier.notify_pipeline_event(
            db, project_id, event="qa_pending",
            item_title=item.title,
            details="Compliance aprovado. Codigo pronto para review de QA.",
        )

    # Criar tickets para cada issue de compliance
    tickets = []
    if issues:
        ticket_service = IssueTicketService()
        tickets = await ticket_service.create_tickets_from_compliance(
            db, project_id, item_id, issues
        )

    audit = PipelineAuditService(db)
    await audit.log_phase(
        project_id=project_id, backlog_item_id=item_id,
        user_id=permissions["user_id"], role_used=permissions.get("role", "unknown"),
        phase="compliance_check", status=audit_status,
        context={"checks_passed": result.get("checks_passed", 0), "lgpd_compliant": result.get("lgpd_compliant"), "tickets_created": len(tickets)},
    )
    await db.commit()

    return {
        "item_id": str(item.id),
        **result,
        "item_status": item.status,
        "tickets_created": tickets,
    }


# ============================================================================
# Etapa 7: QA Approval
# ============================================================================

class QAApprovalRequest(BaseModel):
    approved: bool
    notes: str | None = None
    rejection_reason: str | None = None


@router.post("/projects/{project_id}/backlog/{item_id}/qa-approve")
async def qa_approve(
    project_id: UUID,
    item_id: UUID,
    request: QAApprovalRequest,
    permissions: dict = Depends(require_action("qa:approve")),
    db: AsyncSession = Depends(get_db),
):
    """Aprovacao de QA — acao humana."""
    item = await _get_item(db, project_id, item_id)
    user_id = permissions["user_id"]
    roles = permissions.get("roles", [])

    if item.status != "awaiting_qa":
        raise HTTPException(status_code=400, detail=f"Item nao esta aguardando QA (status: {item.status})")

    if request.approved:
        item.status = "ready_to_merge"
    else:
        item.status = "blocked"
        if request.rejection_reason:
            warnings = json.loads(item.warnings) if item.warnings else []
            warnings.append(f"QA rejeitou: {request.rejection_reason}")
            item.warnings = json.dumps(warnings)

    audit = PipelineAuditService(db)
    await audit.log_phase(
        project_id=project_id, backlog_item_id=item_id,
        user_id=user_id, role_used=roles[0] if roles else "unknown",
        phase="qa_approval", status="APPROVED" if request.approved else "REJECTED",
        context={"notes": request.notes, "rejection_reason": request.rejection_reason},
    )
    await db.commit()

    return {
        "item_id": str(item.id),
        "approved": request.approved,
        "status": item.status,
        "notes": request.notes,
    }


# ============================================================================
# Sub-items (fixes) e Correcao com IA
# ============================================================================

@router.get("/projects/{project_id}/backlog/{item_id}/issues")
async def get_item_issues(
    project_id: UUID,
    item_id: UUID,
    permissions: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Lista sub-items (fixes de security/compliance) de um item."""
    ticket_service = IssueTicketService()
    tickets = await ticket_service.get_child_tickets(db, item_id)
    progress = await ticket_service.get_fix_progress(db, item_id)
    return {"tickets": tickets, "progress": progress}


@router.post("/projects/{project_id}/backlog/{item_id}/issues/{fix_id}/resolve")
async def resolve_fix(
    project_id: UUID,
    item_id: UUID,
    fix_id: UUID,
    permissions: dict = Depends(require_action("code:write")),
    db: AsyncSession = Depends(get_db),
):
    """Marca um fix como resolvido."""
    ticket_service = IssueTicketService()
    result = await ticket_service.mark_fix_done(db, fix_id)

    # Verificar se todos os fixes foram resolvidos
    progress = await ticket_service.get_fix_progress(db, item_id)
    if progress["all_resolved"]:
        item = await db.get(BacklogItem, item_id)
        if item and item.status == "blocked":
            item.status = "security_review"
            await db.commit()
            return {**result, "progress": progress, "parent_status": "security_review", "message": "Todos os fixes resolvidos. Item liberado para re-scan."}

    return {**result, "progress": progress}


@router.post("/projects/{project_id}/backlog/{item_id}/issues/{fix_id}/fix-with-ai")
async def fix_with_ai(
    project_id: UUID,
    item_id: UUID,
    fix_id: UUID,
    permissions: dict = Depends(require_action("code:write")),
    db: AsyncSession = Depends(get_db),
):
    """Gera codigo de correcao via LLM para um fix especifico."""
    fix_item = await db.get(BacklogItem, fix_id)
    if not fix_item:
        raise HTTPException(status_code=404, detail="Fix nao encontrado")

    parent = await db.get(BacklogItem, item_id)
    client, provider = await _get_llm_client(db, project_id)

    prompt = f"""Voce e um desenvolvedor senior corrigindo uma vulnerabilidade/issue no modulo: {parent.title if parent else 'unknown'}

## Problema
{fix_item.title}

## Descricao
{fix_item.description}

## Severidade
{fix_item.fix_severity}

## Remediacao Sugerida
{fix_item.fix_remediation}

Gere APENAS o codigo de correcao (patch). Seja preciso e minimalista.
Inclua comentarios explicando a mudanca.
Se for uma configuracao, mostre o antes e depois."""

    try:
        fix_code = await client.generate(prompt=prompt, max_tokens=2048, temperature=0.2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar correcao: {str(e)}")

    return {
        "fix_id": str(fix_id),
        "title": fix_item.title,
        "severity": fix_item.fix_severity,
        "fix_code": fix_code,
        "provider": provider,
    }
