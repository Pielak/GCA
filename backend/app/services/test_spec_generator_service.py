"""MVP 10 Fase 10.2 — Geração de specs unit/integration via Ollama.

Contrato §7 MVP 10 (§6.2 roteamento híbrido): gerar plano de teste por
módulo é **baixa criticidade** — repetitivo, estruturado, baixa
variabilidade. Cai pra Ollama local. Specs de security/compliance
(globais) ficam pra Fase 10.3 com Premium.

Pipeline:
  1. Carrega módulo + detalhamento (Fase 9.2) + OCG snippet + vizinhos.
  2. Monta prompt markdown estruturado.
  3. Chama Ollama via AIKeyResolver chain (filtrado pra `ollama`).
  4. Persiste em `test_specs` com UniqueConstraint (project, module,
     spec_type) — regenerar sobrescreve in-place mantendo `id`.
  5. provenance_json registra OCG version, questionário, ingestões
     consideradas, LLM, timestamp — pro modal da Fase 10.5 exibir.

Regras duras:
  - Só aplica pra módulos com `module_type` canônico do Roadmap do MVP 9.
  - Não gera spec pra `security` ou `compliance` aqui (globais, Fase 10.3).
  - Sem Ollama configurado → RuntimeError (caller traduz em 503).
  - Integration spec inclui vizinhos e DAG da Fase 9.3 quando disponível.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    IngestedDocument, ModuleCandidate, OCG, Questionnaire, TestSpec,
)

logger = structlog.get_logger(__name__)


#: Tipos de spec que este service aceita. `security` e `compliance` ficam
#: pra Fase 10.3 (Premium obrigatório).
SUPPORTED_TYPES_LOCAL = ("unit", "integration", "e2e")

#: Timeout generoso (Ollama 7B em CPU pode levar ~1-2 min na 1ª chamada,
#: depois fica em memória). Mesmo padrão da Fase 9.2 (DT-069).
OLLAMA_READ_TIMEOUT_SECONDS = 240


SYSTEM_PROMPT = """Você é um engenheiro de teste sênior. Sempre responde
em português-BR e em markdown puro (sem code fences envolvendo a resposta
toda, sem preâmbulo). Foque em testar comportamento, não implementação.
Nunca invente dependências que não estejam contextualizadas pelos outros
módulos listados. Prefira dizer "depende de confirmação do GP" quando
não tem certeza — é mais útil que chutar."""


UNIT_TEMPLATE = """Gere um plano de testes UNITÁRIOS pro módulo abaixo.

Módulo: **{name}** (categoria: {module_type})
Descrição: {description}

Detalhamento técnico (Fase 9.2, gerado por IA local):
{details_block}

Stack do projeto:
- Backend: {backend_stack}
- Frontend: {frontend_stack}
- Banco: {database}

Estrutura obrigatória da saída (markdown):

## Objetivo
Uma frase: o que esses testes unitários protegem.

## Escopo
Lista do que está DENTRO do escopo unitário e o que fica pra integração.

## Casos de teste
Lista numerada (1., 2., 3., ...) de cenários concretos. Cada caso:
- Frase curta descrevendo comportamento.
- Entrada de exemplo (quando aplicável).
- Resultado esperado.

Máximo 12 casos. Priorize caminho feliz + caminhos de erro claros.

## Casos-limite
Entradas extremas (null, vazio, overflow, unicode).

## Mocks e dependências
O que precisa ser mockado; dependências externas a evitar.

## Cobertura esperada
% de cobertura de linhas/branches que justifica este plano."""


INTEGRATION_TEMPLATE = """Gere um plano de testes de INTEGRAÇÃO pro módulo abaixo.

Módulo: **{name}** (categoria: {module_type})
Descrição: {description}

Detalhamento técnico (Fase 9.2):
{details_block}

Módulos vizinhos do mesmo projeto (pra inferir integrações):
{neighbors_block}

Dependências inferidas (Fase 9.3): {deps_label}

Stack do projeto:
- Backend: {backend_stack}
- Banco: {database}
- Modelo de execução: {execution_model}

Estrutura obrigatória da saída (markdown):

## Objetivo
Uma frase: quais integrações esse plano valida.

## Pontos de integração
Lista de interfaces reais entre este módulo e outros. Para cada:
- Módulo/serviço externo envolvido.
- Formato da interação (REST, fila, DB, FS, etc).
- Dado transportado.

## Cenários de integração
Lista numerada de cenários ponta-a-ponta. Cada cenário:
- Contexto inicial.
- Ação.
- Verificação de efeitos em AMBOS os lados.

Máximo 8 cenários.

## Infraestrutura de teste
Containers, banco de teste, fixtures que precisam estar de pé.

