"""MVP 10 Fase 10.3 — Geração Premium de specs globais security/compliance.

Contrato §7 MVP 10 + §6.3 (roteamento híbrido): decisão sobre política
de segurança e aderência a compliance é **alta criticidade** — LLM
local nunca decide sozinha. Requer provider Premium (Anthropic
preferido > OpenAI; Ollama explicitamente ignorado).

Specs são **globais** (module_id=NULL) porque consolidam contexto do
OCG inteiro — não são por módulo. 1 spec 'security' e 1 spec
'compliance' por projeto (idempotente via upsert manual).

Pipeline:
  1. Carrega OCG consolidado: PROJECT_PROFILE + COMPLIANCE_CHECKLIST +
     PILLAR_SCORES + STACK_RECOMMENDATION + ARCHITECTURE_OVERVIEW +
     DELIVERABLES.
  2. Monta prompt Premium em pt-BR com estrutura por tipo.
  3. Chama Anthropic/OpenAI SDK nativo (padrão Fase 9.3).
  4. Persiste em `test_specs` com module_id=NULL + status='draft'.
  5. Provenance registra contexto consolidado + LLM + prompt_hash.

Regras duras:
  - Só aceita spec_type ∈ {'security', 'compliance'}.
  - Sem Premium configurado → RuntimeError (caller traduz 503). Não há
    fallback para Ollama — alta criticidade não usa local.
  - Regeneração rebaixa status pra 'draft' e zera approvals (regra
    idêntica à Fase 10.2).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    IngestedDocument, ModuleCandidate, OCG, TestSpec,
)

logger = structlog.get_logger(__name__)


SUPPORTED_GLOBAL_TYPES = ("security", "compliance")

PREMIUM_PROVIDERS = ("anthropic", "openai")

DEFAULT_PREMIUM_MODEL = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
}


SYSTEM_PROMPT = """Você é um arquiteto sênior de segurança e compliance.
Sempre responde em português-BR e em markdown puro (sem code fences
envolvendo a resposta toda, sem preâmbulo).

Você é **honesto**: nunca inventa obrigações legais ou controles ISO/LGPD
que não tenham contexto claro no OCG; prefere dizer "requer análise
jurídica especializada" ou "depende de confirmação do DPO" quando a
decisão está fora do escopo técnico do plano de testes.

Você é **específico**: escreve cenários testáveis, não discursos
genéricos sobre segurança. Prioriza controles concretos que Dev/QA
podem validar."""


SECURITY_TEMPLATE = """Gere um PLANO DE TESTES DE SEGURANÇA consolidado
pro projeto abaixo. O plano é **global** — cobre o projeto inteiro,
não um módulo específico.

## Contexto consolidado (OCG v{ocg_version})

### Perfil do projeto
{project_profile_block}

### Stack
{stack_block}

### Arquitetura
{architecture_block}

### Pilares de governança (scores)
{pillars_block}

### Entregáveis declarados
{deliverables_block}

### Módulos no Roadmap (resumo)
{modules_summary}

---

Estrutura obrigatória da saída (markdown):

## Objetivo
Duas frases no máximo: qual é o risco que este plano mitiga.

## Modelo de ameaças (STRIDE resumido)
Lista priorizada das ameaças relevantes pro contexto declarado
(Spoofing / Tampering / Repudiation / Info Disclosure / DoS /
Elevation of Privilege). Para cada ameaça:
- Descrição curta.
- Vetor provável no projeto (ex: "endpoint /api/v1/login sem rate limit").
- Severidade (Crítica / Alta / Média / Baixa) com justificativa em 1 frase.

Máximo 8 ameaças.

## Controles obrigatórios
Lista de controles que DEVEM estar implementados antes do go-live.
Para cada controle:
- Nome curto.
- Por que é obrigatório nesse contexto (referência ao OCG).
- Como validar (teste concreto).

Máximo 10 controles. Priorize auth, secrets, logs de auditoria, PII,
injeção, comunicação TLS.

## Testes de segurança
Cenários executáveis por Dev/QA. Cada cenário:
- Tipo (ex: autenticação, autorização, injeção, rate-limit, DoS, secrets).
- Descrição do teste.
- Critério de sucesso binário (passa/falha).

