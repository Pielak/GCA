"""
Code Generation Router
REST endpoints for code generation workflows
"""
import json
import re
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from uuid import UUID

from app.db.database import get_db
from app.services.code_generation_service import CodeGenerationService
from app.services.llm_service import LLMProvider, LLMServiceFactory
from app.models.base import OCG, IngestedDocument, ArguiderAnalysis
from app.models.base import Project, ProjectGitConfig
from app.core.config import settings as app_settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/code-generation", tags=["code-generation"])


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
    """Request para gerar scaffold completo do projeto"""

    project_id: UUID = Field(..., description="ID do projeto")


class ScaffoldFileItem(BaseModel):
    """Arquivo individual do scaffold gerado"""

    path: str
    content: str
    status: str  # "complete", "todo", "nmi"


class ScaffoldResponse(BaseModel):
    """Response do scaffold gerado"""

    files: List[ScaffoldFileItem]
    summary: str


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
async def generate_scaffold(request: ScaffoldRequest, db: AsyncSession = Depends(get_db)):
    """
    Gera scaffold completo do projeto com código fonte real.

    Fluxo:
    1. Busca OCG mais recente do projeto
    2. Busca documentos ingeridos com análises do Arguidor
    3. Constrói prompt abrangente com stack, arquitetura e regras de negócio
    4. Chama LLM pedindo JSON com arquivos de código
    5. Retorna lista de arquivos com status (complete/todo/nmi)
    """
    project_id = request.project_id

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

    prompt = f"""Você é um engenheiro de software sênior. Gere o scaffold completo de um projeto com código fonte REAL.

## REGRA INEGOCIÁVEL — DOCSTRINGS OBRIGATÓRIAS

**TODO arquivo de código DEVE ter docstrings. Sem exceção, sem parametrização.**

- **Python (.py)**: docstring no topo do módulo (aspas triplas) + docstring em toda classe + docstring em toda função/método (exceto `__init__` se trivial). Use PEP 257.
- **TypeScript/JavaScript (.ts/.tsx/.js/.jsx)**: bloco JSDoc (`/** ... */`) em toda função exportada, classe e componente React. Inclua `@param`, `@returns`.
- **Go (.go)**: comentário iniciando com o nome do identificador em toda função, tipo e package (godoc).
- **Java (.java)**: Javadoc (`/** ... */`) em toda classe e método público.

Arquivos sem docstrings serão rejeitados pela validação automática e marcados como TODO. Isso atrasa o projeto — faça direito na primeira vez.

## Projeto
- Nome: {project.name}
- Slug: {project.slug}
- Descrição: {project.description or 'Sem descrição'}

## Stack Tecnológica (do OCG)
{json.dumps(stack, indent=2, ensure_ascii=False) if stack else 'Não definida — use Python + FastAPI como padrão'}

## Arquitetura (do OCG)
{json.dumps(architecture, indent=2, ensure_ascii=False) if architecture else 'Padrão: Clean Architecture com camadas service/repository'}

## Requisitos de Testes (do OCG)
{json.dumps(testing, indent=2, ensure_ascii=False) if testing else 'Testes unitários e de integração obrigatórios'}

## Módulos Identificados (OCG + Arguidor)
{json.dumps(modules, indent=2, ensure_ascii=False) if modules else 'Nenhum módulo identificado no OCG'}
{json.dumps(arguider_modules[:10], indent=2, ensure_ascii=False) if arguider_modules else ''}

## Regras de Negócio
{json.dumps(business_rules[:10], indent=2, ensure_ascii=False) if business_rules else 'Sem regras de negócio explícitas'}

## Gaps Identificados pelo Arguidor
{json.dumps(arguider_gaps[:10], indent=2, ensure_ascii=False) if arguider_gaps else 'Nenhum gap identificado'}

## Findings Críticos
{json.dumps(critical_findings[:5], indent=2, ensure_ascii=False) if critical_findings else 'Nenhum'}

## Compliance
{json.dumps(compliance[:5], indent=2, ensure_ascii=False) if compliance else 'Não definido'}

## Documentos Ingeridos
{doc_context if doc_context else 'Nenhum documento ingerido'}

## INSTRUÇÕES IMPORTANTES

1. Gere arquivos de código REAIS (NÃO .md, NÃO placeholders vazios)
2. Use a stack definida no OCG. Se não definida, use Python + FastAPI + PostgreSQL
3. Os caminhos dos arquivos devem seguir a convenção da stack (ex: Python → .py, TypeScript → .ts/.tsx)
4. Cada arquivo DEVE ter conteúdo real com:
   - Imports necessários
   - TODAS as classes e funções DEVEM ter docstrings completas explicando: propósito, parâmetros, retorno e exceções
   - Módulos devem ter docstring no topo explicando a responsabilidade do arquivo
   - Tratamento de erro básico com mensagens descritivas
   - Type hints em todos os parâmetros e retornos
5. Para partes que precisam de mais detalhes, use comentários TODO:
   `# TODO: Implementar lógica de <funcionalidade>`
6. Para partes onde FALTAM INFORMAÇÕES do projeto, use marcador NMI:
   `# [NMI] Need More Information: <o que falta>`
7. Gere pelo menos: main/entry point, models, routes/controllers, services, config, testes
8. MÁXIMO 25 arquivos para caber no response

## FORMATO DE RESPOSTA

Responda EXCLUSIVAMENTE com JSON válido, sem markdown, sem explicações.
CRÍTICO: No campo "content", use \\n para quebras de linha e escape aspas com \\". NÃO use quebras de linha literais dentro de strings JSON.
{{
  "files": [
    {{
      "path": "src/main.py",
      "content": "conteúdo completo do arquivo aqui",
      "status": "complete"
    }},
    {{
      "path": "src/routes/payments.py",
      "content": "# TODO: Implementar processamento de pagamentos\\n# [NMI] Need More Information: gateway de pagamento\\ndef process_payment():\\n    pass",
      "status": "nmi"
    }}
  ],
  "summary": "Gerados X arquivos para projeto Y com framework Z"
}}

Status possíveis:
- "complete": arquivo com implementação funcional
- "todo": arquivo com TODOs mas estrutura definida
- "nmi": arquivo que precisa de mais informações do projeto
"""

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
            max_tokens=8192,
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

        logger.info(
            "scaffold.generation_success",
            project_id=str(project_id),
            files_count=len(files),
            complete=sum(1 for f in files if f["status"] == "complete"),
            todo=sum(1 for f in files if f["status"] == "todo"),
            nmi=sum(1 for f in files if f["status"] == "nmi"),
        )

        # Persistir cada arquivo no repositório Git do projeto
        from app.services.git_service import GitService
        from fastapi.responses import JSONResponse

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

        # Notificar GPs do projeto: sucesso ou falha parcial
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
            message = f"{committed} arquivo(s) commitado(s) em {project.name}."
            for gp in gps_result.scalars().all():
                await notif_svc.notify(
                    user_id=gp.user_id,
                    event_type="codegen_completed",
                    title=title,
                    message=message,
                    project_id=project_id,
                    resource_type="scaffold",
                    link=f"/projects/{project_id}/code-generator",
                    severity=severity,
                )
        except Exception as notif_err:
            logger.warning("scaffold.notify_failed", error=str(notif_err))

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
        return JSONResponse(content=response_dict)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("scaffold.generation_failed", project_id=str(project_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Falha na geração do scaffold: {str(e)}"
        )


@router.post(
    "/project",
    response_model=CodeGenerationResponse,
    summary="Generate complete project code",
    description="Generate full project codebase using evaluated artifacts and stack recommendations",
)
async def generate_project_code(request: GenerateProjectCodeRequest, db: AsyncSession = Depends(get_db)):
    """
    Generate complete project code

    - **project_id**: Project to generate code for
    - **gp_id**: Gestão de Projeto user ID
    - **language**: Programming language (default: python)
    - **architecture**: Architecture pattern (default: microservices)
    - **llm_provider**: LLM provider (anthropic, openai, grok, deepseek)
    - **api_key**: Optional API key (uses env variable if not provided)
    """

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
async def generate_module_code(request: GenerateModuleCodeRequest, db: AsyncSession = Depends(get_db)):
    """
    Generate code for a specific module

    - **project_id**: Project context
    - **module_name**: Name of module to generate
    - **module_type**: Type of module (backend, frontend, database, api)
    - **language**: Programming language
    - **requirements**: Module-specific requirements
    - **llm_provider**: LLM provider to use
    """

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
):
    """Gera apenas o arquivo indicado (não toca nos outros) e commita no Git."""
    project_id = request.project_id

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    # Guard de Git
    await _require_git_config(db, project_id)

    # Contexto enxuto do OCG
    ocg_data = await _load_ocg_context(db, project_id)
    stack = ocg_data.get("STACK_RECOMMENDATION", {})
    architecture = ocg_data.get("ARCHITECTURE_OVERVIEW", {})

    extra = request.instructions or "Reescreva completamente o arquivo mantendo o propósito detectado pelo path."
    current_block = (
        f"\n## Conteúdo Atual (referência — pode ser inteiramente substituído)\n```\n{request.current_content[:6000]}\n```\n"
        if request.current_content
        else ""
    )

    prompt = f"""Você é um engenheiro de software sênior. Gere o CONTEÚDO COMPLETO de um único arquivo de código.

## REGRA INEGOCIÁVEL — DOCSTRINGS OBRIGATÓRIAS
Todo módulo, classe e função pública DEVE ter docstring (PEP 257 para Python, JSDoc para TS/JS, godoc, Javadoc).

## Projeto
- Nome: {project.name}
- Descrição: {project.description or 'Sem descrição'}

## Stack (do OCG)
{json.dumps(stack, indent=2, ensure_ascii=False) if stack else 'Não definida'}

## Arquitetura (do OCG)
{json.dumps(architecture, indent=2, ensure_ascii=False) if architecture else 'Padrão: Clean Architecture'}

## Arquivo a gerar
Caminho: `{request.path}`

## Instrução
{extra}
{current_block}

## FORMATO DE RESPOSTA
Responda APENAS com JSON válido, sem markdown:
{{
  "content": "conteúdo completo do arquivo (use \\n para quebras)",
  "status": "complete"
}}

Status possíveis:
- "complete": funcional
- "todo": estrutura + TODOs
- "nmi": faltam informações do projeto
"""

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
