"""Auditor ativo pós-CodeGen — Arguidor #2 (2026-04-25).

Após /scaffold/runs/{id}/apply commitar arquivos no Git, este serviço roda
1 LLM call por arquivo de código verificando aderência ao OCG, RNFs,
stack canônica, docstrings PT-BR e práticas de segurança. Cada divergência
vira um `CodeAuditFinding` que o owner decide dismiss/accept.

Princípio: o Arguidor #1 (pré-CodeGen) é construtor — não pune. O Arguidor #2
(pós-CodeGen) é auditor — esse SIM pode ser pessimista, porque o objeto da
auditoria é código existente, não plano. Severidade clara: info/warn/critical.

Otimização de custo: ignora arquivos não-código (README, .gitignore, configs
puros) e arquivos sem `module_candidate_id` no scaffold_run_item (scaffolding
base sem módulo do backlog associado é menos crítico de auditar).
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.models.base import (
    CodeAuditFinding,
    OCG,
    Project,
    ScaffoldRun,
    ScaffoldRunItem,
)

logger = structlog.get_logger(__name__)

# Extensões consideradas "código de produção" — auditadas a fundo. Outras
# (readme, configs, gitignore, etc) são puladas pra economizar LLM calls.
_AUDITED_EXTENSIONS = {
    "py", "ts", "tsx", "js", "jsx", "java", "kt", "cpp", "cc", "c", "h", "hpp",
    "rs", "go", "rb", "cs", "php", "swift", "scala", "lua", "dart",
    "vue", "svelte",
}

# Tamanho máximo do conteúdo do arquivo enviado pro LLM. Arquivos maiores
# são truncados — auditor avisa o owner e segue.
_MAX_CONTENT_CHARS = 8000

# Concorrência: até N audits LLM simultâneos via asyncio.gather.
_AUDIT_BATCH_SIZE = 5


SYSTEM_PROMPT = """Você é o Auditor pós-CodeGen do GCA.
Seu papel é AUDITAR um arquivo de código gerado contra o contexto canônico
do projeto (OCG, RNFs, stack, PT-BR canônico, security básico).

Você é PESSIMISTA por design — encontra divergências reais. NÃO inventa
problemas pra parecer útil. Quando o arquivo está correto, devolve lista vazia.

Severidade obrigatória:
- info: nota informacional, sem ação obrigatória (ex: nome de variável)
- warn: divergência relevante, recomenda correção (ex: docstring fraca)
- critical: bloqueador (RNF violado, security issue grave, stack divergente)

Categoria obrigatória:
- rnf: viola contrato RNF declarado no OCG (latência, cobertura, etc)
- stack: usa lib/feature fora da stack canônica
- security: padrão OWASP relevante (injection, auth fraca, secrets em código,
  validação ausente em entrada de usuário)
- ptbr: docstring/comentário/erro user-facing em EN onde devia ser PT-BR
  (regra canônica do GCA — feedback_ptbr_codigo_obrigatorio)
- scope: arquivo não cumpre o purpose declarado no plano
- doc: docstring ausente ou incompleta em função/classe pública

