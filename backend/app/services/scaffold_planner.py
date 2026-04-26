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

_MAX_FILES_IN_PLAN = 600
_MAX_CHARS_PURPOSE = 120
_MAX_CHARS_CONTEXT_PER_ITEM = 3000


def _compact_module(m: dict[str, Any]) -> dict[str, Any]:
    """Reduz módulo do backlog ao essencial pro prompt: nome, tipo, propósito.

    Mantém o prompt enxuto mesmo quando a lista tem 100+ items. Trunca purpose
    em 200 chars pra forçar densidade.
    """
    purpose = (m.get("description") or "").strip().replace("\n", " ")
    return {
        "name": (m.get("name") or "").strip()[:120],
        "type": m.get("module_type") or "feature",
        "priority": m.get("priority") or "medium",
        "phase": m.get("phase"),
        "purpose": purpose[:200],
    }


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

    Cascata canônica (2026-04-24): a lista `modules` vem do backlog filtrado
    por ready_for_codegen=true e ordenada pela cascata do roadmap (fase 1 →
    2 → 3, ready primeiro). O prompt CONFIA na ordem recebida — não
    reorganiza nem corta. Cada módulo da lista DEVE produzir ao menos 1
    arquivo dedicado no plano.

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

    # Compacta TODOS os módulos prontos — sem slice. A ordem recebida é a
    # ordem canônica do roadmap (priority_rank + ready_rank + created_at)
    # e o prompt preserva pra o LLM gerar arquivos na mesma sequência.
    compact = [
        _compact_module(m)
        for m in (modules or [])
        if isinstance(m, dict)
    ]
    modules_block = json.dumps(compact, ensure_ascii=False, indent=1)
    modules_count = len(compact)

    return (
        f"Você é um arquiteto de software sênior. Planeje o scaffold completo do projeto "
        f"`{project_name}` (slug: {project_slug}).\n\n"
        f"Descrição: {project_description or '(não fornecida)'}\n\n"
        f"Stack recomendada:\n{stack_json}\n\n"
        f"Arquitetura:\n{arch_json}\n\n"
        f"## MÓDULOS DO BACKLOG ORDENADOS PELO ROADMAP ({modules_count} prontos pra CodeGen)\n"
        f"Ordem canônica: critical/high (Fase 1) → medium (Fase 2) → low (Fase 3),\n"
        f"e dentro de cada prioridade, ready_for_codegen primeiro. Preserve essa\n"
        f"ordem na geração do plano — o item N do backlog deve aparecer antes do N+1.\n\n"
        f"{modules_block}\n\n"
        f"## TAREFA\n"
        f"Liste os arquivos que compõem o scaffold COMPLETO. NÃO gere conteúdo — apenas "
        f"a lista com metadata. Limite superior técnico: {_MAX_FILES_IN_PLAN} arquivos.\n\n"
        f"## REGRA DURA — 1 ARQUIVO DE IMPLEMENTAÇÃO POR MÓDULO\n"
        f"Cada módulo do backlog acima TEM QUE produzir EXATAMENTE 1 arquivo dedicado de\n"
        f"implementação no plano. Nada de 'agrupar 5 módulos em 1 arquivo genérico'.\n"
        f"NÃO inclua arquivos de teste neste plano — testes vêm de outro caminho\n"
        f"(test_spec_generator) após o scaffold. Você pode adicionar arquivos comuns\n"
        f"de scaffold (README, configs, entry-points, package manifests) ALÉM dos\n"
        f"módulos — mas nunca em substituição.\n\n"
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
        f"Evite `.gitkeep` puros — prefira arquivos com conteúdo real (README de pasta, índice, etc).\n\n"
        f"## DEPENDÊNCIAS ENTRE ARQUIVOS (OBRIGATÓRIO)\n"
        f"Cada item DEVE declarar `depends_on`: array de paths dos OUTROS arquivos do plano\n"
        f"em que ele depende DIRETAMENTE (importa, estende, instancia, configura, etc).\n"
        f"Regras:\n"
        f"  - paths em depends_on devem existir EXATAMENTE em outro item da mesma lista\n"
        f"  - sem dependências transitivas — só direct imports/refs\n"
        f"  - sem ciclos (A→B→A é proibido). Se houver loop natural, quebre por interface\n"
        f"  - itens base (README, package.json, configs sem código) usam depends_on: []\n"
        f"  - testes dependem do arquivo testado\n"
        f"  - main/entry-points dependem dos módulos que orquestram\n"
        f"  - controllers dependem dos services; services dependem dos models/repositories\n"
        f"\n"
        f"## FORMATO DE RESPOSTA (JSON ESTRITO)\n"
        f"Retorne APENAS JSON válido, sem markdown code fences, sem preâmbulo:\n"
        f'{{"summary": "<breve descrição do scaffold confirmando que TODOS os {modules_count} módulos têm arquivo no plano e TODAS as camadas da stack foram contempladas, até 300 chars>", '
        f'"items": [{{"path": "<path>", "file_type": "<ext>", "purpose": "<até {_MAX_CHARS_PURPOSE} chars>", "est_lines": <int>, "depends_on": ["<path do peer>", ...]}}, ...]}}'
    )


