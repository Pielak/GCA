"""DT-058 Sprint 2.3 — despacho de scaffolders a partir do OCG.

Função pública `dispatch_scaffold(stack_recommendation, project_metadata)`
recebe o conteúdo do `OCG.STACK_RECOMMENDATION` (estrutura DT-046) +
metadados do projeto (nome, slug) e retorna a lista de arquivos a
commitar — ou `None` se a combinação (linguagem × framework) não tem
scaffolder determinístico (caller decide o que fazer: usar LLM-only ou
falhar).

Contrato canônico (saída):
- `(scaffolder_name: str, files: list[ScaffoldFile])` quando tem template
- `None` quando não tem template (caller pode delegar ao LLM)
"""
from typing import List, Optional, Tuple

import structlog

from .types import ScaffoldFile, ScaffoldSpec
from .java_spring import scaffold_java_spring
from .java_quarkus import scaffold_java_quarkus
from .go_app import scaffold_go
from .csharp_aspnet import scaffold_csharp_aspnet
from .php_laravel import scaffold_php_laravel
from .kotlin_spring import scaffold_kotlin_spring

logger = structlog.get_logger(__name__)


def _norm(s) -> str:
    if not isinstance(s, str):
        return ""
    return s.lower().strip()


def _norm_list(value) -> List[str]:
    """Aceita string única OU lista de strings, retorna lista normalizada."""
    if isinstance(value, str):
        return [value.lower().strip()] if value.strip() else []
    if isinstance(value, list):
        return [v.lower().strip() for v in value if isinstance(v, str) and v.strip()]
    return []


def _extract_language(stack: dict) -> str:
    """Lê linguagem do backend, tolerante a estrutura DT-046 e legacy."""
    if not isinstance(stack, dict):
        return ""
    backend = stack.get("backend") or {}
    if isinstance(backend, dict):
        lang = backend.get("language")
        if lang and isinstance(lang, str):
            return _norm(lang)
    legacy = stack.get("primary_language")
    if legacy and isinstance(legacy, str):
        return _norm(legacy)
    return ""


def _extract_framework(stack: dict) -> List[str]:
    """Lê framework(s) do backend. OCG real persiste como string ou lista."""
    if not isinstance(stack, dict):
        return []
    backend = stack.get("backend") or {}
    if isinstance(backend, dict):
        return _norm_list(backend.get("framework"))
    return []


def _build_spec(
    stack: dict,
    project_name: str,
    project_slug: str,
    package: Optional[str] = None,
) -> ScaffoldSpec:
    """Monta `ScaffoldSpec` a partir do OCG.STACK_RECOMMENDATION.

    Decisões binárias derivadas do OCG:
    - `requires_security`: se `ai.enabled` ou se Q43 (security_controls)
      indica auth.
    - `requires_redis`: se `cache.enabled` (DT-046).
    - `database`: se `database.engine` é não-vazio.
    """
    if not isinstance(stack, dict):
        stack = {}
    backend = stack.get("backend") or {}
    db = stack.get("database") or {}
    cache = stack.get("cache") or {}
    if not isinstance(backend, dict): backend = {}
    if not isinstance(db, dict): db = {}
    if not isinstance(cache, dict): cache = {}

    requires_security = bool(stack.get("requires_security")) if isinstance(stack, dict) else False
    requires_redis = bool(cache.get("enabled"))
    db_engine = db.get("engine") if isinstance(db.get("engine"), str) else None

    return ScaffoldSpec(
        project_name=project_name,
        project_slug=project_slug,
        package=package or _default_package(project_slug),
        java_version="21",
        database=db_engine,
        requires_security=requires_security,
        requires_redis=requires_redis,
    )


def _default_package(slug: str) -> str:
    """Slug `automacao-juridica` → package `com.gca.automacaojuridica`.
    Cliente pode trocar via passar `package` explícito."""
    cleaned = "".join(c for c in slug.lower() if c.isalnum() or c == "-")
    short = cleaned.replace("-", "")[:50] or "app"
    return f"com.gca.{short}"


def dispatch_scaffold(
    stack: dict,
    project_name: str,
    project_slug: str,
    package: Optional[str] = None,
) -> Optional[Tuple[str, List[ScaffoldFile]]]:
    """Despacha para o scaffolder correto baseado em `STACK_RECOMMENDATION`.

    Retorna `(nome_do_scaffolder, lista_de_arquivos)` ou `None` se a
    combinação (language, framework) não tem template. Caller decide o
    que fazer no caso `None` — atualmente: cair no fluxo LLM-only do
    `code_generation_service`.
    """
    language = _extract_language(stack)
    frameworks = _extract_framework(stack)

    spec = _build_spec(stack, project_name, project_slug, package)

    log_ctx = {
        "language": language,
        "frameworks": frameworks,
        "project_slug": project_slug,
    }

    if language == "java":
        # Decidir Spring Boot vs Quarkus por hint do GP no questionário
        is_quarkus = any("quarkus" in fw for fw in frameworks)
        is_spring = any("spring" in fw for fw in frameworks)
        if is_quarkus and not is_spring:
            logger.info("scaffold.dispatch", scaffolder="java_quarkus", **log_ctx)
            return "java_quarkus", scaffold_java_quarkus(spec)
        # Default Java: Spring Boot (mais comum em clientes BR)
        logger.info("scaffold.dispatch", scaffolder="java_spring", **log_ctx)
        return "java_spring", scaffold_java_spring(spec)

    if language == "kotlin":
        # Kotlin tem só Spring Boot por enquanto (Ktor é candidato futuro)
        logger.info("scaffold.dispatch", scaffolder="kotlin_spring", **log_ctx)
        return "kotlin_spring", scaffold_kotlin_spring(spec)

    if language == "go":
        logger.info("scaffold.dispatch", scaffolder="go_app", **log_ctx)
        return "go_app", scaffold_go(spec)

    if language in ("csharp", "c#", "cs", ".net", "dotnet"):
        logger.info("scaffold.dispatch", scaffolder="csharp_aspnet", **log_ctx)
        return "csharp_aspnet", scaffold_csharp_aspnet(spec)

    if language == "php":
        # PHP tem só Laravel (Symfony fica como candidato futuro)
        logger.info("scaffold.dispatch", scaffolder="php_laravel", **log_ctx)
        return "php_laravel", scaffold_php_laravel(spec)

    # Linguagens sem template (Python ainda é LLM-only, Node.js, Ruby, etc.)
    logger.info("scaffold.dispatch_no_template", **log_ctx)
    return None
