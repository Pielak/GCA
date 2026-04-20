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
from .nodejs_nestjs import scaffold_nodejs_nestjs
from .nodejs_express import scaffold_nodejs_express

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
    data_model: Optional[dict] = None,
) -> Optional[Tuple[str, List[ScaffoldFile]]]:
    """Despacha para o scaffolder correto baseado em `STACK_RECOMMENDATION`.

    Retorna `(nome_do_scaffolder, lista_de_arquivos)` ou `None` se a
    combinação (language, framework) não tem template. Caller decide o
    que fazer no caso `None` — atualmente: cair no fluxo LLM-only do
    `code_generation_service`.

    DT-076 Fase 3: quando `data_model` é fornecido (vem do OCG.DATA_MODEL),
    anexamos artefatos DDL (schema.sql, seed.sql, migration do framework)
    à lista de arquivos gerados pelo scaffolder. Sem DDL, o app gerado
    não sobe (Spring ddl-auto=validate, TypeORM synchronize=false).
    """
    language = _extract_language(stack)
    frameworks = _extract_framework(stack)

    spec = _build_spec(stack, project_name, project_slug, package)

    log_ctx = {
        "language": language,
        "frameworks": frameworks,
        "project_slug": project_slug,
    }

    def _augment(name: str, files: List[ScaffoldFile]) -> Tuple[str, List[ScaffoldFile]]:
        """DT-076 Fase 3: anexa schema.sql + seed.sql + migration do framework."""
        if not data_model or not data_model.get("dialect_supported"):
            if data_model and not data_model.get("dialect_supported"):
                # Engine não suportado — deixa placeholder explicando
                warning_msg = _engine_placeholder(data_model)
                files = list(files) + [ScaffoldFile(
                    path="db/README_DDL.md", content=warning_msg,
                )]
            return name, files
        # Engine suportado — gera artefatos reais
        ddl_files = _ddl_files_for_scaffolder(name, data_model)
        return name, list(files) + ddl_files

    if language == "java":
        # Decidir Spring Boot vs Quarkus por hint do GP no questionário
        is_quarkus = any("quarkus" in fw for fw in frameworks)
        is_spring = any("spring" in fw for fw in frameworks)
        if is_quarkus and not is_spring:
            logger.info("scaffold.dispatch", scaffolder="java_quarkus", **log_ctx)
            return _augment("java_quarkus", scaffold_java_quarkus(spec))
        # Default Java: Spring Boot (mais comum em clientes BR)
        logger.info("scaffold.dispatch", scaffolder="java_spring", **log_ctx)
        return _augment("java_spring", scaffold_java_spring(spec))

    if language == "kotlin":
        # Kotlin tem só Spring Boot por enquanto (Ktor é candidato futuro)
        logger.info("scaffold.dispatch", scaffolder="kotlin_spring", **log_ctx)
        return _augment("kotlin_spring", scaffold_kotlin_spring(spec))

    if language == "go":
        logger.info("scaffold.dispatch", scaffolder="go_app", **log_ctx)
        return _augment("go_app", scaffold_go(spec))

    if language in ("csharp", "c#", "cs", ".net", "dotnet"):
        logger.info("scaffold.dispatch", scaffolder="csharp_aspnet", **log_ctx)
        return _augment("csharp_aspnet", scaffold_csharp_aspnet(spec))

    if language == "php":
        # PHP tem só Laravel (Symfony fica como candidato futuro)
        logger.info("scaffold.dispatch", scaffolder="php_laravel", **log_ctx)
        return _augment("php_laravel", scaffold_php_laravel(spec))

    # Node.js / TypeScript — Q27 lista "Node.js" como linguagem. Aliases
    # cobrem TypeScript puro também (frontends às vezes ficam aqui).
    if language in ("node.js", "nodejs", "node", "typescript", "javascript"):
        is_express = any("express" in fw for fw in frameworks)
        is_nestjs = any("nest" in fw for fw in frameworks)
        # Se framework explícito é Express E não é NestJS, vai pro minimalista
        if is_express and not is_nestjs:
            logger.info("scaffold.dispatch", scaffolder="nodejs_express", **log_ctx)
            return _augment("nodejs_express", scaffold_nodejs_express(spec))
        # Default Node.js: NestJS (enterprise, mais opinionado, mais valor
        # do template determinístico vs LLM solto)
        logger.info("scaffold.dispatch", scaffolder="nodejs_nestjs", **log_ctx)
        return _augment("nodejs_nestjs", scaffold_nodejs_nestjs(spec))

    # Linguagens sem template (Python ainda é LLM-only, Ruby, Rust, etc.)
    logger.info("scaffold.dispatch_no_template", **log_ctx)
    return None


