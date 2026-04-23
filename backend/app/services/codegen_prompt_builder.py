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

from app.services.design_tokens import (
    from_ocg_dict as _design_from_ocg_dict,
    tokens_as_prompt_block,
)
from app.services.rnf_contracts import (
    RnfContracts,
    contract_as_prompt_block,
    from_ocg_dict,
)


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


# ─── MVP 23 Fase 23.3 — RNF stack-aware ──────────────────────────────


def _detect_stack_key(stack: Mapping[str, Any] | None) -> str:
    """Resolve a linguagem/framework canônico pra escolher dicas RNF.

    Retorna valores canônicos: 'python', 'node_express', 'node_nestjs',
    'java_spring', 'java_quarkus', 'kotlin_spring', 'csharp', 'go',
    'php', 'cpp', 'generic'. Fallback 'generic' quando não conseguir
    detectar.
    """
    if not stack or not isinstance(stack, Mapping):
        return "generic"
    backend = stack.get("backend") or {}
    if not isinstance(backend, Mapping):
        return "generic"
    lang = str(backend.get("language", "")).lower()
    framework = str(backend.get("framework", "")).lower()
    if "python" in lang:
        return "python"
    if "node" in lang or "typescript" in lang or "javascript" in lang:
        if "nest" in framework:
            return "node_nestjs"
        return "node_express"
    if "kotlin" in lang:
        return "kotlin_spring"
    if "java" in lang:
        if "quarkus" in framework:
            return "java_quarkus"
        return "java_spring"
    if "c#" in lang or ".net" in lang or "dotnet" in lang or "csharp" in lang:
        return "csharp"
    if "go" == lang.strip() or "golang" in lang:
        return "go"
    if "php" in lang:
        return "php"
    if "c++" in lang or "cpp" in lang:
        return "cpp"
    return "generic"


