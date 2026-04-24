"""MVP 9 Fase 9.3 — Orquestração premium do Roadmap.

Contrato §6.2: avaliar se um item está pronto pra entrar no escopo do
CodeGen é decisão de **alta criticidade** — exige LLM Premium do
projeto (Anthropic/OpenAI/etc), não Ollama local.

Disparo:
  - Automático: hook após item virar `adicionado` (Fase 9.5.2 chama).
  - Manual: endpoint `POST /modules/{id}/evaluate-readiness`.

Saída persistida em `module_candidates`:
  - `readiness_status` ∈ {ready_for_codegen, partial, needs_input, unknown}
  - `readiness_gaps` — JSON list de strings curtas (até 8) descrevendo
    o que falta.
  - `dependencies_inferred` — JSON list de UUIDs/names de módulos do
    mesmo projeto que este depende.
  - `readiness_evaluated_at`, `readiness_provider`, `readiness_model`.

Usa `AIKeyResolver.resolve_project_provider_chain` pra escolher provider
premium configurado pelo GP. Anthropic primeiro (vision-capable já
preferido na Fase 3B), OpenAI fallback. Ollama é **explicitamente
ignorado** — alta criticidade não cai pra local (regra dura §6.3).

Sem premium configurado: levanta `RuntimeError`. Caller (hook) pega
e loga sem invalidar pipeline; endpoint retorna 503.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import ModuleCandidate, OCG
from app.services.ocg_reader import load_latest_ocg

logger = structlog.get_logger(__name__)


PREMIUM_PROVIDERS = ("anthropic", "openai")

DEFAULT_PREMIUM_MODEL = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
}

ORCHESTRATION_SYSTEM_PROMPT = """Você é um arquiteto sênior avaliando se
um item do Roadmap de um projeto de software tem informação técnica
suficiente para a equipe de desenvolvimento começar a gerar código.

Você sempre responde em português-BR e em JSON puro (sem code fences,
sem texto fora do JSON, sem preâmbulo). Você é honesto: nunca marca
ready_for_codegen quando há gaps relevantes; nunca inventa dependências
que não estejam contextualizadas pelos outros itens listados.

Você prefere `partial` ou `needs_input` quando há dúvida — o GP corrige
do que o Dev gerar código baseado em premissa fraca."""


ORCHESTRATION_USER_TEMPLATE = """Item alvo do Roadmap:
- Nome: {name}
- Categoria: {module_type}
- Status atual: {status}
- Descrição: {description}

Detalhamento já gerado (Fase 9.2):
{details_block}

Outros módulos do MESMO projeto (use só estes para inferir dependências):
{neighbors_block}

Contexto resumido do projeto (OCG):
- Stack backend: {backend_stack}
- Stack frontend: {frontend_stack}
- Banco de dados: {database}
- Modelo de execução: {execution_model}

Tarefa:
1. Avalie se o item está pronto pra entrar no escopo do CodeGen.
2. Liste gaps específicos (informações que faltam).
3. Identifique dependências entre os módulos listados acima.

Retorne JSON com EXATAMENTE este schema:

{{
  "readiness_status": "ready_for_codegen" | "partial" | "needs_input" | "unknown",
  "readiness_reasoning": "1 frase explicando por que esse status",
  "gaps": ["gap específico 1 (curto)", "gap 2", "..."],
  "dependencies": ["nome ou id de outro módulo deste projeto", "..."],
  "estimated_complexity": "low" | "medium" | "high"
}}

Regras DURAS:
- gaps: máximo 8 strings, cada uma até 200 chars.
- dependencies: máximo 5 nomes/ids, SOMENTE de módulos listados acima.
  Se você não consegue identificar dependência clara, retorne lista vazia.
- ready_for_codegen exige: zero gaps OBRIGATÓRIOS + dependências
  resolvidas (ou item independente).
- partial = gaps cosméticos ou opcionais; CodeGen pode iniciar mas
  precisa de input do GP em pontos específicos.
- needs_input = falta informação CRÍTICA (ex: contrato de API externa,
  schema de dados, fluxo de autenticação). CodeGen não deve iniciar.