# ---------------------------------------------------------------------------
# DT-076 Fase 3 — helpers de injeção de DDL
# ---------------------------------------------------------------------------

# Mapeia nome do scaffolder -> framework aceito por generate_migration
_SCAFFOLDER_TO_FRAMEWORK = {
    "java_spring": "flyway",
    "java_quarkus": "flyway",
    "kotlin_spring": "flyway",
    "csharp_aspnet": "efcore",
    "php_laravel": "laravel",
    "go_app": "go-migrate",
    "nodejs_nestjs": "typeorm",
    "nodejs_express": "knex",
}


def _ddl_files_for_scaffolder(
    scaffolder_name: str, data_model: dict,
) -> List[ScaffoldFile]:
    """Gera lista de ScaffoldFile com schema.sql + seed.sql + migration.

    Caso scaffolder desconhecido, retorna só schema.sql + seed.sql em `db/`
    (migration fica como responsabilidade do GP — README explicativo).
    """
    from app.services.ddl_generator_service import generate_ddl, generate_migration

    out: List[ScaffoldFile] = []

    # schema.sql + seed.sql sempre (em db/ pra scaffolders que não usam Flyway
    # etc; Flyway replica o schema dentro de src/main/resources/db/migration).
    for art in generate_ddl(data_model):
        out.append(ScaffoldFile(path=f"db/{art.filename}", content=art.content))

    # Migration específica do framework
    framework = _SCAFFOLDER_TO_FRAMEWORK.get(scaffolder_name)
    if framework:
        mig = generate_migration(data_model, framework)
        if mig is not None:
            out.append(ScaffoldFile(path=mig.filename, content=mig.content))

    # README orientando o ciclo de migration
    out.append(ScaffoldFile(
        path="db/README.md",
        content=_ddl_readme(scaffolder_name, data_model),
    ))

    return out


def _engine_placeholder(data_model: dict) -> str:
    """Placeholder pro caso de engine não suportado em V1 de DDL."""
    engine = data_model.get("engine_raw") or data_model.get("engine") or "?"
    return (
        f"# Modelo de dados — refinar manualmente\n\n"
        f"O GCA detectou `{engine}` como engine do projeto mas ainda não gera\n"
        f"DDL automático para este dialeto (V1 cobre PostgreSQL e MySQL).\n\n"
        f"## O que fazer\n\n"
        f"1. Crie o schema manualmente seguindo o modelo de dados em "
        f"`OCG.DATA_MODEL` (aba OCG do projeto no GCA).\n"
        f"2. Commit o SQL em `db/schema.sql` deste repositório.\n"
        f"3. Abra ticket pedindo suporte ao dialeto se for recorrente no "
        f"seu time.\n\n"
        f"## Por que não automatizamos\n\n"
        f"Dialetos SQL variam demais (tipos, quoting, AUTO_INCREMENT vs "
        f"SEQUENCE, etc). Preferimos não gerar DDL errado que o GP descobre "
        f"em produção. V2 cobre Oracle, SQL Server e SQLite.\n"
    )


def _ddl_readme(scaffolder_name: str, data_model: dict) -> str:
    framework = _SCAFFOLDER_TO_FRAMEWORK.get(scaffolder_name, "(nenhum)")
    engine = data_model.get("engine", "?")
    n_tables = len(data_model.get("tables") or [])
    return (
        f"# Banco de dados\n\n"
        f"**Engine**: {engine}\n"
        f"**Framework de migration**: {framework}\n"
        f"**Tabelas iniciais**: {n_tables}\n\n"
        f"Este diretório foi gerado automaticamente pelo GCA "
        f"(DT-076 Fase 3) a partir do `OCG.DATA_MODEL`.\n\n"
        f"## Arquivos\n\n"
        f"- `schema.sql` — DDL completo para criação do schema do zero.\n"
        f"- `seed.sql` — dados mínimos (admin inicial + config).\n"
        f"- Migration em `{framework}` está na raiz do framework "
        f"(Alembic/Flyway/Knex/etc).\n\n"
        f"## Antes do primeiro boot\n\n"
        f"O seed contém a string placeholder `__REPLACE_ON_BOOT__` no hash "
        f"da senha do admin. O primeiro boot do backend deve substituí-la "
        f"por um hash bcrypt real — ou o admin não loga.\n\n"
        f"## Mudou o modelo?\n\n"
        f"Regere via aba CodeGen do projeto no GCA. Nova versão do "
        f"`schema.sql` é emitida; use migration incremental do framework "
        f"para aplicar as mudanças em prod.\n"
    )