# Dicas canônicas de implementação por stack × controle.
# Cada chave do dict externo é um stack_key; cada chave interno é um
# controle canônico (rate_limit, sqli, hardcoded_secrets, pii_logging).
_STACK_HINTS: dict[str, dict[str, str]] = {
    "python": {
        "rate_limit": (
            "Use `slowapi` (FastAPI) ou `flask-limiter` (Flask). "
            "Exemplo FastAPI: `from slowapi import Limiter; "
            "@limiter.limit(\"60/minute\")` no endpoint."
        ),
        "sqli": (
            "Use SQLAlchemy ORM com parâmetros nomeados (`text('SELECT :id')`) "
            "ou Core `select()`. NUNCA concatene string em query."
        ),
        "hardcoded_secrets": (
            "Leia via `app.core.config.settings` (pydantic-settings) ou "
            "`os.environ`. NUNCA hardcode chave no código."
        ),
        "pii_logging": (
            "`structlog` já mascara por default se configurado. "
            "Nunca inclua senha/token/CPF em `logger.info/debug`. "
            "Use `logger.bind(masked_field='...')` quando necessário."
        ),
    },
    "node_express": {
        "rate_limit": (
            "Use `express-rate-limit`: "
            "`app.use(rateLimit({ windowMs: 60000, max: 60 }))`."
        ),
        "sqli": (
            "Use Knex ou query parameterizada — ex: "
            "`db.raw('SELECT * FROM x WHERE id = ?', [id])`. "
            "Nunca template literal com user input em SQL."
        ),
        "hardcoded_secrets": (
            "Leia via `process.env.X` ou lib `dotenv`. NUNCA hardcode."
        ),
        "pii_logging": "Use logger estruturado (pino/winston) com redaction.",
    },
    "node_nestjs": {
        "rate_limit": (
            "Use `@nestjs/throttler`: "
            "`@UseGuards(ThrottlerGuard)` + `@Throttle(60, 60)`."
        ),
        "sqli": (
            "Use TypeORM QueryBuilder com `.setParameter()` ou ORM repositories. "
            "Nunca concatene SQL."
        ),
        "hardcoded_secrets": (
            "Use `@nestjs/config` com `ConfigService`. Nunca hardcode."
        ),
        "pii_logging": "Logger Nest com contexto estruturado; redact de PII.",
    },
    "java_spring": {
        "rate_limit": (
            "Use `@RateLimiter(name = \"default\")` de `resilience4j` "
            "OU filter Bucket4j."
        ),
        "sqli": (
            "Use Spring Data JPA / Hibernate (queries derivadas ou "
            "`@Query` com `:param`). NUNCA concatene string em JPQL."
        ),
        "hardcoded_secrets": (
            "Use `@Value(\"${app.secret}\")` + Spring Boot profiles. "
            "Nunca hardcode."
        ),
        "pii_logging": (
            "Logback com MDC; nunca logar password/token diretamente."
        ),
    },
    "java_quarkus": {
        "rate_limit": (
            "Use `io.smallrye.faulttolerance.api.RateLimit` ou extensão "
            "`quarkus-smallrye-rate-limit`."
        ),
        "sqli": (
            "Use Panache com métodos nomeados ou `Query.setParameter()`. "
            "Nunca concatene string em JPQL/SQL nativo."
        ),
        "hardcoded_secrets": (
            "Use `@ConfigProperty(name = \"app.secret\")` + arquivo "
            "`application.properties`. Nunca hardcode."
        ),
        "pii_logging": "JBoss Logging com MDC; redact de PII.",
    },
    "kotlin_spring": {
        "rate_limit": "Use `resilience4j-spring-boot` com `@RateLimiter`.",
        "sqli": "Use Spring Data JPA / Exposed DSL. Nunca concatene SQL.",
        "hardcoded_secrets": "Use `@Value(\"\\${app.secret}\")`.",
        "pii_logging": "Logback com MDC.",
    },
    "csharp": {
        "rate_limit": (
            "Use `Microsoft.AspNetCore.RateLimiting` (fixed window): "
            "`services.AddRateLimiter(o => o.AddFixedWindowLimiter(...))`."
        ),
        "sqli": (
            "Use Entity Framework Core com LINQ; para SQL raw, use "
            "`FromSqlInterpolated($\"\")` (parametriza automaticamente)."
        ),
        "hardcoded_secrets": (
            "Use `IConfiguration` + `appsettings.json` + User Secrets / "
            "Azure Key Vault. Nunca hardcode."
        ),
        "pii_logging": "Use Serilog com filtros de PII.",
    },
    "go": {
        "rate_limit": (
            "Use `golang.org/x/time/rate` com `rate.NewLimiter(rate.Limit(1), 60)` "
            "ou middleware `didip/tollbooth`."
        ),
        "sqli": (
            "Use `database/sql` com `?` placeholders ou sqlx "
            "NamedQuery — ex: `db.Exec(\"SELECT * FROM x WHERE id = $1\", id)`."
        ),
        "hardcoded_secrets": (
            "Use `os.Getenv(\"X\")` ou lib `viper`. Nunca hardcode."
        ),
        "pii_logging": "Zerolog/zap com redact de campos sensíveis.",
    },
    "php": {
        "rate_limit": (
            "Laravel: middleware `throttle:60,1`. "
            "Puro PHP: lib `symfony/rate-limiter`."
        ),
        "sqli": (
            "Use Eloquent ORM ou prepared statements via PDO: "
            "`$stmt->bindValue(':id', $id)`. Nunca concatene SQL."
        ),
        "hardcoded_secrets": (
            "Use `env('APP_SECRET')` + arquivo `.env`. Nunca hardcode."
        ),
        "pii_logging": "Monolog com processors de redact.",
    },
    "cpp": {
        "rate_limit": (
            "Depende do framework HTTP (Crow, Pistache); use middleware "
            "custom com `std::chrono` + token bucket."
        ),
        "sqli": (
            "Use prepared statements da lib do DB (libpq `PQexecParams`, "
            "MySQL C API `mysql_stmt_bind_param`). NUNCA concatene."
        ),
        "hardcoded_secrets": (
            "Leia de env var ou arquivo de config parametrizado. Nunca hardcode."
        ),
        "pii_logging": "spdlog com filtros custom.",
    },
}