_MAX_CHARS_PER_PEER_CONTENT = 600


def build_item_prompt(
    *,
    project_name: str,
    project_slug: str,
    stack: dict[str, Any],
    architecture: dict[str, Any],
    item_path: str,
    item_purpose: str,
    item_file_type: str,
    peer_paths: list[str] | None = None,
    peer_contents: dict[str, str] | None = None,
    rnf_contracts: Any = None,
    design_tokens: Any = None,
    build_errors: str | None = None,
) -> str:
    """Monta prompt pra fase ITEM: LLM retorna conteúdo de 1 arquivo.

    Camada C (2026-04-25): aceita `peer_contents` (dict path→content) com
    o conteúdo TRUNCADO dos peers que este arquivo declarou em depends_on.
    O LLM gera assinaturas coerentes (imports reais, classes que existem).
    `peer_paths` continua aceito pra retrocompat com chamadores antigos
    (gera só lista de paths sem conteúdo).
    """
    stack_json = json.dumps(stack or {}, ensure_ascii=False, indent=2)[:_MAX_CHARS_CONTEXT_PER_ITEM]
    arch_json = json.dumps(architecture or {}, ensure_ascii=False, indent=2)[:1500]

    # Camada C — bloco de enlaces. Quando peer_contents está presente,
    # injeta amostras truncadas. Caso contrário, cai no modo legado.
    if peer_contents:
        blocks = []
        for path, content in list(peer_contents.items())[:30]:
            snippet = (content or "").strip()[:_MAX_CHARS_PER_PEER_CONTENT]
            if not snippet:
                continue
            blocks.append(f"### {path}\n```\n{snippet}\n```")
        peers_text = (
            "Peers (arquivos em que este DEPENDE — use APIs/símbolos exatos abaixo, "
            "não invente nomes):\n\n" + "\n\n".join(blocks)
            if blocks
            else "Peers: (nenhum conteúdo de peer disponível ainda)"
        )
    else:
        peers_text = "Peers (paths apenas — referências entre si são legítimas):\n" + "\n".join(
            f"- {p}" for p in (peer_paths or [])[:40]
        )
    rnf_text = ""
    if rnf_contracts:
        rnf_text = f"\n\nContratos RNF (do OCG — OBRIGATÓRIO cumprir):\n{json.dumps(rnf_contracts, ensure_ascii=False)[:2000]}\n"
    tokens_text = ""
    if design_tokens:
        tokens_text = f"\n\nDesign tokens canônicos (frontend — use estes, NÃO invente):\n{json.dumps(design_tokens, ensure_ascii=False)[:2000]}\n"

    # MVP-K (2026-04-26) — quando este arquivo falhou na build local do
    # owner, ele reportou erros via fix-build-errors. Injetamos como seção
    # PRIORITÁRIA pro LLM consertar conscientemente. Se não veio nada,
    # bloco fica vazio e prompt é idêntico ao original.
    build_errors_text = ""
    if build_errors and build_errors.strip():
        build_errors_text = (
            f"\n\n## ⚠️ ERROS DE BUILD A CORRIGIR (PRIORITÁRIO)\n"
            f"Este arquivo já foi gerado antes mas FALHOU no build local do owner.\n"
            f"Os erros abaixo foram capturados do compilador/runtime real.\n"
            f"REGENERE o arquivo CORRIGINDO esses erros específicos. Mantenha o\n"
            f"propósito, peers e estrutura geral; só ajuste o que está quebrado:\n"
            f"```\n{build_errors[:3000]}\n```\n"
            f"Se o erro indica:\n"
            f"  - Import name errado: ajuste o nome real do export do peer.\n"
            f"  - Aridade errada: olhe a função real do peer e corrija a chamada.\n"
            f"  - Type mismatch: alinhe os tipos sem quebrar contratos do peer.\n"
            f"  - Path/module not found: use path correto baseado nos peers listados.\n"
            f"  - Dependency missing: declare em comentário no topo `# DEP_NEEDED: <pkg>`\n"
            f"    pra owner adicionar manualmente; NÃO inventa import quebrado.\n"
        )

    return (
        f"Você é um engenheiro sênior implementando 1 arquivo do scaffold do projeto "
        f"`{project_name}` (slug: {project_slug}).\n\n"
        f"Stack:\n{stack_json}\n\n"
        f"Arquitetura:\n{arch_json}\n"
        f"{rnf_text}"
        f"{tokens_text}\n"
        f"{peers_text}"
        f"{build_errors_text}\n\n"
        f"## ARQUIVO A GERAR\n"
        f"  Path: `{item_path}`\n"
        f"  Tipo: `{item_file_type}`\n"
        f"  Propósito: {item_purpose}\n\n"
        f"## REGRAS\n"
        f"- Escreva o conteúdo COMPLETO, funcional quando possível.\n"
        f"- Se faltar contexto pra implementar 100%, gere esqueleto com `# TODO:` explicando o que falta.\n"
        f"- **DOCSTRING É BLOQUEANTE** — arquivos sem docstring são REJEITADOS na validação\n"
        f"  pós-geração e o commit no Git falha. NÃO ESQUECER:\n"
        f"  • **Python (.py)**: PRIMEIRA linha não-vazia (depois de eventual shebang/encoding)\n"
        f"    DEVE ser docstring de módulo entre triple-quotes. Exemplo OBRIGATÓRIO:\n"
        f'    ```\n    """Descrição curta do propósito do módulo em PT-BR."""\n    ```\n'
        f"    Toda classe, função e método público também leva docstring (PEP 257).\n"
        f"  • **TypeScript/JavaScript (.ts/.tsx/.js/.jsx)**: PRIMEIRA linha do arquivo DEVE\n"
        f"    ser comentário JSDoc `/** ... */` descrevendo o módulo. Exports públicos\n"
        f"    (functions, classes, types) recebem JSDoc próprio. Exemplo OBRIGATÓRIO:\n"
        f'    ```\n    /** Descrição curta do módulo em PT-BR. */\n    ```\n'
        f"  • **Markdown (.md)**: começar com heading `# Título`.\n"
        f"  • Outros tipos (.yaml, .json, configs): comentário inicial quando a sintaxe permite.\n"
        f"- Não invente imports: use só peers listados acima + libs da stack declarada.\n"
        f"- **RESPEITE O TIPO DE EXPORT DO PEER** (default vs named) — lição aprendida do AJA:\n"
        f"  • Se peer_content mostra `export default X` → importe como `import X from '...'`\n"
        f"    (NÃO `import {{ X }} from '...'`).\n"
        f"  • Se peer_content mostra `export const X` ou `export function X` ou `export class X`\n"
        f"    → importe como `import {{ X }} from '...'`.\n"
        f"  • Se peer_content mostra AMBOS (default + named) → use o que faz sentido pelo contexto.\n"
        f"  • Casos canônicos do AJA (e projetos similares):\n"
        f"    - `lib/api-client.ts`: SEMPRE default export (`import apiClient from '@/lib/api-client'`).\n"
        f"    - `components/ui/{{Input,Button,Modal,DataTable}}`: usualmente default export.\n"
        f"    - `hooks/{{useX}}.ts`: usualmente named exports (`import {{ useCases }} from '...'`).\n"
        f"    - Em dúvida sobre peer não listado: verifique a CONVENÇÃO da stack (React: components default,\n"
        f"      hooks named; Node lib: prefira named).\n"
        f"- **PROPRIEDADES E ARIDADE BATEM** — quando chamar função do peer, número e nomes de\n"
        f"  args BATEM com a definição. Se peer expõe `mutate(id, data, opts)` (3 args), NUNCA\n"
        f"  chame `mutate(id, data, opts, extra)` (4 args). Em dúvida: olhe a assinatura no peer_content.\n"
        f"- Não envolva a resposta em code fences markdown (```).\n"
        f"\n"
        f"## IDIOMA — OBRIGATÓRIO PT-BR (feedback canônico)\n"
        f"- Docstrings, comentários, mensagens de erro user-facing, logs descritivos: PT-BR.\n"
        f"- Identificadores de código (nomes de função, variáveis, classes): EN (convenção da stack).\n"
        f"- Termos técnicos canônicos permanecem EN: async, await, JWT, middleware, lib, request,\n"
        f"  response, container, queue, broker, worker, payload, schema, model, controller, etc.\n"
        f"- HTTPException(detail=...), Pydantic Field descriptions, validation errors: PT-BR.\n"
        f"- Strings de UI (labels, mensagens, placeholders): PT-BR.\n\n"
        f"## FORMATO DE RESPOSTA (JSON ESTRITO)\n"
        f'{{"content": "<conteúdo completo do arquivo>", "status": "complete" | "todo", "notes": "<opcional, até 200 chars>"}}\n\n'
        f"Retorne APENAS o JSON, sem markdown, sem preâmbulo."
    )
