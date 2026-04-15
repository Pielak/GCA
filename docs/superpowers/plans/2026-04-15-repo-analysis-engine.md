# Engine de Análise de Repositórios Externos — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir engine Python que analisa repositórios externos (GitHub/GitLab/Bitbucket), extrai conhecimento em 13 categorias, avalia compatibilidade com GCA, e injeta documentos na Ingestão.

**Architecture:** Engine no backend Python com 6 fases (stack detection → security check → compatibility matrix → análise 13 categorias → decisão → ingestão). n8n apenas como dispatcher de trigger. Frontend com painel de 5 abas para visualização.

**Tech Stack:** FastAPI, SQLAlchemy async, httpx, DeepSeek API (via OpenAI SDK), React 18 + TypeScript + Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-04-15-repo-analysis-engine-design.md`

---

## Task 1: Modelos de banco — novas tabelas e campos

**Files:**
- Modify: `backend/app/models/base.py` (linhas 221-250 ProjectExternalRepo, linhas 804-837 IngestedDocument)

- [ ] **Step 1: Adicionar campos ao modelo ProjectExternalRepo**

Em `backend/app/models/base.py`, localizar a classe `ProjectExternalRepo` (linha ~221) e adicionar após `updated_at`:

```python
    # --- Campos de análise (novos) ---
    stack_json = Column(Text, nullable=True)  # JSON string do stack detectado
    compatibility_status = Column(String(50), nullable=True)  # compatível | requer_adaptação | incompatível
    last_compatibility_check = Column(DateTime(timezone=True), nullable=True)
    ai_provider = Column(String(50), default="deepseek")
    is_approved_for_integration = Column(Boolean, default=False)
    approved_by_gp = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
```

- [ ] **Step 2: Adicionar campos ao modelo IngestedDocument**

Localizar classe `IngestedDocument` (linha ~804) e adicionar após `updated_at`:

```python
    # --- Rastreabilidade de origem (novos) ---
    source_type = Column(String(20), default="upload")  # upload | external_repo
    source_url = Column(Text, nullable=True)  # URL do repositório de origem
    source_repo_id = Column(UUID(as_uuid=True), ForeignKey("project_external_repos.id", ondelete="SET NULL"), nullable=True)