def _rnf_stack_hints_block(
    stack: Mapping[str, Any] | None,
    rnf: RnfContracts,
) -> str:
    """Bloco canônico com dicas de implementação por stack.

    Só emite dicas para controles que o contrato realmente exige
    (ex: se rate_limit_rpm_public é None, não emite dica de rate limit).
    Retorna string vazia quando não há dica aplicável.
    """
    stack_key = _detect_stack_key(stack)
    hints = _STACK_HINTS.get(stack_key, {})
    if not hints:
        return ""

    applicable: list[tuple[str, str]] = []
    s = rnf.security

    if s.rate_limit_rpm_public is not None or s.rate_limit_rpm_authenticated is not None:
        if "rate_limit" in hints:
            applicable.append(("Rate limiting", hints["rate_limit"]))

    for cwe in s.required_cwe_protections:
        cwe_norm = cwe.upper().replace("CWE-", "")
        if cwe_norm == "89" and "sqli" in hints:
            applicable.append((f"CWE-89 (SQL injection)", hints["sqli"]))
        elif cwe_norm == "798" and "hardcoded_secrets" in hints:
            applicable.append((f"CWE-798 (credenciais hardcoded)", hints["hardcoded_secrets"]))

    if s.sensitive_data_categories and "pii_logging" in hints:
        applicable.append((
            f"Dados sensíveis ({', '.join(s.sensitive_data_categories)})",
            hints["pii_logging"],
        ))

    if not applicable:
        return ""

    stack_label = {
        "python": "Python",
        "node_express": "Node.js + Express",
        "node_nestjs": "Node.js + NestJS",
        "java_spring": "Java + Spring Boot",
        "java_quarkus": "Java + Quarkus",
        "kotlin_spring": "Kotlin + Spring",
        "csharp": "C# / ASP.NET",
        "go": "Go",
        "php": "PHP / Laravel",
        "cpp": "C++",
        "generic": "stack genérica",
    }.get(stack_key, stack_key)

    lines = [f"## Implementação recomendada ({stack_label})"]
    for label, hint in applicable:
        lines.append(f"- **{label}**: {hint}")
    return "\n".join(lines)


def _rnf_full_block(
    rnf_contracts_raw: Any,
    stack: Mapping[str, Any] | None,
) -> str:
    """Compõe o bloco completo de RNF_CONTRACTS para o prompt do codegen.

    Chamado pelos builders. Retorna string vazia quando não há contrato
    declarado — caller não injeta bloco.
    """
    if rnf_contracts_raw is None or rnf_contracts_raw == {}:
        return ""
    rnf = from_ocg_dict(rnf_contracts_raw)
    if rnf.is_empty:
        return ""
    main_block = contract_as_prompt_block(rnf)
    stack_hints = _rnf_stack_hints_block(stack, rnf)
    if stack_hints:
        return f"{main_block}\n\n{stack_hints}"
    return main_block


# ─── MVP 25 Fase 25.4 — Design tokens stack-aware ────────────────────


def _detect_frontend_stack_key(stack: Mapping[str, Any] | None) -> str:
    """Resolve qual stack de frontend → aplicar hints de design tokens.

    Valores canônicos: 'tailwind', 'styled_components', 'emotion', 'mui',
    'vanilla_extract', 'css_modules', 'plain_css', 'generic'.
    Olha em `frontend.framework`, `frontend.stack`, `frontend.styling`.
    """
    if not stack or not isinstance(stack, Mapping):
        return "generic"
    frontend = stack.get("frontend") or {}
    if not isinstance(frontend, Mapping):
        return "generic"
    haystack = " ".join(
        str(frontend.get(k, "")).lower()
        for k in ("framework", "stack", "styling", "language")
    )
    if "tailwind" in haystack:
        return "tailwind"
    if "styled-components" in haystack or "styled_components" in haystack:
        return "styled_components"
    if "emotion" in haystack:
        return "emotion"
    if "mui" in haystack or "material-ui" in haystack or "material ui" in haystack:
        return "mui"
    if "vanilla-extract" in haystack or "vanilla_extract" in haystack:
        return "vanilla_extract"
    if "css module" in haystack or "css-modules" in haystack:
        return "css_modules"
    # Default quando frontend existe mas sem lib de estilo identificada.
    if haystack.strip():
        return "plain_css"
    return "generic"