Máximo 12 testes.

## Fora do escopo técnico (reconhecimento honesto)
O que NÃO dá pra validar via testes automatizados e requer revisão
humana especializada (pen-test externo, revisão jurídica, análise de
supply chain de dependências). Lista curta.

## Riscos residuais
Aquilo que mesmo após os controles acima continua como risco aceito —
por limite de escopo ou de orçamento. Cada risco com 1 frase de
justificativa."""


COMPLIANCE_TEMPLATE = """Gere um PLANO DE TESTES DE COMPLIANCE consolidado
pro projeto abaixo. O plano é **global** — cobre o projeto inteiro,
não um módulo específico.

## Contexto consolidado (OCG v{ocg_version})

### Perfil do projeto
{project_profile_block}

### Compliance declarada
{compliance_block}

### Stack
{stack_block}

### Arquitetura
{architecture_block}

### Pilares de governança (scores)
{pillars_block}

### Entregáveis declarados
{deliverables_block}

---

Estrutura obrigatória da saída (markdown):

## Objetivo
Duas frases: que regime regulatório este plano atende e qual é o risco
de não-conformidade.

## Aderência a normas
Lista das normas relevantes pro contexto declarado (LGPD, GDPR, ISO
27001, SOC 2, PCI-DSS, etc conforme o OCG). Para cada norma:
- Cláusulas/controles mais relevantes.
- Como o projeto hoje declara atender (do OCG).
- Gap observado (se houver).

Máximo 6 normas.

## Evidências técnicas exigidas
Artefatos que precisam existir pra auditoria (logs de acesso, registros
de consentimento, termos de uso, DPIA, políticas de retenção). Cada:
- Tipo de evidência.
- Origem técnica (log do sistema, export do banco, doc manual).
- Formato e período de retenção.

Máximo 10 evidências.

## Testes de compliance
Testes executáveis que validam conformidade (não substituem auditoria,
mas criam trilha de evidência). Cada teste:
- Norma/cláusula atendida.
- O que valida.
- Como executar.
- Critério binário (conforme/não-conforme).

Máximo 12 testes.

## Decisões que exigem parecer jurídico/DPO
Tópicos que o plano técnico **não decide sozinho** — requer revisão
humana especializada (base legal de tratamento, transferência
internacional, retenção de PII, processos extraordinários de LGPD).
Lista curta.

