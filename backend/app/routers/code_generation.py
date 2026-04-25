"""
Code Generation Router
REST endpoints for code generation workflows
"""
import json
import re
import structlog
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, case
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from uuid import UUID

from app.db.database import get_db
from app.services.code_generation_service import CodeGenerationService
from app.services.llm_service import LLMProvider, LLMServiceFactory
from app.models.base import OCG, IngestedDocument, ArguiderAnalysis
from app.models.base import Project, ProjectGitConfig, BacklogItem, ModuleCandidate
from app.core.config import settings as app_settings
from app.dependencies.require_project_setup import assert_project_setup_complete
from app.dependencies.require_action import resolve_user_roles_in_project
from app.middleware.auth import get_current_user_from_token
from app.core.permissions import has_action_any

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/code-generation", tags=["code-generation"])


# DT-043 — adequação do provedor à criticidade do CodeGen (contrato §7 + §6.2).
# CodeGen é **ALTA criticidade**: geração de código que vai virar commit + base
# do projeto. Exige modelo premium (raciocínio). Providers média/baixa podem
# produzir código sintaticamente OK mas com bugs sutis, falhas de compliance,
# arquitetura fraca. Não bloqueamos (decisão fica do GP/Dev), mas emitimos
# warning no log + no response pra audit trail, mesmo padrão de DT-036
# (ocg_updater).

_CODEGEN_PREMIUM_PROVIDERS = {"anthropic", "openai"}
_CODEGEN_MEDIUM_LOW_PROVIDERS = {"deepseek", "grok", "gemini", "qwen", "ollama"}


async def _check_codegen_provider_adequacy(
    project_id: UUID,
    db: AsyncSession,
) -> Optional[Dict[str, Any]]:
    """Retorna dict com warning se o provider do projeto é inadequado para
    CodeGen (contrato §6.2 Alta criticidade). `None` se adequado ou não
    configurado (neste caso o caller já levanta erro pelo gate de setup).

    Shape do warning: {provider, recommended, reason}.
    """
    from sqlalchemy import text as _text
    try:
        row = (await db.execute(
            _text("SELECT settings_json FROM project_settings WHERE project_id=:pid AND setting_type='llm'"),
            {"pid": str(project_id)},
        )).fetchone()
        if not row or not row[0]:
            return None
        settings_dict = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    except Exception:
        return None

    provider = (settings_dict.get("provider") or "").lower()
    if not provider:
        return None

    if provider in _CODEGEN_MEDIUM_LOW_PROVIDERS:
        logger.warning(
            "codegen.provider_criticality_mismatch",
            project_id=str(project_id),
            provider=provider,
            task="codegen",
        )
        return {
            "provider": provider,
            "criticality": "medium_low",
            "recommended": "anthropic | openai (premium reasoning)",
            "reason": (
                f"CodeGen é ALTA criticidade (contrato §6.2) e gera código que vira commit "
                f"direto no Git do projeto. O provider '{provider}' é classificado como "
                f"média/baixa criticidade — pode gerar código com bugs sutis ou arquitetura "
                f"fraca. A decisão continua com você; considere reconfigurar um provider "
                f"premium (Anthropic/OpenAI) em Configurações → Provedor de IA antes de "
                f"aplicar o scaffold em produção."
            ),
        }
    # Adequado — sem warning.
    return None


