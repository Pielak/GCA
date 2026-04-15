"""
RepoAnalysisService — Engine de análise de repositórios externos.

6 fases: Stack Detection → Security → Compatibility → Categorias → Decisão → Ingestão.

Docstrings:
    - Fase 1: Detecção determinística de stack (linguagem, frameworks, infra)
    - Fase 2: Análise de segurança e deprecação (EOL de runtimes/frameworks)
    - Fase 3: Avaliação de compatibilidade com GCA via IA
    - Fase 4: Análise de 13 categorias de conhecimento via IA
    - Fase 5: Decisão de integração (compatível / requer_adaptação / incompatível)
    - Fase 6: Injeção de documentos na Ingestão + relatório executivo
"""
import hashlib
import json
import re
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    IngestedDocument,
    ProjectExternalRepo,
    RepoAnalysisResult,
    RepoIntegrationRoadmap,
)
from app.services.ai_key_resolver import AIKeyResolver
from app.services.ai_service import AIProvider, AIService

logger = structlog.get_logger(__name__)

# ──────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────

MAX_FILES_PER_CATEGORY = 30
MAX_FILE_SIZE_BYTES = 50 * 1024       # 50 KB por arquivo
MAX_CATEGORY_TOTAL_BYTES = 500 * 1024  # 500 KB total por categoria

SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", "__pycache__", ".next",
    "vendor", ".venv", "venv", ".idea", ".vscode", ".mypy_cache",
    ".pytest_cache", ".tox", "coverage", ".nyc_output",
}

SKIP_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif", "svg", "ico", "woff", "woff2",
    "ttf", "eot", "map", "lock", "min.js", "min.css", "pyc",
    "pyo", "so", "dylib", "dll", "exe", "bin", "dat",
}

# Extensões por linguagem para detecção
LANGUAGE_EXTENSIONS = {
    "python": {"py"},
    "javascript": {"js", "jsx", "mjs", "cjs"},
    "typescript": {"ts", "tsx"},
    "java": {"java"},
    "go": {"go"},
    "rust": {"rs"},
    "csharp": {"cs"},
    "ruby": {"rb"},
    "php": {"php"},
    "swift": {"swift"},
    "kotlin": {"kt", "kts"},
    "cpp": {"cpp", "cc", "cxx", "c", "h", "hpp"},
}

# Manifests por linguagem
MANIFEST_FILES = {
    "python": ["requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile"],
    "javascript": ["package.json"],
    "typescript": ["package.json", "tsconfig.json"],
    "go": ["go.mod", "go.sum"],
    "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
    "rust": ["Cargo.toml"],
    "ruby": ["Gemfile"],
    "php": ["composer.json"],
}

# Frameworks conhecidos por linguagem
KNOWN_FRAMEWORKS = {
    "python": {
        "django": "web_framework",
        "flask": "web_framework",
        "fastapi": "web_framework",
        "celery": "task_queue",
        "sqlalchemy": "orm",
        "pytest": "test_framework",
        "numpy": "data_science",
        "pandas": "data_science",
        "torch": "ml_framework",
        "tensorflow": "ml_framework",
    },
    "javascript": {
        "react": "ui_framework",
        "express": "web_framework",
        "next": "fullstack_framework",
        "nestjs": "web_framework",
        "jest": "test_framework",
        "mocha": "test_framework",
        "vue": "ui_framework",
        "angular": "ui_framework",
    },
    "typescript": {
        "react": "ui_framework",
        "express": "web_framework",
        "next": "fullstack_framework",
        "nestjs": "web_framework",
        "jest": "test_framework",
        "vue": "ui_framework",
        "angular": "ui_framework",
    },
    "go": {
        "gin": "web_framework",
        "echo": "web_framework",
        "fiber": "web_framework",
        "gorm": "orm",
    },
    "java": {
        "spring-boot": "web_framework",
        "quarkus": "web_framework",
        "junit": "test_framework",
        "hibernate": "orm",
    },
    "rust": {
        "actix-web": "web_framework",
        "rocket": "web_framework",
        "axum": "web_framework",
        "tokio": "async_runtime",
    },
}

# Database adapters conhecidos
DB_ADAPTERS = {
    "psycopg2": "postgresql",
    "asyncpg": "postgresql",
    "psycopg": "postgresql",
    "mysql-connector-python": "mysql",
    "pymysql": "mysql",
    "mysqlclient": "mysql",
    "sqlite3": "sqlite",
    "aiosqlite": "sqlite",
    "pymongo": "mongodb",
    "motor": "mongodb",
    "redis": "redis",
    "aioredis": "redis",
    "pg": "postgresql",
    "mysql2": "mysql",
    "better-sqlite3": "sqlite",
    "mongoose": "mongodb",
    "ioredis": "redis",
    "typeorm": "multi_db",
    "prisma": "multi_db",
    "sequelize": "multi_db",
}