#: Hints canônicos por stack × dimensão de token. Cada valor é um
#: snippet curto e concreto com a sintaxe idiomática.
_FRONTEND_DESIGN_HINTS: dict[str, dict[str, str]] = {
    "tailwind": {
        "where": (
            "Em `tailwind.config.ts` → `theme.extend`. Nunca hardcode cores "
            "em classes utilitárias (`bg-[#hex]`). Use nomes semânticos."
        ),
        "palette": (
            "theme.extend.colors: { primary: '#...', secondary: '#...' }. "
            "Consuma via `bg-primary`, `text-primary`, etc."
        ),
        "typography": (
            "theme.extend.fontFamily e fontSize. Ex: "
            "fontFamily: { sans: ['Inter', 'system-ui'] }."
        ),
        "spacing": (
            "theme.extend.spacing: { 1: '4px', 2: '8px', ... }. Não misturar "
            "com Tailwind default scale sem necessidade."
        ),
    },
    "styled_components": {
        "where": (
            "Crie `src/theme.ts` com objeto tipado + envolva o app em "
            "`<ThemeProvider theme={theme}>`. Consuma via `props.theme.*`."
        ),
        "palette": (
            "theme.colors = { primary: '#...' }. Ex: "
            "`styled.button`\\` color: ${p => p.theme.colors.primary}; \\`."
        ),
        "typography": (
            "theme.fonts.body / theme.fontSizes[2]. Garantir tipos via "
            "declaration merging em styled.d.ts."
        ),
        "spacing": (
            "theme.space = [0, 4, 8, 16, 24, ...]; consumir como "
            "`padding: ${p => p.theme.space[2]}px`."
        ),
    },
    "emotion": {
        "where": (
            "Mesma ideia de styled-components: `@emotion/react` ThemeProvider + "
            "`src/theme.ts`. Consuma via `useTheme()` ou `(theme) => ...`."
        ),
        "palette": (
            "theme.colors.primary etc. Usar `css\\`color: ${theme.colors.primary};\\``."
        ),
        "typography": "theme.fonts e theme.fontSizes como arrays/enum.",
        "spacing": "theme.space como array + helper `space(2)`.",
    },
    "mui": {
        "where": (
            "`createTheme({ palette, typography })` em `src/theme.ts` + "
            "`<ThemeProvider theme={theme}>`. NUNCA `sx={{ color: '#hex' }}`."
        ),
        "palette": (
            "palette: { primary: { main: '#...' }, secondary: { main: '#...' } }. "
            "Usar `color='primary'` nos componentes."
        ),
        "typography": (
            "typography: { fontFamily, fontSize, h1: { fontSize } }. "
            "Usar `<Typography variant='h1'>`."
        ),
        "spacing": (
            "theme.spacing(1) = 8px por default. Customize via `spacing: 4`."
        ),
    },
    "vanilla_extract": {
        "where": (
            "Use `createGlobalTheme` em `src/theme.css.ts`. Consuma via "
            "classes geradas + `vars.colors.primary`."
        ),
        "palette": "`createGlobalTheme(':root', { colors: { primary: '#...' } })`.",
        "typography": "vars.fonts.sans = 'Inter'; vars.fontSizes.md = '16px'.",
        "spacing": "vars.space[2] = '8px' — use em `padding: vars.space[2]`.",
    },
    "css_modules": {
        "where": (
            "Declare CSS custom properties em `:root` em `src/styles/tokens.css` "
            "e importe globalmente. Consuma em cada `.module.css` via var()."
        ),
        "palette": "`:root { --color-primary: #...; }` + `color: var(--color-primary)`.",
        "typography": "`--font-sans`, `--font-size-base`, `--font-weight-bold`.",
        "spacing": "`--space-1: 4px; --space-2: 8px;` e `padding: var(--space-2)`.",
    },
    "plain_css": {
        "where": (
            "Crie `src/styles/tokens.css` com CSS custom properties em `:root` "
            "e importe no entrypoint. Todo CSS subsequente consome via `var()`."
        ),
        "palette": "`:root { --color-primary: #...; }` — referenciar com `var(--color-primary)`.",
        "typography": "Custom properties `--font-family-sans`, `--font-size-base`, etc.",
        "spacing": "`--space-1: 4px; --space-2: 8px;` e `padding: var(--space-2)`.",
    },
    "generic": {
        "where": (
            "Exponha tokens como CSS custom properties em `:root` (padrão W3C). "
            "Consumidores leem via `var(--token-name)`."
        ),
        "palette": "`--color-primary`, `--color-secondary` etc.",
        "typography": "`--font-family`, `--font-size-md`, `--font-weight-bold`.",
        "spacing": "`--space-1` até `--space-8` conforme escala.",
    },
}