async def _require_code_action(
    action: str,
    project_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> dict:
    """MVP 3 / DT-042 — enforcement RBAC em endpoints de CodeGen cujo
    `project_id` vem no corpo (não no path — `require_action` assume path).

    Valida que o user tem `action` (ex: "code:write", "git:commit") em pelo
    menos um dos papéis no projeto. GP é barrado (contrato §4.1: GP não
    escreve código). Dev tem `code:write`, `code:review`, `git:commit`.
    Admin sem membership vira `admin_viewer` — não tem `code:*`.

    Retorna dict com user_id, roles, project_id pra logging e audit.
    """
    roles = await resolve_user_roles_in_project(user_id, project_id, db)
    if not has_action_any(roles, action):
        logger.warning(
            "codegen.rbac_denied",
            user_id=str(user_id),
            project_id=str(project_id),
            action=action,
            roles=roles,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acesso negado: seus papéis {roles} não têm permissão para '{action}'. CodeGen exige papel Dev (contrato §4.1).",
        )
    return {"user_id": user_id, "roles": roles, "project_id": project_id}


def _missing_required_docstring(path: str, content: str) -> bool:
    """True se o arquivo exige docstring e não tem.

    Regras por extensão:
    - .py  → exige `\"\"\"...\"\"\"` ou `'''...'''` logo após declarações `def`/`class`
             e docstring de módulo (primeiras linhas não-vazias começam com aspas triplas).
    - .ts/.tsx/.js/.jsx/.mjs → exige bloco `/** ... */` antes de cada `export function`,
                                `export class` ou `export default function`.
    - .go / .java → idem (comentário `//` ou `/** */` antes de funções/métodos).
    - Arquivos `__init__.py` triviais (vazios ou só imports) e arquivos de config
      (`pyproject.toml`, `package.json`, `Dockerfile`, `.env*`, `*.yaml`, `*.yml`,
      `*.md`, `*.json`) são isentos.
    """
    if not path or not content:
        return False
    lowered = path.lower()
    # Isenções: arquivos não-código ou scaffolding trivial
    for ext in (".md", ".json", ".yaml", ".yml", ".toml", ".env", ".lock", ".txt", ".cfg", ".ini"):
        if lowered.endswith(ext):
            return False
    if lowered.endswith("__init__.py") and len(content.strip().splitlines()) <= 3:
        return False
    if lowered.endswith(".py"):
        # Módulo precisa começar com docstring (ignorando shebang/encoding/imports/comentários puros)
        first_code = next(
            (ln for ln in content.splitlines() if ln.strip() and not ln.lstrip().startswith("#")),
            "",
        ).lstrip()
        if not (first_code.startswith('"""') or first_code.startswith("'''")):
            return True
        # Toda `def`/`class` precisa ter aspas triplas na próxima linha não-vazia
        import re as _re

        for m in _re.finditer(r"^(\s*)(?:async\s+)?(?:def|class)\s+\w+[^\n]*:\s*$", content, _re.MULTILINE):
            tail = content[m.end() :].lstrip()
            if not (tail.startswith('"""') or tail.startswith("'''")):
                return True
        return False
    if any(lowered.endswith(ext) for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs")):
        import re as _re

        for m in _re.finditer(
            r"^(\s*)export\s+(?:default\s+)?(?:async\s+)?(?:function|class)\s+\w+",
            content,
            _re.MULTILINE,
        ):
            # Procurar `/**` nas linhas imediatamente acima (máx 2 linhas vazias entre)
            preceding = content[: m.start()].rstrip().splitlines()[-4:]
            if not any("*/" in ln for ln in preceding):
                return True
        return False
    if lowered.endswith(".go") or lowered.endswith(".java"):
        import re as _re

        pattern = r"^(\s*)(?:public\s+|private\s+|protected\s+)?(?:func|class)\s+\w+"
        for m in _re.finditer(pattern, content, _re.MULTILINE):
            preceding = content[: m.start()].rstrip().splitlines()[-4:]
            if not any(ln.lstrip().startswith(("//", "/**", "*")) for ln in preceding):
                return True
        return False
    return False


# ============================================================================
# Pydantic Models
# ============================================================================


class GenerateProjectCodeRequest(BaseModel):
    """Request to generate complete project code"""

    project_id: UUID = Field(..., description="Project to generate code for")
    gp_id: UUID = Field(..., description="Gestão de Projeto user ID")
    language: str = Field(default="python", description="Programming language")
    architecture: str = Field(default="microservices", description="Architecture pattern")
    llm_provider: str = Field(default="anthropic", description="LLM provider to use")
    api_key: Optional[str] = Field(None, description="API key for LLM provider")
    ocg_id: Optional[UUID] = Field(None, description="Optional OCG ID for context enrichment")


class GenerateModuleCodeRequest(BaseModel):
    """Request to generate specific module code"""

    project_id: UUID
    module_name: str = Field(..., description="Name of module to generate")
    module_type: str = Field(..., description="Type: backend, frontend, database, api, etc")
    language: str = Field(default="python")
    requirements: Dict[str, Any] = Field(default_factory=dict)
    llm_provider: str = Field(default="anthropic")
    api_key: Optional[str] = None


class CodeGenerationResponse(BaseModel):
    """Response from code generation"""

    success: bool
    project_id: str
    provider: str
    code_artifact_id: Optional[str] = None
    generated_code: str
    full_code_length: int
    stack_recommendations: Optional[Dict[str, Any]] = None


class ModuleCodeResponse(BaseModel):
    """Response from module generation"""

    success: bool
    module_name: str
    module_type: str
    provider: str
    generated_code: str


class ProviderValidationResponse(BaseModel):
    """Response from provider validation"""

    provider: str
    valid: bool
    message: str


class GenerationHistoryItem(BaseModel):
    """Item in generation history"""

    artifact_id: str
    name: str
    generated_at: str
    size_bytes: int


class ScaffoldRequest(BaseModel):
    """Request para gerar scaffold completo do projeto.

    MVP 3: `dry_run` controla preview-vs-commit. Default `True` — geração
    não toca o Git. Contrato §7 exige preview antes do commit. O GP decide
    aplicar via `POST /scaffold/apply` depois de revisar a lista.
    """

    project_id: UUID = Field(..., description="ID do projeto")
    dry_run: bool = Field(
        default=True,
        description="Se True (default), só gera e retorna arquivos. Se False, commita direto (legado — mantido pra scripts; UX oficial é preview + apply).",
    )


class ScaffoldFileItem(BaseModel):
    """Arquivo individual do scaffold gerado"""

    path: str
    content: str
    status: str  # "complete", "todo", "nmi"


class ScaffoldResponse(BaseModel):
    """Response do scaffold gerado"""

    files: List[ScaffoldFileItem]
    summary: str


class ScaffoldApplyRequest(BaseModel):
    """Request para aplicar (commitar) arquivos gerados por `POST /scaffold` com dry_run=True.

    Fluxo oficial MVP 3:
      1. POST /scaffold {project_id} → recebe files[]
      2. GP revisa no frontend
      3. POST /scaffold/apply {project_id, files} → commits

    O backend re-valida docstrings e docpath antes de commitar — não
    confia cegamente no payload do cliente.
    """

    project_id: UUID = Field(..., description="ID do projeto")
    files: List[ScaffoldFileItem] = Field(..., description="Arquivos gerados no preview, revisados pelo GP")


class ScaffoldApplyResponse(BaseModel):
    """Response do /scaffold/apply — resumo dos commits."""

    committed: int
    failed: int
    skipped_nmi: int
    results: List[Dict[str, Any]]


class ScaffoldPlanItem(BaseModel):
    """Item do plano de scaffold — metadata SEM conteúdo."""

    path: str = Field(..., description="Path completo do arquivo no repo")
    file_type: str = Field(..., description="Extensão/tipo (py, tsx, md, yaml, etc)")
    purpose: str = Field(..., description="Descrição curta (<=120 chars) do que o arquivo faz")
    est_lines: int = Field(default=0, description="Estimativa de linhas; 0 se desconhecido")


class ScaffoldPlanResponse(BaseModel):
    """Response do /scaffold/plan — lista dos arquivos a gerar."""

    items: List[ScaffoldPlanItem]
    summary: str = Field(..., description="Descrição curta do scaffold proposto")


class ScaffoldItemRequest(BaseModel):
    """Request do /scaffold/item — gera UM arquivo do plano."""

    project_id: UUID = Field(..., description="ID do projeto")
    path: str = Field(..., description="Path do arquivo a gerar (vindo do /plan)")
    file_type: str = Field(..., description="Tipo do arquivo")
    purpose: str = Field(..., description="Propósito (vindo do /plan)")


class ScaffoldItemResponse(BaseModel):
    """Response do /scaffold/item — 1 arquivo gerado."""

    path: str
    content: str
    status: str
    tokens_used: int = 0
    error_message: Optional[str] = None


class ScaffoldStartRequest(BaseModel):
    """Request do POST /scaffold/start — dispara run server-side persistida."""

    project_id: UUID = Field(..., description="ID do projeto")


class ScaffoldStartResponse(BaseModel):
    """Response do /scaffold/start — run criada e enfileirada."""

    run_id: UUID
    status: str


class ValidateCodeRequest(BaseModel):
    """Payload para validar código antes de salvar."""

    code: str = Field(..., description="Conteúdo do arquivo a validar")
    path: Optional[str] = Field(None, description="Caminho do arquivo (infere linguagem)")
    language: Optional[str] = Field(None, description="Override explícito da linguagem")


class RegenerateFileRequest(BaseModel):
    """Payload para regenerar UM arquivo específico via LLM."""

    project_id: UUID = Field(..., description="ID do projeto")
    path: str = Field(..., description="Caminho do arquivo no repo")
    current_content: Optional[str] = Field(None, description="Conteúdo atual (para contexto de 'melhorar')")
    instructions: Optional[str] = Field(None, description="Instrução adicional (ex: 'corrija erro de importação')")


class RegenerateFileResponse(BaseModel):
    path: str
    content: str
    status: str
    committed: bool
    commit_error: Optional[str] = None


class ValidateCodeIssue(BaseModel):
    line: int
    column: int
    message: str
    severity: str


class ValidateCodeResponse(BaseModel):
    supported: bool
    language: str
    valid: bool
    issues: List[ValidateCodeIssue]


# ============================================================================
# Helpers compartilhados entre /scaffold e /regenerate-file
# ============================================================================


async def _require_git_config(db: AsyncSession, project_id: UUID) -> ProjectGitConfig:
    """Retorna o ProjectGitConfig do projeto ou levanta 400 se ausente.

    Guard usado por endpoints que persistem código no Git do projeto —
    sem repositório configurado, scaffold/regenerate não tem onde commitar.
    """
    git_config = (
        await db.execute(select(ProjectGitConfig).where(ProjectGitConfig.project_id == project_id))
    ).scalar_one_or_none()
    if not git_config or not git_config.repository_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Repositório Git do projeto não configurado. " "Configure em Admin → Projetos antes de gerar código."
            ),
        )
    return git_config


async def _load_ocg_context(db: AsyncSession, project_id: UUID) -> Dict[str, Any]:
    """Carrega o OCG mais recente do projeto e parseia ocg_data como dict.

    Retorna sempre um dict — vazio se não houver OCG ou se o parse falhar —
    para que o chamador possa fazer .get(\"STACK_RECOMMENDATION\", {}) etc.
    sem se preocupar com None.
    """
    ocg_result = await db.execute(select(OCG).where(OCG.project_id == project_id).order_by(desc(OCG.version)).limit(1))
    ocg = ocg_result.scalar_one_or_none()
    if not ocg or not ocg.ocg_data:
        return {}
    try:
        return json.loads(ocg.ocg_data) if isinstance(ocg.ocg_data, str) else ocg.ocg_data
    except (json.JSONDecodeError, TypeError):
        return {}


# ============================================================================
# Endpoints
# ============================================================================


