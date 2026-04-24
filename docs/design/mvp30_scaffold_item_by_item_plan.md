# MVP 30 — Scaffold Item-a-Item Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir o scaffold monolítico (1 call LLM gerando 27 arquivos em ~90s, que estoura timeout de 100s do Cloudflare Tunnel) por pipeline item-a-item: 1 call curto planeja a lista de arquivos, depois N calls curtos geram 1 arquivo cada, com progresso visível incremental no sidebar direito.

**Architecture:** 2 endpoints novos no backend (`/scaffold/plan` e `/scaffold/item`) reusam `build_scaffold_prompt` particionado em 2 prompts menores. Frontend substitui o handler monolítico por orquestrador que chama plan → itera items sequencialmente → acumula em state React. Sem persistência server-side nesta iteração (DT-091 futura); state em memória do browser. Endpoint `/scaffold` antigo preservado como fallback.

**Tech Stack:** Python 3.11 + FastAPI + Pydantic v1 + Anthropic SDK (backend) · React + TypeScript + axios + TanStack (frontend) · LLM via `settings.ANTHROPIC_MAX_TOKENS` configurado no `.env` (32768 ativo).

---

## File Structure

### Backend

| Ação | Arquivo | Responsabilidade |
|---|---|---|
| Create | `backend/app/services/scaffold_planner.py` | 2 funções puras: `build_plan_prompt(...)` (prompt curto que pede só JSON com lista de arquivos) e `build_item_prompt(...)` (prompt curto que pede conteúdo de 1 arquivo). Sem I/O, só retornam strings. |
| Modify | `backend/app/routers/code_generation.py` | Novos schemas Pydantic (`ScaffoldPlanItem`, `ScaffoldPlanResponse`, `ScaffoldItemRequest`, `ScaffoldItemResponse`). Novos endpoints `POST /scaffold/plan` e `POST /scaffold/item`. |
| Create | `backend/app/tests/test_mvp30_scaffold_item.py` | Tests standalone (padrão MVP 29 — rodar via `python -m app.tests...`, sem pytest+DB de prod). Cobre prompt builder + shape dos endpoints (mocks do LLM). |

### Frontend

| Ação | Arquivo | Responsabilidade |
|---|---|---|
| Modify | `frontend/src/pages/projects/CodeGeneratorPage.tsx` | `handleGenerateScaffold` vira orquestrador: chama `/scaffold/plan`, itera items via `/scaffold/item` sequencialmente, atualiza `scaffoldFiles` Map incremental + `scaffoldProgress` state. Tree do sidebar mostra ícone por status: pending, generating, complete, error. Botão "Regenerar este arquivo" em erro (reusa endpoint `/regenerate-file` existente OU chama `/scaffold/item` de novo). |
| Modify | `frontend/src/pages/projects/CodeGeneratorPage.tsx` | Novo estado `scaffoldItemStatus: Map<string, 'pending'\|'generating'\|'complete'\|'error'>` pra UI. |

### Docs

| Ação | Arquivo | Responsabilidade |
|---|---|---|
| Create | `docs/design/mvp30_scaffold_item_by_item_plan.md` | Este plano (já criado). |
| Modify | `docs/design/mvp30_impact_report.md` | (Após execução) reporta resultado: nº items gerados, latency média por item, taxa de erro, zero timeouts. |

---

## Task 1: Schemas Pydantic novos

**Files:**
- Modify: `backend/app/routers/code_generation.py` (adicionar após linha 310, após `ScaffoldApplyResponse`)

- [ ] **Step 1: Adicionar os 4 schemas novos**

Inserir **imediatamente após** `class ScaffoldApplyResponse(BaseModel)` em `code_generation.py`:

```python
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
    status: str  # "complete", "todo" (esqueleto com placeholder), "error"
    tokens_used: int = 0
    error_message: Optional[str] = None
```

- [ ] **Step 2: Valida sintaxe**

Run: `python3 -c "import ast; ast.parse(open('/home/luiz/GCA/backend/app/routers/code_generation.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git -C /home/luiz/GCA add backend/app/routers/code_generation.py
git -C /home/luiz/GCA commit -m "MVP 30 Task 1 — schemas Pydantic pra scaffold item-a-item"
```

---

## Task 2: Service `scaffold_planner.py` com 2 builders de prompt