def _design_tokens_stack_hints_block(
    stack: Mapping[str, Any] | None,
    view: Any,
) -> str:
    """Bloco canônico com dicas de implementação por frontend stack.

    Emite dicas apenas para dimensões que realmente têm valor extraído
    (ex: sem spacing, não emite dica de spacing).
    """
    stack_key = _detect_frontend_stack_key(stack)
    hints = _FRONTEND_DESIGN_HINTS.get(stack_key, {})
    if not hints or view.is_empty:
        return ""

    stack_label = {
        "tailwind": "Tailwind CSS",
        "styled_components": "styled-components",
        "emotion": "Emotion",
        "mui": "MUI / Material UI",
        "vanilla_extract": "vanilla-extract",
        "css_modules": "CSS Modules",
        "plain_css": "CSS puro",
        "generic": "stack genérica",
    }.get(stack_key, stack_key)

    lines = [f"## Implementação de tokens ({stack_label})"]
    if "where" in hints:
        lines.append(f"- **Onde declarar**: {hints['where']}")
    if not view.palette.is_empty and "palette" in hints:
        lines.append(f"- **Paleta**: {hints['palette']}")
    if not view.typography.is_empty and "typography" in hints:
        lines.append(f"- **Tipografia**: {hints['typography']}")
    if view.spacing_px and "spacing" in hints:
        lines.append(f"- **Spacing**: {hints['spacing']}")
    return "\n".join(lines)


def _design_tokens_full_block(
    design_tokens_raw: Any,
    stack: Mapping[str, Any] | None,
) -> str:
    """Bloco completo de design tokens + hints por frontend stack.

    Retorna string vazia quando não há tokens declarados no OCG.
    """
    if design_tokens_raw is None or design_tokens_raw == {}:
        return ""
    view = _design_from_ocg_dict(design_tokens_raw)
    if view.is_empty:
        return ""
    main = tokens_as_prompt_block(view)
    stack_hints = _design_tokens_stack_hints_block(stack, view)
    if stack_hints:
        return f"{main}\n\n{stack_hints}"
    return main


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
    rnf_contracts: Any | None = None,
    design_tokens: Any | None = None,
) -> str:
    """Prompt canônico para `POST /scaffold`.

    MVP 23 Fase 23.3: aceita `rnf_contracts` (dict vindo de
    `OCGResponse.RNF_CONTRACTS`). Quando presente, injeta bloco
    estruturado de contratos + dicas de implementação por stack.
    MVP 25 Fase 25.4: aceita `design_tokens` (dict vindo de
    `OCGResponse.STACK_RECOMMENDATION.frontend.design_tokens`). Quando
    presente, injeta paleta/tipografia/escala + hints por frontend stack.
    Caller pode passar None quando OCG não tem o campo — bloco é omitido.
    """
    modules_block = _fmt_json(modules, fallback="Nenhum módulo identificado no OCG")
    arguider_modules_block = _fmt_json(list(arguider_modules)[:10] if arguider_modules else None, fallback="")
    business_rules_block = _fmt_json(list(business_rules)[:10] if business_rules else None, fallback="Sem regras de negócio explícitas")
    gaps_block = _fmt_json(list(arguider_gaps)[:10] if arguider_gaps else None, fallback="Nenhum gap identificado")
    findings_block = _fmt_json(list(critical_findings)[:5] if critical_findings else None, fallback="Nenhum")
    compliance_block = _fmt_json(list(compliance)[:5] if compliance else None, fallback="Não definido")
    rnf_block = _rnf_full_block(rnf_contracts, stack)
    rnf_section = f"\n\n{rnf_block}\n" if rnf_block else ""
    design_block = _design_tokens_full_block(design_tokens, stack)
    design_section = f"\n\n{design_block}\n" if design_block else ""

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
{rnf_section}{design_section}
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
    rnf_contracts: Any | None = None,
    design_tokens: Any | None = None,
) -> str:
    """Prompt canônico para `POST /regenerate-file`.

    MVP 23 Fase 23.3: aceita `rnf_contracts` opcional. Quando presente,
    injeta bloco canônico + dicas de stack logo após o contexto do OCG.
    MVP 25 Fase 25.4: aceita `design_tokens` opcional — mesma lógica
    (bloco canônico de paleta/tipografia + hints por frontend stack).
    """
    extra = instruction or "Reescreva completamente o arquivo mantendo o propósito detectado pelo path."
    current_block = (
        f"\n## Conteúdo Atual (referência — pode ser inteiramente substituído)\n```\n{current_content[:6000]}\n```\n"
        if current_content
        else ""
    )
    rnf_block = _rnf_full_block(rnf_contracts, stack)
    rnf_section = f"\n\n{rnf_block}\n" if rnf_block else ""
    design_block = _design_tokens_full_block(design_tokens, stack)
    design_section = f"\n\n{design_block}\n" if design_block else ""

    return f"""{_HEADER_REGENERATE}

{_DOCSTRING_RULE_COMPACT}

{_project_block(project_name, slug=None, description=project_description)}

{_ocg_context_block(stack, architecture, compact=True)}
{rnf_section}{design_section}
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