- unknown = falta de contexto pra avaliar — GP precisa enriquecer OCG
  ou o detalhamento do item antes."""


CANONICAL_READINESS = {"ready_for_codegen", "partial", "needs_input", "unknown"}


async def evaluate_module_readiness(
    db: AsyncSession,
    project_id: UUID,
    module_id: UUID,
) -> dict[str, Any]:
    """Avalia readiness do módulo via Premium. Persiste e retorna o resultado.

    Levanta:
      - `ValueError` se módulo não existe ou não pertence ao projeto.
      - `RuntimeError` se nenhum provider premium configurado.
    """
    module = await db.get(ModuleCandidate, module_id)
    if not module or module.project_id != project_id:
        raise ValueError(f"Módulo {module_id} não encontrado no projeto {project_id}")

    config = await _resolve_premium_config(db, project_id)
    if not config:
        raise RuntimeError(
            "Nenhum provider Premium (Anthropic/OpenAI) configurado no projeto. "
            "Avaliação de readiness é alta criticidade e não cai para LLM local "
            "(contrato §6.3). Configure em Settings → IA."
        )

    ocg_data = await _load_latest_ocg(db, project_id)
    neighbors = await _load_neighbor_modules(db, project_id, exclude_id=module_id)
    details = _safe_load_details(module)

    user_prompt = _build_user_prompt(
        module=module, details=details, neighbors=neighbors, ocg_data=ocg_data or {},
    )

    response_text = await _call_premium(
        provider=config["provider"], model=config["model"],
        api_key=config["api_key"],
        system_prompt=ORCHESTRATION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )

    parsed = _parse_response(response_text)
    parsed = _normalize_response(parsed, neighbors=neighbors)

    # Persiste
    module.readiness_status = parsed["readiness_status"]
    module.readiness_gaps = json.dumps(parsed["gaps"], ensure_ascii=False)
    module.dependencies_inferred = json.dumps(parsed["dependencies"], ensure_ascii=False)
    module.readiness_evaluated_at = datetime.now(timezone.utc)
    module.readiness_provider = config["provider"]
    module.readiness_model = config["model"]
    await db.commit()

    parsed["_provider"] = config["provider"]
    parsed["_model"] = config["model"]
    parsed["_evaluated_at"] = module.readiness_evaluated_at.isoformat()
    return parsed


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

async def _resolve_premium_config(
    db: AsyncSession, project_id: UUID
) -> Optional[dict[str, Any]]:
    """Procura primeiro provider Premium da chain do projeto que tenha
    chave configurada. Anthropic é preferido."""
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


async def _load_latest_ocg(db: AsyncSession, project_id: UUID) -> Optional[dict[str, Any]]:
    """Thin wrapper sobre ocg_reader.load_latest_ocg que parseia o JSON do campo ocg_data."""
    ocg = await load_latest_ocg(db, project_id)
    if not ocg or not ocg.ocg_data:
        return None
    try:
        return json.loads(ocg.ocg_data)
    except (ValueError, TypeError):
        return None


async def _load_neighbor_modules(
    db: AsyncSession, project_id: UUID, *, exclude_id: UUID,
) -> list[dict[str, Any]]:
    """Lista os outros módulos do mesmo projeto pra inferir dependências.

    Limita a 30 itens (priority desc, name) pra prompt não estourar.
    """
    rows = await db.execute(
        select(ModuleCandidate)
        .where(ModuleCandidate.project_id == project_id)
        .where(ModuleCandidate.id != exclude_id)
    )
    items = rows.scalars().all()
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    items_sorted = sorted(
        items,
        key=lambda m: (priority_rank.get(m.priority or "medium", 1), m.name or ""),
    )[:30]
    return [
        {
            "id": str(m.id),
            "name": m.name or "(sem nome)",
            "module_type": m.module_type or "feature",
            "status": m.status or "sugerido",
        }
        for m in items_sorted
    ]


def _safe_load_details(module: ModuleCandidate) -> dict[str, Any]:
    if not module.details_json:
        return {}
    try:
        return json.loads(module.details_json)
    except (ValueError, TypeError):
        return {}


def _build_user_prompt(
    *, module: ModuleCandidate, details: dict[str, Any],
    neighbors: list[dict[str, Any]], ocg_data: dict[str, Any],
) -> str:
    stack = ocg_data.get("STACK_RECOMMENDATION") or {}
    arch = ocg_data.get("ARCHITECTURE_OVERVIEW") or {}

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
        details_lines = [
            f"- O que é: {details.get('what_it_is', '—')}",
            f"- Pré-requisitos: {', '.join(details.get('prerequisites', [])) or '—'}",
            f"- Inputs faltantes detectados: {', '.join(details.get('missing_inputs', [])) or '—'}",
        ]
        details_block = "\n".join(details_lines)
    else:
        details_block = "(detalhamento ainda não gerado — Fase 9.2 não rodou pra este item)"

    if neighbors:
        neighbors_block = "\n".join(
            f"  · {n['name']} (id={n['id']}, tipo={n['module_type']}, status={n['status']})"
            for n in neighbors
        )
    else:
        neighbors_block = "(este é o único módulo do projeto)"

    return ORCHESTRATION_USER_TEMPLATE.format(
        name=module.name or "(sem nome)",
        module_type=module.module_type or "feature",
        status=module.status or "sugerido",
        description=module.description or "(sem descrição)",
        details_block=details_block,
        neighbors_block=neighbors_block,
        backend_stack=backend_stack,
        frontend_stack=frontend_stack,
        database=db_engine,
        execution_model=exec_model,
    )


async def _call_premium(
    *, provider: str, model: str, api_key: str,
    system_prompt: str, user_prompt: str,
) -> str:
    """Chama Anthropic OU OpenAI. Retorna texto bruto pro caller parsear."""
    if provider == "anthropic":
        return await _call_anthropic(api_key, model, system_prompt, user_prompt)
    if provider == "openai":
        return await _call_openai(api_key, model, system_prompt, user_prompt)
    raise ValueError(f"Provider sem handler na 9.3: {provider}")


async def _call_anthropic(api_key: str, model: str, system: str, prompt: str) -> str:
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=api_key)
    resp = await client.messages.create(
        model=model,
        max_tokens=2048,
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
        max_tokens=2048,
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


# ---------------------------------------------------------------------------
# Parsing + normalização (mesmo padrão do Arguider DT-067)
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n?(?P<body>.*?)\n?```\s*$", re.DOTALL)


def _parse_response(text: str) -> dict[str, Any]:
    if not text:
        return {}
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    m = _FENCE_RE.match(stripped)
    if m:
        try:
            return json.loads(m.group("body").strip())
        except json.JSONDecodeError:
            pass
    # balanced object
    start = stripped.find("{")
    if start >= 0:
        depth = 0; in_str = False; esc = False
        for i in range(start, len(stripped)):
            c = stripped[i]
            if esc:
                esc = False; continue
            if c == "\\":
                esc = True; continue
            if c == '"':
                in_str = not in_str; continue
            if in_str:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(stripped[start : i + 1])
                    except json.JSONDecodeError:
                        break
    logger.warning("orchestration.parse_failed", preview=text[:300])
    return {}


def _normalize_response(
    parsed: dict[str, Any], *, neighbors: list[dict[str, Any]],
) -> dict[str, Any]:
    """Garante shape estável e limites; sanitiza dependencies pra só
    nomes/ids que existem em neighbors."""
    status = str(parsed.get("readiness_status") or "unknown").strip().lower()
    if status not in CANONICAL_READINESS:
        status = "unknown"

    reasoning = str(parsed.get("readiness_reasoning") or "").strip()[:400]

    gaps_raw = parsed.get("gaps") or []
    gaps: list[str] = []
    if isinstance(gaps_raw, list):
        for g in gaps_raw[:8]:
            if isinstance(g, str) and g.strip():
                gaps.append(g.strip()[:200])
            elif isinstance(g, dict):
                t = g.get("text") or g.get("description") or g.get("name")
                if t:
                    gaps.append(str(t)[:200])

    deps_raw = parsed.get("dependencies") or []
    valid_ids = {n["id"] for n in neighbors}
    valid_names = {n["name"].strip().lower() for n in neighbors}
    deps: list[str] = []
    if isinstance(deps_raw, list):
        for d in deps_raw[:5]:
            v = str(d).strip() if isinstance(d, (str, int, float)) else None
            if isinstance(d, dict):
                v = str(d.get("id") or d.get("name") or "").strip()
            if not v:
                continue
            # Aceita se UUID match ou name match (case-insensitive)
            if v in valid_ids or v.lower() in valid_names:
                deps.append(v)

    complexity_raw = str(parsed.get("estimated_complexity") or "").strip().lower()
    complexity = complexity_raw if complexity_raw in ("low", "medium", "high") else None

    # Sanity: se status=ready_for_codegen mas há gaps, rebaixa pra partial
    if status == "ready_for_codegen" and gaps:
        logger.info("orchestration.demoted_ready_to_partial", gap_count=len(gaps))
        status = "partial"

    return {
        "readiness_status": status,
        "readiness_reasoning": reasoning,
        "gaps": gaps,
        "dependencies": deps,
        "estimated_complexity": complexity,
    }