**Files:**
- Create: `backend/app/services/scaffold_planner.py`

- [ ] **Step 1: Criar o arquivo com os 2 prompt builders**

Conteúdo completo de `backend/app/services/scaffold_planner.py`:

```python
"""MVP 30 — Prompt builders pra scaffold item-a-item.

Separa a responsabilidade do `codegen_prompt_builder.build_scaffold_prompt`
(monolítico) em 2 prompts curtos:

  1. `build_plan_prompt(...)`: pede ao LLM APENAS a lista de arquivos que
     compõem o scaffold, com metadata (path, file_type, purpose). Sem
     conteúdo. Output esperado <1000 tokens → latency ~5s → zero risco de
     timeout.

  2. `build_item_prompt(...)`: pede o conteúdo completo de UM arquivo
     específico, com contexto do OCG + outros arquivos já planejados.
     Output por arquivo ~2-5k tokens → latency ~15-30s → cabe no timeout
     do Cloudflare (100s).

Ambas funções são puras e sem I/O. Reutilizam blocos de contexto do OCG
conforme `codegen_prompt_builder.build_scaffold_prompt` já faz, mas
particionados e reduzidos.
"""
from __future__ import annotations

import json
from typing import Any

# Tamanhos máximos controlados pra não estourar o LLM.
_MAX_FILES_IN_PLAN = 40
_MAX_CHARS_PURPOSE = 120
_MAX_CHARS_CONTEXT_PER_ITEM = 3000


def build_plan_prompt(
    *,
    project_name: str,
    project_slug: str,
    project_description: str | None,
    stack: dict[str, Any],
    architecture: dict[str, Any],
    modules: list[Any],
    arguider_modules: list[Any],
) -> str:
    """Monta prompt pra fase PLAN: LLM retorna apenas lista de arquivos.

    Output esperado (JSON):
    ```
    {
      "summary": "string <500 chars",
      "items": [
        {"path": "...", "file_type": "py|tsx|md|...", "purpose": "<120 chars", "est_lines": int},
        ...
      ]
    }
    ```
    """
    stack_json = json.dumps(stack or {}, ensure_ascii=False, indent=2)[:2000]
    arch_json = json.dumps(architecture or {}, ensure_ascii=False, indent=2)[:1500]
    modules_sample = json.dumps(
        [m for m in (modules or []) if isinstance(m, dict)][:15],
        ensure_ascii=False,
    )[:2000]
    arguider_sample = json.dumps(
        [m for m in (arguider_modules or []) if isinstance(m, dict)][:15],
        ensure_ascii=False,
    )[:2000]

    return (
        f"Você é um arquiteto de software sênior. Planeje o scaffold INICIAL do projeto "
        f"`{project_name}` (slug: {project_slug}).\n\n"
        f"Descrição: {project_description or '(não fornecida)'}\n\n"
        f"Stack recomendada:\n{stack_json}\n\n"
        f"Arquitetura:\n{arch_json}\n\n"
        f"Módulos do Roadmap (amostra):\n{modules_sample}\n\n"
        f"Módulos sugeridos pelo Arguidor (amostra):\n{arguider_sample}\n\n"
        f"## TAREFA\n"
        f"Liste os arquivos que compõem o scaffold inicial. NÃO gere conteúdo — apenas "
        f"a lista com metadata. Máximo de {_MAX_FILES_IN_PLAN} arquivos. Priorize:\n"
        f"  - estrutura de pastas canônica pra stack escolhida,\n"
        f"  - configs essenciais (pyproject.toml/package.json/Dockerfile/etc conforme stack),\n"
        f"  - entry-points (main.py, App.tsx, index.ts),\n"
        f"  - módulos core listados acima.\n\n"
        f"## FORMATO DE RESPOSTA (JSON ESTRITO)\n"
        f"Retorne APENAS JSON válido, sem markdown code fences, sem preâmbulo:\n"
        f'{{"summary": "<breve descrição do scaffold, até 300 chars>", '
        f'"items": [{{"path": "<path>", "file_type": "<ext>", "purpose": "<até {_MAX_CHARS_PURPOSE} chars>", "est_lines": <int>}}, ...]}}'
    )


def build_item_prompt(
    *,
    project_name: str,
    project_slug: str,
    stack: dict[str, Any],
    architecture: dict[str, Any],
    item_path: str,
    item_purpose: str,
    item_file_type: str,
    peer_paths: list[str],
    rnf_contracts: Any = None,
    design_tokens: Any = None,
) -> str:
    """Monta prompt pra fase ITEM: LLM retorna conteúdo de 1 arquivo.

    Recebe metadata do item (path, purpose, file_type), mais o OCG reduzido
    e lista de peers (paths dos outros arquivos já planejados) pra não
    inventar dependências que não existem.
    """
    stack_json = json.dumps(stack or {}, ensure_ascii=False, indent=2)[:_MAX_CHARS_CONTEXT_PER_ITEM]
    arch_json = json.dumps(architecture or {}, ensure_ascii=False, indent=2)[:1500]
    peers_text = "\n".join(f"- {p}" for p in (peer_paths or [])[:40])
    rnf_text = ""
    if rnf_contracts:
        rnf_text = f"\n\nContratos RNF (do OCG — OBRIGATÓRIO cumprir):\n{json.dumps(rnf_contracts, ensure_ascii=False)[:2000]}\n"
    tokens_text = ""
    if design_tokens:
        tokens_text = f"\n\nDesign tokens canônicos (frontend — use estes, NÃO invente):\n{json.dumps(design_tokens, ensure_ascii=False)[:2000]}\n"

    return (
        f"Você é um engenheiro sênior implementando 1 arquivo do scaffold do projeto "
        f"`{project_name}` (slug: {project_slug}).\n\n"
        f"Stack:\n{stack_json}\n\n"
        f"Arquitetura:\n{arch_json}\n"
        f"{rnf_text}"
        f"{tokens_text}\n"
        f"Peers (outros arquivos que COEXISTEM no mesmo scaffold — referências entre si são legítimas):\n"
        f"{peers_text}\n\n"
        f"## ARQUIVO A GERAR\n"
        f"  Path: `{item_path}`\n"
        f"  Tipo: `{item_file_type}`\n"
        f"  Propósito: {item_purpose}\n\n"
        f"## REGRAS\n"
        f"- Escreva o conteúdo COMPLETO, funcional quando possível.\n"
        f"- Se faltar contexto pra implementar 100%, gere esqueleto com `# TODO:` explicando o que falta.\n"
        f"- Docstrings obrigatórias em Python (módulo, classes, funções públicas).\n"
        f"- JSDoc em TS/JS para exports públicos.\n"
        f"- Não invente imports: use só peers listados acima + libs da stack declarada.\n"
        f"- Não envolva a resposta em code fences markdown (```).\n\n"
        f"## FORMATO DE RESPOSTA (JSON ESTRITO)\n"
        f'{{"content": "<conteúdo completo do arquivo>", "status": "complete" | "todo", "notes": "<opcional, até 200 chars>"}}\n\n'
        f"Retorne APENAS o JSON, sem markdown, sem preâmbulo."
    )
