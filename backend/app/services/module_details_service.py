"""MVP 9 Fase 9.2 — Detalhamento on-demand de itens do Roadmap via LLM local.

Contrato §7 MVP 9 (roteamento híbrido): geração de texto explicativo é
**baixa criticidade** (§6.2) → pode rodar em LLM local (Ollama). O GP
clica num item do Roadmap e vê em 2-3 segundos: o que é, pré-requisitos,
o que falta na ingestão, exemplos. Sem custo de tokens externos.

Fluxo:
  1. GP clica no item → frontend chama GET /projects/{pid}/modules/{mid}/details
  2. Endpoint chama `get_or_generate(db, project_id, module_id)`:
     - Se `module_candidates.details_json` existe → retorna direto (cache).
     - Senão: monta prompt com contexto OCG + item, chama Ollama do projeto,
       persiste no cache e retorna.
  3. Refresh explícito (botão "Regenerar") força nova chamada.

Schema do detalhamento (JSON):
    {
      "what_it_is": "descrição técnica curta do que o item faz",
      "prerequisites": ["pré-req 1", "pré-req 2", ...],
      "missing_inputs": ["info 1 que precisa vir na ingestão", ...],
      "input_examples": ["exemplo de doc/trecho que viabiliza", ...],
      "suggested_template_sections": [
        {"section": "...", "fields": [{"name": "...", "from_ocg": "..." | null}]}
      ]
    }

`suggested_template_sections` alimenta a Fase 9.5.1 (template PDF AcroForm).
Esta fase só persiste o JSON; renderização do PDF é responsabilidade da 9.5.

Regras duras:
  - Se nenhum provider Ollama configurado, falha explícita (sem fallback
    pra premium — §6.5: detalhamento é baixa criticidade, não justifica
    custo de tokens externos).
  - LLM local não decide arquitetura — só descreve. Saída é insumo pro GP,
    não produção oficial.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import ModuleCandidate, OCG

logger = structlog.get_logger(__name__)


DETAIL_PROMPT_SYSTEM = """Você é um arquiteto de software auxiliando o
gerente de projeto (GP) a entender um item do Roadmap. Você sempre
responde em português-BR e em JSON puro (sem code fences, sem texto
fora do JSON). Foque em ser útil pro GP — não invente decisões de
arquitetura, só descreva o item e o que falta saber pra construí-lo."""


DETAIL_PROMPT_USER_TEMPLATE = """Item do Roadmap:
- Nome: {name}
- Categoria: {module_type}
- Descrição: {description}

Contexto resumido do projeto (OCG):
- Stack backend: {backend_stack}
- Stack frontend: {frontend_stack}
- Banco de dados: {database}
- Modelo de execução: {execution_model}
- Entregáveis: {deliverables}

Gere um JSON com exatamente as chaves abaixo:

{{
  "what_it_is": "Descrição técnica do item em 2-3 frases. O que ele faz, qual problema resolve.",
  "prerequisites": ["Pré-requisito 1 (curto)", "Pré-requisito 2", "..."],
  "missing_inputs": ["Informação que falta na Ingestão pra elaborar este item (curto)", "..."],
  "input_examples": ["Exemplo de documento ou trecho que viabilizaria o item", "..."],
  "suggested_template_sections": [
    {{
      "section": "Nome da seção do template",
      "fields": [
        {{"name": "campo_a", "from_ocg": "valor já no OCG ou null", "hint": "instrução curta pro GP"}}
      ]
    }}
  ]
}}

