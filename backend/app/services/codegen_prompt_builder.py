"""MVP 12 Fase 12.9 — Builder canônico de prompts para CodeGen.

Consolida a lógica de montagem de prompt antes duplicada entre
`/scaffold` (gera projeto inteiro) e `/regenerate-file` (gera um arquivo).
Ambos compartilham:
- Header "Você é um engenheiro sênior".
- REGRA INEGOCIÁVEL — docstrings obrigatórias.
- Contexto do OCG (stack, arquitetura).
- Metadata do projeto.

Cada scope adiciona suas seções específicas:
- scaffold: testing, modules, business rules, gaps, findings, compliance,
  docs ingeridos + FORMATO multi-arquivo.
- regenerate_file: path alvo, instrução e conteúdo atual (referência)
  + FORMATO single-file.

Objetivo: ponto único de evolução dos prompts, facilita mock em testes
e garante consistência entre os dois caminhos de CodeGen.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence


# ─── Blocos compartilhados ────────────────────────────────────────────


_HEADER_SCAFFOLD = (
    "Você é um engenheiro de software sênior. Gere o scaffold completo "
    "de um projeto com código fonte REAL."
)

_HEADER_REGENERATE = (
    "Você é um engenheiro de software sênior. Gere o CONTEÚDO COMPLETO "
    "de um único arquivo de código."
)

_DOCSTRING_RULE_FULL = (
    "## REGRA INEGOCIÁVEL — DOCSTRINGS OBRIGATÓRIAS\n\n"
    "**TODO arquivo de código DEVE ter docstrings. Sem exceção, sem parametrização.**\n\n"
    "- **Python (.py)**: docstring no topo do módulo (aspas triplas) + docstring em toda classe + docstring em toda função/método (exceto `__init__` se trivial). Use PEP 257.\n"
    "- **TypeScript/JavaScript (.ts/.tsx/.js/.jsx)**: bloco JSDoc (`/** ... */`) em toda função exportada, classe e componente React. Inclua `@param`, `@returns`.\n"
    "- **Go (.go)**: comentário iniciando com o nome do identificador em toda função, tipo e package (godoc).\n"
    "- **Java (.java)**: Javadoc (`/** ... */`) em toda classe e método público.\n\n"
    "Arquivos sem docstrings serão rejeitados pela validação automática e marcados como TODO. "
    "Isso atrasa o projeto — faça direito na primeira vez."
)

_DOCSTRING_RULE_COMPACT = (
    "## REGRA INEGOCIÁVEL — DOCSTRINGS OBRIGATÓRIAS\n"
    "Todo módulo, classe e função pública DEVE ter docstring "
    "(PEP 257 para Python, JSDoc para TS/JS, godoc, Javadoc)."
)


def _fmt_json(value: Any, *, fallback: str = "", indent: int = 2) -> str:
    """Formata valor como JSON indentado; retorna fallback se vazio/None."""
    if not value:
        return fallback
    return json.dumps(value, indent=indent, ensure_ascii=False)


def _project_block(name: str, slug: str | None, description: str | None) -> str:
    lines = [f"## Projeto", f"- Nome: {name}"]
    if slug is not None:
        lines.append(f"- Slug: {slug}")
    lines.append(f"- Descrição: {description or 'Sem descrição'}")
    return "\n".join(lines)


_TESTING_OMIT = object()  # sentinela: não renderizar bloco de testing


def _ocg_context_block(
    stack: Mapping[str, Any] | None,
    architecture: Mapping[str, Any] | None,
    testing: Mapping[str, Any] | None | object = _TESTING_OMIT,
    *,
    compact: bool = False,
) -> str:
    parts = []
    stack_json = _fmt_json(stack, fallback="Não definida — use Python + FastAPI como padrão" if not compact else "Não definida")
    arch_json = _fmt_json(architecture, fallback="Padrão: Clean Architecture com camadas service/repository" if not compact else "Padrão: Clean Architecture")
    parts.append(f"## Stack Tecnológica (do OCG)\n{stack_json}")
    parts.append(f"## Arquitetura (do OCG)\n{arch_json}")
    if testing is not _TESTING_OMIT:
        # None ou dict vazio renderiza com fallback; sentinela omite a seção.
        parts.append(
            "## Requisitos de Testes (do OCG)\n"
            + _fmt_json(testing, fallback="Testes unitários e de integração obrigatórios")
        )
    return "\n\n".join(parts)


# ─── Scaffold (multi-arquivo) ─────────────────────────────────────────


def build_scaffold_prompt(
    *,
    project_name: str,
    project_slug: str | None,
    project_description: str | None,
    stack: Mapping[str, Any] | None,
    architecture: Mapping[str, Any] | None,
    testing: Mapping[str, Any] | None,
    modules: Sequence[Any] | Mapping[str, Any] | None,
    arguider_modules: Sequence[Any] | None,
    business_rules: Sequence[Any] | None,
    arguider_gaps: Sequence[Any] | None,
    critical_findings: Sequence[Any] | None,
    compliance: Sequence[Any] | None,
    ingested_docs_context: str = "",
) -> str:
    """Prompt canônico para `POST /scaffold`.

    Equivalente ao prompt in-line anterior (code_generation.py:486-569).
    """
    modules_block = _fmt_json(modules, fallback="Nenhum módulo identificado no OCG")
    arguider_modules_block = _fmt_json(list(arguider_modules)[:10] if arguider_modules else None, fallback="")
    business_rules_block = _fmt_json(list(business_rules)[:10] if business_rules else None, fallback="Sem regras de negócio explícitas")
    gaps_block = _fmt_json(list(arguider_gaps)[:10] if arguider_gaps else None, fallback="Nenhum gap identificado")
    findings_block = _fmt_json(list(critical_findings)[:5] if critical_findings else None, fallback="Nenhum")
    compliance_block = _fmt_json(list(compliance)[:5] if compliance else None, fallback="Não definido")

    return f"""{_HEADER_SCAFFOLD}

{_DOCSTRING_RULE_FULL}

{_project_block(project_name, project_slug, project_description)}

{_ocg_context_block(stack, architecture, testing)}

## Módulos Identificados (OCG + Arguidor)
{modules_block}
{arguider_modules_block}

## Regras de Negócio
{business_rules_block}

## Gaps Identificados pelo Arguidor
{gaps_block}

## Findings Críticos
{findings_block}

## Compliance
{compliance_block}

## Documentos Ingeridos
{ingested_docs_context if ingested_docs_context else 'Nenhum documento ingerido'}

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


# ─── Regenerate file (single-arquivo) ─────────────────────────────────


def build_regenerate_file_prompt(
    *,
    project_name: str,
    project_description: str | None,
    stack: Mapping[str, Any] | None,
    architecture: Mapping[str, Any] | None,
    path: str,
    instruction: str | None,
    current_content: str | None,
) -> str:
    """Prompt canônico para `POST /regenerate-file`.

    Equivalente ao prompt in-line anterior (code_generation.py:1263-1296).
    """
    extra = instruction or "Reescreva completamente o arquivo mantendo o propósito detectado pelo path."
    current_block = (
        f"\n## Conteúdo Atual (referência — pode ser inteiramente substituído)\n```\n{current_content[:6000]}\n```\n"
        if current_content
        else ""
    )

    return f"""{_HEADER_REGENERATE}

{_DOCSTRING_RULE_COMPACT}

{_project_block(project_name, slug=None, description=project_description)}

{_ocg_context_block(stack, architecture, compact=True)}

## Arquivo a gerar
Caminho: `{path}`

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