## Riscos de não-conformidade
Riscos residuais de compliance com severidade (Crítica/Alta/Média/Baixa)."""


TEMPLATE_BY_TYPE = {
    "security": SECURITY_TEMPLATE,
    "compliance": COMPLIANCE_TEMPLATE,
}


async def generate_global_spec(
    db: AsyncSession,
    project_id: UUID,
    spec_type: str,
) -> TestSpec:
    """Gera (ou regera) TestSpec global de security ou compliance.

    Levanta:
      - `ValueError` se spec_type ∉ {security, compliance}.
      - `ValueError` se projeto inexistente (via OCG não encontrado).
      - `RuntimeError` se nenhum provider Premium configurado.
    """
    if spec_type not in SUPPORTED_GLOBAL_TYPES:
        raise ValueError(
            f"spec_type '{spec_type}' não suportado aqui. "
            f"Aceitos: {SUPPORTED_GLOBAL_TYPES}. "
            f"Unit/integration/e2e são por módulo (Fase 10.2, Ollama)."
        )

    config = await _resolve_premium_config(db, project_id)
    if not config:
        raise RuntimeError(
            "Nenhum provider Premium (Anthropic/OpenAI) configurado no projeto. "
            "Specs globais de security/compliance são alta criticidade "
            "(§6.3) e não caem para LLM local. Configure em Settings → IA."
        )

    ocg_ctx = await _load_ocg_context(db, project_id)
    if ocg_ctx["version"] is None:
        raise ValueError(
            f"Projeto {project_id} não tem OCG — gere via questionário antes "
            f"de solicitar specs globais."
        )

    modules_summary = await _load_modules_summary(db, project_id)
    prompt = _build_prompt(
        spec_type=spec_type, ocg_ctx=ocg_ctx, modules_summary=modules_summary,
    )

    content = await _call_premium(
        provider=config["provider"], model=config["model"],
        api_key=config["api_key"],
        system_prompt=SYSTEM_PROMPT, user_prompt=prompt,
    )
    content = _strip_outer_fence(content.strip())

    # Upsert via busca explícita (PostgreSQL trata NULL como distinto
    # em UniqueConstraint; lookup manual é mais portátil)
    spec = await _find_existing_global(db, project_id, spec_type)
    is_new = spec is None

    provenance = _build_provenance(
        ocg_ctx=ocg_ctx, modules_summary=modules_summary,
        prompt=prompt, config=config,
    )

    if spec is None:
        spec = TestSpec(
            project_id=project_id,
            module_id=None,  # global
            spec_type=spec_type,
            content=content,
            provenance_json=json.dumps(provenance, ensure_ascii=False),
            ocg_version_at_generation=ocg_ctx.get("version"),
            generated_at=datetime.now(timezone.utc),
            generator_provider=config["provider"],
            generator_model=config["model"],
            status="draft",
        )
        db.add(spec)
    else:
        spec.content = content
        spec.provenance_json = json.dumps(provenance, ensure_ascii=False)
        spec.ocg_version_at_generation = ocg_ctx.get("version")
        spec.generated_at = datetime.now(timezone.utc)
        spec.generator_provider = config["provider"]
        spec.generator_model = config["model"]
        # Regeneração rebaixa pra draft (regra dura §7 MVP 10)
        spec.status = "draft"
        spec.approved_by = None
        spec.approved_at = None
        spec.rejected_by = None
        spec.rejection_reason = None

    await db.commit()
    logger.info(
        "global_spec.generated",
        spec_id=str(spec.id), project_id=str(project_id),
        spec_type=spec_type, new=is_new,
        provider=config["provider"], model=config["model"],
        content_chars=len(content),
    )
    return spec


async def regenerate_all_global_specs(
    db: AsyncSession, project_id: UUID,
) -> dict[str, Any]:
    """Regenera security + compliance pra um projeto (bulk)."""
    report: dict[str, Any] = {
        "generated": 0, "failed": 0, "errors": [],
    }
    for st in SUPPORTED_GLOBAL_TYPES:
        try:
            await generate_global_spec(db, project_id, st)
            report["generated"] += 1
        except Exception as exc:
            report["failed"] += 1
            report["errors"].append({
                "spec_type": st,
                "error": str(exc)[:300],
            })
            logger.warning(
                "global_spec.generation_failed",
                spec_type=st, project_id=str(project_id), error=str(exc),
            )
    return report


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

async def _resolve_premium_config(
    db: AsyncSession, project_id: UUID,
) -> Optional[dict[str, Any]]:
    """Anthropic preferido > OpenAI. Ollama explicitamente ignorado
    (§6.3 — alta criticidade). Mesma lógica da Fase 9.3."""
    from app.services.ai_key_resolver import AIKeyResolver

    chain = await AIKeyResolver.resolve_project_provider_chain(db, project_id)
    for entry in chain:
        provider = (entry.get("provider") or "").lower()
        if provider not in PREMIUM_PROVIDERS:
            continue
        api_key = await AIKeyResolver.get_project_key(db, project_id, provider)
        if not api_key:
            continue
        model = entry.get("model") or DEFAULT_PREMIUM_MODEL[provider]
        return {"provider": provider, "model": model, "api_key": api_key}
    return None


async def _load_ocg_context(
    db: AsyncSession, project_id: UUID,
) -> dict[str, Any]:
    row = await db.execute(
        select(OCG).where(OCG.project_id == project_id)
        .order_by(OCG.version.desc()).limit(1)
    )
    ocg = row.scalar_one_or_none()
    if not ocg:
        return {"version": None, "data": {}, "questionnaire_id": None, "ingested_doc_ids": []}
    try:
        data = json.loads(ocg.ocg_data) if ocg.ocg_data else {}
    except (ValueError, TypeError):
        data = {}
    # MVP 34: filtra docs soft-deleted — spec global não deve incluir docs deletados.
    docs_rows = await db.execute(
        select(IngestedDocument.id).where(
            IngestedDocument.project_id == project_id,
            IngestedDocument.arguider_status == "completed",
            IngestedDocument.deleted_at.is_(None),
        )
    )
    doc_ids = [str(r[0]) for r in docs_rows.all()]
    return {
        "version": ocg.version,
        "data": data,
        "questionnaire_id": str(ocg.questionnaire_id) if ocg.questionnaire_id else None,
        "ingested_doc_ids": doc_ids,
    }


async def _load_modules_summary(
    db: AsyncSession, project_id: UUID, max_items: int = 20,
) -> list[dict[str, Any]]:
    """Lista compacta dos módulos pro prompt entender o que será construído."""
    rows = await db.execute(
        select(ModuleCandidate).where(ModuleCandidate.project_id == project_id)
    )
    items = rows.scalars().all()
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    items_sorted = sorted(
        items,
        key=lambda m: (priority_rank.get(m.priority or "medium", 1), m.name or ""),
    )[:max_items]
    return [
        {
            "id": str(m.id),
            "name": m.name or "(sem nome)",
            "module_type": m.module_type or "feature",
            "priority": m.priority or "medium",
        }
        for m in items_sorted
    ]


async def _find_existing_global(
    db: AsyncSession, project_id: UUID, spec_type: str,
) -> Optional[TestSpec]:
    row = await db.execute(
        select(TestSpec).where(
            TestSpec.project_id == project_id,
            TestSpec.module_id.is_(None),
            TestSpec.spec_type == spec_type,
        )
    )
    return row.scalar_one_or_none()


def _build_prompt(
    *, spec_type: str, ocg_ctx: dict[str, Any],
    modules_summary: list[dict[str, Any]],
) -> str:
    template = TEMPLATE_BY_TYPE[spec_type]
    data = ocg_ctx.get("data", {})

    profile = data.get("PROJECT_PROFILE") or {}
    arch = data.get("ARCHITECTURE_OVERVIEW") or {}
    stack = data.get("STACK_RECOMMENDATION") or {}
    pillars = data.get("PILLAR_SCORES") or {}
    compliance = data.get("COMPLIANCE_CHECKLIST") or {}
    deliverables_src = data.get("DELIVERABLES") or {}

    project_profile_block = _render_dict(
        profile, include=(
            "initiative_type", "handles_pii", "pii_expected",
            "criticality_level", "frontend_type", "backend_type",
            "output_formats", "deliverables",
        ),
    )
    stack_block = _render_stack(stack)
    architecture_block = _render_dict(
        arch, include=(
            "architectural_profile", "execution_model", "multi_tenant",
            "high_availability", "async_processing", "deliverables",
        ),
    )
    pillars_block = _render_pillars(pillars)
    compliance_block = _render_compliance(compliance)
    deliverables_block = _render_deliverables(deliverables_src)
    modules_block = "\n".join(
        f"- {m['name']} ({m['module_type']}, prioridade {m['priority']})"
        for m in modules_summary
    ) or "(nenhum módulo no Roadmap)"

    return template.format(
        ocg_version=ocg_ctx.get("version") or "?",
        project_profile_block=project_profile_block,
        stack_block=stack_block,
        architecture_block=architecture_block,
        pillars_block=pillars_block,
        compliance_block=compliance_block,
        deliverables_block=deliverables_block,
        modules_summary=modules_block,
    )


def _render_dict(d: dict[str, Any], *, include: tuple[str, ...]) -> str:
    """Render linhas 'chave: valor' só pras chaves relevantes; 'valor'
    formatado pra list/dict com join simples."""
    if not d:
        return "(não declarado no OCG)"
    lines = []
    for key in include:
        if key not in d:
            continue
        value = d[key]
        if isinstance(value, list):
            rendered = ", ".join(str(x) for x in value) if value else "—"
        elif isinstance(value, dict):
            rendered = ", ".join(f"{k}={v}" for k, v in value.items()) or "—"
        elif value is None:
            rendered = "—"
        else:
            rendered = str(value)
        lines.append(f"- {key}: {rendered}")
    return "\n".join(lines) if lines else "(chaves relevantes não preenchidas)"


def _render_stack(stack: dict[str, Any]) -> str:
    if not stack:
        return "(stack não declarado)"
    lines = []
    for layer in ("backend", "frontend", "database", "cache", "messaging", "ai"):
        sub = stack.get(layer)
        if not isinstance(sub, dict):
            continue
        enabled = sub.get("enabled")
        if enabled is False:
            lines.append(f"- {layer}: não habilitado")
            continue
        bits = []
        for k in ("framework", "stack", "language", "engine", "provider", "purpose"):
            v = sub.get(k)
            if isinstance(v, list) and v:
                bits.append(f"{k}={', '.join(str(x) for x in v)}")
            elif isinstance(v, str) and v:
                bits.append(f"{k}={v}")
        if bits:
            lines.append(f"- {layer}: " + "; ".join(bits))
    return "\n".join(lines) if lines else "(stack com chaves relevantes vazias)"


def _render_pillars(pillars: Any) -> str:
    if not isinstance(pillars, dict) or not pillars:
        return "(pilares não avaliados)"
    lines = []
    for pk in sorted(pillars.keys()):
        pv = pillars[pk]
        if isinstance(pv, dict):
            score = pv.get("score")
            status = pv.get("status")
            lines.append(f"- {pk}: score={score} status={status}")
        else:
            lines.append(f"- {pk}: {pv}")
    return "\n".join(lines)


def _render_compliance(compliance: Any) -> str:
    if not compliance:
        return "(compliance não declarada)"
    if isinstance(compliance, dict):
        lines = []
        for k, v in compliance.items():
            if v:
                lines.append(f"- {k}: {v if isinstance(v, str) else 'sim'}")
        return "\n".join(lines) if lines else "(dict de compliance vazio)"
    if isinstance(compliance, list):
        return "\n".join(f"- {x}" for x in compliance) or "(lista vazia)"
    return str(compliance)


def _render_deliverables(deliverables: Any) -> str:
    if not deliverables:
        return "(entregáveis não declarados)"
    if isinstance(deliverables, dict):
        parts = []
        for k, v in deliverables.items():
            if isinstance(v, list):
                parts.append(f"- {k}: {', '.join(str(x) for x in v)}")
            else:
                parts.append(f"- {k}: {v}")
        return "\n".join(parts)
    if isinstance(deliverables, list):
        return "\n".join(f"- {x}" for x in deliverables)
    return str(deliverables)


def _build_provenance(
    *, ocg_ctx: dict[str, Any], modules_summary: list[dict[str, Any]],
    prompt: str, config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "ocg_version": ocg_ctx.get("version"),
        "questionnaire_id": ocg_ctx.get("questionnaire_id"),
        "ingested_doc_ids": ocg_ctx.get("ingested_doc_ids", []),
        "modules_considered": [m["id"] for m in modules_summary],
        "llm": {
            "provider": config["provider"],
            "model": config["model"],
        },
        "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _call_premium(
    *, provider: str, model: str, api_key: str,
    system_prompt: str, user_prompt: str,
) -> str:
    if provider == "anthropic":
        return await _call_anthropic(api_key, model, system_prompt, user_prompt)
    if provider == "openai":
        return await _call_openai(api_key, model, system_prompt, user_prompt)
    raise ValueError(f"Provider sem handler na 10.3: {provider}")


async def _call_anthropic(api_key: str, model: str, system: str, prompt: str) -> str:
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=api_key)
    resp = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    blocks = getattr(resp, "content", []) or []
    return "\n".join(getattr(b, "text", "") or "" for b in blocks).strip()


async def _call_openai(api_key: str, model: str, system: str, prompt: str) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key)
    resp = await client.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    choices = getattr(resp, "choices", []) or []
    if not choices:
        return ""
    msg = getattr(choices[0], "message", None)
    return (getattr(msg, "content", "") or "").strip() if msg else ""


def _strip_outer_fence(text: str) -> str:
    import re
    m = re.match(
        r"^\s*```(?:markdown|md)?\s*\n?(?P<body>.*?)\n?```\s*$",
        text, re.DOTALL,
    )
    return m.group("body").strip() if m else text