## Falhas a simular
Timeout, 5xx, rede fora, contrato quebrado."""


E2E_TEMPLATE = """Gere um plano de testes E2E (end-to-end) pro módulo abaixo.

Módulo: **{name}** (categoria: {module_type})
Descrição: {description}

Detalhamento técnico:
{details_block}

Estrutura obrigatória da saída (markdown):

## Objetivo
Cenário de usuário final completo que esse E2E valida.

## Personas envolvidas
GP/Dev/Tester/QA/usuário externo — conforme aplicável.

## Fluxo ponta-a-ponta
Passos numerados do início ao fim. Cada passo:
- Ator.
- Ação.
- Estado observável do sistema após.

## Critérios de aceite
Condição binária de sucesso (✓/✗).

## Dados e ambiente
Seeds/fixtures necessários.

Máximo 1 fluxo principal + 2 variações de exceção."""


TEMPLATE_BY_TYPE = {
    "unit": UNIT_TEMPLATE,
    "integration": INTEGRATION_TEMPLATE,
    "e2e": E2E_TEMPLATE,
}


async def generate_module_spec(
    db: AsyncSession,
    project_id: UUID,
    module_id: UUID,
    spec_type: str,
) -> TestSpec:
    """Gera (ou regera) um TestSpec de `spec_type` para o módulo dado.

    Idempotente: se já existe spec com (project, module, type), faz UPDATE
    in-place mantendo `id` e `created_at`; atualiza `updated_at`,
    `generated_at` e `provenance_json`.

    Levanta:
      - `ValueError` se módulo não existe ou não pertence ao projeto.
      - `ValueError` se `spec_type` fora de {unit, integration, e2e}.
      - `RuntimeError` se Ollama não configurado.
    """
    if spec_type not in SUPPORTED_TYPES_LOCAL:
        raise ValueError(
            f"spec_type '{spec_type}' não suportado aqui. "
            f"Aceitos: {SUPPORTED_TYPES_LOCAL}. "
            f"Security/compliance são globais (Fase 10.3, Premium)."
        )

    module = await db.get(ModuleCandidate, module_id)
    if not module or module.project_id != project_id:
        raise ValueError(f"Módulo {module_id} não encontrado no projeto {project_id}")

    config = await _resolve_ollama_config(db, project_id)
    if not config:
        raise RuntimeError(
            "Nenhum provider Ollama configurado no projeto. "
            "Geração de specs unit/integration exige LLM local "
            "(contrato §6.2 — baixa criticidade). Configure em "
            "Settings → IA ou rode sem gerar."
        )

    ocg_ctx = await _load_ocg_context(db, project_id)
    neighbors = await _load_neighbors(db, project_id, exclude_id=module_id)
    details = _safe_load_details(module)

    prompt = _build_prompt(
        spec_type=spec_type, module=module, details=details,
        ocg_ctx=ocg_ctx, neighbors=neighbors,
    )

    content = await _call_ollama(
        base_url=config["base_url"], model=config["model"],
        system_prompt=SYSTEM_PROMPT, user_prompt=prompt,
    )
    content = _strip_outer_fence(content.strip())

    # Idempotência: upsert manual
    spec = await _find_existing(db, project_id, module_id, spec_type)
    is_new = spec is None

    provenance = _build_provenance(
        module=module, ocg_ctx=ocg_ctx, neighbors=neighbors,
        prompt=prompt, config=config,
    )

    if spec is None:
        spec = TestSpec(
            project_id=project_id,
            module_id=module_id,
            spec_type=spec_type,
            content=content,
            provenance_json=json.dumps(provenance, ensure_ascii=False),
            ocg_version_at_generation=ocg_ctx.get("version"),
            generated_at=datetime.now(timezone.utc),
            generator_provider="ollama",
            generator_model=config["model"],
            status="draft",
        )
        db.add(spec)
    else:
        spec.content = content
        spec.provenance_json = json.dumps(provenance, ensure_ascii=False)
        spec.ocg_version_at_generation = ocg_ctx.get("version")
        spec.generated_at = datetime.now(timezone.utc)
        spec.generator_provider = "ollama"
        spec.generator_model = config["model"]
        # Regeneração volta pra draft mesmo se estava approved/rejected.
        # Conteúdo novo exige re-revisão (regra dura §7 MVP 10).
        spec.status = "draft"
        spec.approved_by = None
        spec.approved_at = None
        spec.rejected_by = None
        spec.rejection_reason = None

    await db.commit()
    logger.info(
        "test_spec.generated",
        spec_id=str(spec.id), project_id=str(project_id),
        module_id=str(module_id), spec_type=spec_type,
        new=is_new, content_chars=len(content),
    )
    return spec


async def regenerate_project_specs(
    db: AsyncSession,
    project_id: UUID,
    spec_types: tuple[str, ...] = ("unit", "integration"),
    module_type_filter: Optional[tuple[str, ...]] = None,
) -> dict[str, Any]:
    """Regenera specs em bulk para todos os módulos do projeto.

    `module_type_filter`: se fornecido, só gera pra módulos dessas
    categorias (ex: só 'backend_service' + 'feature'). Default: todas
    as categorias canônicas do MVP 9.
    """
    if module_type_filter is None:
        module_type_filter = (
            "feature", "backend_service", "middleware",
            "infrastructure", "observability", "deploy_pipeline",
        )

    rows = await db.execute(
        select(ModuleCandidate).where(
            ModuleCandidate.project_id == project_id,
            ModuleCandidate.module_type.in_(module_type_filter),
        )
    )
    modules = rows.scalars().all()

    report = {
        "total_modules": len(modules),
        "spec_types": list(spec_types),
        "generated": 0,
        "failed": 0,
        "errors": [],
    }

    for mc in modules:
        for st in spec_types:
            if st not in SUPPORTED_TYPES_LOCAL:
                continue
            try:
                await generate_module_spec(db, project_id, mc.id, st)
                report["generated"] += 1
            except Exception as exc:
                report["failed"] += 1
                report["errors"].append({
                    "module_id": str(mc.id),
                    "module_name": mc.name,
                    "spec_type": st,
                    "error": str(exc)[:300],
                })
                logger.warning(
                    "test_spec.generation_failed",
                    module_id=str(mc.id), spec_type=st, error=str(exc),
                )

    logger.info("test_spec.bulk_regenerate_done", **{
        k: v for k, v in report.items() if k != "errors"
    })
    return report


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

async def _resolve_ollama_config(
    db: AsyncSession, project_id: UUID,
) -> Optional[dict[str, Any]]:
    """Mesma lógica do module_details_service.9.2 — Ollama na chain
    com base_url válido."""
    from app.services.ai_key_resolver import AIKeyResolver
    chain = await AIKeyResolver.resolve_project_provider_chain(db, project_id)
    for entry in chain:
        if (entry.get("provider") or "").lower() != "ollama":
            continue
        base_url = entry.get("base_url")
        if not base_url:
            continue
        return {
            "base_url": base_url.rstrip("/"),
            "model": entry.get("model") or "qwen2.5-coder:7b",
        }
    return None


async def _load_ocg_context(db: AsyncSession, project_id: UUID) -> dict[str, Any]:
    """Carrega OCG mais recente + questionnaire id + ingested doc ids
    pra serializar em provenance."""
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

    # Docs ingeridos considerados: todos os que viraram análise do projeto.
    docs_rows = await db.execute(
        select(IngestedDocument.id).where(
            IngestedDocument.project_id == project_id,
            IngestedDocument.arguider_status == "completed",
        )
    )
    doc_ids = [str(r[0]) for r in docs_rows.all()]

    return {
        "version": ocg.version,
        "data": data,
        "questionnaire_id": str(ocg.questionnaire_id) if ocg.questionnaire_id else None,
        "ingested_doc_ids": doc_ids,
    }


async def _load_neighbors(
    db: AsyncSession, project_id: UUID, exclude_id: UUID,
) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(ModuleCandidate).where(
            ModuleCandidate.project_id == project_id,
            ModuleCandidate.id != exclude_id,
        )
    )
    items = rows.scalars().all()
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    items_sorted = sorted(
        items,
        key=lambda m: (priority_rank.get(m.priority or "medium", 1), m.name or ""),
    )[:25]
    return [
        {"id": str(m.id), "name": m.name or "(sem nome)",
         "module_type": m.module_type or "feature"}
        for m in items_sorted
    ]


def _safe_load_details(module: ModuleCandidate) -> dict[str, Any]:
    if not module.details_json:
        return {}
    try:
        return json.loads(module.details_json)
    except (ValueError, TypeError):
        return {}


def _build_prompt(
    *, spec_type: str, module: ModuleCandidate, details: dict[str, Any],
    ocg_ctx: dict[str, Any], neighbors: list[dict[str, Any]],
) -> str:
    template = TEMPLATE_BY_TYPE[spec_type]

    stack = ocg_ctx.get("data", {}).get("STACK_RECOMMENDATION") or {}
    arch = ocg_ctx.get("data", {}).get("ARCHITECTURE_OVERVIEW") or {}

    backend = stack.get("backend") or {}
    frontend = stack.get("frontend") or {}
    database = stack.get("database") or {}

    def _list_str(v):
        if isinstance(v, list) and v:
            return ", ".join(str(x) for x in v)
        return str(v) if v else "—"

    backend_stack = _list_str(backend.get("framework")) if backend.get("enabled") else "não habilitado"
    frontend_stack = _list_str(frontend.get("stack")) if frontend.get("enabled") else "não habilitado"
    db_engine = database.get("engine") or "—"
    exec_model = _list_str(arch.get("execution_model"))

    if details:
        details_block = (
            f"- O que é: {details.get('what_it_is', '—')}\n"
            f"- Pré-requisitos: {', '.join(details.get('prerequisites', [])) or '—'}\n"
            f"- Inputs faltantes: {', '.join(details.get('missing_inputs', [])) or '—'}"
        )
    else:
        details_block = "(detalhamento não gerado — considere comportamento típico da categoria)"

    neighbors_block = "\n".join(
        f"  · {n['name']} ({n['module_type']})" for n in neighbors
    ) or "(este é o único módulo do projeto)"

    # Dependências inferidas (Fase 9.3)
    deps_label = "(não avaliado — Fase 9.3 ainda não rodou)"
    if module.dependencies_inferred:
        try:
            deps = json.loads(module.dependencies_inferred)
            if deps:
                deps_label = ", ".join(str(d) for d in deps[:8])
        except (ValueError, TypeError):
            pass

    return template.format(
        name=module.name or "(sem nome)",
        module_type=module.module_type or "feature",
        description=module.description or "(sem descrição)",
        details_block=details_block,
        backend_stack=backend_stack,
        frontend_stack=frontend_stack,
        database=db_engine,
        execution_model=exec_model,
        neighbors_block=neighbors_block,
        deps_label=deps_label,
    )


def _build_provenance(
    *, module: ModuleCandidate, ocg_ctx: dict[str, Any],
    neighbors: list[dict[str, Any]], prompt: str, config: dict[str, Any],
) -> dict[str, Any]:
    """Serializa contexto pro modal da Fase 10.5 explicar 'como foi criado'."""
    return {
        "ocg_version": ocg_ctx.get("version"),
        "questionnaire_id": ocg_ctx.get("questionnaire_id"),
        "ingested_doc_ids": ocg_ctx.get("ingested_doc_ids", []),
        "module_snapshot": {
            "id": str(module.id),
            "name": module.name,
            "module_type": module.module_type,
            "readiness_status": module.readiness_status,
        },
        "neighbors_considered": [n["id"] for n in neighbors],
        "llm": {
            "provider": "ollama",
            "model": config["model"],
            "base_url_host": _host_of(config["base_url"]),
        },
        "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _host_of(url: str) -> str:
    from urllib.parse import urlparse
    try:
        return urlparse(url).hostname or url
    except Exception:
        return url


async def _find_existing(
    db: AsyncSession, project_id: UUID, module_id: UUID, spec_type: str,
) -> Optional[TestSpec]:
    row = await db.execute(
        select(TestSpec).where(
            TestSpec.project_id == project_id,
            TestSpec.module_id == module_id,
            TestSpec.spec_type == spec_type,
        )
    )
    return row.scalar_one_or_none()


async def _call_ollama(
    *, base_url: str, model: str, system_prompt: str, user_prompt: str,
) -> str:
    """Copy cirúrgico do padrão da Fase 9.2 (DT-069): timeout 240s,
    OpenAI-compatible, RuntimeError em timeout com mensagem clara."""
    import time
    url = f"{base_url}/v1/chat/completions"
    payload = {
        "model": model,
        "max_tokens": 3000,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    timeout = httpx.Timeout(
        connect=10.0, read=OLLAMA_READ_TIMEOUT_SECONDS, write=10.0, pool=5.0,
    )
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url, json=payload, headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            body = resp.json()
    except httpx.ReadTimeout as exc:
        elapsed = time.monotonic() - started
        logger.warning(
            "test_spec.ollama_timeout",
            base_url=base_url, model=model, elapsed_s=round(elapsed, 1),
        )
        raise RuntimeError(
            f"Ollama ({model}) não respondeu em {OLLAMA_READ_TIMEOUT_SECONDS}s. "
            "Modelo pode estar carregando do disco (1ª chamada). Tente novamente."
        ) from exc
    elapsed = time.monotonic() - started
    logger.info("test_spec.ollama_call_ok", model=model, elapsed_s=round(elapsed, 1))
    choices = body.get("choices") or []
    if not choices:
        return ""
    return choices[0].get("message", {}).get("content", "") or ""


def _strip_outer_fence(text: str) -> str:
    """Se o LLM envolveu tudo em ```markdown ... ```, remove. Mantém
    fences internos (code blocks legítimos). Padrão DT-067."""
    import re
    m = re.match(
        r"^\s*```(?:markdown|md)?\s*\n?(?P<body>.*?)\n?```\s*$",
        text, re.DOTALL,
    )
    return m.group("body").strip() if m else text