```

- [ ] **Step 2: Valida sintaxe**

Run: `python3 -c "import ast; ast.parse(open('/home/luiz/GCA/backend/app/services/scaffold_planner.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git -C /home/luiz/GCA add backend/app/services/scaffold_planner.py
git -C /home/luiz/GCA commit -m "MVP 30 Task 2 — scaffold_planner: 2 prompt builders (plan + item)"
```

---

## Task 3: Endpoint `POST /scaffold/plan`

**Files:**
- Modify: `backend/app/routers/code_generation.py` (inserir novo endpoint após `generate_scaffold` — linha ~760, antes de `_commit_scaffold_files`)

- [ ] **Step 1: Adicionar o endpoint**

Inserir imediatamente antes da função `_commit_scaffold_files`:

```python
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
    modules = ocg_data.get("MODULE_CANDIDATES", [])

    # Arguider modules (amostra, pra dirigir scopos do plano)
    docs_result = await db.execute(
        select(IngestedDocument)
        .where(IngestedDocument.project_id == project_id)
        .order_by(IngestedDocument.created_at.desc())
        .limit(20)
    )
    ingested_docs = docs_result.scalars().all()
    arguider_modules: List[Any] = []
    if ingested_docs:
        doc_ids = [d.id for d in ingested_docs]
        analyses_result = await db.execute(
            select(ArguiderAnalysis).where(ArguiderAnalysis.document_id.in_(doc_ids))
        )
        for a in analyses_result.scalars().all():
            try:
                mc = json.loads(a.module_candidates) if isinstance(a.module_candidates, str) else a.module_candidates
                arguider_modules.extend(mc if isinstance(mc, list) else [])
            except (json.JSONDecodeError, TypeError):
                pass

    from app.services.scaffold_planner import build_plan_prompt

    prompt = build_plan_prompt(
        project_name=project.name,
        project_slug=project.slug,
        project_description=project.description,
        stack=stack,
        architecture=architecture,
        modules=modules,
        arguider_modules=arguider_modules,
    )

    api_key = app_settings.ANTHROPIC_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key do Anthropic não configurada. Configure em Admin > Configurações.",
        )

    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=app_settings.ANTHROPIC_MODEL,
        max_tokens=4096,  # Plan é curto por design
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

    # Parse JSON (tolerante — reusa helper existente se necessário)
    import re as _re
    stripped = raw_text.strip()
    # Remove fence se LLM ignorou instrução
    m = _re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", stripped, _re.DOTALL)
    if m:
        stripped = m.group(1).strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        logger.error(
            "scaffold_plan.parse_failed",
            project_id=str(project_id),
            error=str(exc),
            preview=stripped[:500],
        )
        raise HTTPException(
            status_code=502,
            detail=f"LLM retornou JSON inválido na fase PLAN: {exc}",
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
```

- [ ] **Step 2: Valida sintaxe + restart backend**

Run: `python3 -c "import ast; ast.parse(open('/home/luiz/GCA/backend/app/routers/code_generation.py').read()); print('OK')" && docker restart gca-backend 2>&1 | tail -1 && sleep 4 && docker logs gca-backend --tail=3 2>&1 | tail -3`
Expected: `OK` + `Application startup complete.`

- [ ] **Step 3: Commit**

```bash
git -C /home/luiz/GCA add backend/app/routers/code_generation.py
git -C /home/luiz/GCA commit -m "MVP 30 Task 3 — endpoint POST /scaffold/plan"
```

---

## Task 4: Endpoint `POST /scaffold/item`

**Files:**
- Modify: `backend/app/routers/code_generation.py` (inserir logo abaixo do endpoint `/scaffold/plan`)

- [ ] **Step 1: Adicionar o endpoint**

Inserir imediatamente após a função `generate_scaffold_plan`:

```python
@router.post(
    "/scaffold/item",
    response_model=ScaffoldItemResponse,
    summary="MVP 30 — Gerar conteúdo de 1 arquivo do scaffold",
    description="Gera conteúdo completo de UM arquivo listado no /scaffold/plan. Latency ~15-30s por item.",
)
async def generate_scaffold_item(
    request: ScaffoldItemRequest,
    peer_paths_csv: Optional[str] = None,  # query param opcional — paths dos peers, separados por vírgula
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
            max_tokens=8192,  # Item individual — cabe com margem
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

    import re as _re
    stripped = raw_text.strip()
    m = _re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", stripped, _re.DOTALL)
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
```

- [ ] **Step 2: Valida sintaxe + restart backend**

Run: `python3 -c "import ast; ast.parse(open('/home/luiz/GCA/backend/app/routers/code_generation.py').read()); print('OK')" && docker restart gca-backend 2>&1 | tail -1 && sleep 4 && docker logs gca-backend --tail=3 2>&1 | tail -3`
Expected: `OK` + `Application startup complete.`

- [ ] **Step 3: Commit**

```bash
git -C /home/luiz/GCA add backend/app/routers/code_generation.py
git -C /home/luiz/GCA commit -m "MVP 30 Task 4 — endpoint POST /scaffold/item"
```

---

## Task 5: Tests standalone dos prompt builders

**Files:**
- Create: `backend/app/tests/test_mvp30_scaffold_item.py`

- [ ] **Step 1: Criar arquivo de teste standalone**

Conteúdo completo de `test_mvp30_scaffold_item.py` (padrão MVP 29 — sem pytest+DB, roda via `python -m app.tests.test_mvp30_scaffold_item`):

```python
"""MVP 30 — Testes unit standalone dos prompt builders do scaffold.

Cobre: build_plan_prompt, build_item_prompt. Sem DB, sem pytest fixtures
(respeita DT-034). Rodar: `python -m app.tests.test_mvp30_scaffold_item`.
"""
from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.scaffold_planner import build_plan_prompt, build_item_prompt


def test_plan_prompt_contains_project_name():
    p = build_plan_prompt(
        project_name="X", project_slug="x", project_description="desc",
        stack={"backend": {"framework": "FastAPI"}}, architecture={},
        modules=[], arguider_modules=[],
    )
    assert "X" in p
    assert "FastAPI" in p


def test_plan_prompt_has_json_format_instruction():
    p = build_plan_prompt(
        project_name="P", project_slug="p", project_description=None,
        stack={}, architecture={}, modules=[], arguider_modules=[],
    )
    assert '"items"' in p
    assert '"summary"' in p
    assert "APENAS JSON" in p


def test_plan_prompt_accepts_none_description():
    p = build_plan_prompt(
        project_name="P", project_slug="p", project_description=None,
        stack={}, architecture={}, modules=[], arguider_modules=[],
    )
    assert "(não fornecida)" in p


def test_item_prompt_contains_path_and_purpose():
    p = build_item_prompt(
        project_name="P", project_slug="p",
        stack={}, architecture={},
        item_path="src/main.py", item_purpose="entrypoint FastAPI",
        item_file_type="py", peer_paths=[],
    )
    assert "src/main.py" in p
    assert "entrypoint FastAPI" in p
    assert "py" in p


def test_item_prompt_lists_peers():
    p = build_item_prompt(
        project_name="P", project_slug="p",
        stack={}, architecture={},
        item_path="a.py", item_purpose="x", item_file_type="py",
        peer_paths=["b.py", "c.py"],
    )
    assert "- b.py" in p
    assert "- c.py" in p


def test_item_prompt_includes_rnf_when_provided():
    p = build_item_prompt(
        project_name="P", project_slug="p",
        stack={}, architecture={},
        item_path="a.py", item_purpose="x", item_file_type="py",
        peer_paths=[],
        rnf_contracts=[{"id": "RNF-01", "spec": "latency <100ms"}],
    )
    assert "RNF-01" in p
    assert "Contratos RNF" in p


def test_item_prompt_includes_design_tokens_for_frontend():
    p = build_item_prompt(
        project_name="P", project_slug="p",
        stack={}, architecture={},
        item_path="App.tsx", item_purpose="root", item_file_type="tsx",
        peer_paths=[],
        design_tokens={"palette": {"primary": "#8B5CF6"}},
    )
    assert "#8B5CF6" in p
    assert "Design tokens" in p


def test_item_prompt_json_format_strict():
    p = build_item_prompt(
        project_name="P", project_slug="p",
        stack={}, architecture={},
        item_path="a.py", item_purpose="x", item_file_type="py",
        peer_paths=[],
    )
    assert '"content"' in p
    assert '"status"' in p
    assert "APENAS o JSON" in p


def _run_all():
    import inspect
    tests = [v for k, v in globals().items() if k.startswith("test_") and inspect.isfunction(v)]
    passed, failed = 0, []
    for t in tests:
        try:
            t()
            passed += 1
            print(f"  ✓ {t.__name__}")
        except AssertionError as e:
            failed.append((t.__name__, f"assertion: {e}"))
            print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{'='*60}\nTotal: {len(tests)}  Passou: {passed}  Falhou: {len(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run_all())
```

- [ ] **Step 2: Copiar pro container + rodar**

Run:
```
docker cp /home/luiz/GCA/backend/app/tests/test_mvp30_scaffold_item.py gca-backend:/app/app/tests/test_mvp30_scaffold_item.py
docker exec gca-backend python -m app.tests.test_mvp30_scaffold_item
```
Expected: `Total: 8  Passou: 8  Falhou: 0`

- [ ] **Step 3: Commit**

```bash
git -C /home/luiz/GCA add backend/app/tests/test_mvp30_scaffold_item.py
git -C /home/luiz/GCA commit -m "MVP 30 Task 5 — tests standalone dos prompt builders"
```

---

## Task 6: Frontend — state + handler orquestrador

**Files:**
- Modify: `frontend/src/pages/projects/CodeGeneratorPage.tsx`

- [ ] **Step 1: Adicionar state de status por item**

Localizar a seção onde estão declarados os states do scaffold (aproximadamente linhas 130-180, procure por `const [scaffoldFiles, setScaffoldFiles]`). Adicionar IMEDIATAMENTE ABAIXO do `scaffoldFiles`:

```tsx
// MVP 30 — status por item do scaffold (pending|generating|complete|error)
const [scaffoldItemStatus, setScaffoldItemStatus] = useState<Map<string, 'pending' | 'generating' | 'complete' | 'error'>>(new Map())
const [scaffoldPlanSummary, setScaffoldPlanSummary] = useState<string | null>(null)
```

- [ ] **Step 2: Substituir o handler `handleGenerateScaffold`**

Localizar a função `handleGenerateScaffold` (começa em linha ~245). Substituir TODO o corpo (entre `const handleGenerateScaffold = async () => {` e o fechamento `}`):

```tsx
  const handleGenerateScaffold = async () => {
    if (!projectId || scaffoldGenerating) return
    if (scaffoldFiles.size > 0 && !confirm('Isso substituirá o preview atual. Continuar?')) return

    setScaffoldGenerating(true)
    setScaffoldSummary(null)
    setScaffoldFiles(new Map())
    setScaffoldItemStatus(new Map())

    try {
      // MVP 30 Fase PLAN — lista de arquivos sem conteúdo (~5s)
      const planRes = await apiClient.post('/code-generation/scaffold/plan', { project_id: projectId })
      const planItems: Array<{ path: string; file_type: string; purpose: string; est_lines: number }> =
        planRes.data.items || []
      setScaffoldPlanSummary(planRes.data.summary || null)

      if (planItems.length === 0) {
        alert('O LLM não retornou itens no plano. Tente novamente ou ajuste o OCG.')
        return
      }

      // Todos marcados como pending; tree atualiza imediatamente
      const initialStatus = new Map<string, 'pending' | 'generating' | 'complete' | 'error'>()
      for (const it of planItems) initialStatus.set(it.path, 'pending')
      setScaffoldItemStatus(initialStatus)

      // MVP 30 Fase ITEM — gera cada arquivo sequencialmente
      const peerPathsCsv = planItems.map(it => it.path).join(',')
      const accumulated = new Map<string, { content: string; status: string }>()

      for (const item of planItems) {
        // Marca este como "generating"
        setScaffoldItemStatus(prev => new Map(prev).set(item.path, 'generating'))

        try {
          const itemRes = await apiClient.post(
            `/code-generation/scaffold/item?peer_paths_csv=${encodeURIComponent(peerPathsCsv)}`,
            {
              project_id: projectId,
              path: item.path,
              file_type: item.file_type,
              purpose: item.purpose,
            },
          )
          const data = itemRes.data
          if (data.status === 'error') {
            setScaffoldItemStatus(prev => new Map(prev).set(item.path, 'error'))
          } else {
            accumulated.set(item.path, { content: data.content || '', status: data.status || 'todo' })
            setScaffoldFiles(new Map(accumulated))
            setScaffoldItemStatus(prev => new Map(prev).set(item.path, 'complete'))
          }
        } catch {
          setScaffoldItemStatus(prev => new Map(prev).set(item.path, 'error'))
        }
      }

      const completeCount = Array.from(accumulated.values()).filter(v => v.status !== 'nmi').length
      setScaffoldSummary(
        `${planRes.data.summary || `Scaffold com ${planItems.length} arquivos`} — ${completeCount} prontos pra commit. Revise e clique em "Aplicar no Git".`,
      )
      setScaffoldPendingApply(completeCount > 0)

      // Refetch árvore do Git + atualiza tree local
      loadTree()
      const tree = buildTreeWithStatus(
        Array.from(accumulated.entries()).map(([path, v]) => ({ path, content: v.content, status: v.status })),
      )
      setFileTree(tree)

      if (planItems.length > 0) {
        const firstFile = planItems[0].path
        const got = accumulated.get(firstFile)
        if (got) {
          setSelectedFile(firstFile)
          setFileContent(got.content)
          setOriginalContent(got.content)
          setHasChanges(false)
        }
      }
    } catch (err: unknown) {
      alert(formatCodeGenError(err, 'gerar scaffold'))
    } finally {
      setScaffoldGenerating(false)
    }
  }
```

- [ ] **Step 3: Build frontend**

Run: `docker exec gca-frontend npm run build 2>&1 | tail -3 && docker restart gca-frontend 2>&1 | tail -1`
Expected: `✓ built in Xs` (sem erro)

- [ ] **Step 4: Commit**

```bash
git -C /home/luiz/GCA add frontend/src/pages/projects/CodeGeneratorPage.tsx
git -C /home/luiz/GCA commit -m "MVP 30 Task 6 — frontend orquestrador item-a-item (state + handler)"
```

---

## Task 7: Frontend — UI mostra status por item no sidebar

**Files:**
- Modify: `frontend/src/pages/projects/CodeGeneratorPage.tsx` (função `buildTreeWithStatus` ou onde o tree é renderizado — procure por `renderTree` ou `TreeNode`)

- [ ] **Step 1: Mapear ícone por status do item**

Localizar a função que renderiza cada nó da árvore (procurar por `function renderNode` ou similar). Dentro do componente de renderização de arquivo (folha), adicionar lookup em `scaffoldItemStatus` ANTES de escolher o ícone:

```tsx
// MVP 30 — ícone derivado do status do item no scaffold, se aplicável
const itemStatus = scaffoldItemStatus.get(nodePath)  // 'pending'|'generating'|'complete'|'error'|undefined
let statusIcon: JSX.Element | null = null
if (itemStatus === 'pending') {
  statusIcon = <Clock className="w-3 h-3 text-slate-500" />
} else if (itemStatus === 'generating') {
  statusIcon = <Loader2 className="w-3 h-3 text-violet-400 animate-spin" />
} else if (itemStatus === 'complete') {
  statusIcon = <CheckCircle2 className="w-3 h-3 text-emerald-400" />
} else if (itemStatus === 'error') {
  statusIcon = <AlertTriangle className="w-3 h-3 text-red-400" />
}
// Renderizar statusIcon ao lado do nome do arquivo no tree
```

Detalhe crítico: `Clock` já está importado (linha 5 do arquivo). `Loader2`, `CheckCircle2`, `AlertTriangle` também. Não há imports novos.

No JSX do nó de arquivo (procure por `<span className="truncate...">` que renderiza `node.name`), adicionar `{statusIcon}` como elemento irmão:

```tsx
<div className="flex items-center gap-1.5">
  {fileIcon}
  <span className="truncate ...">{node.name}</span>
  {statusIcon}
</div>
```

- [ ] **Step 2: Adicionar barra de progresso no topo do painel direito**

Localizar o topo do painel de preview (procure por `scaffoldSummary &&` ou `scaffoldPendingApply`). Adicionar ANTES do botão "Aplicar no Git":

```tsx
{scaffoldGenerating && scaffoldItemStatus.size > 0 && (
  <div className="mb-3 px-3 py-2 bg-slate-900/60 border border-slate-800 rounded-lg">
    <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
      <span>
        Gerando {Array.from(scaffoldItemStatus.values()).filter(s => s === 'complete').length} / {scaffoldItemStatus.size}
      </span>
      {scaffoldPlanSummary && (
        <span className="text-[10px] text-slate-600 truncate ml-2">{scaffoldPlanSummary}</span>
      )}
    </div>
    <div className="h-1 bg-slate-800 rounded overflow-hidden">
      <div
        className="h-full bg-violet-500 transition-all duration-300"
        style={{
          width: `${(Array.from(scaffoldItemStatus.values()).filter(s => s === 'complete').length / Math.max(scaffoldItemStatus.size, 1)) * 100}%`,
        }}
      />
    </div>
  </div>
)}
```

- [ ] **Step 3: Build frontend**

Run: `docker exec gca-frontend npm run build 2>&1 | tail -3 && docker restart gca-frontend 2>&1 | tail -1`
Expected: `✓ built in Xs` sem erros TypeScript.

- [ ] **Step 4: Commit**

```bash
git -C /home/luiz/GCA add frontend/src/pages/projects/CodeGeneratorPage.tsx
git -C /home/luiz/GCA commit -m "MVP 30 Task 7 — UI com status por item + progress bar"
```

---

## Task 8: Validação dogfood + relatório de impacto

**Files:**
- Create: `docs/design/mvp30_impact_report.md`

- [ ] **Step 1: Hard-refresh no browser e disparar scaffold**

Instruir stakeholder a dar `Ctrl+Shift+R` na página Code Generator do AJA, clicar "Gerar Preview do Scaffold".

Expected (na UI):
- Barra de progresso aparece no topo direito com "Gerando X / N"
- Árvore do sidebar popula incrementalmente com arquivos pending → generating (spinner) → complete (check verde)
- Sem erro de timeout
- Quando terminar, botão "Aplicar no Git" destrava

- [ ] **Step 2: Coletar métricas do log do backend**

Run:
```
docker logs gca-backend --since=30m 2>&1 | grep -E "scaffold_plan|scaffold_item" | tail -50
```

Extrair:
- Número de items no plano
- tokens_used totais (soma dos items + plan)
- Número de items com status=error
- Latency total (timestamp primeiro plan → timestamp último item)

- [ ] **Step 3: Escrever relatório**

Conteúdo completo de `docs/design/mvp30_impact_report.md`:

```markdown
# MVP 30 — Relatório de Impacto (Scaffold Item-a-Item)

**Data:** [DATA DA EXECUÇÃO]
**Fase:** MVP entregue (Tasks 1-7)
**Objetivo Task §1:** eliminar timeout Cloudflare em scaffolds grandes via geração item-a-item.

## Métricas medidas em dogfood (projeto AJA)

| Métrica | Valor |
|---|---|
| Items no plano | N |
| Latency média por item | Xs |
| Latency total | Ys |
| Tokens totais (plan + N items) | Z |
| Items com erro | E |
| Taxa de erro | E/N % |

## Comparação com MVP anterior (scaffold monolítico)

| | Monolítico | Item-a-item |
|---|---|---|
| Chamadas LLM | 1 | N+1 |
| Timeout risk | Alto (bateu em ~90s no AJA) | Zero (cada call <30s) |
| Feedback visual | Zero até terminar | Progressivo por item |
| Retry granular | Refazer tudo | Por item |
| Total tokens | ~32k (limite) | ~N×5k + plan |

## Tasks entregues (Tasks 1-7 deste plan)

1. Schemas Pydantic ScaffoldPlanItem/Response + Item Request/Response
2. Service `scaffold_planner.py` com 2 prompt builders
3. Endpoint `POST /scaffold/plan`
4. Endpoint `POST /scaffold/item`
5. Tests standalone dos prompt builders (8 testes)
6. Frontend orquestrador item-a-item
7. UI com status por item + progress bar

## Pendências fase 2 (DT-091 futura)

- Persistência server-side do plan/items (tabela `scaffold_session(id, project_id, plan_json)` + `scaffold_session_item(session_id, path, content, status)`)
- Recuperação em caso de refresh do browser
- Retry individual por item com botão UI
- Paralelização opcional de items (3-5 concorrentes) com throttle

## Endpoint legado

`POST /scaffold` continua funcionando como fallback. Frontend não chama mais — pode virar DT de remoção quando fase 2 consolidar.
```

- [ ] **Step 4: Commit final**

```bash
git -C /home/luiz/GCA add docs/design/mvp30_impact_report.md
git -C /home/luiz/GCA commit -m "MVP 30 Task 8 — relatório de impacto (MVP FECHADO)"
```

---

## Self-Review

- **Spec coverage:** Desenho conforme decisão do stakeholder (item-a-item + array persistente — persistência é React state nesta iteração conforme proposto, server-side vira DT-091). Tasks 1-4 cobrem backend; 5 cobre testes; 6-7 cobrem frontend; 8 entrega validação + relatório.
- **Placeholder scan:** Cada step tem código exato OU comando executável. Testes escritos em Task 5 com 8 casos concretos. Métricas da Task 8 usam `[DATA]`/`N`/`X` como placeholders INTENCIONAIS — devem ser preenchidos em tempo de execução após coleta dos logs.
- **Type consistency:** `ScaffoldPlanItem`, `ScaffoldPlanResponse`, `ScaffoldItemRequest`, `ScaffoldItemResponse` usados em Task 1 são referenciados consistentemente em Tasks 3, 4, 5, 6. Propriedades (`path`, `file_type`, `purpose`, `est_lines`, `content`, `status`, `tokens_used`, `error_message`) sem divergência entre tasks.