class RepoAnalysisService:
    """Engine de análise de repositórios externos para o GCA.

    Orquestra 6 fases de análise:
        1. Stack Detection (determinístico)
        2. Security & Deprecation (determinístico)
        3. GCA Compatibility (IA)
        4. Análise de 13 categorias de conhecimento (IA)
        5. Decisão de integração
        6. Injeção na Ingestão + relatório executivo
    """

    # ──────────────────────────────────────────────────────────
    # EOL databases (atualizadas até 2026)
    # ──────────────────────────────────────────────────────────

    RUNTIME_EOL = {
        "python": {
            "3.8": "2024-10-14",
            "3.9": "2025-10-05",
            "3.10": "2026-10-04",
            "3.11": "2027-10-24",
            "3.12": "2028-10-02",
            "3.13": "2029-10-01",
        },
        "javascript": {
            "14": "2023-04-30",
            "16": "2023-09-11",
            "18": "2025-04-30",
            "20": "2026-04-30",
            "22": "2027-04-30",
        },
    }

    FRAMEWORK_EOL = {
        "django": {
            "3.2": "2024-04-01",
            "4.2": "2026-04-01",
            "5.0": "2025-04-01",
            "5.2": "2028-04-01",
        },
        "flask": {},
        "react": {},
        "express": {},
    }

    # ──────────────────────────────────────────────────────────
    # Regras de categorização — 13 categorias
    # ──────────────────────────────────────────────────────────

    CATEGORY_RULES = {
        "business_rules": {
            "extensions": {"py", "ts", "js", "java", "go", "rs", "cs", "kt", "rb"},
            "exclude_patterns": ["test", "spec", "__test__", "conftest"],
            "include_patterns": ["model", "domain", "rule", "validator", "constant", "enum", "service"],
            "description": "Validações, constantes, enums, lógica de domínio",
        },
        "domain_glossary": {
            "extensions": {"py", "ts", "js", "java", "go"},
            "include_patterns": ["model", "entity", "domain", "schema", "type", "interface", "enum"],
            "description": "Termos de domínio, entidades, vocabulário ubíquo",
        },
        "workflows": {
            "extensions": {"py", "ts", "js", "java", "go", "yml", "yaml"},
            "include_patterns": ["workflow", "flow", "state", "machine", "saga", "pipeline", "process"],
            "description": "Fluxos de usuário, máquinas de estado",
        },
        "technical_docs": {
            "extensions": {"md", "txt", "rst", "adoc"},
            "include_patterns": ["readme", "contributing", "architecture", "adr", "doc", "guide", "changelog"],
            "description": "Documentação técnica, arquitetura, setup",
        },
        "architecture_patterns": {
            "extensions": {"py", "ts", "js", "java", "go", "rs"},
            "include_patterns": [
                "src/", "lib/", "app/", "core/", "service", "controller",
                "route", "middleware", "handler",
            ],
            "description": "Design patterns, organização de módulos",
        },
        "data_models": {
            "extensions": {"py", "ts", "js", "java", "sql", "prisma"},
            "include_patterns": ["model", "schema", "migration", "alembic", "prisma", "entity", "table"],
            "description": "Schemas de banco, entidades, relacionamentos",
        },
        "api_contracts": {
            "extensions": {"py", "ts", "js", "json", "yaml", "yml", "proto", "graphql", "gql"},
            "include_patterns": [
                "openapi", "swagger", "proto", "schema", "type",
                "interface", "route", "endpoint", "api",
            ],
            "description": "Endpoints, schemas, interfaces",
        },
        "processes": {
            "extensions": {"yml", "yaml", "dockerfile", "sh", "bash", "toml", "makefile"},
            "include_patterns": [
                ".github/", "dockerfile", "docker-compose", "compose",
                "alembic", "makefile", "ci", "cd", "deploy",
            ],
            "description": "CI/CD, deploy, migrations, infra",
        },
        "dependencies": {
            "extensions": {"txt", "toml", "json", "lock", "cfg", "xml", "gradle"},
            "include_patterns": [
                "requirements", "package.json", "pyproject", "go.mod",
                "cargo", "gemfile", "composer", "pom.xml", "build.gradle",
            ],
            "exact_files": True,
            "description": "Stack, versões, compatibilidade",
        },
        "integration_points": {
            "extensions": {"py", "ts", "js", "java", "go"},
            "include_patterns": [
                "client", "sdk", "webhook", "queue", "broker",
                "integration", "adapter", "connector", "gateway", "proxy",
            ],
            "description": "Serviços externos, webhooks, filas",
        },
        "security_patterns": {
            "extensions": {"py", "ts", "js", "java", "go"},
            "include_patterns": [
                "auth", "security", "middleware", "guard", "policy",
                "permission", "rbac", "jwt", "oauth", "cors",
            ],
            "description": "Auth, RBAC, criptografia, sessões",
        },
        "error_handling": {
            "extensions": {"py", "ts", "js", "java", "go"},
            "include_patterns": [
                "error", "exception", "handler", "fallback", "retry",
                "circuit", "logger", "logging",
            ],
            "description": "Códigos de erro, fallbacks, retry",
        },
        "test_patterns": {
            "extensions": {"py", "ts", "js", "java", "go", "rs"},
            "include_patterns": [
                "test", "spec", "conftest", "fixture", "factory",
                "mock", "jest", "pytest",
            ],
            "description": "Estratégia de testes, cobertura, fixtures",
        },
    }

    # ──────────────────────────────────────────────────────────
    # Prompts por categoria
    # ──────────────────────────────────────────────────────────

    CATEGORY_PROMPTS = {
        "business_rules": (
            "Identifique validações, constantes de domínio, enums, regras de negócio implícitas no código. "
            "Documente cada regra com contexto, condições e impacto. Separe regras explícitas de implícitas. "
            "**Como será usado em GCA:** Mapeadas para CodeGenerator e Gatekeeper."
        ),
        "domain_glossary": (
            "Extraia todos os termos de domínio: entidades, conceitos, estados, enums. "
            "Monte glossário com definição, sinônimos e relacionamentos. "
            "**Como será usado em GCA:** Vocabulário para o OCG e treinamento de LLMs."
        ),
        "workflows": (
            "Mapeie fluxos de usuário, processos de negócio, máquinas de estado. "
            "Para cada fluxo: trigger, passos, condições, resultado, tratamento de erro. "
            "**Como será usado em GCA:** Referência para o Arguidor Técnico."
        ),
        "technical_docs": (
            "Extraia decisões de arquitetura, padrões, setup, requisitos de ambiente. "
            "Organize como documentação técnica. "
            "**Como será usado em GCA:** LiveDocs para referência."
        ),
        "architecture_patterns": (
            "Identifique design patterns (MVC, CQRS, etc.), camadas, separação de responsabilidades, DI. "
            "Documente conexões entre módulos. "
            "**Como será usado em GCA:** Patterns para CodeGenerator e Gatekeeper (7 pilares)."
        ),
        "data_models": (
            "Mapeie entidades, campos, tipos, relacionamentos (1:1, 1:N, N:N), índices, constraints. "
            "**Como será usado em GCA:** Mapeamento para schema GCA, validação no Gatekeeper."
        ),
        "api_contracts": (
            "Mapeie endpoints, schemas, interfaces, contratos de entrada/saída, status codes, paginação. "
            "**Como será usado em GCA:** Integração com sistemas externos via n8n."
        ),
        "processes": (
            "Descreva CI/CD, deploy, migrations, automação, dependências de infra. "
            "**Como será usado em GCA:** Modelo para CI/CD do novo projeto."
        ),
        "dependencies": (
            "Liste dependências com versões, conflitos, vulnerabilidades. "
            "Classifique: core, dev, optional. "
            "**Como será usado em GCA:** Auditoria no Gatekeeper."
        ),
        "integration_points": (
            "Identifique integrações: APIs, SDKs, webhooks, filas, bancos externos. "
            "Para cada: URL, auth, formato, frequência. "
            "**Como será usado em GCA:** Mapa para Gatekeeper e CodeGenerator."
        ),
        "security_patterns": (
            "Analise auth, RBAC, criptografia, sessões/tokens, sanitização, CORS, rate limiting. "
            "**Como será usado em GCA:** Validação no Gatekeeper (pilares de segurança)."
        ),
        "error_handling": (
            "Mapeie tratamento de erros: códigos custom, fallbacks, retry, circuit breakers, logging. "
            "**Como será usado em GCA:** Padrões para CodeGenerator."
        ),
        "test_patterns": (
            "Analise testes: unitários, integração, E2E. Fixtures, factories, mocks, cobertura. "
            "**Como será usado em GCA:** Modelo para testes automáticos."
        ),
    }

    # ──────────────────────────────────────────────────────────
    # Construtor
    # ──────────────────────────────────────────────────────────

    def __init__(self, db: AsyncSession):
        """Inicializa o serviço com sessão de banco.

        Args:
            db: Sessão assíncrona do SQLAlchemy.
        """
        self.db = db

    # ──────────────────────────────────────────────────────────
    # Orquestrador principal
    # ──────────────────────────────────────────────────────────

    async def analyze_repository(self, project_id: UUID, repo_id: UUID) -> dict:
        """Orquestra as 6 fases de análise do repositório.

        Args:
            project_id: UUID do projeto.
            repo_id: UUID do repositório externo.

        Returns:
            Dicionário com status, compatibilidade, categorias e contagem de arquivos.
        """
        repo = await self.db.get(ProjectExternalRepo, repo_id)
        if not repo or repo.project_id != project_id:
            return {"error": "Repositório não encontrado", "status": "error"}

        try:
            # Atualizar status
            repo.status = "reading"
            await self.db.commit()

            # ── Fase 1: Stack Detection ──
            logger.info("repo_analysis.phase1_start", repo_id=str(repo_id))
            tree = await self._list_files(repo.provider, repo.repo_url, repo.branch, repo_id)
            if not tree:
                return await self._fail(repo, "Não foi possível listar arquivos do repositório")

            stack = self._detect_stack(tree)
            await self._save_stack(repo, stack)

            # ── Fase 2: Security & Deprecation (determinístico) ──
            logger.info("repo_analysis.phase2_start", repo_id=str(repo_id))
            vulnerabilities = self._analyze_security(stack)

            # ── Fase 3: GCA Compatibility (IA) ──
            logger.info("repo_analysis.phase3_start", repo_id=str(repo_id))
            ai_provider_str = repo.ai_provider or "deepseek"
            api_key = await AIKeyResolver.get_project_key(self.db, project_id, ai_provider_str)
            if not api_key:
                # Fallback para key global
                from app.core.config import settings
                api_key = getattr(settings, f"{ai_provider_str.upper()}_API_KEY", None)

            compatibility = await self._assess_compatibility(
                stack, vulnerabilities, tree, ai_provider_str, api_key, str(repo_id)
            )

            # ── Fase 4: Análise por categoria (IA) ──
            logger.info("repo_analysis.phase4_start", repo_id=str(repo_id))
            categories = self._categorize_files(tree)
            repo_path = self._extract_repo_path(repo.provider, repo.repo_url)
            total_files = sum(len(files) for files in categories.values())
            processed = 0
            documents = []

            for category, files in categories.items():
                if not files:
                    continue
                contents = await self._fetch_file_contents(
                    repo.provider, repo_path, files, repo.branch, repo_id
                )
                if contents:
                    analysis = await self._analyze_category(
                        category, contents, ai_provider_str, api_key, repo.repo_url
                    )
                    if analysis:
                        await self._save_category_result(
                            repo_id, project_id, category, analysis,
                            len(files), ai_provider_str, stack, vulnerabilities, compatibility,
                        )
                        documents.append({
                            "category": category,
                            "content": analysis,
                            "files_count": len(files),
                        })
                processed += len(files)
                repo.files_processed = processed
                repo.files_total = total_files
                await self.db.commit()

            # ── Fase 5: Decisão ──
            logger.info("repo_analysis.phase5_start", repo_id=str(repo_id))
            overall_status = (
                compatibility
                .get("compatibility_assessment", {})
                .get("overall_status", "incompatível")
            )
            repo.compatibility_status = overall_status

            if overall_status == "incompatível":
                repo.status = "completed"
                repo.last_read_at = datetime.now(timezone.utc)
                await self.db.commit()
                return {
                    "status": "completed",
                    "compatibility": overall_status,
                    "message": "Análise concluída — repositório incompatível para integração",
                }

            if overall_status == "requer_adaptação":
                await self._create_roadmap(repo_id, project_id, compatibility)

            # ── Fase 6: Ingestão ──
            logger.info("repo_analysis.phase6_start", repo_id=str(repo_id))
            repo_name = self._extract_repo_name(repo.repo_url)
            if overall_status == "compatível" or repo.is_approved_for_integration:
                await self._inject_into_ingestion(
                    project_id, repo_id, repo.repo_url, repo.branch,
                    ai_provider_str, repo_name, documents, repo.added_by,
                )

            # Gerar relatório executivo
            executive_report = self._generate_executive_report(
                repo_name, repo.repo_url, repo.branch, stack,
                vulnerabilities, compatibility, documents, ai_provider_str,
            )
            await self._inject_single_document(
                project_id, repo_id, repo.repo_url,
                f"external_{repo_name}_RELATORIO_EXECUTIVO.md",
                executive_report, repo.added_by,
            )

            # Finalizar
            repo.status = "completed"
            repo.last_read_at = datetime.now(timezone.utc)
            repo.files_total = total_files
            repo.files_processed = processed
            await self.db.commit()

            logger.info(
                "repo_analysis.completed",
                repo_id=str(repo_id),
                categories=len(documents),
                compatibility=overall_status,
            )

            return {
                "status": "completed",
                "compatibility": overall_status,
                "categories_analyzed": len(documents),
                "files_total": total_files,
                "files_processed": processed,
            }

        except Exception as e:
            logger.error("repo_analysis.error", repo_id=str(repo_id), error=str(e))
            return await self._fail(repo, str(e)[:500])

    # ──────────────────────────────────────────────────────────
    # Utilidades
    # ──────────────────────────────────────────────────────────

    async def _fail(self, repo: ProjectExternalRepo, error_msg: str) -> dict:
        """Marca o repo como erro e retorna resultado de falha.

        Args:
            repo: Instância do repositório externo.
            error_msg: Mensagem de erro.

        Returns:
            Dicionário com status de erro.
        """
        repo.status = "error"
        repo.error_message = error_msg
        await self.db.commit()
        return {"error": error_msg, "status": "error"}

    def _extract_repo_path(self, provider: str, repo_url: str) -> str:
        """Extrai owner/repo do URL conforme o provider.

        Args:
            provider: Nome do provider (github, gitlab, bitbucket).
            repo_url: URL completa do repositório.

        Returns:
            String no formato owner/repo.
        """
        if provider == "github":
            match = re.search(r"github\.com/([^/]+/[^/]+?)(?:\.git)?$", repo_url)
            return match.group(1) if match else ""
        elif provider == "gitlab":
            match = re.search(r"gitlab\.com/(.+?)(?:\.git)?$", repo_url)
            return match.group(1) if match else ""
        elif provider == "bitbucket":
            match = re.search(r"bitbucket\.org/([^/]+/[^/]+?)(?:\.git)?$", repo_url)
            return match.group(1) if match else ""
        return ""

    def _extract_repo_name(self, repo_url: str) -> str:
        """Extrai nome do repositório do URL.

        Args:
            repo_url: URL completa do repositório.

        Returns:
            Nome do repositório.
        """
        match = re.search(r"/([^/]+?)(?:\.git)?$", repo_url)
        return match.group(1) if match else "unknown"

    def _resolve_ai_provider(self, provider_str: str) -> AIProvider:
        """Converte string de provider para AIProvider enum.

        Args:
            provider_str: Nome do provider como string.

        Returns:
            AIProvider enum correspondente.
        """
        try:
            return AIProvider(provider_str.lower())
        except ValueError:
            logger.warning("repo_analysis.unknown_provider", provider=provider_str)
            return AIProvider.DEEPSEEK

    # ──────────────────────────────────────────────────────────
    # Fase 1: Listagem de arquivos e Stack Detection
    # ──────────────────────────────────────────────────────────

    async def _list_files(
        self, provider: str, repo_url: str, branch: str, repo_id: UUID
    ) -> list[dict]:
        """Lista árvore de arquivos do repositório via API do provider.

        Args:
            provider: Nome do provider (github, gitlab, bitbucket).
            repo_url: URL completa do repositório.
            branch: Branch a ser analisada.
            repo_id: UUID do repositório para recuperar token.

        Returns:
            Lista de dicts com path, type e size.
        """
        repo_path = self._extract_repo_path(provider, repo_url)
        if not repo_path:
            logger.error("repo_analysis.invalid_url", repo_url=repo_url)
            return []

        # Recuperar token se existir
        repo = await self.db.get(ProjectExternalRepo, repo_id)
        access_token = None
        if repo and repo.access_token_encrypted:
            try:
                from app.services.vault_service import VaultService
                vault = VaultService()
                access_token = await vault.get_secret(
                    self.db, repo.project_id, "repo_token", repo.repo_url
                )
            except Exception as e:
                logger.warning("repo_analysis.token_decrypt_error", error=str(e))

        headers = {"Accept": "application/json"}
        if access_token:
            if provider == "gitlab":
                headers["Private-Token"] = access_token
            else:
                headers["Authorization"] = f"Bearer {access_token}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if provider == "github":
                    url = (
                        f"https://api.github.com/repos/{repo_path}"
                        f"/git/trees/{branch}?recursive=1"
                    )
                    headers["Accept"] = "application/vnd.github.v3+json"
                    resp = await client.get(url, headers=headers)
                elif provider == "gitlab":
                    encoded_path = repo_path.replace("/", "%2F")
                    url = (
                        f"https://gitlab.com/api/v4/projects/{encoded_path}"
                        f"/repository/tree?recursive=true&ref={branch}&per_page=100"
                    )
                    resp = await client.get(url, headers=headers)
                elif provider == "bitbucket":
                    url = (
                        f"https://api.bitbucket.org/2.0/repositories/{repo_path}"
                        f"/src/{branch}/?pagelen=100"
                    )
                    resp = await client.get(url, headers=headers)
                else:
                    return []

                if resp.status_code != 200:
                    logger.error(
                        "repo_analysis.list_files_failed",
                        status=resp.status_code,
                        body=resp.text[:200],
                    )
                    return []

                data = resp.json()

                # Normalizar resposta por provider
                if provider == "github":
                    return [
                        {"path": item["path"], "type": item["type"], "size": item.get("size", 0)}
                        for item in data.get("tree", [])
                        if item["type"] == "blob"
                    ]
                elif provider == "gitlab":
                    return [
                        {"path": item["path"], "type": "blob", "size": 0}
                        for item in data
                        if item.get("type") == "blob"
                    ]
                elif provider == "bitbucket":
                    return [
                        {"path": item["path"], "type": "blob", "size": item.get("size", 0)}
                        for item in data.get("values", [])
                        if item.get("type") == "commit_file"
                    ]

        except Exception as e:
            logger.error("repo_analysis.list_files_error", error=str(e))
            return []

        return []

    def _detect_stack(self, tree: list[dict]) -> dict:
        """Fase 1: Detecta stack do repositório (determinístico, sem IA).

        Analisa extensões de arquivos, manifests, patterns de diretórios e
        arquivos conhecidos para inferir linguagem, frameworks, banco de dados,
        CI/CD, Docker e testes.

        Args:
            tree: Lista de arquivos do repositório.

        Returns:
            Dicionário com stack completo detectado.
        """
        paths = [f["path"] for f in tree]

        # Detectar linguagem primária por contagem de extensões
        lang_counts: dict[str, int] = {}
        for path in paths:
            ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            for lang, exts in LANGUAGE_EXTENSIONS.items():
                if ext in exts:
                    lang_counts[lang] = lang_counts.get(lang, 0) + 1

        total_code = sum(lang_counts.values()) or 1
        primary_language = max(lang_counts, key=lang_counts.get) if lang_counts else "unknown"
        distribution = {
            lang: round(count / total_code * 100)
            for lang, count in lang_counts.items()
        }

        # Detectar manifests presentes
        all_manifest_names = sum(MANIFEST_FILES.values(), [])
        manifests_found = [
            p for p in paths if p.rsplit("/", 1)[-1] in all_manifest_names
        ]

        # Detectar frameworks (baseado em nomes de arquivos e diretórios)
        frameworks_detected = []
        path_lower = " ".join(paths).lower()

        if primary_language in KNOWN_FRAMEWORKS:
            for fw_name, fw_category in KNOWN_FRAMEWORKS[primary_language].items():
                if fw_name.replace("-", "") in path_lower or fw_name in path_lower:
                    frameworks_detected.append({
                        "name": fw_name,
                        "version": "unknown",
                        "category": fw_category,
                    })

        # Detectar patterns de infraestrutura
        has_dockerfile = any("dockerfile" in p.lower() for p in paths)
        has_docker_compose = any(
            "docker-compose" in p.lower() or "compose.yml" in p.lower()
            for p in paths
        )
        has_cicd = any(
            p.startswith(".github/workflows/")
            or ".gitlab-ci" in p
            or "Jenkinsfile" in p
            or ".circleci" in p
            for p in paths
        )
        has_tests = any(
            "test" in p.lower() or "spec" in p.lower() or "conftest" in p.lower()
            for p in paths
        )

        # Detectar test framework
        test_framework = None
        if any("conftest.py" in p or "pytest" in p.lower() for p in paths):
            test_framework = "pytest"
        elif any("jest.config" in p or "jest.setup" in p for p in paths):
            test_framework = "jest"
        elif any("mocha" in p.lower() for p in paths):
            test_framework = "mocha"

        # Detectar database
        databases: set[str] = set()
        for path in paths:
            path_l = path.lower()
            if "alembic" in path_l or "migrations" in path_l:
                databases.add("postgresql")
            if "prisma" in path_l:
                databases.add("multi_db")

        # Detectar API style
        api_style = "unknown"
        if any("openapi" in p.lower() or "swagger" in p.lower() for p in paths):
            api_style = "rest"
        elif any(".proto" in p for p in paths):
            api_style = "grpc"
        elif any("schema.graphql" in p.lower() or "schema.gql" in p.lower() for p in paths):
            api_style = "graphql"
        elif any("routes" in p.lower() or "router" in p.lower() or "views" in p.lower() for p in paths):
            api_style = "rest"

        stack = {
            "repository": {
                "name": "",  # preenchido depois em _save_stack
                "files_total": len(tree),
            },
            "language": {
                "primary": primary_language,
                "distribution": distribution,
            },
            "runtime": {
                "type": primary_language,
                "required_version": "unknown",
            },
            "frameworks": frameworks_detected,
            "database": {
                "supported": list(databases),
            },
            "api_style": api_style,
            "detected_patterns": [],
            "has_dockerfile": has_dockerfile,
            "has_docker_compose": has_docker_compose,
            "has_cicd": has_cicd,
            "has_tests": has_tests,
            "test_framework": test_framework,
            "manifests_found": manifests_found,
        }

        return stack

    async def _save_stack(self, repo: ProjectExternalRepo, stack: dict):
        """Salva stack.json no registro do repositório.

        Args:
            repo: Instância do repositório externo.
            stack: Dicionário com stack detectado.
        """
        stack["repository"]["name"] = self._extract_repo_name(repo.repo_url)
        stack["repository"]["url"] = repo.repo_url
        stack["repository"]["branch"] = repo.branch
        repo.stack_json = json.dumps(stack, ensure_ascii=False)
        await self.db.commit()

    # ──────────────────────────────────────────────────────────
    # Fase 2: Security & Deprecation
    # ──────────────────────────────────────────────────────────

    def _analyze_security(self, stack: dict) -> dict:
        """Fase 2: Analisa segurança e deprecação (determinístico).

        Verifica EOL de runtimes e frameworks conhecidos.

        Args:
            stack: Dicionário com stack detectado na Fase 1.

        Returns:
            Dicionário com resumo de segurança, vulnerabilidades e breaking changes.
        """
        vulnerabilities = []
        breaking_changes = []

        language = stack.get("language", {}).get("primary", "unknown")
        runtime_version = stack.get("runtime", {}).get("required_version", "unknown")

        # Verificar EOL do runtime
        if language in self.RUNTIME_EOL and runtime_version != "unknown":
            parts = runtime_version.replace("+", "").split(".")
            version_key = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else runtime_version
            eol_date_str = self.RUNTIME_EOL.get(language, {}).get(version_key)
            if eol_date_str:
                eol = date.fromisoformat(eol_date_str)
                today = date.today()
                if today > eol:
                    vulnerabilities.append({
                        "package": language,
                        "version": runtime_version,
                        "type": "eol",
                        "severity": "high",
                        "issue": f"Runtime {language} {runtime_version} está em EOL desde {eol_date_str}",
                        "recommended_version": "Última versão LTS",
                        "impact_on_integration": "Requer atualização obrigatória antes de integração",
                    })
                    breaking_changes.append(
                        f"{language} {runtime_version} EOL em {eol_date_str}: migrar para versão suportada"
                    )

        # Verificar EOL de frameworks
        for fw in stack.get("frameworks", []):
            fw_name = fw.get("name", "").lower()
            fw_version = fw.get("version", "unknown")
            if fw_name in self.FRAMEWORK_EOL and fw_version != "unknown":
                major_minor = ".".join(fw_version.split(".")[:2])
                eol_date_str = self.FRAMEWORK_EOL.get(fw_name, {}).get(major_minor)
                if eol_date_str:
                    eol = date.fromisoformat(eol_date_str)
                    today = date.today()
                    if today > eol:
                        vulnerabilities.append({
                            "package": fw_name,
                            "version": fw_version,
                            "type": "eol",
                            "severity": "high",
                            "issue": f"{fw_name} {fw_version} está em EOL desde {eol_date_str}",
                            "recommended_version": "Última versão LTS",
                            "impact_on_integration": "Requer atualização antes de integração",
                        })
                        breaking_changes.append(
                            f"{fw_name} {fw_version} -> versão LTS: verificar breaking changes"
                        )

        # Classificar risco geral
        critical = sum(1 for v in vulnerabilities if v["severity"] == "critical")
        high = sum(1 for v in vulnerabilities if v["severity"] == "high")
        medium = sum(1 for v in vulnerabilities if v["severity"] == "medium")

        if critical > 0:
            risk_level = "alto"
        elif high > 0:
            risk_level = "médio"
        elif medium > 0:
            risk_level = "baixo"
        else:
            risk_level = "baixo"

        return {
            "security_summary": {
                "total_vulnerabilities": len(vulnerabilities),
                "critical": critical,
                "high": high,
                "medium": medium,
                "low": sum(1 for v in vulnerabilities if v["severity"] == "low"),
                "risk_level": risk_level,
            },
            "vulnerabilities": vulnerabilities,
            "breaking_changes": breaking_changes,
        }

    # ──────────────────────────────────────────────────────────
    # Fase 3: GCA Compatibility (IA)
    # ──────────────────────────────────────────────────────────

    async def _assess_compatibility(
        self,
        stack: dict,
        vulnerabilities: dict,
        tree: list[dict],
        ai_provider: str,
        api_key: Optional[str],
        repo_id: str,
    ) -> dict:
        """Fase 3: Avalia compatibilidade com GCA via IA.

        Args:
            stack: Stack detectado na Fase 1.
            vulnerabilities: Resultado da Fase 2.
            tree: Árvore de arquivos.
            ai_provider: Provider de IA a ser usado.
            api_key: API key para chamadas de IA.
            repo_id: UUID do repositório (para logging).

        Returns:
            Dicionário com matriz de compatibilidade completa.
        """
        if not api_key:
            logger.warning("repo_analysis.no_api_key", provider=ai_provider)
            return self._default_compatibility()

        # Resumo da árvore (não enviar tudo, apenas estrutura)
        tree_summary = "\n".join(f["path"] for f in tree[:100])

        prompt = f"""Você é um especialista em arquitetura de software e integração de sistemas.

Analise este repositório externo para determinar sua compatibilidade com integração em GCA (Gerenciador Central de Arquiteturas).

## Stack detectado
{json.dumps(stack, indent=2, ensure_ascii=False)}

## Vulnerabilidades/Deprecações
{json.dumps(vulnerabilities, indent=2, ensure_ascii=False)}

## Arquitetura GCA (para referência)
- Backend: FastAPI + Python 3.11+
- Frontend: React 18 + Vite + TypeScript + Tailwind CSS
- Database: PostgreSQL 16+
- Integração: n8n, Cloudflare Tunnel
- LLMs: Multi-provider (Anthropic, OpenAI, Gemini, DeepSeek)

## Estrutura do repositório
{tree_summary}

## Seu objetivo
Retorne APENAS um JSON válido (sem markdown, sem comentários, sem preamble) com esta estrutura exata:
{{
  "compatibility_assessment": {{
    "overall_status": "compatível | requer_adaptação | incompatível",
    "risk_level": "baixo | médio | alto",
    "effort_estimate_days": <número>,
    "can_proceed_with_integration": <boolean>
  }},
  "gca_backend_compatibility": {{
    "status": "compatível | requer_adaptação | incompatível",
    "reason": "<descrição>",
    "effort": "baixo | médio | alto",
    "blockers": []
  }},
  "gca_frontend_compatibility": {{
    "status": "compatível | requer_adaptação | incompatível",
    "reason": "<descrição>",
    "effort": "baixo | médio | alto",
    "blockers": []
  }},
  "gca_database_compatibility": {{
    "status": "compatível | requer_adaptação | incompatível",
    "reason": "<descrição>",
    "effort": "baixo | médio | alto"
  }},
  "gca_integration_pattern": {{
    "recommended": "<padrão>",
    "description": "<explicação>",
    "steps": ["passo1", "passo2"]
  }},
  "breaking_changes_for_integration": [
    {{"issue": "<descrição>", "impact": "<impacto>", "resolution": "<resolução>"}}
  ],
  "security_impact_on_integration": {{
    "vulnerabilities_must_fix": [],
    "vulnerabilities_recommended": [],
    "compliance_gaps": []
  }},
  "technical_debt_detected": [],
  "reuse_potential": {{
    "high_value_components": [{{"component": "<nome>", "reuse_effort": "baixo", "reason": "<motivo>"}}],
    "low_value_components": []
  }}
}}"""

        provider_enum = self._resolve_ai_provider(ai_provider)
        model = "deepseek-chat" if ai_provider == "deepseek" else "claude-sonnet-4-6"

        success, response, error = await AIService.query(
            prompt=prompt,
            provider=provider_enum,
            model=model,
            system_prompt="Você é um avaliador de compatibilidade de sistemas. Retorne APENAS JSON válido.",
            temperature=0.2,
            max_tokens=4096,
            api_key=api_key,
        )

        if not success:
            logger.error("repo_analysis.compatibility_ai_error", error=error)
            return self._default_compatibility()

        # Parsear JSON da resposta
        try:
            clean = response.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                clean = clean.rsplit("```", 1)[0]
            return json.loads(clean)
        except json.JSONDecodeError:
            logger.error("repo_analysis.compatibility_json_parse_error", response=response[:200])
            return self._default_compatibility()

    def _default_compatibility(self) -> dict:
        """Retorna matriz de compatibilidade padrão quando IA falha.

        Returns:
            Dicionário com valores padrão conservadores.
        """
        return {
            "compatibility_assessment": {
                "overall_status": "requer_adaptação",
                "risk_level": "médio",
                "effort_estimate_days": 0,
                "can_proceed_with_integration": False,
            },
            "gca_backend_compatibility": {
                "status": "unknown",
                "reason": "Análise não disponível",
                "effort": "unknown",
                "blockers": [],
            },
            "gca_frontend_compatibility": {
                "status": "unknown",
                "reason": "Análise não disponível",
                "effort": "unknown",
                "blockers": [],
            },
            "gca_database_compatibility": {
                "status": "unknown",
                "reason": "Análise não disponível",
                "effort": "unknown",
            },
            "gca_integration_pattern": {
                "recommended": "unknown",
                "description": "Análise não disponível",
                "steps": [],
            },
            "breaking_changes_for_integration": [],
            "security_impact_on_integration": {
                "vulnerabilities_must_fix": [],
                "vulnerabilities_recommended": [],
                "compliance_gaps": [],
            },
            "technical_debt_detected": [],
            "reuse_potential": {
                "high_value_components": [],
                "low_value_components": [],
            },
        }

    # ──────────────────────────────────────────────────────────
    # Fase 4: Categorização e Análise IA (13 categorias)
    # ──────────────────────────────────────────────────────────

    def _categorize_files(self, tree: list[dict]) -> dict[str, list[str]]:
        """Categoriza arquivos em 13 categorias de conhecimento.

        Aplica regras de extensão, include_patterns e exclude_patterns.
        Cada arquivo vai para a primeira categoria que fizer match.
        Respeita MAX_FILES_PER_CATEGORY.

        Args:
            tree: Árvore de arquivos do repositório.

        Returns:
            Dicionário categoria -> lista de paths.
        """
        categories: dict[str, list[str]] = {cat: [] for cat in self.CATEGORY_RULES}

        for file_info in tree:
            path = file_info["path"]
            path_lower = path.lower()

            # Pular diretórios ignorados
            if any(skip_dir + "/" in path_lower for skip_dir in SKIP_DIRS):
                continue

            # Pular extensões ignoradas
            ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            if ext in SKIP_EXTENSIONS:
                continue

            # Tentar categorizar em cada categoria
            for cat_name, rules in self.CATEGORY_RULES.items():
                # Verificar extensão
                if "extensions" in rules and ext not in rules["extensions"]:
                    # Para arquivos sem extensão como Dockerfile, Makefile
                    basename = path.rsplit("/", 1)[-1].lower()
                    if not any(p in basename for p in rules.get("include_patterns", [])):
                        continue

                # Verificar exclude patterns
                if any(exc in path_lower for exc in rules.get("exclude_patterns", [])):
                    continue

                # Verificar include patterns
                if rules.get("include_patterns"):
                    if any(inc in path_lower for inc in rules["include_patterns"]):
                        if len(categories[cat_name]) < MAX_FILES_PER_CATEGORY:
                            categories[cat_name].append(path)
                            break  # Um arquivo vai para a primeira categoria que match

        return categories

    async def _fetch_file_contents(
        self,
        provider: str,
        repo_path: str,
        files: list[str],
        branch: str,
        repo_id: UUID,
    ) -> dict[str, str]:
        """Baixa conteúdo dos arquivos via API do provider.

        Respeita MAX_FILE_SIZE_BYTES por arquivo e MAX_CATEGORY_TOTAL_BYTES total.

        Args:
            provider: Nome do provider.
            repo_path: Caminho owner/repo.
            files: Lista de paths dos arquivos.
            branch: Branch a ser lida.
            repo_id: UUID do repositório para recuperar token.

        Returns:
            Dicionário path -> conteúdo do arquivo.
        """
        repo = await self.db.get(ProjectExternalRepo, repo_id)
        access_token = None
        if repo and repo.access_token_encrypted:
            try:
                from app.services.vault_service import VaultService
                vault = VaultService()
                access_token = await vault.get_secret(
                    self.db, repo.project_id, "repo_token", repo.repo_url
                )
            except Exception as e:
                logger.warning("repo_analysis.token_decrypt_error", error=str(e))

        headers: dict[str, str] = {}
        if access_token:
            if provider == "gitlab":
                headers["Private-Token"] = access_token
            else:
                headers["Authorization"] = f"Bearer {access_token}"

        contents: dict[str, str] = {}
        total_bytes = 0

        async with httpx.AsyncClient(timeout=15.0) as client:
            for file_path in files:
                if total_bytes >= MAX_CATEGORY_TOTAL_BYTES:
                    break

                try:
                    if provider == "github":
                        url = (
                            f"https://api.github.com/repos/{repo_path}"
                            f"/contents/{file_path}?ref={branch}"
                        )
                        req_headers = {**headers, "Accept": "application/vnd.github.v3.raw"}
                        resp = await client.get(url, headers=req_headers)
                    elif provider == "gitlab":
                        encoded_path = repo_path.replace("/", "%2F")
                        encoded_file = file_path.replace("/", "%2F")
                        url = (
                            f"https://gitlab.com/api/v4/projects/{encoded_path}"
                            f"/repository/files/{encoded_file}/raw?ref={branch}"
                        )
                        resp = await client.get(url, headers=headers)
                    elif provider == "bitbucket":
                        url = (
                            f"https://api.bitbucket.org/2.0/repositories/{repo_path}"
                            f"/src/{branch}/{file_path}"
                        )
                        resp = await client.get(url, headers=headers)
                    else:
                        continue

                    if resp.status_code == 200:
                        content = resp.text
                        content_bytes = len(content.encode("utf-8"))
                        if content_bytes <= MAX_FILE_SIZE_BYTES:
                            contents[file_path] = content
                            total_bytes += content_bytes

                except Exception as e:
                    logger.warning(
                        "repo_analysis.fetch_file_error",
                        file=file_path,
                        error=str(e),
                    )
                    continue

        return contents

    async def _analyze_category(
        self,
        category: str,
        file_contents: dict[str, str],
        ai_provider: str,
        api_key: Optional[str],
        repo_url: str,
    ) -> str:
        """Analisa uma categoria de arquivos via IA.

        Args:
            category: Nome da categoria (ex: business_rules).
            file_contents: Dicionário path -> conteúdo.
            ai_provider: Provider de IA.
            api_key: API key.
            repo_url: URL do repositório (para contexto).

        Returns:
            Texto Markdown com análise da categoria, ou string vazia se falhar.
        """
        if not api_key:
            return ""

        category_prompt = self.CATEGORY_PROMPTS.get(category, "Analise estes arquivos.")

        # Montar conteúdo dos arquivos para o prompt (truncar cada arquivo a 5KB)
        files_text = ""
        for path, content in file_contents.items():
            files_text += f"\n### Arquivo: {path}\n```\n{content[:5000]}\n```\n"

        prompt = f"""Você está analisando um repositório externo para extrair conhecimento que será reutilizado em outro projeto.
Documente de forma clara e completa em Português-BR.

## Repositório: {repo_url}
## Categoria: {category}

## Instrução específica
{category_prompt}

## Arquivos para análise ({len(file_contents)} arquivos)
{files_text}

Gere um documento de análise completo e estruturado em Markdown."""

        provider_enum = self._resolve_ai_provider(ai_provider)
        model = "deepseek-chat" if ai_provider == "deepseek" else "claude-sonnet-4-6"

        success, response, error = await AIService.query(
            prompt=prompt,
            provider=provider_enum,
            model=model,
            system_prompt="Você é um analista técnico do GCA. Gere documentação técnica estruturada em Português-BR.",
            temperature=0.3,
            max_tokens=4096,
            api_key=api_key,
        )

        if not success:
            logger.error("repo_analysis.category_ai_error", category=category, error=error)
            return ""

        return response or ""

    async def _save_category_result(
        self,
        repo_id: UUID,
        project_id: UUID,
        category: str,
        analysis: str,
        files_count: int,
        ai_provider: str,
        stack: dict,
        vulnerabilities: dict,
        compatibility: dict,
    ):
        """Salva resultado de análise de uma categoria no banco.

        Args:
            repo_id: UUID do repositório.
            project_id: UUID do projeto.
            category: Nome da categoria.
            analysis: Texto da análise gerada por IA.
            files_count: Quantidade de arquivos analisados.
            ai_provider: Provider de IA utilizado.
            stack: Stack detectado na Fase 1.
            vulnerabilities: Resultado da Fase 2.
            compatibility: Resultado da Fase 3.
        """
        frameworks = stack.get("frameworks", [])
        result = RepoAnalysisResult(
            repo_id=repo_id,
            project_id=project_id,
            category=category,
            summary=analysis,
            files_analyzed=files_count,
            ai_provider_used=ai_provider,
            # Stack (compartilhado entre categorias)
            stack_json=json.dumps(stack, ensure_ascii=False),
            primary_language=stack.get("language", {}).get("primary"),
            framework_name=frameworks[0].get("name") if frameworks else None,
            has_docker=stack.get("has_dockerfile", False),
            has_cicd=stack.get("has_cicd", False),
            has_tests=stack.get("has_tests", False),
            # Security
            vulnerabilities_json=json.dumps(vulnerabilities, ensure_ascii=False),
            risk_level=vulnerabilities.get("security_summary", {}).get("risk_level", "baixo"),
            vulnerabilities_count=vulnerabilities.get("security_summary", {}).get("total_vulnerabilities", 0),
            critical_vulnerabilities=vulnerabilities.get("security_summary", {}).get("critical", 0),
            # Compatibility
            compatibility_matrix=json.dumps(compatibility, ensure_ascii=False),
            gca_overall_status=compatibility.get("compatibility_assessment", {}).get("overall_status"),
            gca_integration_effort_days=compatibility.get("compatibility_assessment", {}).get("effort_estimate_days"),
            gca_backend_compatible=(
                compatibility.get("gca_backend_compatibility", {}).get("status") == "compatível"
            ),
            gca_frontend_compatible=(
                compatibility.get("gca_frontend_compatibility", {}).get("status") == "compatível"
            ),
            gca_database_compatible=(
                compatibility.get("gca_database_compatibility", {}).get("status") == "compatível"
            ),
        )
        self.db.add(result)
        await self.db.commit()

    # ──────────────────────────────────────────────────────────
    # Fase 5: Decisão — Roadmap de integração
    # ──────────────────────────────────────────────────────────

    async def _create_roadmap(self, repo_id: UUID, project_id: UUID, compatibility: dict):
        """Cria roadmap de integração para repos que requerem adaptação.

        Args:
            repo_id: UUID do repositório.
            project_id: UUID do projeto.
            compatibility: Resultado da Fase 3.
        """
        steps = compatibility.get("gca_integration_pattern", {}).get("steps", [])

        for i, step_text in enumerate(steps, 1):
            roadmap = RepoIntegrationRoadmap(
                repo_id=repo_id,
                project_id=project_id,
                step_number=i,
                title=step_text if isinstance(step_text, str) else step_text.get("title", f"Passo {i}"),
                description=step_text if isinstance(step_text, str) else step_text.get("description", ""),
                effort_hours=8,  # Estimativa padrão
            )
            self.db.add(roadmap)

        await self.db.commit()

    # ──────────────────────────────────────────────────────────
    # Fase 6: Ingestão e Relatório Executivo
    # ──────────────────────────────────────────────────────────

    async def _inject_into_ingestion(
        self,
        project_id: UUID,
        repo_id: UUID,
        repo_url: str,
        branch: str,
        ai_provider: str,
        repo_name: str,
        documents: list[dict],
        uploaded_by: UUID,
    ):
        """Fase 6: Injeta documentos na Ingestão como source_type='external_repo'.

        Args:
            project_id: UUID do projeto.
            repo_id: UUID do repositório.
            repo_url: URL do repositório.
            branch: Branch analisada.
            ai_provider: Provider de IA utilizado.
            repo_name: Nome do repositório.
            documents: Lista de documentos analisados por categoria.
            uploaded_by: UUID do usuário que adicionou o repositório.
        """
        for doc in documents:
            category = doc["category"]
            content = doc["content"]
            if not content:
                continue

            markdown_content = f"""# [EXTERNO] {repo_name} — {category.replace('_', ' ').title()}
**Origem:** {repo_url} (branch: {branch})
**Analisado em:** {datetime.now(timezone.utc).isoformat()}
**Provider IA:** {ai_provider}
**Categoria:** {category}
**Arquivos analisados:** {doc.get('files_count', 0)}

---

{content}
"""
            await self._inject_single_document(
                project_id, repo_id, repo_url,
                f"external_{repo_name}_{category}.md",
                markdown_content, uploaded_by,
            )

    async def _inject_single_document(
        self,
        project_id: UUID,
        repo_id: UUID,
        repo_url: str,
        filename: str,
        content: str,
        uploaded_by: UUID,
    ):
        """Injeta um único documento na tabela de ingestão.

        Verifica duplicatas pelo hash SHA-256 antes de inserir.

        Args:
            project_id: UUID do projeto.
            repo_id: UUID do repositório.
            repo_url: URL do repositório.
            filename: Nome original do arquivo.
            content: Conteúdo Markdown do documento.
            uploaded_by: UUID do usuário responsável.
        """
        file_bytes = content.encode("utf-8")
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        # Verificar duplicata por hash
        existing = await self.db.execute(
            select(IngestedDocument).where(
                IngestedDocument.project_id == project_id,
                IngestedDocument.file_hash == file_hash,
            )
        )
        if existing.scalar_one_or_none():
            return  # Já existe

        doc = IngestedDocument(
            project_id=project_id,
            filename=f"{uuid4()}.md",
            original_filename=filename,
            file_type="markdown",
            file_hash=file_hash,
            file_size_bytes=len(file_bytes),
            uploaded_by=uploaded_by,
            quarantine_status="none",
            pii_detected=False,
            arguider_status="pending",
            git_file_path=f"docs/ingested/external/{filename}",
            source_type="external_repo",
            source_url=repo_url,
            source_repo_id=repo_id,
        )
        self.db.add(doc)
        await self.db.commit()

    def _generate_executive_report(
        self,
        repo_name: str,
        repo_url: str,
        branch: str,
        stack: dict,
        vulnerabilities: dict,
        compatibility: dict,
        documents: list[dict],
        ai_provider: str,
    ) -> str:
        """Gera relatório executivo consolidado para o GP.

        Args:
            repo_name: Nome do repositório.
            repo_url: URL do repositório.
            branch: Branch analisada.
            stack: Stack detectado.
            vulnerabilities: Resultado de segurança.
            compatibility: Resultado de compatibilidade.
            documents: Lista de documentos gerados por categoria.
            ai_provider: Provider de IA utilizado.

        Returns:
            String com relatório em Markdown.
        """
        lang = stack.get("language", {}).get("primary", "desconhecida")
        frameworks = (
            ", ".join(fw.get("name", "") for fw in stack.get("frameworks", []))
            or "nenhum detectado"
        )
        overall = (
            compatibility.get("compatibility_assessment", {}).get("overall_status", "desconhecido")
        )
        risk = vulnerabilities.get("security_summary", {}).get("risk_level", "desconhecido")
        effort = compatibility.get("compatibility_assessment", {}).get("effort_estimate_days", "N/A")
        vuln_total = vulnerabilities.get("security_summary", {}).get("total_vulnerabilities", 0)
        categories_analyzed = len(documents)

        # Breaking changes
        bc_list = compatibility.get("breaking_changes_for_integration", [])
        bc_text = ""
        for bc in bc_list:
            if isinstance(bc, dict):
                bc_text += f"- **{bc.get('issue', '')}**: {bc.get('impact', '')} -> {bc.get('resolution', '')}\n"
            else:
                bc_text += f"- {bc}\n"

        # Reuse potential
        reuse = compatibility.get("reuse_potential", {})
        high_value = reuse.get("high_value_components", [])
        reuse_text = ""
        for comp in high_value:
            if isinstance(comp, dict):
                reuse_text += (
                    f"- **{comp.get('component', '')}** "
                    f"(esforço: {comp.get('reuse_effort', '')}) "
                    f"-- {comp.get('reason', '')}\n"
                )

        # Documentos gerados
        docs_list = "\n".join(
            f"- `external_{repo_name}_{doc['category']}.md` ({doc.get('files_count', 0)} arquivos)"
            for doc in documents
        )

        return f"""# [EXTERNO] {repo_name} -- RELATORIO EXECUTIVO
**Origem:** {repo_url} (branch: {branch})
**Analisado em:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
**Provider IA:** {ai_provider}

---

## Resumo Executivo

| Item | Valor |
|------|-------|
| Linguagem principal | {lang} |
| Frameworks | {frameworks} |
| Compatibilidade GCA | {overall} |
| Nivel de risco | {risk} |
| Vulnerabilidades | {vuln_total} |
| Esforço estimado | {effort} dias |
| Categorias analisadas | {categories_analyzed}/13 |
| Docker | {'Sim' if stack.get('has_dockerfile') else 'Nao'} |
| CI/CD | {'Sim' if stack.get('has_cicd') else 'Nao'} |
| Testes | {'Sim' if stack.get('has_tests') else 'Nao'} |

## Breaking Changes
{bc_text or 'Nenhum detectado.'}

## Componentes Reutilizaveis
{reuse_text or 'Nenhum identificado.'}

## Documentos Gerados
{docs_list}

---
*Relatorio gerado automaticamente pelo GCA Engine de Analise de Repositorios Externos.*
"""