@router.post(
    "/scaffold",
    response_model=ScaffoldResponse,
    summary="Gerar scaffold completo do projeto",
    description="Gera estrutura de código real baseada no OCG, documentos ingeridos e análises do Arguidor",
)
async def generate_scaffold(
    request: ScaffoldRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    """
    Gera scaffold completo do projeto com código fonte real.

    Fluxo:
    1. Busca OCG mais recente do projeto
    2. Busca documentos ingeridos com análises do Arguidor
    3. Constrói prompt abrangente com stack, arquitetura e regras de negócio
    4. Chama LLM pedindo JSON com arquivos de código
    5. Retorna lista de arquivos com status (complete/todo/nmi)

    DT-042: exige `code:write` (Dev). GP é barrado com 403.
    """
    project_id = request.project_id
    await _require_code_action("code:write", project_id, user_id, db)
    await assert_project_setup_complete(db, project_id)

    # DT-043: análise de adequação do provedor ao CodeGen (contrato §7).
    # Warning se provider é média/baixa criticidade. Não bloqueia.
    provider_warning = await _check_codegen_provider_adequacy(project_id, db)

    # 1. Buscar projeto
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

    # Guard: projeto precisa ter Git configurado para receber os commits
    await _require_git_config(db, project_id)

    # 2. Buscar OCG mais recente do projeto
    ocg_data = await _load_ocg_context(db, project_id)

    # 3. Buscar documentos ingeridos e análises do Arguidor
    docs_result = await db.execute(
        select(IngestedDocument)
        .where(IngestedDocument.project_id == project_id)
        .order_by(IngestedDocument.created_at.desc())
    )
    ingested_docs = docs_result.scalars().all()

    # Buscar análises do Arguidor para esses documentos
    doc_ids = [d.id for d in ingested_docs]
    arguider_analyses = []
    if doc_ids:
        analyses_result = await db.execute(select(ArguiderAnalysis).where(ArguiderAnalysis.document_id.in_(doc_ids)))
        arguider_analyses = analyses_result.scalars().all()

    # 4. Construir prompt abrangente
    stack = ocg_data.get("STACK_RECOMMENDATION", {})
    architecture = ocg_data.get("ARCHITECTURE_OVERVIEW", {})
    testing = ocg_data.get("TESTING_REQUIREMENTS", {})
    modules = ocg_data.get("MODULE_CANDIDATES", [])
    business_rules = ocg_data.get("BUSINESS_RULES", [])
    critical_findings = ocg_data.get("CRITICAL_FINDINGS", [])
    compliance = ocg_data.get("COMPLIANCE_CHECKLIST", [])

    # Extrair module candidates das análises do Arguidor
    arguider_modules = []
    arguider_gaps = []
    for analysis in arguider_analyses:
        try:
            mc = (
                json.loads(analysis.module_candidates)
                if isinstance(analysis.module_candidates, str)
                else analysis.module_candidates
            )
            arguider_modules.extend(mc if isinstance(mc, list) else [])
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            gaps = json.loads(analysis.gaps) if isinstance(analysis.gaps, str) else analysis.gaps
            arguider_gaps.extend(gaps if isinstance(gaps, list) else [])
        except (json.JSONDecodeError, TypeError):
            pass

    # Documentos ingeridos como contexto
    doc_context = ""
    for doc in ingested_docs[:10]:  # Limitar a 10 para não estourar tokens
        doc_context += f"- {doc.original_filename} ({doc.file_type}, categoria: {doc.document_category or 'N/A'})\n"

    # MVP 12 Fase 12.9 — prompt consolidado via builder canônico.
    from app.services.codegen_prompt_builder import build_scaffold_prompt
    # MVP 23 Fase 23.3 — contratos RNF do OCG entram como contrato obrigatório
    # no prompt; stack-aware hints guiam implementação por linguagem/framework.
    rnf_contracts = ocg_data.get("RNF_CONTRACTS")
    # MVP 25 Fase 25.4 — design tokens derivados da ingestão alimentam o
    # prompt para frontend não inventar paleta/tipografia.
    frontend_obj = (stack or {}).get("frontend") if isinstance(stack, dict) else None
    design_tokens = (
        frontend_obj.get("design_tokens")
        if isinstance(frontend_obj, dict) else None
    )
    prompt = build_scaffold_prompt(
        project_name=project.name,
        project_slug=project.slug,
        project_description=project.description,
        stack=stack,
        architecture=architecture,
        testing=testing,
        modules=modules,
        arguider_modules=arguider_modules,
        business_rules=business_rules,
        arguider_gaps=arguider_gaps,
        critical_findings=critical_findings,
        compliance=compliance,
        ingested_docs_context=doc_context,
        rnf_contracts=rnf_contracts,
        design_tokens=design_tokens,
    )

    # 5. Chamar LLM
    api_key = app_settings.ANTHROPIC_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key do Anthropic não configurada. Configure em Admin > Configurações.",
        )

    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=app_settings.ANTHROPIC_MODEL,
            max_tokens=app_settings.ANTHROPIC_MAX_TOKENS,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = response.content[0].text

        logger.info(
            "scaffold.llm_response",
            project_id=str(project_id),
            tokens_used=response.usage.output_tokens,
            response_length=len(raw_text),
        )

        # 6. Parsear resposta JSON (com múltiplas estratégias de fallback)
        result = None
        parse_attempts = [
            lambda: json.loads(raw_text),
        ]

        # Extrair de bloco markdown
        json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", raw_text)
        if json_match:
            parse_attempts.append(lambda m=json_match: json.loads(m.group(1)))

        # Extrair JSON direto
        json_match2 = re.search(r'\{[\s\S]*"files"[\s\S]*\}', raw_text)
        if json_match2:
            parse_attempts.append(lambda m=json_match2: json.loads(m.group()))

        for attempt in parse_attempts:
            try:
                result = attempt()
                if isinstance(result, dict) and "files" in result:
                    break
                result = None
            except (json.JSONDecodeError, Exception):
                continue

        if not result or "files" not in result:
            # Último recurso: tentar reparar JSON truncado/malformado
            try:
                # Encontrar o array "files" e extrair arquivos individuais
                files_match = re.search(r'"files"\s*:\s*\[([\s\S]*)', raw_text)
                if files_match:
                    files_text = files_match.group(1)
                    # Extrair objetos individuais do array
                    file_objects = re.findall(
                        r'\{[^{}]*"path"\s*:\s*"[^"]*"[^{}]*"content"\s*:\s*"(?:[^"\\]|\\.)*"[^{}]*\}', files_text
                    )
                    if file_objects:
                        repaired = (
                            '{"files": [' + ",".join(file_objects) + '], "summary": "Scaffold gerado (JSON reparado)"}'
                        )
                        result = json.loads(repaired)
            except Exception:
                pass

        if not result or "files" not in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Resposta da IA não contém JSON válido. Tente novamente.",
            )

        files = result.get("files", [])
        summary = result.get("summary", f"Gerados {len(files)} arquivos para {project.name}")

        # Validar e normalizar status
        valid_statuses = {"complete", "todo", "nmi"}
        for f in files:
            if f.get("status") not in valid_statuses:
                # Determinar status baseado no conteúdo
                content = f.get("content", "")
                if "[NMI]" in content:
                    f["status"] = "nmi"
                elif "TODO" in content:
                    f["status"] = "todo"
                else:
                    f["status"] = "complete"

        # Validação OBRIGATÓRIA de docstrings — arquivos sem docstring caem para status=todo
        docstring_failures = []
        for f in files:
            if f.get("status") != "complete":
                continue
            path = f.get("path", "")
            content = f.get("content", "")
            if _missing_required_docstring(path, content):
                f["status"] = "todo"
                f["content"] = (
                    f"# [DOCSTRING MISSING] Regerar este arquivo com docstrings completas.\n"
                    f"# Regra: todo módulo, classe e função exige docstring (PEP 257 para Python, JSDoc para TS/JS).\n\n"
                    + content
                )
                docstring_failures.append(path)
        if docstring_failures:
            logger.warning(
                "scaffold.docstring_validation_failed",
                project_id=str(project_id),
                files=docstring_failures,
            )

        # MVP 23 Fase 23.4 — validação estática contra RNF_CONTRACTS do OCG.
        # Grep determinístico sobre os arquivos; violações blocker rebaixam
        # o status pra "todo" (obriga Dev a regerar) e emitem audit canônico
        # CODEGEN_RNF_VIOLATION. Sem contrato declarado → no-op zero-impact.
        rnf_violations_payload: List[Dict[str, Any]] = []
        try:
            from app.services.rnf_contracts import from_ocg_dict
            from app.services.rnf_validation_service import validate_files

            ocg_row = (
                await db.execute(
                    select(OCG).where(OCG.project_id == project_id)
                    .order_by(desc(OCG.version)).limit(1)
                )
            ).scalar_one_or_none()
            ocg_data = {}
            if ocg_row and ocg_row.ocg_data:
                try:
                    ocg_data = json.loads(ocg_row.ocg_data)
                except (ValueError, TypeError):
                    ocg_data = {}

            rnf = from_ocg_dict(ocg_data.get("RNF_CONTRACTS"))
            rnf_report = validate_files(rnf, files)

            if rnf_report.violations:
                blocker_paths = rnf_report.blocker_files
                for f in files:
                    if f.get("status") != "complete":
                        continue
                    if f.get("path") in blocker_paths:
                        f["status"] = "todo"
                        f["content"] = (
                            "# [RNF_CONTRACT_VIOLATION] Regerar atendendo contrato do OCG.\n"
                            "# Falhas detectadas na validação estática (grep canônico).\n\n"
                            + (f.get("content") or "")
                        )
                rnf_violations_payload = rnf_report.to_dict()["violations"]
                logger.warning(
                    "scaffold.rnf_validation_failed",
                    project_id=str(project_id),
                    violations=len(rnf_report.violations),
                    blocker_files=sorted(blocker_paths),
                )
        except Exception as exc:
            # Validação estática não pode bloquear o happy path. Loga e segue.
            logger.warning(
                "scaffold.rnf_validation_error",
                project_id=str(project_id),
                error=str(exc)[:300],
            )

        logger.info(
            "scaffold.generation_success",
            project_id=str(project_id),
            files_count=len(files),
            complete=sum(1 for f in files if f["status"] == "complete"),
            todo=sum(1 for f in files if f["status"] == "todo"),
            nmi=sum(1 for f in files if f["status"] == "nmi"),
        )

        # MVP 13 Fase 13.7 — audit canônico de scaffold gerado.
        from app.services.audit_service import AuditEvents, AuditService
        audit = AuditService(db)
        await audit.log_codegen_event(
            event_type=AuditEvents.CODEGEN_SCAFFOLD_GENERATED,
            actor_id=user_id,
            project_id=project_id,
            action="generate_scaffold_dry_run" if request.dry_run else "generate_scaffold_commit",
            files_count=len(files),
        )
        # MVP 23 Fase 23.4 — audit canônico de violação RNF, quando houve.
        if rnf_violations_payload:
            await audit.log_codegen_event(
                event_type=AuditEvents.CODEGEN_RNF_VIOLATION,
                actor_id=user_id,
                project_id=project_id,
                action="rnf_contract_violation",
                files_count=len({v["file_path"] for v in rnf_violations_payload}),
                extra={"violations": rnf_violations_payload},
            )
        await db.commit()

        from fastapi.responses import JSONResponse

        # MVP 3: modo preview é o default. Retorna files sem tocar no Git.
        # O GP revisa no frontend e clica "Aplicar" → POST /scaffold/apply.
        if request.dry_run:
            logger.info(
                "scaffold.preview_returned",
                project_id=str(project_id),
                files_count=len(files),
            )
            response = ScaffoldResponse(
                files=[ScaffoldFileItem(**f) for f in files],
                summary=summary,
            )
            response_dict = response.model_dump()
            response_dict["commit_summary"] = None  # Explícito: nada commitado
            response_dict["dry_run"] = True
            response_dict["provider_warning"] = provider_warning  # DT-043
            return JSONResponse(content=response_dict)

        # Legacy: dry_run=False commita direto (mantido pra scripts e
        # retrocompat; UX oficial usa preview + apply).
        committed, failed, commit_results = await _commit_scaffold_files(db, project_id, files)
        await _notify_scaffold_completion(db, project_id, project.name, committed, failed)

        response = ScaffoldResponse(
            files=[ScaffoldFileItem(**f) for f in files],
            summary=summary,
        )
        response_dict = response.model_dump()
        response_dict["commit_summary"] = {
            "committed": committed,
            "failed": failed,
            "results": commit_results,
        }
        response_dict["dry_run"] = False
        response_dict["provider_warning"] = provider_warning  # DT-043
        return JSONResponse(content=response_dict)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("scaffold.generation_failed", project_id=str(project_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Falha na geração do scaffold: {str(e)}"
        )


# ──────────────────────────────────────────────────────────────────────
# Scaffold server-side persistido (camada A, 2026-04-25)
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/scaffold/start",
    response_model=ScaffoldStartResponse,
    summary="Iniciar scaffold em background (Celery, persistido)",
    description=(
        "Cria uma ScaffoldRun pendente e enfileira a execução server-side. "
        "Retorna run_id imediatamente. Frontend acompanha via "
        "GET /scaffold/runs/{run_id}. Sobrevive a desconexão de rede."
    ),
)
async def start_scaffold_run(
    request: ScaffoldStartRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    project_id = request.project_id
    await _require_code_action("code:write", project_id, user_id, db)
    await assert_project_setup_complete(db, project_id)
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")
    await _require_git_config(db, project_id)

    from app.services.scaffold_run_service import create_run

    run = await create_run(db, project_id, triggered_by=user_id)

    # Enfileira no Celery (idempotente: o execute_run guarda contra status != pending)
    from app.tasks.scaffold import scaffold_run_executor
    scaffold_run_executor.delay(str(run.id))

    return ScaffoldStartResponse(run_id=run.id, status=run.status)


@router.get(
    "/scaffold/runs/{run_id}",
    summary="Snapshot da run server-side",
    description="Status global + lista de items com flags de progresso.",
)
async def get_scaffold_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    from app.models.base import ScaffoldRun
    from app.services.scaffold_run_service import snapshot_run

    run = await db.get(ScaffoldRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run não encontrada")
    await _require_code_action("project:view", run.project_id, user_id, db)

    snap = await snapshot_run(db, run_id)
    return snap


@router.get(
    "/scaffold/runs/{run_id}/items/{item_id}/content",
    summary="Conteúdo gerado de um item específico",
    description="Útil pro frontend exibir editor sob demanda sem trazer todo o content na listagem.",
)
async def get_scaffold_run_item_content(
    run_id: UUID,
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    from app.models.base import ScaffoldRun, ScaffoldRunItem

    run = await db.get(ScaffoldRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run não encontrada")
    await _require_code_action("project:view", run.project_id, user_id, db)

    item = await db.get(ScaffoldRunItem, item_id)
    if item is None or item.run_id != run_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item não encontrado nesta run")

    return {
        "id": str(item.id),
        "path": item.path,
        "status": item.status,
        "content": item.content or "",
        "notes": item.notes,
        "error": item.error,
        "tokens_used": item.tokens_used,
    }


@router.post(
    "/scaffold/runs/{run_id}/apply",
    response_model=ScaffoldApplyResponse,
    summary="Commitar items done de uma run no Git",
    description="Pega os items com status='done' e content preenchido e commita pelo helper canônico.",
)
async def apply_scaffold_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    from app.models.base import ScaffoldRun, ScaffoldRunItem, TestArtifact

    run = await db.get(ScaffoldRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run não encontrada")
    await _require_code_action("git:commit", run.project_id, user_id, db)
    await assert_project_setup_complete(db, run.project_id)
    project = await db.get(Project, run.project_id)
    await _require_git_config(db, run.project_id)

    items_q = await db.execute(
        select(ScaffoldRunItem)
        .where(ScaffoldRunItem.run_id == run_id, ScaffoldRunItem.status == "done")
        .order_by(ScaffoldRunItem.ordinal.asc())
    )
    done_items = items_q.scalars().all()
    if not done_items:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nenhum item da run está com status='done' pra commitar.",
        )

    files_dict = [
        {"path": it.path, "content": it.content or "", "status": "ready"}
        for it in done_items
    ]
    committed, failed, results = await _commit_scaffold_files(db, run.project_id, files_dict)
    await _notify_scaffold_completion(db, run.project_id, project.name, committed, failed)

    # QA review automático: arquivos de teste comitados viram TestArtifact pending
    import re as _re
    TEST_FILE_RE = _re.compile(
        r"(^|/)(tests?/|test_[^/]+\.py$|[^/]+_test\.[a-z]+$|[^/]+\.test\.[a-z]+$|[^/]+\.spec\.[a-z]+$)",
        _re.IGNORECASE,
    )
    qa_artifacts_created = 0
    try:
        for r in results or []:
            if not isinstance(r, dict) or r.get("status") != "ok":
                continue
            file_path = r.get("path")
            content_match = next(
                (it.content for it in done_items if it.path == file_path),
                None,
            )
            if not file_path or not content_match:
                continue
            if not TEST_FILE_RE.search(file_path):
                continue
            db.add(TestArtifact(
                project_id=run.project_id,
                module_id=None,
                test_type="unit",
                title=file_path.rsplit("/", 1)[-1][:255],
                description=f"Teste gerado pelo scaffold run {run_id} em {file_path}",
                file_path=file_path,
                content=str(content_match),
                status="pending_review",
                created_by=user_id,
            ))
            qa_artifacts_created += 1
    except Exception as qa_err:  # noqa: BLE001
        logger.warning(
            "scaffold_run.apply_qa_failed",
            run_id=str(run_id),
            error=str(qa_err),
        )

    run.status = "applied"
    run.applied_at = datetime.now(timezone.utc)
    run.apply_committed = committed
    run.apply_failed = failed

    from app.services.audit_service import AuditEvents, AuditService
    await AuditService(db).log_codegen_event(
        event_type=AuditEvents.CODEGEN_SCAFFOLD_APPLIED,
        actor_id=user_id,
        project_id=run.project_id,
        action="apply_scaffold_run",
        files_count=committed,
        extra={
            "run_id": str(run_id),
            "failed": failed,
            "qa_artifacts_created": qa_artifacts_created,
        },
    )
    await db.commit()

    # Arguidor #2 (2026-04-25): dispara auditoria pós-CodeGen automaticamente
    # quando houve commits. Falha do enqueue não invalida o apply.
    if committed > 0:
        try:
            from app.tasks.scaffold import code_audit_executor
            code_audit_executor.delay(str(run_id))
            logger.info(
                "scaffold_run.audit_triggered",
                run_id=str(run_id),
                project_id=str(run.project_id),
            )
        except Exception as audit_err:  # noqa: BLE001
            logger.warning(
                "scaffold_run.audit_trigger_failed",
                run_id=str(run_id),
                error=str(audit_err),
            )

    return ScaffoldApplyResponse(
        committed=committed,
        failed=failed,
        skipped_nmi=0,
        results=results,
    )


@router.post(
    "/scaffold/plan",
    response_model=ScaffoldPlanResponse,
    summary="MVP 30 — Planejar scaffold (só lista de arquivos)",
    description="Gera a lista de arquivos do scaffold SEM conteúdo. Usar depois `/scaffold/item` pra cada item.",
)
async def generate_scaffold_plan(
    request: ScaffoldRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    """MVP 30 — Fase PLAN do scaffold item-a-item.

    Gera apenas a lista de arquivos com metadata (path, file_type, purpose,
    est_lines). Output ~500 tokens → latency ~5s. Frontend chama este
    endpoint primeiro, depois itera `/scaffold/item` pra cada item.

    Resolve o timeout Cloudflare que estourava em scaffolds grandes (27+
    arquivos consumindo ~90s num único LLM call).
    """
    project_id = request.project_id
    await _require_code_action("code:write", project_id, user_id, db)
    await assert_project_setup_complete(db, project_id)

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")
    await _require_git_config(db, project_id)

    ocg_data = await _load_ocg_context(db, project_id)
    stack = ocg_data.get("STACK_RECOMMENDATION", {})
    architecture = ocg_data.get("ARCHITECTURE_OVERVIEW", {})

    # Cascata canônica Backlog→Roadmap→Scaffold (2026-04-24): scaffold lê
    # do backlog filtrado por items prontos pra CodeGen. governance é
    # excluído sempre (PM corporativo nunca vira código). Items sem
    # vínculo com candidato (source=ocg) entram igual; items vindos do
    # Arguidor só entram se o candidato sinalizou ready_for_codegen=true.
    #
    # Ordenação canônica do roadmap (estável e determinística):
    #   1) prioridade: critical → high → medium → low → outros
    #   2) dentro da prioridade, ready_for_codegen=true primeiro
    #   3) desempate FIFO por created_at ASC
    priority_rank = case(
        (BacklogItem.priority == "critical", 0),
        (BacklogItem.priority == "high", 1),
        (BacklogItem.priority == "medium", 2),
        (BacklogItem.priority == "low", 3),
        else_=4,
    )
    ready_rank = case(
        (ModuleCandidate.ready_for_codegen.is_(True), 0),
        (ModuleCandidate.id.is_(None), 0),  # OCG direto = ready
        else_=1,
    )
    backlog_rows = (await db.execute(
        select(BacklogItem, ModuleCandidate)
        .outerjoin(ModuleCandidate, ModuleCandidate.id == BacklogItem.module_candidate_id)
        .where(
            BacklogItem.project_id == project_id,
            BacklogItem.parent_item_id.is_(None),
            BacklogItem.category != "governance",
            BacklogItem.status.notin_(("completed", "concluido", "rejected")),
        )
        .order_by(priority_rank, ready_rank, BacklogItem.created_at.asc())
    )).all()

    # Mapa prioridade → fase do roadmap (canônico, espelha RoadmapService)
    PHASE_MAP = {"critical": 1, "high": 1, "medium": 2, "low": 3}

    modules: List[Dict[str, Any]] = []
    deferred = 0
    for bl, mc in backlog_rows:
        # Items do Arguidor: só entram se o candidato está ready_for_codegen.
        # Items do OCG (sem candidato vinculado) entram sempre — eles vêm
        # da regeneração canônica do OCG e já assumem que o stakeholder
        # validou o escopo.
        if mc is not None and not bool(mc.ready_for_codegen):
            deferred += 1
            continue
        modules.append({
            "name": bl.title,
            "description": bl.description or "",
            "module_type": bl.module_type or (mc.module_type if mc else "feature"),
            "priority": bl.priority or "medium",
            "phase": PHASE_MAP.get((bl.priority or "medium").lower(), 2),
            "category": bl.category,
            "ready_for_codegen": bool(mc.ready_for_codegen) if mc else True,
        })

    logger.info(
        "scaffold_plan.modules_from_backlog",
        project_id=str(project_id),
        included=len(modules),
        deferred_not_ready=deferred,
    )

    if not modules:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Nenhum item do backlog está pronto pra CodeGen. "
                "Responda Questões em Aberto ou ingira mais documentos pra liberar items."
            ),
        )

    from app.services.scaffold_planner import build_plan_prompt

    # arguider_modules legado mantido pra retrocompat do prompt builder,
    # mas a fonte canônica agora é `modules` vindo do backlog.
    prompt = build_plan_prompt(
        project_name=project.name,
        project_slug=project.slug,
        project_description=project.description,
        stack=stack,
        architecture=architecture,
        modules=modules,
        arguider_modules=[],
    )

    api_key = app_settings.ANTHROPIC_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key do Anthropic não configurada. Configure em Admin > Configurações.",
        )

    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=api_key)
    # max_tokens 16384: 4096 estourava com >50 arquivos no plano (cada item
    # JSON ~80 tokens). 16384 cobre ~200 itens com folga. LLM nunca cuspe
    # mais que isso pra um plan; se chegar perto do teto, é sinal de prompt
    # quebrado, não de falta de espaço.
    response = await client.messages.create(
        model=app_settings.ANTHROPIC_MODEL,
        max_tokens=16384,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_text = response.content[0].text

    logger.info(
        "scaffold_plan.llm_response",
        project_id=str(project_id),
        tokens_used=response.usage.output_tokens,
        response_length=len(raw_text),
    )

    # Parser robusto: o LLM ocasionalmente envolve a resposta em
    # ```json ... ``` apesar da instrução. Tentamos:
    #  1. json.loads direto
    #  2. extrair conteúdo de bloco ```json ... ``` (fechado)
    #  3. extrair tudo após ```json sem fechamento (truncate parcial)
    #  4. fallback: primeiro `{` até o último `}` balanceado
    stripped = raw_text.strip()

    def _try_parse(s: str) -> Optional[dict]:
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return None

    data = _try_parse(stripped)
    if data is None:
        m = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", stripped, re.DOTALL)
        if m:
            data = _try_parse(m.group(1).strip())
    if data is None:
        m = re.match(r"^```(?:json)?\s*\n?([\s\S]*)$", stripped)
        if m:
            data = _try_parse(m.group(1).strip())
    if data is None:
        first_brace = stripped.find("{")
        last_brace = stripped.rfind("}")
        if 0 <= first_brace < last_brace:
            data = _try_parse(stripped[first_brace : last_brace + 1])
    if data is None:
        logger.error(
            "scaffold_plan.parse_failed",
            project_id=str(project_id),
            tokens_used=response.usage.output_tokens,
            response_length=len(raw_text),
            preview=stripped[:500],
        )
        raise HTTPException(
            status_code=502,
            detail=(
                "LLM retornou plano inválido. Tokens usados: "
                f"{response.usage.output_tokens}/16384. "
                "Se bateu o teto, reduzimos o escopo do prompt; tente novamente."
            ),
        )

    items_raw = data.get("items") or []
    items = [
        ScaffoldPlanItem(
            path=it.get("path", ""),
            file_type=it.get("file_type", ""),
            purpose=(it.get("purpose") or "")[:120],
            est_lines=int(it.get("est_lines") or 0),
        )
        for it in items_raw
        if isinstance(it, dict) and it.get("path")
    ]
    summary = (data.get("summary") or f"Scaffold de {len(items)} arquivos")[:500]

    return ScaffoldPlanResponse(items=items, summary=summary)


@router.post(
    "/scaffold/item",
    response_model=ScaffoldItemResponse,
    summary="MVP 30 — Gerar conteúdo de 1 arquivo do scaffold",
    description="Gera conteúdo completo de UM arquivo listado no /scaffold/plan. Latency ~15-30s por item.",
)
async def generate_scaffold_item(
    request: ScaffoldItemRequest,
    peer_paths_csv: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    """MVP 30 — Fase ITEM do scaffold item-a-item.

    Gera conteúdo de 1 arquivo específico. Frontend passa o `path` do plano
    e opcionalmente os paths dos peers (pra LLM não inventar dependências).
    Output ~2-5k tokens → cabe no timeout Cloudflare com folga.

    Em caso de falha no LLM ou parse do JSON, retorna
    `status="error"` com `error_message` — frontend decide se retry.
    """
    project_id = request.project_id
    await _require_code_action("code:write", project_id, user_id, db)
    await assert_project_setup_complete(db, project_id)

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")
    await _require_git_config(db, project_id)

    ocg_data = await _load_ocg_context(db, project_id)
    stack = ocg_data.get("STACK_RECOMMENDATION", {})
    architecture = ocg_data.get("ARCHITECTURE_OVERVIEW", {})
    rnf_contracts = ocg_data.get("RNF_CONTRACTS")
    frontend_obj = (stack or {}).get("frontend") if isinstance(stack, dict) else None
    design_tokens = frontend_obj.get("design_tokens") if isinstance(frontend_obj, dict) else None

    peer_paths: List[str] = []
    if peer_paths_csv:
        peer_paths = [p.strip() for p in peer_paths_csv.split(",") if p.strip()]

    from app.services.scaffold_planner import build_item_prompt

    prompt = build_item_prompt(
        project_name=project.name,
        project_slug=project.slug,
        stack=stack,
        architecture=architecture,
        item_path=request.path,
        item_purpose=request.purpose,
        item_file_type=request.file_type,
        peer_paths=peer_paths,
        rnf_contracts=rnf_contracts,
        design_tokens=design_tokens,
    )

    api_key = app_settings.ANTHROPIC_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key do Anthropic não configurada.",
        )

    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=api_key)
    try:
        response = await client.messages.create(
            model=app_settings.ANTHROPIC_MODEL,
            max_tokens=8192,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "scaffold_item.llm_error",
            project_id=str(project_id),
            path=request.path,
            error=str(exc),
        )
        return ScaffoldItemResponse(
            path=request.path, content="",
            status="error", tokens_used=0,
            error_message=f"LLM falhou: {str(exc)[:200]}",
        )

    raw_text = response.content[0].text
    tokens = response.usage.output_tokens

    logger.info(
        "scaffold_item.llm_response",
        project_id=str(project_id),
        path=request.path,
        tokens_used=tokens,
    )

    stripped = raw_text.strip()
    m = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", stripped, re.DOTALL)
    if m:
        stripped = m.group(1).strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return ScaffoldItemResponse(
            path=request.path, content="",
            status="error", tokens_used=tokens,
            error_message=f"JSON inválido do LLM: {exc}",
        )

    content = data.get("content") or ""
    status_value = data.get("status") or "todo"
    if status_value not in ("complete", "todo"):
        status_value = "todo"

    return ScaffoldItemResponse(
        path=request.path, content=content, status=status_value,
        tokens_used=tokens, error_message=None,
    )


# Helpers para commit — usados por /scaffold (dry_run=False) e /scaffold/apply.


async def _commit_scaffold_files(db: AsyncSession, project_id: UUID, files: List[Dict[str, Any]]):
    """Commita a lista de files no Git do projeto. Re-valida docstrings
    (preview-apply pode ter gap de tempo; arquivo editado no frontend
    pode ter perdido docstring).

    Retorna (committed, failed, results).
    """
    from app.services.git_service import GitService

    git_service = GitService(db)

    commit_results = []
    committed = 0
    failed = 0
    for f in files:
        if f.get("status") == "nmi":
            continue
        path = f.get("path") or f.get("file_path")
        content = f.get("content") or ""
        if not path or not content:
            continue
        # Re-checa docstring no momento do commit — impede que um frontend
        # bugado ou malicioso mande conteúdo sem docstring.
        if _missing_required_docstring(path, content):
            failed += 1
            commit_results.append({
                "path": path,
                "status": "error",
                "error": "Docstring obrigatória ausente (re-validação no apply).",
            })
            continue
        result = await git_service.commit_file(
            project_id=project_id,
            file_path=path,
            content=content,
            commit_message=f"feat(codegen): {path}",
        )
        if result.get("success"):
            committed += 1
            commit_results.append({"path": path, "status": "ok"})
        else:
            failed += 1
            commit_results.append({"path": path, "status": "error", "error": result.get("message")})

    logger.info(
        "scaffold.commits_finished",
        project_id=str(project_id),
        committed=committed,
        failed=failed,
    )
    return committed, failed, commit_results


async def _notify_scaffold_completion(
    db: AsyncSession,
    project_id: UUID,
    project_name: str,
    committed: int,
    failed: int,
):
    """Notifica GPs do projeto após o apply concluir."""
    try:
        from app.services.notification_inapp_service import InAppNotificationService
        from app.models.base import ProjectMember

        gps_result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.role == "gp",
                ProjectMember.is_active == True,
            )
        )
        notif_svc = InAppNotificationService(db)
        severity = "warning" if failed > 0 else "success"
        title = "Geração de código concluída" + (f" com {failed} falha(s)" if failed > 0 else "")
        message = f"{committed} arquivo(s) commitado(s) em {project_name}."
        for gp in gps_result.scalars().all():
            await notif_svc.notify(
                user_id=gp.user_id,
                event_type="codegen_completed",
                title=title,
                message=message,
                project_id=project_id,
                resource_type="scaffold",
                link=f"/projects/{project_id}/codegen",
                severity=severity,
            )
    except Exception as notif_err:
        logger.warning("scaffold.notify_failed", error=str(notif_err))