Regras:
- Máximo 4 itens em prerequisites, missing_inputs, input_examples.
- Máximo 3 sections em suggested_template_sections; cada section com até 5 fields.
- Cada string até 150 chars.
- Se algum dado já está no OCG (acima), preencha `from_ocg` com o valor; caso contrário null.
- Não inclua texto fora do JSON. Não use code fences."""


async def get_or_generate_details(
    db: AsyncSession,
    project_id: UUID,
    module_id: UUID,
    *,
    force_regenerate: bool = False,
) -> dict[str, Any]:
    """Retorna detalhamento de um item, gerando via Ollama se necessário.

    `force_regenerate=True` ignora cache e regenera. Default usa cache.
    """
    module = await db.get(ModuleCandidate, module_id)
    if not module or module.project_id != project_id:
        raise ValueError(f"Módulo {module_id} não encontrado no projeto {project_id}")

    if module.details_json and not force_regenerate:
        try:
            cached = json.loads(module.details_json)
            cached["_cached"] = True
            cached["_generated_at"] = (
                module.details_generated_at.isoformat() if module.details_generated_at else None
            )
            cached["_provider"] = module.details_provider
            cached["_model"] = module.details_model
            # MVP 9 Fase 9.3 — anexa readiness se já avaliado
            cached["readiness"] = _build_readiness_payload(module)
            return cached
        except (ValueError, TypeError):
            logger.warning("module_details.cache_corrupted", module_id=str(module_id))
            # cai pra regeneração

    ocg_data = await _load_latest_ocg(db, project_id)
    prompt = _build_user_prompt(module, ocg_data or {})

    config = await _resolve_ollama_config(db, project_id)
    if not config:
        raise RuntimeError(
            "Nenhum provider Ollama configurado no projeto. Detalhamento "
            "on-demand exige LLM local — configure em Settings → IA."
        )

    response_text = await _call_ollama(
        base_url=config["base_url"],
        model=config["model"],
        system_prompt=DETAIL_PROMPT_SYSTEM,
        user_prompt=prompt,
    )
    parsed = _parse_json_response(response_text)

    # Persistir cache
    module.details_json = json.dumps(parsed, ensure_ascii=False)
    module.details_generated_at = datetime.now(timezone.utc)
    module.details_provider = "ollama"
    module.details_model = config["model"]
    await db.commit()

    parsed["_cached"] = False
    parsed["_generated_at"] = module.details_generated_at.isoformat()
    parsed["_provider"] = "ollama"
    parsed["_model"] = config["model"]
    # MVP 9 Fase 9.3 — anexa readiness se disponível
    parsed["readiness"] = _build_readiness_payload(module)
    return parsed


def _build_readiness_payload(module) -> dict[str, Any] | None:
    """Empacota readiness_* fields do módulo num dict pra resposta API.
    Retorna None se nunca foi avaliado (Fase 9.3 ainda não rodou)."""
    if not module.readiness_status:
        return None
    try:
        gaps = json.loads(module.readiness_gaps) if module.readiness_gaps else []
    except (ValueError, TypeError):
        gaps = []
    try:
        deps = json.loads(module.dependencies_inferred) if module.dependencies_inferred else []
    except (ValueError, TypeError):
        deps = []
    return {
        "status": module.readiness_status,
        "gaps": gaps,
        "dependencies_inferred": deps,
        "evaluated_at": module.readiness_evaluated_at.isoformat() if module.readiness_evaluated_at else None,
        "provider": module.readiness_provider,
        "model": module.readiness_model,
    }


async def _load_latest_ocg(db: AsyncSession, project_id: UUID) -> dict[str, Any] | None:
    row = await db.execute(
        select(OCG)
        .where(OCG.project_id == project_id)
        .order_by(OCG.version.desc())
        .limit(1)
    )
    ocg = row.scalar_one_or_none()
    if not ocg or not ocg.ocg_data:
        return None
    try:
        return json.loads(ocg.ocg_data)
    except (ValueError, TypeError):
        return None


def _build_user_prompt(module: ModuleCandidate, ocg_data: dict[str, Any]) -> str:
    """Constrói o prompt customizado por item (P2=b — schema gerado por item)."""
    stack = ocg_data.get("STACK_RECOMMENDATION") or {}
    arch = ocg_data.get("ARCHITECTURE_OVERVIEW") or {}
    profile = ocg_data.get("PROJECT_PROFILE") or {}

    backend = stack.get("backend") or {}
    frontend = stack.get("frontend") or {}
    database = stack.get("database") or {}

    def _list_or_dash(value):
        if isinstance(value, list) and value:
            return ", ".join(str(v) for v in value)
        if isinstance(value, str) and value:
            return value
        return "—"

    backend_stack = _list_or_dash(backend.get("framework")) if backend.get("enabled") else "não habilitado"
    frontend_stack = _list_or_dash(frontend.get("stack")) if frontend.get("enabled") else "não habilitado"
    db_engine = database.get("engine") or "—"
    exec_model = _list_or_dash(arch.get("execution_model"))
    deliverables = _list_or_dash(profile.get("deliverables") or arch.get("deliverables") or [])

    return DETAIL_PROMPT_USER_TEMPLATE.format(
        name=module.name,
        module_type=module.module_type or "feature",
        description=module.description or "(sem descrição)",
        backend_stack=backend_stack,
        frontend_stack=frontend_stack,
        database=db_engine,
        execution_model=exec_model,
        deliverables=deliverables,
    )


async def _resolve_ollama_config(
    db: AsyncSession, project_id: UUID
) -> dict[str, Any] | None:
    """Procura provider 'ollama' na chain do projeto. Retorna
    {base_url, model} ou None se ausente/sem base_url."""
    from app.services.ai_key_resolver import AIKeyResolver

    chain = await AIKeyResolver.resolve_project_provider_chain(db, project_id)
    for entry in chain:
        if (entry.get("provider") or "").lower() != "ollama":
            continue
        base_url = entry.get("base_url")
        if not base_url:
            logger.warning(
                "module_details.ollama_without_base_url",
                project_id=str(project_id),
            )
            continue
        return {
            "base_url": base_url.rstrip("/"),
            "model": entry.get("model") or "qwen2.5-coder:7b",
        }
    return None


#: Timeout generoso pra Ollama em CPU. qwen2.5-coder:7b leva 30-180s
#: por chamada quando não há GPU dedicada. Se o user tem GPU, a
#: resposta volta em ≤10s — timeout só protege contra hang real.
OLLAMA_READ_TIMEOUT_SECONDS = 240


async def _call_ollama(
    *, base_url: str, model: str, system_prompt: str, user_prompt: str,
) -> str:
    """POST OpenAI-compatible em /v1/chat/completions do daemon Ollama
    do projeto. Retorna o texto cru da resposta — caller faz parse.

    Timeout dividido: connect=10s (fail rápido se daemon caiu),
    read=240s (modelo 7b em CPU pode demorar). Logs marcam tempo
    decorrido pra debug.
    """
    import time
    url = f"{base_url}/v1/chat/completions"
    payload = {
        "model": model,
        "max_tokens": 1500,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    timeout = httpx.Timeout(connect=10.0, read=OLLAMA_READ_TIMEOUT_SECONDS, write=10.0, pool=5.0)
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
            resp.raise_for_status()
            body = resp.json()
    except httpx.ReadTimeout as exc:
        elapsed = time.monotonic() - started
        logger.warning(
            "module_details.ollama_timeout",
            base_url=base_url, model=model,
            elapsed_s=round(elapsed, 1),
            limit_s=OLLAMA_READ_TIMEOUT_SECONDS,
        )
        raise RuntimeError(
            f"Ollama ({model}) não respondeu em {OLLAMA_READ_TIMEOUT_SECONDS}s. "
            "Modelo pode estar carregando do disco (primeira chamada) "
            "ou rodando em CPU lenta. Tente novamente — modelo já está "
            "em memória após o primeiro carregamento."
        ) from exc
    elapsed = time.monotonic() - started
    logger.info("module_details.ollama_call_ok", model=model, elapsed_s=round(elapsed, 1))
    choices = body.get("choices") or []
    if not choices:
        return ""
    return choices[0].get("message", {}).get("content", "") or ""


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n?(?P<body>.*?)\n?```\s*$", re.DOTALL)


def _parse_json_response(text: str) -> dict[str, Any]:
    """Parser tolerante: aceita JSON puro, dentro de fence ou cercado de
    texto. Pra falha total, retorna shape mínimo com what_it_is contendo
    o motivo (UI mostra 'falha temporária') — não levanta."""
    if not text:
        return _fallback_shape("Resposta vazia do LLM local.")

    # 1. JSON puro
    stripped = text.strip()
    try:
        return _normalize_shape(json.loads(stripped))
    except json.JSONDecodeError:
        pass

    # 2. Fence
    m = _FENCE_RE.match(stripped)
    if m:
        try:
            return _normalize_shape(json.loads(m.group("body").strip()))
        except json.JSONDecodeError:
            pass

    # 3. Primeiro { até último } balanceado (mesmo algoritmo do Arguider)
    start = stripped.find("{")
    if start >= 0:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(stripped)):
            c = stripped[i]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidate = stripped[start : i + 1]
                    try:
                        return _normalize_shape(json.loads(candidate))
                    except json.JSONDecodeError:
                        break

    logger.warning("module_details.parse_failed", preview=text[:300])
    return _fallback_shape("Não foi possível interpretar a resposta do LLM local.")


def _normalize_shape(parsed: dict[str, Any]) -> dict[str, Any]:
    """Garante todas as chaves do schema, mesmo que LLM tenha omitido."""
    return {
        "what_it_is": str(parsed.get("what_it_is") or "").strip(),
        "prerequisites": _coerce_str_list(parsed.get("prerequisites"), limit=4),
        "missing_inputs": _coerce_str_list(parsed.get("missing_inputs"), limit=4),
        "input_examples": _coerce_str_list(parsed.get("input_examples"), limit=4),
        "suggested_template_sections": _coerce_sections(
            parsed.get("suggested_template_sections")
        ),
    }


def _coerce_str_list(value, *, limit: int = 4) -> list[str]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip()[:200])
        elif isinstance(item, dict):
            text = item.get("text") or item.get("name") or item.get("description")
            if text:
                out.append(str(text)[:200])
        if len(out) >= limit:
            break
    return out


def _coerce_sections(value) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sections = []
    for s in value[:3]:
        if not isinstance(s, dict):
            continue
        section_name = str(s.get("section") or s.get("name") or "").strip()[:80]
        if not section_name:
            continue
        fields_raw = s.get("fields") or []
        fields = []
        if isinstance(fields_raw, list):
            for f in fields_raw[:5]:
                if not isinstance(f, dict):
                    continue
                fname = str(f.get("name") or "").strip()[:60]
                if not fname:
                    continue
                fields.append({
                    "name": fname,
                    "from_ocg": _none_if_empty(f.get("from_ocg")),
                    "hint": (str(f.get("hint") or "").strip() or None),
                })
        sections.append({"section": section_name, "fields": fields})
    return sections


def _none_if_empty(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s.lower() not in ("none", "null") else None


def _fallback_shape(reason: str) -> dict[str, Any]:
    return {
        "what_it_is": reason,
        "prerequisites": [],
        "missing_inputs": [],
        "input_examples": [],
        "suggested_template_sections": [],
    }
