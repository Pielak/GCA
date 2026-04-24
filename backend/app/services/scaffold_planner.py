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
        f"a lista com metadata. Máximo de {_MAX_FILES_IN_PLAN} arquivos.\n\n"
        f"## REGRA OBRIGATÓRIA DE COBERTURA\n"
        f"Se a stack declarada inclui MÚLTIPLAS CAMADAS (ex: frontend + backend + sidecar + mobile + "
        f"embedded + DB), o plano TEM QUE conter arquivos representativos de TODAS elas. É proibido "
        f"focar só em uma camada — o resultado tem que ser um projeto FUNCIONAL end-to-end após o "
        f"apply. Contemple, sempre que a stack exigir:\n"
        f"  - BACKEND: entry-point, módulos domain/application/infra, Cargo.toml / pyproject.toml / "
        f"go.mod / package.json conforme linguagem, configs (tauri.conf.json, .env.example).\n"
        f"  - FRONTEND: package.json, tsconfig, vite.config (ou bundler equivalente), index.html, "
        f"src/main.tsx OU src/App.tsx, ao menos 2-3 componentes ou páginas canônicas da UI.\n"
        f"  - SIDECAR / WORKER: main.py (ou equivalente), requirements.txt / pyproject.toml, Dockerfile "
        f"se necessário, módulos principais.\n"
        f"  - CI/CD: .github/workflows/*.yml OU .gitlab-ci.yml cobrindo lint/test/build multi-plataforma.\n"
        f"  - DB / MIGRATIONS: schema inicial, 1ª migration, seed de referência se aplicável.\n"
        f"  - DOCS MÍNIMOS: README.md, .gitignore, CHANGELOG.md.\n"
        f"  - TESTES: pelo menos 1 teste por camada (unit/integration) como placeholder.\n"
        f"Evite `.gitkeep` puros — prefira arquivos com conteúdo real (README de pasta, índice, etc).\n\n"
        f"## FORMATO DE RESPOSTA (JSON ESTRITO)\n"
        f"Retorne APENAS JSON válido, sem markdown code fences, sem preâmbulo:\n"
        f'{{"summary": "<breve descrição do scaffold mostrando que TODAS as camadas foram contempladas, até 300 chars>", '
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