```

- [ ] **Step 3: Criar modelo RepoAnalysisResult**

Adicionar nova classe após `ProjectExternalRepo`:

```python
class RepoAnalysisResult(Base):
    """Resultado de análise de repositório externo — uma linha por categoria."""
    __tablename__ = "repo_analysis_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    repo_id = Column(UUID(as_uuid=True), ForeignKey("project_external_repos.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    # Stack detection (preenchido na Fase 1, mesmo valor em todas as rows do repo)
    stack_json = Column(Text, nullable=True)
    primary_language = Column(String(50), nullable=True)
    framework_name = Column(String(100), nullable=True)
    framework_version = Column(String(20), nullable=True)
    has_docker = Column(Boolean, default=False)
    has_cicd = Column(Boolean, default=False)
    has_tests = Column(Boolean, default=False)

    # Security & Deprecation (Fase 2)
    vulnerabilities_json = Column(Text, nullable=True)
    risk_level = Column(String(20), nullable=True)  # baixo | médio | alto
    vulnerabilities_count = Column(Integer, default=0)
    critical_vulnerabilities = Column(Integer, default=0)

    # GCA Compatibility (Fase 3)
    compatibility_matrix = Column(Text, nullable=True)
    gca_overall_status = Column(String(50), nullable=True)
    gca_integration_effort_days = Column(Integer, nullable=True)
    gca_backend_compatible = Column(Boolean, nullable=True)
    gca_frontend_compatible = Column(Boolean, nullable=True)
    gca_database_compatible = Column(Boolean, nullable=True)

    # Análise por categoria (Fase 4)
    category = Column(String(50), nullable=False)  # business_rules, technical_docs, etc.
    summary = Column(Text, nullable=True)
    metrics = Column(Text, nullable=True)  # JSON
    files_analyzed = Column(Integer, default=0)
    ai_provider_used = Column(String(50), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    repo = relationship("ProjectExternalRepo", backref="analysis_results")
    project = relationship("Project", foreign_keys=[project_id])

    __table_args__ = (
        Index("idx_repo_analysis_repo_id", "repo_id"),
        Index("idx_repo_analysis_gca_status", "gca_overall_status"),
    )
```

- [ ] **Step 4: Criar modelo RepoIntegrationRoadmap**

```python
class RepoIntegrationRoadmap(Base):
    """Roadmap de integração para repos que requerem adaptação."""
    __tablename__ = "repo_integration_roadmap"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    repo_id = Column(UUID(as_uuid=True), ForeignKey("project_external_repos.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    step_number = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    effort_hours = Column(Integer, nullable=True)
    status = Column(String(20), default="pending")  # pending | in_progress | completed | blocked

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)

    repo = relationship("ProjectExternalRepo", backref="integration_roadmap")
```

- [ ] **Step 5: Reiniciar backend para criar tabelas**

```bash
cd /home/luiz/GCA && docker compose restart backend
```

Verificar:
```bash
docker compose exec -T postgres psql -U gca -d gca -c "\dt repo_*"
```

Expected: `repo_analysis_results` e `repo_integration_roadmap` listadas.

Verificar campos novos:
```bash
docker compose exec -T postgres psql -U gca -d gca -c "\d project_external_repos" | grep -E "stack_json|compatibility|ai_provider|approved"
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/base.py
git commit -m "feat: modelos para análise de repos externos — RepoAnalysisResult, RepoIntegrationRoadmap, campos novos"
```

---

## Task 2: RepoAnalysisService — Fase 1: Stack Detection (determinístico)

**Files:**
- Create: `backend/app/services/repo_analysis_service.py`

- [ ] **Step 1: Criar estrutura base do serviço**

```python
"""
RepoAnalysisService — Engine de análise de repositórios externos.
6 fases: Stack Detection → Security → Compatibility → Categorias → Decisão → Ingestão.
"""
import json
import re
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional
import httpx
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.base import (
    ProjectExternalRepo, RepoAnalysisResult, RepoIntegrationRoadmap, IngestedDocument
)
from app.services.ai_service import AIService
from app.services.ai_key_resolver import AIKeyResolver

logger = structlog.get_logger(__name__)

# Constantes
MAX_FILES_PER_CATEGORY = 30
MAX_FILE_SIZE_BYTES = 50 * 1024  # 50KB por arquivo
MAX_CATEGORY_TOTAL_BYTES = 500 * 1024  # 500KB total por categoria

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
    """Engine de análise de repositórios externos para o GCA."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai_service = AIService()

    async def analyze_repository(self, project_id: UUID, repo_id: UUID) -> dict:
        """Orquestra as 6 fases de análise do repositório."""
        repo = await self.db.get(ProjectExternalRepo, repo_id)
        if not repo or repo.project_id != project_id:
            return {"error": "Repositório não encontrado", "status": "error"}

        try:
            # Atualizar status
            repo.status = "reading"
            await self.db.commit()

            # Fase 1: Stack Detection
            logger.info("repo_analysis.phase1_start", repo_id=str(repo_id))
            tree = await self._list_files(repo.provider, repo.repo_url, repo.branch, repo_id)
            if not tree:
                return await self._fail(repo, "Não foi possível listar arquivos do repositório")

            stack = self._detect_stack(tree)
            await self._save_stack(repo, stack)

            # Fase 2: Security & Deprecation (determinístico)
            logger.info("repo_analysis.phase2_start", repo_id=str(repo_id))
            vulnerabilities = self._analyze_security(stack)

            # Fase 3: GCA Compatibility (IA)
            logger.info("repo_analysis.phase3_start", repo_id=str(repo_id))
            ai_provider = repo.ai_provider or "deepseek"
            api_key = await AIKeyResolver.get_project_key(self.db, project_id, ai_provider)
            if not api_key:
                # Fallback para key global
                from app.core.config import settings
                api_key = getattr(settings, f"{ai_provider.upper()}_API_KEY", None)

            compatibility = await self._assess_compatibility(
                stack, vulnerabilities, tree, ai_provider, api_key, str(repo_id)
            )

            # Fase 4: Análise por categoria (IA)
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
                        category, contents, ai_provider, api_key, repo.repo_url
                    )
                    if analysis:
                        await self._save_category_result(
                            repo_id, project_id, category, analysis,
                            len(files), ai_provider, stack, vulnerabilities, compatibility
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

            # Fase 5: Decisão
            logger.info("repo_analysis.phase5_start", repo_id=str(repo_id))
            overall_status = compatibility.get("compatibility_assessment", {}).get("overall_status", "incompatível")
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

            # Fase 6: Ingestão
            logger.info("repo_analysis.phase6_start", repo_id=str(repo_id))
            repo_name = self._extract_repo_name(repo.repo_url)
            if overall_status == "compatível" or repo.is_approved_for_integration:
                await self._inject_into_ingestion(
                    project_id, repo_id, repo.repo_url, repo.branch,
                    ai_provider, repo_name, documents
                )

            # Gerar relatório executivo
            executive_report = self._generate_executive_report(
                repo_name, repo.repo_url, repo.branch, stack,
                vulnerabilities, compatibility, documents, ai_provider
            )
            await self._inject_single_document(
                project_id, repo_id, repo.repo_url,
                f"external_{repo_name}_RELATORIO_EXECUTIVO.md",
                executive_report
            )

            # Finalizar
            repo.status = "completed"
            repo.last_read_at = datetime.now(timezone.utc)
            repo.files_total = total_files
            repo.files_processed = processed
            await self.db.commit()

            logger.info("repo_analysis.completed",
                        repo_id=str(repo_id),
                        categories=len(documents),
                        compatibility=overall_status)

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

    async def _fail(self, repo: ProjectExternalRepo, error_msg: str) -> dict:
        """Marca o repo como erro e retorna."""
        repo.status = "error"
        repo.error_message = error_msg
        await self.db.commit()
        return {"error": error_msg, "status": "error"}
```

- [ ] **Step 2: Implementar _list_files e _extract_repo_path**

Adicionar ao `RepoAnalysisService`:

```python
    def _extract_repo_path(self, provider: str, repo_url: str) -> str:
        """Extrai owner/repo do URL."""
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
        """Extrai nome do repo do URL."""
        match = re.search(r"/([^/]+?)(?:\.git)?$", repo_url)
        return match.group(1) if match else "unknown"

    async def _list_files(self, provider: str, repo_url: str, branch: str, repo_id: UUID) -> list[dict]:
        """Lista árvore de arquivos do repositório via API do provider."""
        repo_path = self._extract_repo_path(provider, repo_url)
        if not repo_path:
            logger.error("repo_analysis.invalid_url", repo_url=repo_url)
            return []

        # Recuperar token se existir
        repo = await self.db.get(ProjectExternalRepo, repo_id)
        access_token = None
        if repo and repo.access_token_encrypted:
            from app.services.vault_service import VaultService
            vault = VaultService()
            access_token = await vault.get_secret(self.db, repo.project_id, "repo_token", repo.repo_url)

        headers = {"Accept": "application/json"}
        if access_token:
            if provider == "gitlab":
                headers["Private-Token"] = access_token
            else:
                headers["Authorization"] = f"Bearer {access_token}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if provider == "github":
                    url = f"https://api.github.com/repos/{repo_path}/git/trees/{branch}?recursive=1"
                    headers["Accept"] = "application/vnd.github.v3+json"
                    resp = await client.get(url, headers=headers)
                elif provider == "gitlab":
                    encoded_path = repo_path.replace("/", "%2F")
                    url = f"https://gitlab.com/api/v4/projects/{encoded_path}/repository/tree?recursive=true&ref={branch}&per_page=100"
                    resp = await client.get(url, headers=headers)
                elif provider == "bitbucket":
                    url = f"https://api.bitbucket.org/2.0/repositories/{repo_path}/src/{branch}/?pagelen=100"
                    resp = await client.get(url, headers=headers)
                else:
                    return []

                if resp.status_code != 200:
                    logger.error("repo_analysis.list_files_failed",
                                 status=resp.status_code, body=resp.text[:200])
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
```

- [ ] **Step 3: Implementar _detect_stack (Fase 1)**

```python
    def _detect_stack(self, tree: list[dict]) -> dict:
        """Fase 1: Detecta stack do repositório (determinístico, sem IA)."""
        paths = [f["path"] for f in tree]

        # Detectar linguagem primária por contagem de extensões
        lang_counts = {}
        for path in paths:
            ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            for lang, exts in LANGUAGE_EXTENSIONS.items():
                if ext in exts:
                    lang_counts[lang] = lang_counts.get(lang, 0) + 1

        total_code = sum(lang_counts.values()) or 1
        primary_language = max(lang_counts, key=lang_counts.get) if lang_counts else "unknown"
        distribution = {lang: round(count / total_code * 100) for lang, count in lang_counts.items()}

        # Detectar manifests presentes
        manifests_found = [p for p in paths if p.rsplit("/", 1)[-1] in sum(MANIFEST_FILES.values(), [])]

        # Detectar frameworks (baseado em nomes de arquivos e diretórios)
        frameworks_detected = []
        path_lower = " ".join(paths).lower()

        if primary_language in KNOWN_FRAMEWORKS:
            for fw_name, fw_category in KNOWN_FRAMEWORKS[primary_language].items():
                # Verificar se aparece em manifests ou estrutura
                if fw_name.replace("-", "") in path_lower or fw_name in path_lower:
                    frameworks_detected.append({
                        "name": fw_name,
                        "version": "unknown",
                        "category": fw_category,
                    })

        # Detectar patterns
        has_dockerfile = any("dockerfile" in p.lower() for p in paths)
        has_docker_compose = any("docker-compose" in p.lower() or "compose.yml" in p.lower() for p in paths)
        has_cicd = any(
            p.startswith(".github/workflows/") or
            ".gitlab-ci" in p or
            "Jenkinsfile" in p or
            ".circleci" in p
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
        databases = set()
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
                "name": self._extract_repo_name(""),  # preenchido depois
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
        """Salva stack.json no repo."""
        stack["repository"]["name"] = self._extract_repo_name(repo.repo_url)
        stack["repository"]["url"] = repo.repo_url
        stack["repository"]["branch"] = repo.branch
        repo.stack_json = json.dumps(stack, ensure_ascii=False)
        await self.db.commit()
```

- [ ] **Step 4: Verificar stack detection com samplemod**

```bash
docker compose exec backend python3 -c "
import asyncio
from app.db.database import AsyncSessionLocal
from app.services.repo_analysis_service import RepoAnalysisService
from uuid import UUID

async def test():
    async with AsyncSessionLocal() as db:
        svc = RepoAnalysisService(db)
        tree = await svc._list_files('github', 'https://github.com/navdeep-G/samplemod', 'master', UUID('7afa77b3-c8f8-47ff-8844-b6fb92b0e416'))
        print(f'Files found: {len(tree)}')
        stack = svc._detect_stack(tree)
        import json
        print(json.dumps(stack, indent=2))

asyncio.run(test())
"
```

Expected: Deve listar ~21 arquivos e detectar Python como linguagem primária.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/repo_analysis_service.py
git commit -m "feat: RepoAnalysisService — Fase 1 Stack Detection (listagem + detecção determinística)"
```

---

## Task 3: RepoAnalysisService — Fase 2: Security & Deprecation

**Files:**
- Modify: `backend/app/services/repo_analysis_service.py`

- [ ] **Step 1: Implementar _analyze_security**

Adicionar ao `RepoAnalysisService`:

```python
    # Datas de EOL conhecidas (atualizadas até 2026)
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
        "flask": {},  # Flask não tem EOL formal
        "react": {},  # React não tem EOL formal
        "express": {},
    }

    def _analyze_security(self, stack: dict) -> dict:
        """Fase 2: Analisa segurança e deprecação (determinístico)."""
        vulnerabilities = []
        breaking_changes = []

        language = stack.get("language", {}).get("primary", "unknown")
        runtime_version = stack.get("runtime", {}).get("required_version", "unknown")

        # Verificar EOL do runtime
        if language in self.RUNTIME_EOL and runtime_version != "unknown":
            version_key = runtime_version.replace("+", "").split(".")[0] + "." + runtime_version.replace("+", "").split(".")[1] if "." in runtime_version else runtime_version
            eol_date = self.RUNTIME_EOL.get(language, {}).get(version_key)
            if eol_date:
                from datetime import date
                eol = date.fromisoformat(eol_date)
                today = date.today()
                if today > eol:
                    vulnerabilities.append({
                        "package": language,
                        "version": runtime_version,
                        "type": "eol",
                        "severity": "high",
                        "issue": f"Runtime {language} {runtime_version} está em EOL desde {eol_date}",
                        "recommended_version": "Última versão LTS",
                        "impact_on_integration": "Requer atualização obrigatória antes de integração",
                    })
                    breaking_changes.append(f"{language} {runtime_version} EOL em {eol_date}: migrar para versão suportada")

        # Verificar EOL de frameworks
        for fw in stack.get("frameworks", []):
            fw_name = fw.get("name", "").lower()
            fw_version = fw.get("version", "unknown")
            if fw_name in self.FRAMEWORK_EOL and fw_version != "unknown":
                major_minor = ".".join(fw_version.split(".")[:2])
                eol_date = self.FRAMEWORK_EOL.get(fw_name, {}).get(major_minor)
                if eol_date:
                    from datetime import date
                    eol = date.fromisoformat(eol_date)
                    today = date.today()
                    if today > eol:
                        vulnerabilities.append({
                            "package": fw_name,
                            "version": fw_version,
                            "type": "eol",
                            "severity": "high",
                            "issue": f"{fw_name} {fw_version} está em EOL desde {eol_date}",
                            "recommended_version": "Última versão LTS",
                            "impact_on_integration": "Requer atualização antes de integração",
                        })
                        breaking_changes.append(f"{fw_name} {fw_version} → versão LTS: verificar breaking changes")

        # Classificar risco
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/repo_analysis_service.py
git commit -m "feat: RepoAnalysisService — Fase 2 Security & Deprecation Analysis"
```

---

## Task 4: RepoAnalysisService — Fase 3: GCA Compatibility Matrix (IA)

**Files:**
- Modify: `backend/app/services/repo_analysis_service.py`

- [ ] **Step 1: Implementar _assess_compatibility**

```python
    async def _assess_compatibility(
        self, stack: dict, vulnerabilities: dict, tree: list[dict],
        ai_provider: str, api_key: str, repo_id: str
    ) -> dict:
        """Fase 3: Avalia compatibilidade com GCA via IA."""
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

        model = "deepseek-chat" if ai_provider == "deepseek" else "claude-sonnet-4-6"
        success, response, error = await self.ai_service.query(
            prompt=prompt,
            provider=ai_provider,
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
            # Limpar possíveis markdown wrappers
            clean = response.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                clean = clean.rsplit("```", 1)[0]
            return json.loads(clean)
        except json.JSONDecodeError:
            logger.error("repo_analysis.compatibility_json_parse_error", response=response[:200])
            return self._default_compatibility()

    def _default_compatibility(self) -> dict:
        """Retorna matriz de compatibilidade padrão quando IA falha."""
        return {
            "compatibility_assessment": {
                "overall_status": "requer_adaptação",
                "risk_level": "médio",
                "effort_estimate_days": 0,
                "can_proceed_with_integration": False,
            },
            "gca_backend_compatibility": {"status": "unknown", "reason": "Análise não disponível", "effort": "unknown", "blockers": []},
            "gca_frontend_compatibility": {"status": "unknown", "reason": "Análise não disponível", "effort": "unknown", "blockers": []},
            "gca_database_compatibility": {"status": "unknown", "reason": "Análise não disponível", "effort": "unknown"},
            "gca_integration_pattern": {"recommended": "unknown", "description": "Análise não disponível", "steps": []},
            "breaking_changes_for_integration": [],
            "security_impact_on_integration": {"vulnerabilities_must_fix": [], "vulnerabilities_recommended": [], "compliance_gaps": []},
            "technical_debt_detected": [],
            "reuse_potential": {"high_value_components": [], "low_value_components": []},
        }
```

- [ ] **Step 2: Verificar que AIService.query aceita api_key**

Verificar `backend/app/services/ai_service.py` — se o método `query()` não aceitar `api_key` como parâmetro, adicionar:

```python
async def query(self, prompt: str, provider: str = ..., model: str = ...,
                system_prompt: str = ..., temperature: float = ...,
                max_tokens: int = ..., api_key: str = None) -> tuple:
```

E passar `api_key` para os métodos `_query_*` internos.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/repo_analysis_service.py backend/app/services/ai_service.py
git commit -m "feat: RepoAnalysisService — Fase 3 GCA Compatibility Matrix via IA"
```

---

## Task 5: RepoAnalysisService — Fase 4: Categorização e Análise IA (13 categorias)

**Files:**
- Modify: `backend/app/services/repo_analysis_service.py`

- [ ] **Step 1: Implementar _categorize_files**

```python
    # Regras de categorização — 13 categorias
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
            "include_patterns": ["src/", "lib/", "app/", "core/", "service", "controller", "route", "middleware", "handler"],
            "description": "Design patterns, organização de módulos",
        },
        "data_models": {
            "extensions": {"py", "ts", "js", "java", "sql", "prisma"},
            "include_patterns": ["model", "schema", "migration", "alembic", "prisma", "entity", "table"],
            "description": "Schemas de banco, entidades, relacionamentos",
        },
        "api_contracts": {
            "extensions": {"py", "ts", "js", "json", "yaml", "yml", "proto", "graphql", "gql"},
            "include_patterns": ["openapi", "swagger", "proto", "schema", "type", "interface", "route", "endpoint", "api"],
            "description": "Endpoints, schemas, interfaces",
        },
        "processes": {
            "extensions": {"yml", "yaml", "dockerfile", "sh", "bash", "toml", "makefile"},
            "include_patterns": [".github/", "dockerfile", "docker-compose", "compose", "alembic", "makefile", "ci", "cd", "deploy"],
            "description": "CI/CD, deploy, migrations, infra",
        },
        "dependencies": {
            "extensions": {"txt", "toml", "json", "lock", "cfg", "xml", "gradle"},
            "include_patterns": ["requirements", "package.json", "pyproject", "go.mod", "cargo", "gemfile", "composer", "pom.xml", "build.gradle"],
            "exact_files": True,
            "description": "Stack, versões, compatibilidade",
        },
        "integration_points": {
            "extensions": {"py", "ts", "js", "java", "go"},
            "include_patterns": ["client", "sdk", "webhook", "queue", "broker", "integration", "adapter", "connector", "gateway", "proxy"],
            "description": "Serviços externos, webhooks, filas",
        },
        "security_patterns": {
            "extensions": {"py", "ts", "js", "java", "go"},
            "include_patterns": ["auth", "security", "middleware", "guard", "policy", "permission", "rbac", "jwt", "oauth", "cors"],
            "description": "Auth, RBAC, criptografia, sessões",
        },
        "error_handling": {
            "extensions": {"py", "ts", "js", "java", "go"},
            "include_patterns": ["error", "exception", "handler", "fallback", "retry", "circuit", "logger", "logging"],
            "description": "Códigos de erro, fallbacks, retry",
        },
        "test_patterns": {
            "extensions": {"py", "ts", "js", "java", "go", "rs"},
            "include_patterns": ["test", "spec", "conftest", "fixture", "factory", "mock", "jest", "pytest"],
            "description": "Estratégia de testes, cobertura, fixtures",
        },
    }

    def _categorize_files(self, tree: list[dict]) -> dict[str, list[str]]:
        """Categoriza arquivos em 13 categorias de conhecimento."""
        categories = {cat: [] for cat in self.CATEGORY_RULES}

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
```

- [ ] **Step 2: Implementar _fetch_file_contents**

```python
    async def _fetch_file_contents(
        self, provider: str, repo_path: str, files: list[str],
        branch: str, repo_id: UUID
    ) -> dict[str, str]:
        """Baixa conteúdo dos arquivos via API do provider."""
        repo = await self.db.get(ProjectExternalRepo, repo_id)
        access_token = None
        if repo and repo.access_token_encrypted:
            from app.services.vault_service import VaultService
            vault = VaultService()
            access_token = await vault.get_secret(self.db, repo.project_id, "repo_token", repo.repo_url)

        headers = {}
        if access_token:
            if provider == "gitlab":
                headers["Private-Token"] = access_token
            else:
                headers["Authorization"] = f"Bearer {access_token}"

        contents = {}
        total_bytes = 0

        async with httpx.AsyncClient(timeout=15.0) as client:
            for file_path in files:
                if total_bytes >= MAX_CATEGORY_TOTAL_BYTES:
                    break

                try:
                    if provider == "github":
                        url = f"https://api.github.com/repos/{repo_path}/contents/{file_path}?ref={branch}"
                        headers["Accept"] = "application/vnd.github.v3.raw"
                        resp = await client.get(url, headers=headers)
                    elif provider == "gitlab":
                        encoded_path = repo_path.replace("/", "%2F")
                        encoded_file = file_path.replace("/", "%2F")
                        url = f"https://gitlab.com/api/v4/projects/{encoded_path}/repository/files/{encoded_file}/raw?ref={branch}"
                        resp = await client.get(url, headers=headers)
                    elif provider == "bitbucket":
                        url = f"https://api.bitbucket.org/2.0/repositories/{repo_path}/src/{branch}/{file_path}"
                        resp = await client.get(url, headers=headers)
                    else:
                        continue

                    if resp.status_code == 200:
                        content = resp.text
                        if len(content.encode()) <= MAX_FILE_SIZE_BYTES:
                            contents[file_path] = content
                            total_bytes += len(content.encode())

                except Exception as e:
                    logger.warning("repo_analysis.fetch_file_error", file=file_path, error=str(e))
                    continue

        return contents
```

- [ ] **Step 3: Implementar _analyze_category com prompts das 13 categorias**

```python
    CATEGORY_PROMPTS = {
        "business_rules": "Identifique validações, constantes de domínio, enums, regras de negócio implícitas no código. Documente cada regra com contexto, condições e impacto. Separe regras explícitas de implícitas. **Como será usado em GCA:** Mapeadas para CodeGenerator e Gatekeeper.",
        "domain_glossary": "Extraia todos os termos de domínio: entidades, conceitos, estados, enums. Monte glossário com definição, sinônimos e relacionamentos. **Como será usado em GCA:** Vocabulário para o OCG e treinamento de LLMs.",
        "workflows": "Mapeie fluxos de usuário, processos de negócio, máquinas de estado. Para cada fluxo: trigger, passos, condições, resultado, tratamento de erro. **Como será usado em GCA:** Referência para o Arguidor Técnico.",
        "technical_docs": "Extraia decisões de arquitetura, padrões, setup, requisitos de ambiente. Organize como documentação técnica. **Como será usado em GCA:** LiveDocs para referência.",
        "architecture_patterns": "Identifique design patterns (MVC, CQRS, etc.), camadas, separação de responsabilidades, DI. Documente conexões entre módulos. **Como será usado em GCA:** Patterns para CodeGenerator e Gatekeeper (7 pilares).",
        "data_models": "Mapeie entidades, campos, tipos, relacionamentos (1:1, 1:N, N:N), índices, constraints. **Como será usado em GCA:** Mapeamento para schema GCA, validação no Gatekeeper.",
        "api_contracts": "Mapeie endpoints, schemas, interfaces, contratos de entrada/saída, status codes, paginação. **Como será usado em GCA:** Integração com sistemas externos via n8n.",
        "processes": "Descreva CI/CD, deploy, migrations, automação, dependências de infra. **Como será usado em GCA:** Modelo para CI/CD do novo projeto.",
        "dependencies": "Liste dependências com versões, conflitos, vulnerabilidades. Classifique: core, dev, optional. **Como será usado em GCA:** Auditoria no Gatekeeper.",
        "integration_points": "Identifique integrações: APIs, SDKs, webhooks, filas, bancos externos. Para cada: URL, auth, formato, frequência. **Como será usado em GCA:** Mapa para Gatekeeper e CodeGenerator.",
        "security_patterns": "Analise auth, RBAC, criptografia, sessões/tokens, sanitização, CORS, rate limiting. **Como será usado em GCA:** Validação no Gatekeeper (pilares de segurança).",
        "error_handling": "Mapeie tratamento de erros: códigos custom, fallbacks, retry, circuit breakers, logging. **Como será usado em GCA:** Padrões para CodeGenerator.",
        "test_patterns": "Analise testes: unitários, integração, E2E. Fixtures, factories, mocks, cobertura. **Como será usado em GCA:** Modelo para testes automáticos.",
    }

    async def _analyze_category(
        self, category: str, file_contents: dict[str, str],
        ai_provider: str, api_key: str, repo_url: str
    ) -> str:
        """Analisa uma categoria de arquivos via IA."""
        if not api_key:
            return ""

        category_prompt = self.CATEGORY_PROMPTS.get(category, "Analise estes arquivos.")

        # Montar conteúdo dos arquivos para o prompt
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

        model = "deepseek-chat" if ai_provider == "deepseek" else "claude-sonnet-4-6"
        success, response, error = await self.ai_service.query(
            prompt=prompt,
            provider=ai_provider,
            model=model,
            system_prompt="Você é um analista técnico do GCA. Gere documentação técnica estruturada em Português-BR.",
            temperature=0.3,
            max_tokens=4096,
            api_key=api_key,
        )

        if not success:
            logger.error("repo_analysis.category_ai_error", category=category, error=error)
            return ""

        return response
```

- [ ] **Step 4: Implementar _save_category_result**

```python
    async def _save_category_result(
        self, repo_id: UUID, project_id: UUID, category: str,
        analysis: str, files_count: int, ai_provider: str,
        stack: dict, vulnerabilities: dict, compatibility: dict
    ):
        """Salva resultado de análise de uma categoria."""
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
            framework_name=stack.get("frameworks", [{}])[0].get("name") if stack.get("frameworks") else None,
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
            gca_backend_compatible=compatibility.get("gca_backend_compatibility", {}).get("status") == "compatível",
            gca_frontend_compatible=compatibility.get("gca_frontend_compatibility", {}).get("status") == "compatível",
            gca_database_compatible=compatibility.get("gca_database_compatibility", {}).get("status") == "compatível",
        )
        self.db.add(result)
        await self.db.commit()
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/repo_analysis_service.py
git commit -m "feat: RepoAnalysisService — Fase 4 categorização e análise IA (13 categorias)"
```

---

## Task 6: RepoAnalysisService — Fases 5-6: Decisão, Ingestão e Relatório Executivo

**Files:**
- Modify: `backend/app/services/repo_analysis_service.py`

- [ ] **Step 1: Implementar _create_roadmap**

```python
    async def _create_roadmap(self, repo_id: UUID, project_id: UUID, compatibility: dict):
        """Cria roadmap de integração para repos que requerem adaptação."""
        steps = compatibility.get("gca_integration_pattern", {}).get("steps", [])
        breaking_changes = compatibility.get("breaking_changes_for_integration", [])

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
```

- [ ] **Step 2: Implementar _inject_into_ingestion e _inject_single_document**

```python
    async def _inject_into_ingestion(
        self, project_id: UUID, repo_id: UUID, repo_url: str,
        branch: str, ai_provider: str, repo_name: str, documents: list[dict]
    ):
        """Fase 6: Injeta documentos na Ingestão como source_type='external_repo'."""
        import hashlib

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
                markdown_content,
            )

    async def _inject_single_document(
        self, project_id: UUID, repo_id: UUID, repo_url: str,
        filename: str, content: str
    ):
        """Injeta um único documento na tabela de ingestão."""
        import hashlib
        from uuid import uuid4

        file_bytes = content.encode("utf-8")
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        # Verificar duplicata
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
            uploaded_by=None,  # Sistema
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
```

- [ ] **Step 3: Implementar _generate_executive_report**

```python
    def _generate_executive_report(
        self, repo_name: str, repo_url: str, branch: str,
        stack: dict, vulnerabilities: dict, compatibility: dict,
        documents: list[dict], ai_provider: str
    ) -> str:
        """Gera relatório executivo consolidado para o GP."""
        lang = stack.get("language", {}).get("primary", "desconhecida")
        frameworks = ", ".join(fw.get("name", "") for fw in stack.get("frameworks", [])) or "nenhum detectado"
        overall = compatibility.get("compatibility_assessment", {}).get("overall_status", "desconhecido")
        risk = vulnerabilities.get("security_summary", {}).get("risk_level", "desconhecido")
        effort = compatibility.get("compatibility_assessment", {}).get("effort_estimate_days", "N/A")
        vuln_total = vulnerabilities.get("security_summary", {}).get("total_vulnerabilities", 0)
        categories_analyzed = len(documents)

        # Status badges
        status_emoji = {"compatível": "✅", "requer_adaptação": "⚠️", "incompatível": "❌"}.get(overall, "❓")
        risk_emoji = {"baixo": "🟢", "médio": "🟡", "alto": "🔴"}.get(risk, "⚪")

        # Breaking changes
        bc_list = compatibility.get("breaking_changes_for_integration", [])
        bc_text = ""
        for bc in bc_list:
            if isinstance(bc, dict):
                bc_text += f"- **{bc.get('issue', '')}**: {bc.get('impact', '')} → {bc.get('resolution', '')}\n"
            else:
                bc_text += f"- {bc}\n"

        # Reuse potential
        reuse = compatibility.get("reuse_potential", {})
        high_value = reuse.get("high_value_components", [])
        reuse_text = ""
        for comp in high_value:
            if isinstance(comp, dict):
                reuse_text += f"- **{comp.get('component', '')}** (esforço: {comp.get('reuse_effort', '')}) — {comp.get('reason', '')}\n"

        return f"""# [EXTERNO] {repo_name} — RELATÓRIO EXECUTIVO
**Origem:** {repo_url} (branch: {branch})
**Analisado em:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
**Provider IA:** {ai_provider}

---

## Resumo Executivo

| Item | Valor |
|------|-------|
| Linguagem principal | {lang} |
| Frameworks | {frameworks} |
| Compatibilidade GCA | {status_emoji} {overall} |
| Nível de risco | {risk_emoji} {risk} |
| Vulnerabilidades | {vuln_total} |
| Esforço estimado | {effort} dias |
| Categorias analisadas | {categories_analyzed}/13 |
| Docker | {'✅' if stack.get('has_dockerfile') else '❌'} |
| CI/CD | {'✅' if stack.get('has_cicd') else '❌'} |
| Testes | {'✅' if stack.get('has_tests') else '❌'} |

## Breaking Changes
{bc_text or 'Nenhum detectado.'}

## Componentes Reutilizáveis
{reuse_text or 'Nenhum identificado.'}

## Documentos Gerados
{chr(10).join(f'- `external_{repo_name}_{doc["category"]}.md` ({doc.get("files_count", 0)} arquivos)' for doc in documents)}

---
*Relatório gerado automaticamente pelo GCA Engine de Análise de Repositórios Externos.*
"""
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/repo_analysis_service.py
git commit -m "feat: RepoAnalysisService — Fases 5-6 decisão, ingestão e relatório executivo"
```

---

## Task 7: Router — Novos endpoints + correção n8n webhook

**Files:**
- Modify: `backend/app/routers/external_repos_router.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Adicionar endpoint POST /analyze**

Em `external_repos_router.py`, adicionar após o endpoint de callback (linha ~256):

```python
@router.post("/projects/{project_id}/external-repos/{repo_id}/analyze")
async def analyze_repo(
    project_id: UUID,
    repo_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Executa análise completa do repositório (chamado pelo n8n ou diretamente)."""
    from app.services.repo_analysis_service import RepoAnalysisService

    service = RepoAnalysisService(db)
    result = await service.analyze_repository(project_id, repo_id)

    status_code = 200 if result.get("status") != "error" else 500
    return result


@router.get("/projects/{project_id}/external-repos/{repo_id}/analysis")
async def get_analysis(
    project_id: UUID,
    repo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna resultados da análise do repositório."""
    from app.models.base import RepoAnalysisResult, RepoIntegrationRoadmap
    import json

    # Buscar resultados por categoria
    result = await db.execute(
        select(RepoAnalysisResult)
        .where(RepoAnalysisResult.repo_id == repo_id)
        .order_by(RepoAnalysisResult.category)
    )
    results = result.scalars().all()

    if not results:
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    # Stack e compatibility vêm do primeiro resultado (compartilhados)
    first = results[0]
    stack = json.loads(first.stack_json) if first.stack_json else {}
    vulnerabilities = json.loads(first.vulnerabilities_json) if first.vulnerabilities_json else {}
    compatibility = json.loads(first.compatibility_matrix) if first.compatibility_matrix else {}

    # Buscar roadmap
    roadmap_result = await db.execute(
        select(RepoIntegrationRoadmap)
        .where(RepoIntegrationRoadmap.repo_id == repo_id)
        .order_by(RepoIntegrationRoadmap.step_number)
    )
    roadmap = roadmap_result.scalars().all()

    # Buscar documentos injetados
    from app.models.base import IngestedDocument
    docs_result = await db.execute(
        select(IngestedDocument)
        .where(
            IngestedDocument.source_repo_id == repo_id,
            IngestedDocument.source_type == "external_repo",
        )
        .order_by(IngestedDocument.original_filename)
    )
    injected_docs = docs_result.scalars().all()

    return {
        "stack": stack,
        "vulnerabilities": vulnerabilities,
        "compatibility": compatibility,
        "gca_overall_status": first.gca_overall_status,
        "risk_level": first.risk_level,
        "categories": [
            {
                "category": r.category,
                "summary": r.summary,
                "metrics": json.loads(r.metrics) if r.metrics else {},
                "files_analyzed": r.files_analyzed,
                "ai_provider": r.ai_provider_used,
            }
            for r in results
        ],
        "roadmap": [
            {
                "step_number": r.step_number,
                "title": r.title,
                "description": r.description,
                "effort_hours": r.effort_hours,
                "status": r.status,
            }
            for r in roadmap
        ],
        "injected_documents": [
            {
                "id": str(d.id),
                "filename": d.original_filename,
                "file_type": d.file_type,
                "source_url": d.source_url,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in injected_docs
        ],
    }


@router.post("/projects/{project_id}/external-repos/{repo_id}/approve-integration")
async def approve_integration(
    project_id: UUID,
    repo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """GP aprova ingestão de repo que 'requer adaptação'."""
    repo = await db.get(ProjectExternalRepo, repo_id)
    if not repo or repo.project_id != project_id:
        raise HTTPException(status_code=404, detail="Repositório não encontrado")

    repo.is_approved_for_integration = True
    repo.approved_by_gp = current_user_id
    await db.commit()

    # Disparar ingestão dos documentos já analisados
    from app.services.repo_analysis_service import RepoAnalysisService
    import json

    service = RepoAnalysisService(db)
    repo_name = service._extract_repo_name(repo.repo_url)

    # Buscar resultados de análise existentes
    from app.models.base import RepoAnalysisResult
    analysis_results = await db.execute(
        select(RepoAnalysisResult)
        .where(RepoAnalysisResult.repo_id == repo_id)
    )
    results = analysis_results.scalars().all()

    documents = [
        {"category": r.category, "content": r.summary, "files_count": r.files_analyzed}
        for r in results if r.summary
    ]

    if documents:
        await service._inject_into_ingestion(
            project_id, repo_id, repo.repo_url, repo.branch,
            repo.ai_provider or "deepseek", repo_name, documents
        )

    return {"message": "Integração aprovada, documentos injetados na Ingestão"}
```

- [ ] **Step 2: Corrigir trigger_read para usar path correto do n8n ou chamar direto**

Modificar o endpoint `trigger_read` (linha ~139) para chamar o engine diretamente como fallback:

```python
@router.post("/projects/{project_id}/external-repos/{repo_id}/read")
async def trigger_read(
    project_id: UUID,
    repo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Disparar leitura do repositório — tenta n8n, fallback para engine direto."""
    repo = await db.get(ProjectExternalRepo, repo_id)
    if not repo or repo.project_id != project_id:
        raise HTTPException(status_code=404, detail="Repositório não encontrado")

    if repo.status == "reading":
        raise HTTPException(status_code=409, detail="Leitura já em andamento")

    # Tentar disparar via n8n
    try:
        import httpx
        from app.core.config import settings

        n8n_base = getattr(settings, 'N8N_WEBHOOK_URL', None) or "http://n8n:5678/webhook"
        # n8n 2.x prefixa webhook com workflow ID
        n8n_url = f"{n8n_base}/gca-external-repo-reader/webhook/read-external-repo"

        analyze_url = f"http://gca-backend:8000{settings.API_PREFIX}/projects/{project_id}/external-repos/{repo_id}/analyze"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(n8n_url, json={
                "project_id": str(project_id),
                "repo_id": str(repo_id),
                "analyze_url": analyze_url,
            })

        if resp.status_code in (200, 201):
            logger.info("repo.read_triggered_via_n8n", repo_id=str(repo_id))
            return {"message": "Leitura iniciada via n8n", "status": "reading"}

    except Exception as e:
        logger.warning("repo.n8n_unavailable", error=str(e))

    # Fallback: executar engine diretamente (em background)
    import asyncio
    from app.services.repo_analysis_service import RepoAnalysisService

    async def run_analysis():
        from app.db.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            service = RepoAnalysisService(session)
            await service.analyze_repository(project_id, repo_id)

    asyncio.create_task(run_analysis())

    logger.info("repo.read_triggered_direct", repo_id=str(repo_id))
    return {"message": "Leitura iniciada (engine direto)", "status": "reading"}
```

- [ ] **Step 3: Adicionar import do RepoAnalysisResult no router**

No topo de `external_repos_router.py`, atualizar imports:

```python
from app.models.base import ProjectExternalRepo, RepoAnalysisResult, RepoIntegrationRoadmap, IngestedDocument
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/external_repos_router.py
git commit -m "feat: endpoints analyze, analysis, approve-integration + fallback direto sem n8n"
```

---

## Task 8: n8n — Workflow simplificado (dispatcher)

**Files:**
- Modify: `infra/n8n-workflow-external-repo.json`

- [ ] **Step 1: Reescrever workflow como dispatcher**

```json
{
  "name": "GCA — Leitura de Repositório Externo",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "read-external-repo",
        "responseMode": "responseNode"
      },
      "name": "Webhook",
      "type": "n8n-nodes-base.webhook",
      "position": [250, 300],
      "typeVersion": 2
    },
    {
      "parameters": {
        "method": "POST",
        "url": "={{ $json.analyze_url }}",
        "options": {
          "timeout": 300000
        }
      },
      "name": "Chamar Engine GCA",
      "type": "n8n-nodes-base.httpRequest",
      "position": [500, 300],
      "typeVersion": 4
    },
    {
      "parameters": {
        "respondWith": "json",
        "responseBody": "={{ JSON.stringify({ status: 'triggered', result: $json }) }}"
      },
      "name": "Responder",
      "type": "n8n-nodes-base.respondToWebhook",
      "position": [750, 300],
      "typeVersion": 1
    }
  ],
  "connections": {
    "Webhook": {
      "main": [
        [{ "node": "Chamar Engine GCA", "type": "main", "index": 0 }]
      ]
    },
    "Chamar Engine GCA": {
      "main": [
        [{ "node": "Responder", "type": "main", "index": 0 }]
      ]
    }
  },
  "settings": {
    "executionTimeout": 600
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add infra/n8n-workflow-external-repo.json
git commit -m "feat: n8n workflow simplificado — apenas dispatcher para engine Python"
```

---

## Task 9: Teste E2E — samplemod

**Files:**
- Nenhum novo — teste via API

- [ ] **Step 1: Reiniciar backend com novos modelos**

```bash
cd /home/luiz/GCA && docker compose restart backend
```

Aguardar: `docker compose logs backend --tail=5` deve mostrar "Application startup complete"

- [ ] **Step 2: Resetar status do repo de teste**

```bash
export TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"pielak.ctba@gmail.com","password":"Topazio01#"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

export PROJECT_ID="9220601b-e006-4e10-9310-ab8aa0fb9250"
export REPO_ID="7afa77b3-c8f8-47ff-8844-b6fb92b0e416"

# Resetar status do repo
docker compose exec -T postgres psql -U gca -d gca -c "
  UPDATE project_external_repos SET status='pending', error_message=NULL
  WHERE id='$REPO_ID';
"
```

- [ ] **Step 3: Disparar análise direta (sem n8n)**

```bash
curl -s -X POST http://localhost:8000/api/v1/projects/$PROJECT_ID/external-repos/$REPO_ID/analyze \
  | python3 -m json.tool
```

Expected: JSON com status "completed" ou "error" com mensagem útil.

- [ ] **Step 4: Verificar resultados**

```bash
# Resultados de análise
curl -s http://localhost:8000/api/v1/projects/$PROJECT_ID/external-repos/$REPO_ID/analysis \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -50

# Documentos injetados
docker compose exec -T postgres psql -U gca -d gca -c "
  SELECT original_filename, source_type, source_url
  FROM ingested_documents
  WHERE source_type='external_repo'
  ORDER BY original_filename;
"
```

- [ ] **Step 5: Verificar via trigger_read (com fallback)**

```bash
curl -s -X POST http://localhost:8000/api/v1/projects/$PROJECT_ID/external-repos/$REPO_ID/read \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Expected: `"message": "Leitura iniciada (engine direto)"` (n8n pode não estar configurado)

- [ ] **Step 6: Commit se houver ajustes**

```bash
git add -A && git commit -m "fix: ajustes pós-teste E2E com samplemod"
```

---

## Task 10: Frontend — Painel de resultados (5 abas)

**Files:**
- Modify: `frontend/src/pages/projects/ExternalReposPage.tsx`

- [ ] **Step 1: Adicionar interfaces TypeScript**

No topo do arquivo, adicionar:

```typescript
interface AnalysisResult {
  stack: Record<string, any>;
  vulnerabilities: Record<string, any>;
  compatibility: Record<string, any>;
  gca_overall_status: string | null;
  risk_level: string | null;
  categories: Array<{
    category: string;
    summary: string;
    metrics: Record<string, any>;
    files_analyzed: number;
    ai_provider: string;
  }>;
  roadmap: Array<{
    step_number: number;
    title: string;
    description: string;
    effort_hours: number;
    status: string;
  }>;
  injected_documents: Array<{
    id: string;
    filename: string;
    file_type: string;
    source_url: string;
    created_at: string;
  }>;
}
```

- [ ] **Step 2: Adicionar state e função de carregamento**

Na função do componente, adicionar state:

```typescript
const [analysisData, setAnalysisData] = useState<AnalysisResult | null>(null);
const [showAnalysis, setShowAnalysis] = useState<string | null>(null); // repo_id
const [analysisLoading, setAnalysisLoading] = useState(false);
const [activeTab, setActiveTab] = useState<string>('stack');

const loadAnalysis = async (repoId: string) => {
  setAnalysisLoading(true);
  try {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/external-repos/${repoId}/analysis`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    if (res.ok) {
      const data = await res.json();
      setAnalysisData(data);
      setShowAnalysis(repoId);
      setActiveTab('stack');
    }
  } catch (err) {
    console.error('Erro ao carregar análise:', err);
  } finally {
    setAnalysisLoading(false);
  }
};
```

- [ ] **Step 3: Adicionar botão "Ver Análise" na lista de repos**

Na renderização de cada repo, após o botão de Play, adicionar quando status === 'completed':

```tsx
{repo.status === 'completed' && (
  <button
    onClick={() => loadAnalysis(repo.id)}
    className="p-2 rounded-lg bg-violet-500/20 text-violet-400 hover:bg-violet-500/30 transition-colors"
    title="Ver Análise"
  >
    <BarChart3 className="w-4 h-4" />
  </button>
)}
```

Adicionar import: `BarChart3` do lucide-react.

- [ ] **Step 4: Implementar painel de análise com 5 abas**

Após a lista de repos, adicionar o painel (renderizado quando `showAnalysis` não é null):

```tsx
{showAnalysis && analysisData && (
  <div className="mt-6 bg-dark-200/50 rounded-xl border border-dark-100/20 p-6">
    {/* Header */}
    <div className="flex items-center justify-between mb-6">
      <h3 className="text-lg font-semibold text-white">Resultado da Análise</h3>
      <button onClick={() => setShowAnalysis(null)} className="text-dark-100/60 hover:text-white">✕</button>
    </div>

    {/* Tabs */}
    <div className="flex gap-2 mb-6 border-b border-dark-100/20 pb-2">
      {[
        { id: 'stack', label: 'Stack Detectado' },
        { id: 'security', label: 'Segurança' },
        { id: 'compatibility', label: 'Compatibilidade GCA' },
        { id: 'categories', label: 'Categorias (13)' },
        { id: 'documents', label: 'Documentos' },
      ].map(tab => (
        <button
          key={tab.id}
          onClick={() => setActiveTab(tab.id)}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            activeTab === tab.id
              ? 'bg-violet-600 text-white'
              : 'text-dark-100/60 hover:text-white hover:bg-dark-200'
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>

    {/* Tab Content */}
    <div className="min-h-[300px]">
      {/* Aba 1: Stack */}
      {activeTab === 'stack' && analysisData.stack && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-dark-200 rounded-lg p-4">
              <div className="text-xs text-dark-100/60 mb-1">Linguagem</div>
              <div className="text-white font-semibold">{analysisData.stack.language?.primary || 'N/A'}</div>
            </div>
            <div className="bg-dark-200 rounded-lg p-4">
              <div className="text-xs text-dark-100/60 mb-1">Arquivos</div>
              <div className="text-white font-semibold">{analysisData.stack.repository?.files_total || 0}</div>
            </div>
            <div className="bg-dark-200 rounded-lg p-4">
              <div className="text-xs text-dark-100/60 mb-1">Docker</div>
              <div className={analysisData.stack.has_dockerfile ? 'text-emerald-400' : 'text-red-400'}>
                {analysisData.stack.has_dockerfile ? '✅ Sim' : '❌ Não'}
              </div>
            </div>
            <div className="bg-dark-200 rounded-lg p-4">
              <div className="text-xs text-dark-100/60 mb-1">Testes</div>
              <div className={analysisData.stack.has_tests ? 'text-emerald-400' : 'text-red-400'}>
                {analysisData.stack.has_tests ? '✅ Sim' : '❌ Não'}
              </div>
            </div>
          </div>
          {analysisData.stack.frameworks?.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-dark-100/80 mb-2">Frameworks</h4>
              <div className="flex gap-2 flex-wrap">
                {analysisData.stack.frameworks.map((fw: any, i: number) => (
                  <span key={i} className="px-3 py-1 bg-violet-500/20 text-violet-300 rounded-full text-xs">
                    {fw.name} {fw.version !== 'unknown' ? fw.version : ''}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Aba 2: Segurança */}
      {activeTab === 'security' && analysisData.vulnerabilities && (
        <div className="space-y-4">
          <div className="flex items-center gap-4">
            <span className={`px-3 py-1 rounded-full text-sm font-medium ${
              analysisData.risk_level === 'baixo' ? 'bg-emerald-500/20 text-emerald-400' :
              analysisData.risk_level === 'médio' ? 'bg-amber-500/20 text-amber-400' :
              'bg-red-500/20 text-red-400'
            }`}>
              Risco: {analysisData.risk_level || 'N/A'}
            </span>
            <span className="text-dark-100/60 text-sm">
              {analysisData.vulnerabilities.security_summary?.total_vulnerabilities || 0} vulnerabilidades
            </span>
          </div>
          {analysisData.vulnerabilities.vulnerabilities?.map((v: any, i: number) => (
            <div key={i} className="bg-dark-200 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-white font-medium">{v.package} {v.version}</span>
                <span className={`px-2 py-0.5 rounded text-xs ${
                  v.severity === 'high' ? 'bg-red-500/20 text-red-400' :
                  v.severity === 'medium' ? 'bg-amber-500/20 text-amber-400' :
                  'bg-slate-500/20 text-slate-400'
                }`}>{v.severity}</span>
              </div>
              <p className="text-sm text-dark-100/60">{v.issue}</p>
              {v.recommended_version && (
                <p className="text-xs text-emerald-400 mt-1">Recomendado: {v.recommended_version}</p>
              )}
            </div>
          ))}
          {(!analysisData.vulnerabilities.vulnerabilities?.length) && (
            <p className="text-dark-100/60 text-sm">Nenhuma vulnerabilidade detectada.</p>
          )}
        </div>
      )}

      {/* Aba 3: Compatibilidade GCA */}
      {activeTab === 'compatibility' && analysisData.compatibility && (
        <div className="space-y-4">
          <div className="flex items-center gap-4 mb-4">
            <span className={`px-4 py-2 rounded-full text-sm font-bold ${
              analysisData.gca_overall_status === 'compatível' ? 'bg-emerald-500/20 text-emerald-400' :
              analysisData.gca_overall_status === 'requer_adaptação' ? 'bg-amber-500/20 text-amber-400' :
              'bg-red-500/20 text-red-400'
            }`}>
              {analysisData.gca_overall_status === 'compatível' ? '✅' :
               analysisData.gca_overall_status === 'requer_adaptação' ? '⚠️' : '❌'}
              {' '}{analysisData.gca_overall_status || 'N/A'}
            </span>
            {analysisData.compatibility.compatibility_assessment?.effort_estimate_days && (
              <span className="text-dark-100/60 text-sm">
                Esforço: {analysisData.compatibility.compatibility_assessment.effort_estimate_days} dias
              </span>
            )}
          </div>
          {['gca_backend_compatibility', 'gca_frontend_compatibility', 'gca_database_compatibility'].map(key => {
            const comp = analysisData.compatibility[key];
            if (!comp) return null;
            const label = key.replace('gca_', '').replace('_compatibility', '').replace('_', ' ');
            return (
              <div key={key} className="bg-dark-200 rounded-lg p-4">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-white font-medium capitalize">{label}</span>
                  <span className={`px-2 py-0.5 rounded text-xs ${
                    comp.status === 'compatível' ? 'bg-emerald-500/20 text-emerald-400' :
                    comp.status === 'requer_adaptação' ? 'bg-amber-500/20 text-amber-400' :
                    'bg-red-500/20 text-red-400'
                  }`}>{comp.status}</span>
                </div>
                <p className="text-sm text-dark-100/60">{comp.reason}</p>
              </div>
            );
          })}
          {analysisData.roadmap?.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-dark-100/80 mb-2">Roadmap de Integração</h4>
              {analysisData.roadmap.map((step, i) => (
                <div key={i} className="flex items-start gap-3 py-2 border-b border-dark-100/10">
                  <span className="text-violet-400 font-mono text-sm">{step.step_number}.</span>
                  <span className="text-white text-sm">{step.title}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Aba 4: Categorias */}
      {activeTab === 'categories' && (
        <div className="space-y-3">
          {analysisData.categories.map((cat, i) => (
            <details key={i} className="bg-dark-200 rounded-lg">
              <summary className="p-4 cursor-pointer flex items-center justify-between">
                <span className="text-white font-medium">{cat.category.replace(/_/g, ' ')}</span>
                <span className="text-xs text-dark-100/60">{cat.files_analyzed} arquivos</span>
              </summary>
              <div className="px-4 pb-4 text-sm text-dark-100/80 whitespace-pre-wrap">
                {cat.summary?.substring(0, 2000) || 'Sem análise disponível.'}
                {(cat.summary?.length || 0) > 2000 && '...'}
              </div>
            </details>
          ))}
        </div>
      )}

      {/* Aba 5: Documentos */}
      {activeTab === 'documents' && (
        <div className="space-y-2">
          {analysisData.injected_documents.length > 0 ? (
            analysisData.injected_documents.map((doc, i) => (
              <div key={i} className="flex items-center justify-between bg-dark-200 rounded-lg p-3">
                <div>
                  <span className="text-white text-sm">{doc.filename}</span>
                  <span className="ml-2 text-xs px-2 py-0.5 bg-violet-500/20 text-violet-300 rounded">[EXTERNO]</span>
                </div>
                <span className="text-xs text-dark-100/60">{doc.created_at?.split('T')[0]}</span>
              </div>
            ))
          ) : (
            <p className="text-dark-100/60 text-sm">Nenhum documento injetado ainda.</p>
          )}
        </div>
      )}
    </div>
  </div>
)}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/projects/ExternalReposPage.tsx
git commit -m "feat: ExternalReposPage — painel de análise com 5 abas (stack, segurança, compatibilidade, categorias, documentos)"
```

---

## Task 11: Verificação final E2E

- [ ] **Step 1: Rebuild frontend**

```bash
cd /home/luiz/GCA && docker compose restart frontend
```

- [ ] **Step 2: Testar fluxo completo via UI**

1. Abrir `http://localhost:5173`
2. Login: `pielak.ctba@gmail.com` / `Topazio01#`
3. Navegar para projeto FinanceHub Pro → Repos Externos
4. O repo `samplemod` já está cadastrado
5. Clicar "Ler Dados" (Play)
6. Aguardar status mudar para "completed"
7. Clicar "Ver Análise" (BarChart3)
8. Verificar as 5 abas

- [ ] **Step 3: Validar documentos na Ingestão**

Navegar para a página de Ingestão do projeto e verificar que os documentos `[EXTERNO]` aparecem.

- [ ] **Step 4: Commit final**

```bash
git add -A && git commit -m "feat: Engine de Análise de Repositórios Externos — completo (6 fases, 13 categorias)"
```