@router.post(
    "/scaffold/apply",
    response_model=ScaffoldApplyResponse,
    summary="Aplicar (commitar) scaffold gerado previamente",
    description="Aceita a lista de arquivos revisada pelo GP (após POST /scaffold com dry_run=True) e commita cada um no repositório Git do projeto. Re-valida docstrings e gate de setup.",
)
async def apply_scaffold(
    request: ScaffoldApplyRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    """Fluxo oficial MVP 3 do CodeGen:

      1. `POST /scaffold {project_id}` → recebe `files[]` + `summary` (dry_run default).
      2. Dev revisa no frontend.
      3. `POST /scaffold/apply {project_id, files}` → commits.

    O backend **não confia** no payload do cliente:
    - RBAC: exige `git:commit` (Dev). GP é barrado (§4.1 — GP revisa mas
      não commita código);
    - gate `require_project_setup_complete` executa de novo (coerência com
      /scaffold; se setup foi revertido entre preview e apply, barra);
    - docstrings são re-validadas por arquivo (commit é barrado por
      arquivo que falhar, não rejeita o batch inteiro);
    - arquivos com `status=nmi` são pulados (marcador do preview).

    Retorna resumo dos commits + lista de results por arquivo.
    """
    project_id = request.project_id
    await _require_code_action("git:commit", project_id, user_id, db)
    await assert_project_setup_complete(db, project_id)

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

    await _require_git_config(db, project_id)

    # Converte lista tipada Pydantic pra dicts (formato esperado pelo helper).
    files_dict = [f.model_dump() for f in request.files]

    skipped_nmi = sum(1 for f in files_dict if f.get("status") == "nmi")

    committed, failed, results = await _commit_scaffold_files(db, project_id, files_dict)
    await _notify_scaffold_completion(db, project_id, project.name, committed, failed)

    logger.info(
        "scaffold.apply_completed",
        project_id=str(project_id),
        committed=committed,
        failed=failed,
        skipped_nmi=skipped_nmi,
    )

    # Cascata canônica CodeGen → QA (2026-04-24): pra cada arquivo de teste
    # comitado, cria TestArtifact pending_review. O tester recebe na fila
    # automaticamente — sem ação manual. Heurística de detecção de teste:
    # path contém /test/ ou /tests/, ou nome bate test_*.py / *_test.* /
    # *.test.* / *.spec.*. Falha graciosa: não invalida o commit do
    # scaffold se a criação do artifact quebrar.
    from app.models.base import TestArtifact
    import re as _re
    TEST_FILE_RE = _re.compile(
        r"(^|/)(tests?/|test_[^/]+\.py$|[^/]+_test\.[a-z]+$|[^/]+\.test\.[a-z]+$|[^/]+\.spec\.[a-z]+$)",
        _re.IGNORECASE,
    )
    qa_artifacts_created = 0
    try:
        for r in results or []:
            if not isinstance(r, dict):
                continue
            if r.get("status") != "committed":
                continue
            file_path = r.get("path") or r.get("file_path")
            content = r.get("content")
            if not file_path or not content:
                continue
            if not TEST_FILE_RE.search(file_path):
                continue
            artifact = TestArtifact(
                project_id=project_id,
                module_id=None,  # mapeamento test→módulo é incremental, ainda sem FK
                test_type="unit",  # default conservador; o tester reclassifica se for outro tipo
                title=file_path.rsplit("/", 1)[-1][:255],
                description=f"Teste gerado automaticamente pelo scaffold em {file_path}",
                file_path=file_path,
                content=str(content),
                status="pending_review",
                created_by=user_id,
            )
            db.add(artifact)
            qa_artifacts_created += 1
        if qa_artifacts_created:
            logger.info(
                "scaffold.qa_artifacts_created",
                project_id=str(project_id),
                count=qa_artifacts_created,
            )
    except Exception as qa_err:  # noqa: BLE001
        logger.warning(
            "scaffold.qa_artifacts_failed",
            project_id=str(project_id),
            error=str(qa_err),
        )

    # MVP 13 Fase 13.7 — audit canônico de scaffold aplicado.
    from app.services.audit_service import AuditEvents, AuditService
    await AuditService(db).log_codegen_event(
        event_type=AuditEvents.CODEGEN_SCAFFOLD_APPLIED,
        actor_id=user_id,
        project_id=project_id,
        action="apply_scaffold",
        files_count=committed,
        extra={
            "failed": failed,
            "skipped_nmi": skipped_nmi,
            "qa_artifacts_created": qa_artifacts_created,
        },
    )
    await db.commit()

    return ScaffoldApplyResponse(
        committed=committed,
        failed=failed,
        skipped_nmi=skipped_nmi,
        results=results,
    )


@router.post(
    "/project",
    response_model=CodeGenerationResponse,
    summary="Generate complete project code",
    description="Generate full project codebase using evaluated artifacts and stack recommendations",
)
async def generate_project_code(
    request: GenerateProjectCodeRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    """
    Generate complete project code

    - **project_id**: Project to generate code for
    - **gp_id**: Gestão de Projeto user ID
    - **language**: Programming language (default: python)
    - **architecture**: Architecture pattern (default: microservices)
    - **llm_provider**: LLM provider (anthropic, openai, grok, deepseek)
    - **api_key**: Optional API key (uses env variable if not provided)

    DT-042: exige `code:write` (Dev).
    """
    project_id = request.project_id
    await _require_code_action("code:write", project_id, user_id, db)
    await assert_project_setup_complete(db, project_id)

    try:
        provider = LLMProvider(request.llm_provider.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Provedor LLM inválido: {request.llm_provider}"
        )

    # Validate OCG if provided
    ocg_data = None
    if request.ocg_id:
        from app.models.base import OCG

        ocg = await db.get(OCG, request.ocg_id)
        if not ocg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OCG não encontrado")
        if ocg.project_id and ocg.project_id != request.project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inconsistência de projeto no OCG")

    try:
        # Resolver chave: request > vault do projeto > env
        project_api_key = request.api_key
        if not project_api_key and request.project_id:
            from app.services.ai_key_resolver import AIKeyResolver

            project_api_key = await AIKeyResolver.get_project_key(db, request.project_id, provider.value)

        service = CodeGenerationService(db, llm_provider=provider, project_api_key=project_api_key)
        result = await service.generate_project_code(
            project_id=request.project_id,
            gp_id=request.gp_id,
            language=request.language,
            architecture=request.architecture,
            api_key=project_api_key,
            ocg_id=request.ocg_id,  # ← PASS OCG
        )

        return CodeGenerationResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Falha na geração de código: {str(e)}"
        )


@router.post(
    "/module",
    response_model=ModuleCodeResponse,
    summary="Generate specific module code",
    description="Generate code for a specific module or component",
)
async def generate_module_code(
    request: GenerateModuleCodeRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    """
    Generate code for a specific module

    - **project_id**: Project context
    - **module_name**: Name of module to generate
    - **module_type**: Type of module (backend, frontend, database, api)
    - **language**: Programming language
    - **requirements**: Module-specific requirements
    - **llm_provider**: LLM provider to use

    DT-042: exige `code:write` (Dev).
    """
    project_id = request.project_id
    await _require_code_action("code:write", project_id, user_id, db)
    await assert_project_setup_complete(db, project_id)

    try:
        provider = LLMProvider(request.llm_provider.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Provedor LLM inválido: {request.llm_provider}"
        )

    try:
        service = CodeGenerationService(db, llm_provider=provider)
        result = await service.generate_module_code(
            project_id=request.project_id,
            module_name=request.module_name,
            module_type=request.module_type,
            requirements=request.requirements,
            api_key=request.api_key,
        )

        return ModuleCodeResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Falha na geração do módulo: {str(e)}"
        )


@router.post(
    "/validate-provider",
    response_model=ProviderValidationResponse,
    summary="Validate LLM provider credentials",
    description="Test connection and validate API credentials for specified LLM provider",
)
async def validate_provider(provider: str, api_key: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """
    Validate LLM provider credentials

    - **provider**: LLM provider name (anthropic, openai, grok, deepseek)
    - **api_key**: API key to validate (uses env variable if not provided)
    """

    try:
        provider_enum = LLMProvider(provider.lower())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Provedor LLM inválido: {provider}")

    try:
        service = CodeGenerationService(db, llm_provider=provider_enum)
        valid = await service.validate_llm_provider(api_key=api_key)

        return ProviderValidationResponse(
            provider=provider,
            valid=valid,
            message="Credenciais do provedor validadas com sucesso" if valid else "Validação do provedor falhou",
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Validação do provedor falhou: {str(e)}"
        )


@router.get(
    "/history/{project_id}",
    response_model=list[GenerationHistoryItem],
    summary="Get code generation history",
    description="Get list of previous code generations for a project",
)
async def get_generation_history(project_id: UUID, limit: int = 10, db: AsyncSession = Depends(get_db)):
    """
    Get code generation history for a project

    - **project_id**: Project ID to get history for
    - **limit**: Maximum number of results (default: 10)
    """

    try:
        service = CodeGenerationService(db)
        history = await service.get_generation_history(project_id=project_id, limit=limit)

        return [GenerationHistoryItem(**item) for item in history]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Falha ao recuperar histórico: {str(e)}"
        )


@router.get("/providers", summary="List available LLM providers", description="Get list of available LLM providers")
async def list_providers():
    """Get list of available LLM providers"""

    return {
        "providers": [
            {
                "name": "anthropic",
                "model": "claude-opus-4-1",
                "description": "Anthropic Claude - Recommended for code generation",
            },
            {"name": "openai", "model": "gpt-4-turbo-preview", "description": "OpenAI GPT-4 - Advanced reasoning"},
            {"name": "grok", "model": "grok-1", "description": "xAI Grok - Real-time knowledge"},
            {"name": "deepseek", "model": "deepseek-coder", "description": "DeepSeek - Specialized for coding"},
        ]
    }


# ============================================================================
# Code Review by AI (pre-save validation)
# ============================================================================


class CodeReviewRequest(BaseModel):
    project_id: UUID
    code: str
    file_path: str


@router.post("/review-code")
async def review_code_by_ai(
    req: CodeReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Revisão de código pela IA antes de salvar.
    Verifica gaps, erros, práticas da empresa e discrepâncias.
    """
    try:
        from anthropic import AsyncAnthropic
        from app.core.config import settings as app_settings

        if not app_settings.ANTHROPIC_API_KEY:
            return {
                "review": {
                    "approved": True,
                    "gaps": [],
                    "errors": [],
                    "warnings": ["Revisão IA indisponível (API key não configurada)"],
                    "suggestions": [],
                }
            }

        client = AsyncAnthropic(api_key=app_settings.ANTHROPIC_API_KEY)

        response = await client.messages.create(
            model=app_settings.ANTHROPIC_MODEL,
            max_tokens=2048,
            temperature=0.1,
            system="""Você é um revisor de código sênior do GCA. Analise o código abaixo e identifique:
1. ERROS: bugs, problemas de sintaxe, falhas de lógica
2. GAPS: funcionalidades faltantes, tratamento de erro ausente
3. AVISOS: práticas ruins, código não seguro, problemas de performance
4. SUGESTÕES: melhorias de qualidade, legibilidade, manutenibilidade

Regras da empresa:
- Código deve ter tratamento de exceções
- Funções devem ter docstrings/comentários
- Não hardcodar segredos/credenciais
- Seguir princípios SOLID
- Código deve ser testável

Responda SOMENTE com JSON válido:
{
  "approved": true/false,
  "errors": ["..."],
  "gaps": ["..."],
  "warnings": ["..."],
  "suggestions": ["..."]
}""",
            messages=[
                {
                    "role": "user",
                    "content": f"Arquivo: {req.file_path}\n\nCódigo:\n```\n{req.code[:8000]}\n```",
                }
            ],
        )

        import json, re

        text = response.content[0].text
        try:
            review = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            review = (
                json.loads(match.group())
                if match
                else {"approved": True, "errors": [], "gaps": [], "warnings": [], "suggestions": []}
            )

        return {"review": review}

    except Exception as e:
        return {
            "review": {
                "approved": True,
                "gaps": [],
                "errors": [],
                "warnings": [f"Revisão IA falhou: {str(e)[:100]}"],
                "suggestions": [],
            }
        }


@router.post("/validate", response_model=ValidateCodeResponse, summary="Validar código antes de salvar")
async def validate_code_endpoint(request: ValidateCodeRequest) -> ValidateCodeResponse:
    """Valida sintaxe/lint do código. Retorna issues com linha/coluna para markers no editor."""
    from app.core.validation import validate_code

    result = validate_code(request.code, request.language, request.path)
    return ValidateCodeResponse(
        supported=result.supported,
        language=result.language,
        valid=result.valid,
        issues=[ValidateCodeIssue(**i.to_dict()) for i in result.issues],
    )


@router.post(
    "/regenerate-file",
    response_model=RegenerateFileResponse,
    summary="Regerar UM arquivo específico preservando os demais",
)
async def regenerate_single_file(
    request: RegenerateFileRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_from_token),
):
    """Gera apenas o arquivo indicado (não toca nos outros) e commita no Git.

    DT-042: exige `code:write` (Dev). Também envolve commit — mas é fluxo
    atômico (geração + commit no mesmo endpoint), então `code:write` basta;
    Dev por contrato §4.1 já tem `git:commit` também.
    """
    project_id = request.project_id
    await _require_code_action("code:write", project_id, user_id, db)
    await assert_project_setup_complete(db, project_id)

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    # Guard de Git
    await _require_git_config(db, project_id)

    # Contexto enxuto do OCG
    ocg_data = await _load_ocg_context(db, project_id)
    stack = ocg_data.get("STACK_RECOMMENDATION", {})
    architecture = ocg_data.get("ARCHITECTURE_OVERVIEW", {})
    # MVP 23 Fase 23.3 — RNF injetado também em regenerate-file
    # (refactor consciente preserva contratos quando arquivo é rescrito).
    rnf_contracts = ocg_data.get("RNF_CONTRACTS")
    # MVP 25 Fase 25.4 — design tokens preservados no regenerate.
    frontend_obj_rf = stack.get("frontend") if isinstance(stack, dict) else None
    design_tokens = (
        frontend_obj_rf.get("design_tokens")
        if isinstance(frontend_obj_rf, dict) else None
    )

    # MVP 12 Fase 12.9 — prompt consolidado via builder canônico.
    from app.services.codegen_prompt_builder import build_regenerate_file_prompt
    prompt = build_regenerate_file_prompt(
        project_name=project.name,
        project_description=project.description,
        stack=stack,
        architecture=architecture,
        path=request.path,
        instruction=request.instructions,
        current_content=request.current_content,
        rnf_contracts=rnf_contracts,
        design_tokens=design_tokens,
    )

    api_key = app_settings.ANTHROPIC_API_KEY
    if not api_key:
        raise HTTPException(status_code=503, detail="API key do Anthropic não configurada.")

    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=app_settings.ANTHROPIC_MODEL,
            max_tokens=4096,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = response.content[0].text

        # Parse JSON com fallbacks
        parsed = None
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\"content\"[\s\S]*\}", raw_text)
            if m:
                try:
                    parsed = json.loads(m.group())
                except json.JSONDecodeError:
                    pass
        if not parsed or "content" not in parsed:
            raise HTTPException(status_code=500, detail="Resposta da IA sem JSON válido. Tente novamente.")

        content = parsed.get("content") or ""
        status_value = parsed.get("status") or ("complete" if content.strip() else "todo")

        # Validação de docstring (reaproveitada)
        if status_value == "complete" and _missing_required_docstring(request.path, content):
            status_value = "todo"
            content = "# [DOCSTRING MISSING] Regerar este arquivo com docstrings completas.\n\n" + content

        # Commit no Git
        from app.services.git_service import GitService

        git_service = GitService(db)
        commit_result = await git_service.commit_file(
            project_id=project_id,
            file_path=request.path,
            content=content,
            commit_message=f"feat(codegen): regenerar {request.path}",
        )

        logger.info(
            "regenerate_file.done",
            project_id=str(project_id),
            path=request.path,
            status=status_value,
            committed=bool(commit_result.get("success")),
        )

        # MVP 13 Fase 13.7 — audit canônico de arquivo regenerado.
        from app.services.audit_service import AuditEvents, AuditService
        await AuditService(db).log_codegen_event(
            event_type=AuditEvents.CODEGEN_FILE_REGENERATED,
            actor_id=user_id,
            project_id=project_id,
            action="regenerate_file",
            file_path=request.path,
            commit_sha=commit_result.get("sha") or commit_result.get("commit_sha"),
            extra={"status": status_value, "committed": bool(commit_result.get("success"))},
        )
        await db.commit()

        return RegenerateFileResponse(
            path=request.path,
            content=content,
            status=status_value,
            committed=bool(commit_result.get("success")),
            commit_error=None if commit_result.get("success") else commit_result.get("message"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("regenerate_file.failed", project_id=str(project_id), path=request.path, error=str(e))
        raise HTTPException(status_code=500, detail=f"Falha ao regenerar arquivo: {e}")