Responda SOMENTE JSON válido, sem markdown:
{"findings":[{"severity":"...","category":"...","finding":"<até 300 chars>","suggested_fix":"<até 200 chars opcional>"}]}
"""


def _is_auditable_file(path: str) -> bool:
    """Decide se vale rodar LLM no arquivo. Pula docs/configs/scaffolding."""
    if not path:
        return False
    if "/" in path:
        ext = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    else:
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return ext in _AUDITED_EXTENSIONS


def _try_parse(s: str) -> Optional[dict]:
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def _parse_audit_response(raw: str) -> Optional[dict]:
    """Parser tolerante: json direto → fence fechado → fence aberto → primeiro {} balanceado."""
    s = raw.strip()
    parsed = _try_parse(s)
    if parsed is not None:
        return parsed
    m = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", s, re.DOTALL)
    if m:
        parsed = _try_parse(m.group(1).strip())
        if parsed is not None:
            return parsed
    m = re.match(r"^```(?:json)?\s*\n?([\s\S]*)$", s)
    if m:
        parsed = _try_parse(m.group(1).strip())
        if parsed is not None:
            return parsed
    fb, lb = s.find("{"), s.rfind("}")
    if 0 <= fb < lb:
        return _try_parse(s[fb : lb + 1])
    return None


def _build_audit_prompt(
    *,
    project_name: str,
    file_path: str,
    purpose: str,
    content: str,
    stack: dict,
    rnf_contracts: Any,
) -> str:
    """Monta prompt enxuto pro LLM auditor."""
    stack_compact = json.dumps(stack or {}, ensure_ascii=False)[:1500]
    rnf_compact = ""
    if rnf_contracts:
        rnf_compact = (
            f"\n\nContratos RNF do OCG (auditar aderência):\n"
            f"{json.dumps(rnf_contracts, ensure_ascii=False)[:1500]}"
        )

    truncate_note = ""
    if len(content) > _MAX_CONTENT_CHARS:
        content = content[:_MAX_CONTENT_CHARS]
        truncate_note = f"\n\n[ARQUIVO TRUNCADO em {_MAX_CONTENT_CHARS} chars; auditar parcial.]"

    return (
        f"Audite o arquivo abaixo do projeto `{project_name}`.\n\n"
        f"Path: `{file_path}`\n"
        f"Propósito declarado no plano: {purpose or '(não fornecido)'}\n\n"
        f"Stack canônica:\n{stack_compact}"
        f"{rnf_compact}\n\n"
        f"=== CONTEÚDO DO ARQUIVO ==={truncate_note}\n"
        f"```\n{content}\n```\n\n"
        f"Liste APENAS divergências reais entre o arquivo e o contexto. "
        f"Se está tudo aderente, devolva findings:[].\n"
        f"Foque em: aderência ao purpose, stack, RNFs, PT-BR em docstrings/erros, "
        f"docstrings em funções públicas, problemas OWASP claros."
    )


async def _audit_one_item(
    *,
    llm_cfg: dict,
    project_name: str,
    item: ScaffoldRunItem,
    stack: dict,
    rnf_contracts: Any,
    project_id: UUID,
    run_id: UUID,
) -> List[Dict[str, Any]]:
    """Roda 1 LLM call pra 1 arquivo, retorna lista de findings (sem persistir)."""
    if not item.content or not _is_auditable_file(item.path):
        return []

    prompt = _build_audit_prompt(
        project_name=project_name,
        file_path=item.path,
        purpose=item.purpose or "",
        content=item.content,
        stack=stack,
        rnf_contracts=rnf_contracts,
    )

    try:
        from app.services.llm_low_criticality import call_llm, clamp_max_tokens
        item_max_tokens = clamp_max_tokens(llm_cfg["model"], 4096)
        raw = await call_llm(
            config=llm_cfg,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=item_max_tokens,
            temperature=0.1,
            log_context="code_audit.item",
        )
        tokens = 0  # call_llm não devolve usage
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "code_audit.llm_error",
            project_id=str(project_id),
            run_id=str(run_id),
            file_path=item.path,
            error=str(exc),
        )
        return []

    parsed = _parse_audit_response(raw)
    if parsed is None:
        logger.warning(
            "code_audit.parse_failed",
            project_id=str(project_id),
            file_path=item.path,
            preview=raw[:200],
        )
        return []

    findings_raw = parsed.get("findings") or []
    out: List[Dict[str, Any]] = []
    for f in findings_raw:
        if not isinstance(f, dict):
            continue
        severity = str(f.get("severity") or "info").lower()
        if severity not in ("info", "warn", "critical"):
            severity = "info"
        category = str(f.get("category") or "doc").lower()
        if category not in ("rnf", "stack", "security", "ptbr", "scope", "doc"):
            category = "doc"
        text = str(f.get("finding") or "").strip()
        if not text:
            continue
        out.append({
            "severity": severity,
            "category": category,
            "finding": text[:1000],
            "suggested_fix": (str(f.get("suggested_fix") or "")[:500] or None),
            "tokens_used": tokens,
            "run_item_id": item.id,
            "file_path": item.path,
        })
    return out


async def audit_run(run_id: UUID) -> Dict[str, Any]:
    """Pipeline de auditoria pós-CodeGen pra uma run inteira.

    1. Carrega run + items done com module_candidate_id IS NOT NULL
       (módulos do backlog — scaffolding base é skipped pra economizar LLM)
    2. Filtra arquivos auditáveis (extensões de código)
    3. Em batches de 5 via asyncio.gather, chama LLM por arquivo
    4. Persiste todos os findings de uma vez no fim

    Retorna {audited, skipped, findings_created, errors}.
    """
    from app.db.database import AsyncSessionLocal
    from app.services.llm_low_criticality import resolve_llm_config

    # MVP-B fase 2 (2026-04-25): Arguidor #2 é trabalho DO PROJETO (audita
    # código gerado pelo tenant), não trabalho de admin do GCA. Logo o
    # billing fica com o tenant e a IA usada deve ser a configurada no
    # projeto. Antes desta correção, code_audit_service usava
    # `app_settings.ANTHROPIC_API_KEY` (env global do GCA admin) — o que
    # significa que o tenant trocava pra DeepSeek na UI mas Arguidor #2
    # continuava queimando conta de Anthropic do admin. Regra arquitetural
    # canônica: env global do GCA = SÓ análise de questionário inicial e
    # bootstrap (decisão admin de aceitar projeto). Resto = config do
    # projeto.
    async with AsyncSessionLocal() as db_pre:
        run_pre = await db_pre.get(ScaffoldRun, run_id)
        if run_pre is None:
            return {"audited": 0, "skipped": 0, "findings_created": 0, "errors": ["run_not_found"]}
        project_id_pre = run_pre.project_id

    async with AsyncSessionLocal() as db_cfg:
        llm_cfg = await resolve_llm_config(db_cfg, project_id_pre, prefer_ollama=False)
    if llm_cfg is None:
        # Fallback EXPLÍCITO pro env global do GCA com warning. Acontece
        # quando GP ainda não configurou provedor próprio. Admin absorve
        # o custo temporariamente — sinalizamos via WARNING pra alertar.
        api_key = app_settings.ANTHROPIC_API_KEY
        if not api_key:
            logger.warning(
                "code_audit.no_provider",
                run_id=str(run_id),
                project_id=str(project_id_pre),
            )
            return {
                "audited": 0,
                "skipped": 0,
                "findings_created": 0,
                "errors": ["nenhum provedor de IA configurado pra projeto nem pro GCA admin"],
            }
        logger.warning(
            "code_audit.fallback_to_admin_env",
            run_id=str(run_id),
            project_id=str(project_id_pre),
            note="projeto sem provider — usando env global do GCA admin (custo absorvido pelo admin)",
        )
        llm_cfg = {
            "provider": "anthropic",
            "base_url": None,
            "api_key": api_key,
            "model": app_settings.ANTHROPIC_MODEL,
        }

    async with AsyncSessionLocal() as db:
        run = await db.get(ScaffoldRun, run_id)
        if run is None:
            return {"audited": 0, "skipped": 0, "findings_created": 0, "errors": ["run_not_found"]}
        project = await db.get(Project, run.project_id)
        project_name = project.name if project else "(projeto)"
        project_id = run.project_id

        # Carrega OCG canônico
        ocg_row = await db.execute(
            select(OCG.ocg_data).where(OCG.project_id == project_id).order_by(OCG.version.desc()).limit(1)
        )
        ocg_raw = ocg_row.scalar() or "{}"
        try:
            ocg_data = json.loads(ocg_raw) if isinstance(ocg_raw, str) else ocg_raw
        except json.JSONDecodeError:
            ocg_data = {}
        stack = ocg_data.get("STACK_RECOMMENDATION", {}) if isinstance(ocg_data, dict) else {}
        rnf_contracts = ocg_data.get("RNF_CONTRACTS") if isinstance(ocg_data, dict) else None

        # Items done — apenas auditáveis
        items_q = await db.execute(
            select(ScaffoldRunItem)
            .where(
                ScaffoldRunItem.run_id == run_id,
                ScaffoldRunItem.status == "done",
            )
        )
        all_items = items_q.scalars().all()

    auditable = [it for it in all_items if _is_auditable_file(it.path) and it.content]
    skipped = len(all_items) - len(auditable)

    logger.info(
        "code_audit.start",
        run_id=str(run_id),
        project_id=str(project_id),
        total=len(all_items),
        auditable=len(auditable),
        skipped=skipped,
    )

    # Bate em batches pra não estourar rate-limit
    all_findings: List[Dict[str, Any]] = []
    for i in range(0, len(auditable), _AUDIT_BATCH_SIZE):
        batch = auditable[i : i + _AUDIT_BATCH_SIZE]
        results = await asyncio.gather(*[
            _audit_one_item(
                llm_cfg=llm_cfg,
                project_name=project_name,
                item=it,
                stack=stack,
                rnf_contracts=rnf_contracts,
                project_id=project_id,
                run_id=run_id,
            )
            for it in batch
        ], return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_findings.extend(r)
            elif isinstance(r, Exception):
                logger.warning("code_audit.batch_exception", error=str(r))

    # Persiste num único commit
    async with AsyncSessionLocal() as db:
        for f in all_findings:
            db.add(CodeAuditFinding(
                project_id=project_id,
                run_id=run_id,
                run_item_id=f["run_item_id"],
                file_path=f["file_path"],
                severity=f["severity"],
                category=f["category"],
                finding=f["finding"],
                suggested_fix=f["suggested_fix"],
                tokens_used=f.get("tokens_used"),
            ))
        await db.commit()

    logger.info(
        "code_audit.completed",
        run_id=str(run_id),
        project_id=str(project_id),
        findings_created=len(all_findings),
        audited=len(auditable),
        skipped=skipped,
    )
    return {
        "audited": len(auditable),
        "skipped": skipped,
        "findings_created": len(all_findings),
        "errors": [],
    }


async def list_findings(
    db: AsyncSession,
    project_id: UUID,
    *,
    severity: Optional[str] = None,
    run_id: Optional[UUID] = None,
    file_path: Optional[str] = None,
    owner_action: Optional[str] = None,
    pending_only: bool = False,
) -> List[dict]:
    """Lista findings com filtros. Owner_action='__pending__' filtra null."""
    stmt = select(CodeAuditFinding).where(CodeAuditFinding.project_id == project_id)
    if severity:
        stmt = stmt.where(CodeAuditFinding.severity == severity)
    if run_id:
        stmt = stmt.where(CodeAuditFinding.run_id == run_id)
    if file_path:
        stmt = stmt.where(CodeAuditFinding.file_path == file_path)
    if pending_only:
        stmt = stmt.where(CodeAuditFinding.owner_action.is_(None))
    elif owner_action:
        stmt = stmt.where(CodeAuditFinding.owner_action == owner_action)
    stmt = stmt.order_by(CodeAuditFinding.created_at.desc())

    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(f.id),
            "run_id": str(f.run_id),
            "file_path": f.file_path,
            "severity": f.severity,
            "category": f.category,
            "finding": f.finding,
            "suggested_fix": f.suggested_fix,
            "owner_action": f.owner_action,
            "owner_note": f.owner_note,
            "owner_acted_at": f.owner_acted_at.isoformat() if f.owner_acted_at else None,
            "backlog_fix_item_id": str(f.backlog_fix_item_id) if f.backlog_fix_item_id else None,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in rows
    ]
