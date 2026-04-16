"""Testes dos auto-generators (Fase C.1+C.2+C.3+C.4).

Mocka commit Git (não exige projeto real conectado a GitHub) e foca em:
  - dispatcher (generate_kind) com kinds conhecidos/desconhecidos
  - estrutura/conteúdo de cada generator
  - skipped_reason quando OCG está vazio
  - path correto (compliance.md, adr/000N-*.md, architecture.mmd)
"""
import json
import re
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.deliverable_generators import (
    GeneratorResult,
    generate_kind,
    has_generator,
    list_generator_kinds,
)


PROJECT_ID = uuid4()


# ────────────────────────── dispatcher ──────────────────────────────

def test_registry_lists_known_kinds():
    kinds = list_generator_kinds()
    # Pelo menos os 3 que implementamos na C.2/3/4
    assert "compliance_doc" in kinds
    assert "adr" in kinds
    assert "architecture_diagram" in kinds


def test_has_generator_true_false():
    assert has_generator("adr") is True
    assert has_generator("kind_inexistente") is False


@pytest.mark.asyncio
async def test_generate_unknown_kind_returns_not_committed():
    db = AsyncMock()
    res = await generate_kind("doesnt_exist", PROJECT_ID, db, {})
    assert res.committed is False
    assert "sem generator" in (res.skipped_reason or "")


# ────────────────────────── compliance_doc ───────────────────────────

@pytest.mark.asyncio
async def test_compliance_doc_generates_table():
    db = AsyncMock()
    ocg = {
        "PROJECT_PROFILE": {"project_name": "P Test"},
        "COMPLIANCE_CHECKLIST": [
            {"item": "AIPD LGPD", "status": "PENDENTE", "owner": "DPO"},
            {"item": "Criptografia em repouso", "status": "DONE", "owner": "DBA"},
        ],
    }
    captured = {}

    async def fake_commit(project_id, db, path, content, commit_message):
        captured["path"] = path
        captured["content"] = content
        captured["commit_message"] = commit_message
        return True

    with patch(
        "app.services.deliverable_generators_impl._commit_via_git",
        new=fake_commit,
    ):
        res = await generate_kind("compliance_doc", PROJECT_ID, db, ocg)

    assert res.committed is True
    assert res.path == "docs/compliance.md"
    assert captured["path"] == "docs/compliance.md"
    assert "P Test" in captured["content"]
    assert "AIPD LGPD" in captured["content"]
    assert "PENDENTE" in captured["content"]
    assert "DONE" in captured["content"]
    assert "✅" in captured["content"]
    assert "⏳" in captured["content"]
    assert "<!-- gca:auto" in captured["content"]


@pytest.mark.asyncio
async def test_compliance_doc_skips_when_checklist_empty():
    db = AsyncMock()
    ocg = {"COMPLIANCE_CHECKLIST": []}
    res = await generate_kind("compliance_doc", PROJECT_ID, db, ocg)
    assert res.committed is False
    assert "vazio" in (res.skipped_reason or "")


@pytest.mark.asyncio
async def test_compliance_doc_handles_missing_key():
    db = AsyncMock()
    res = await generate_kind("compliance_doc", PROJECT_ID, db, {"PROJECT_PROFILE": {}})
    assert res.committed is False


@pytest.mark.asyncio
async def test_compliance_doc_returns_not_committed_when_git_fails():
    db = AsyncMock()
    ocg = {"COMPLIANCE_CHECKLIST": [{"item": "X", "status": "PENDENTE"}]}
    with patch(
        "app.services.deliverable_generators_impl._commit_via_git",
        new=AsyncMock(return_value=False),
    ):
        res = await generate_kind("compliance_doc", PROJECT_ID, db, ocg)
    assert res.committed is False
    assert "Git" in (res.skipped_reason or "")


@pytest.mark.asyncio
async def test_compliance_doc_escapes_pipe_in_text():
    """Tabela markdown precisa escapar | dentro do texto."""
    db = AsyncMock()
    ocg = {"COMPLIANCE_CHECKLIST": [{"item": "Item com | pipe", "status": "OK", "owner": "x | y"}]}
    captured = {}

    async def fake_commit(project_id, db, path, content, commit_message):
        captured["content"] = content
        return True

    with patch("app.services.deliverable_generators_impl._commit_via_git", new=fake_commit):
        await generate_kind("compliance_doc", PROJECT_ID, db, ocg)
    assert "Item com \\| pipe" in captured["content"]


# ────────────────────────── adr ──────────────────────────────────────

@pytest.mark.asyncio
async def test_adr_generates_stack_and_finding_adrs():
    db = AsyncMock()
    ocg = {
        "PROJECT_PROFILE": {"project_name": "P Test"},
        "STACK_RECOMMENDATION": {
            "backend": {"framework": "FastAPI", "language": "Python", "rationale": "high perf"},
            "frontend": {"framework": "React", "language": "TS", "rationale": "DX"},
            "database": {"primary": "Postgres", "rationale": "ACID"},
        },
        "CRITICAL_FINDINGS": [
            {"finding": "Falta caso de negócio", "severity": "HIGH", "pillar": "P1",
             "recommendation": "Documentar ROI antes de prosseguir"},
        ],
    }
    paths_committed: list = []

    async def fake_commit(project_id, db, path, content, commit_message):
        paths_committed.append(path)
        return True

    with patch("app.services.deliverable_generators_impl._commit_via_git", new=fake_commit):
        res = await generate_kind("adr", PROJECT_ID, db, ocg)

    assert res.committed is True
    assert res.path.startswith("docs/adr/")
    assert "1 stack" in str(res.notes)
    # 2 ADRs gerados: stack + 1 finding
    assert len(paths_committed) == 2
    assert any("0001-stack-recommendation" in p for p in paths_committed)
    assert any(re.match(r"docs/adr/0002-.+\.md$", p) for p in paths_committed)


@pytest.mark.asyncio
async def test_adr_handles_critical_findings_as_dict():
    """OCG pode ter CRITICAL_FINDINGS como dict único (não list) — aceitar."""
    db = AsyncMock()
    ocg = {
        "CRITICAL_FINDINGS": {"finding": "X", "severity": "HIGH", "pillar": "P3", "recommendation": "y"},
    }
    paths = []
    async def fake_commit(project_id, db, path, content, commit_message):
        paths.append(path)
        return True
    with patch("app.services.deliverable_generators_impl._commit_via_git", new=fake_commit):
        res = await generate_kind("adr", PROJECT_ID, db, ocg)
    assert res.committed is True
    # Sem stack: ADR começa em 0002 (porque idx começa em 2)
    assert any("0002-" in p for p in paths)


@pytest.mark.asyncio
async def test_adr_skips_when_no_findings_no_stack():
    db = AsyncMock()
    res = await generate_kind("adr", PROJECT_ID, db, {"PROJECT_PROFILE": {"project_name": "X"}})
    assert res.committed is False
    assert "sem CRITICAL_FINDINGS" in (res.skipped_reason or "")


# ────────────────────────── architecture_diagram ─────────────────────

@pytest.mark.asyncio
async def test_architecture_diagram_generates_mermaid():
    db = AsyncMock()
    ocg = {
        "PROJECT_PROFILE": {"project_name": "P"},
        "ARCHITECTURE_OVERVIEW": {
            "style": "Modular Monolith",
            "key_components": ["Frontend SPA React", "Backend API FastAPI", "Postgres database", "Kafka broker"],
        },
    }
    captured = {}
    async def fake_commit(project_id, db, path, content, commit_message):
        captured["path"] = path
        captured["content"] = content
        return True
    with patch("app.services.deliverable_generators_impl._commit_via_git", new=fake_commit):
        res = await generate_kind("architecture_diagram", PROJECT_ID, db, ocg)
    assert res.committed is True
    assert res.path == "docs/architecture.mmd"
    assert "graph LR" in captured["content"]
    assert "🖥️ Frontend SPA React" in captured["content"]
    assert "⚙️ Backend API FastAPI" in captured["content"]
    assert "🗄️ Postgres database" in captured["content"]
    assert "📨 Kafka broker" in captured["content"]
    # 4 nodes → 3 edges (`-->` aparece também em comentários HTML do header)
    edge_lines = [ln for ln in captured["content"].splitlines() if "-->" in ln and "<!--" not in ln and "%%" not in ln]
    assert len(edge_lines) == 3


@pytest.mark.asyncio
async def test_architecture_diagram_skips_when_components_empty():
    db = AsyncMock()
    ocg = {"ARCHITECTURE_OVERVIEW": {"style": "Hexagonal", "key_components": []}}
    res = await generate_kind("architecture_diagram", PROJECT_ID, db, ocg)
    assert res.committed is False
    assert "vazio" in (res.skipped_reason or "")


# ────────────────────────── dockerfile (C.6) ─────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("language,framework,expected_in", [
    ("Python", "FastAPI", "uvicorn"),
    ("Python", "Django", "gunicorn"),
    ("TypeScript", "Express", 'CMD ["npm", "start"]'),
    ("Go", "Gin", "golang:1.22"),
    ("Java", "Spring", "eclipse-temurin"),
])
async def test_dockerfile_generates_per_stack(language, framework, expected_in):
    db = AsyncMock()
    ocg = {"STACK_RECOMMENDATION": {"backend": {"language": language, "framework": framework}}}
    captured = {}
    async def fake_commit(project_id, db, path, content, commit_message):
        captured["path"] = path
        captured["content"] = content
        return True
    with patch("app.services.deliverable_generators_impl._commit_via_git", new=fake_commit):
        res = await generate_kind("dockerfile", PROJECT_ID, db, ocg)
    assert res.committed is True
    assert captured["path"] == "Dockerfile"
    assert expected_in in captured["content"]


@pytest.mark.asyncio
async def test_dockerfile_skips_unknown_stack():
    db = AsyncMock()
    ocg = {"STACK_RECOMMENDATION": {"backend": {"language": "Cobol", "framework": "x"}}}
    res = await generate_kind("dockerfile", PROJECT_ID, db, ocg)
    assert res.committed is False
    assert "sem template" in (res.skipped_reason or "")


# ────────────────────────── ci_pipeline (C.6) ────────────────────────

@pytest.mark.asyncio
async def test_ci_pipeline_python_uses_actions():
    db = AsyncMock()
    ocg = {"STACK_RECOMMENDATION": {"backend": {"language": "Python"}}, "PROJECT_PROFILE": {"project_name": "P"}}
    captured = {}
    async def fake_commit(project_id, db, path, content, commit_message):
        captured["path"] = path
        captured["content"] = content
        return True
    with patch("app.services.deliverable_generators_impl._commit_via_git", new=fake_commit):
        res = await generate_kind("ci_pipeline", PROJECT_ID, db, ocg)
    assert res.committed is True
    assert captured["path"] == ".github/workflows/ci.yml"
    assert "actions/setup-python@v5" in captured["content"]
    assert "pytest" in captured["content"]


@pytest.mark.asyncio
async def test_ci_pipeline_skips_unknown_stack():
    db = AsyncMock()
    ocg = {"STACK_RECOMMENDATION": {"backend": {"language": "rust"}}}
    res = await generate_kind("ci_pipeline", PROJECT_ID, db, ocg)
    assert res.committed is False
    assert "sem template" in (res.skipped_reason or "")


# ────────────────────────── openapi (C.6) ────────────────────────────

@pytest.mark.asyncio
async def test_openapi_stub_has_health_endpoint():
    db = AsyncMock()
    ocg = {"PROJECT_PROFILE": {"project_name": "P Test"}, "STACK_RECOMMENDATION": {"backend": {"framework": "FastAPI"}}}
    captured = {}
    async def fake_commit(project_id, db, path, content, commit_message):
        captured["path"] = path
        captured["content"] = content
        return True
    with patch("app.services.deliverable_generators_impl._commit_via_git", new=fake_commit):
        res = await generate_kind("openapi", PROJECT_ID, db, ocg)
    assert res.committed is True
    assert captured["path"] == "docs/openapi.yaml"
    assert "openapi: 3.1.0" in captured["content"]
    assert "/health:" in captured["content"]
    assert "P Test API" in captured["content"]


# ────────────────────────── observability (C.6) ──────────────────────

# ────────────────────────── test_plan (C.7) ──────────────────────────

@pytest.mark.asyncio
async def test_test_plan_generates_sections_per_modality():
    db = AsyncMock()
    ocg = {
        "PROJECT_PROFILE": {"project_name": "P Test"},
        "TESTING_REQUIREMENTS": {
            "unit_testing": {"scope": "Lógica", "tools": "pytest", "coverage_target": ">80%", "rationale": "qualidade"},
            "integration_testing": {"scope": "APIs", "tools": "pytest+Testcontainers", "rationale": "fluxos"},
            "security_testing": {"tools": "Snyk", "frequency": "CI/CD"},
        },
    }
    captured = {}
    async def fake_commit(project_id, db, path, content, commit_message):
        captured["path"] = path
        captured["content"] = content
        return True
    with patch("app.services.deliverable_generators_impl._commit_via_git", new=fake_commit):
        res = await generate_kind("test_plan", PROJECT_ID, db, ocg)
    assert res.committed is True
    assert captured["path"] == "docs/test_plan.md"
    assert "Plano de Testes — P Test" in captured["content"]
    # Sumário tabular
    assert "| Modalidade | Tools | Coverage / Frequency |" in captured["content"]
    assert "Unit Testing" in captured["content"]
    assert "Integration Testing" in captured["content"]
    assert "Security Testing" in captured["content"]
    # Seções detalhadas com fields
    assert "**Scope:**" in captured["content"]
    assert "pytest" in captured["content"]
    assert ">80%" in captured["content"]


@pytest.mark.asyncio
async def test_test_plan_skips_when_testing_requirements_empty():
    db = AsyncMock()
    res = await generate_kind("test_plan", PROJECT_ID, db, {"PROJECT_PROFILE": {"project_name": "X"}})
    assert res.committed is False
    assert "vazio" in (res.skipped_reason or "")


@pytest.mark.asyncio
async def test_test_plan_handles_list_and_dict_fields():
    """Campos como list (scenarios) ou dict (sub-config) renderizados como bullets."""
    db = AsyncMock()
    ocg = {
        "TESTING_REQUIREMENTS": {
            "performance_testing": {
                "tools": "k6",
                "scenarios": ["login burst", "report generation"],
                "thresholds": {"p95": "500ms", "p99": "1s"},
            },
        },
    }
    captured = {}
    async def fake_commit(project_id, db, path, content, commit_message):
        captured["content"] = content
        return True
    with patch("app.services.deliverable_generators_impl._commit_via_git", new=fake_commit):
        await generate_kind("test_plan", PROJECT_ID, db, ocg)
    # List vira bullets
    assert "- login burst" in captured["content"]
    assert "- report generation" in captured["content"]
    # Dict vira sub-bullets
    assert "`p95`: 500ms" in captured["content"]


# ────────────────────────── sbom (C.7) ───────────────────────────────

@pytest.mark.asyncio
async def test_sbom_parses_pyproject_poetry():
    db = AsyncMock()
    ocg = {"PROJECT_PROFILE": {"project_name": "P"}}
    pyproject_content = '''
[tool.poetry]
name = "test-project"

[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.110.0"
sqlalchemy = "^2.0.0"

[tool.poetry.group.dev.dependencies]
pytest = "^7.4.4"
'''

    async def fake_get_file(self, project_id, path):
        if path == "pyproject.toml":
            return pyproject_content
        return None

    captured = {}
    async def fake_commit(project_id, db, path, content, commit_message):
        captured["path"] = path
        captured["content"] = content
        return True

    with patch("app.services.deliverable_generators_impl._commit_via_git", new=fake_commit), \
         patch("app.services.git_service.GitService.get_file_content", new=fake_get_file):
        res = await generate_kind("sbom", PROJECT_ID, db, ocg)

    assert res.committed is True
    assert captured["path"] == "sbom.json"
    bom = json.loads(captured["content"])
    assert bom["bomFormat"] == "CycloneDX"
    assert bom["specVersion"] == "1.5"
    names = {c["name"] for c in bom["components"]}
    assert "fastapi" in names
    assert "sqlalchemy" in names
    assert "pytest" in names
    assert "python" not in names  # python é skipado (não é package)


@pytest.mark.asyncio
async def test_sbom_parses_package_json():
    db = AsyncMock()
    ocg = {"PROJECT_PROFILE": {"project_name": "P"}}
    pkg = json.dumps({
        "name": "front",
        "dependencies": {"react": "^18.0.0", "axios": "1.6.0"},
        "devDependencies": {"vitest": "^1.0.0"},
    })

    async def fake_get_file(self, project_id, path):
        if path in ("pyproject.toml", "backend/pyproject.toml"):
            return None
        if path == "package.json":
            return pkg
        return None

    captured = {}
    async def fake_commit(project_id, db, path, content, commit_message):
        captured["content"] = content
        return True

    with patch("app.services.deliverable_generators_impl._commit_via_git", new=fake_commit), \
         patch("app.services.git_service.GitService.get_file_content", new=fake_get_file):
        res = await generate_kind("sbom", PROJECT_ID, db, ocg)

    assert res.committed is True
    bom = json.loads(captured["content"])
    names = {c["name"] for c in bom["components"]}
    assert "react" in names
    assert "axios" in names
    assert "vitest" in names
    # Versões limpas (sem ^/~)
    react = next(c for c in bom["components"] if c["name"] == "react")
    assert react["version"] == "18.0.0"
    assert react["purl"] == "pkg:npm/react@18.0.0"


@pytest.mark.asyncio
async def test_sbom_skips_when_no_manifests():
    db = AsyncMock()
    async def fake_get_file(self, project_id, path):
        return None
    with patch("app.services.git_service.GitService.get_file_content", new=fake_get_file):
        res = await generate_kind("sbom", PROJECT_ID, db, {"PROJECT_PROFILE": {"project_name": "P"}})
    assert res.committed is False
    assert "manifest" in (res.skipped_reason or "")


@pytest.mark.asyncio
async def test_observability_generates_prometheus_and_grafana():
    db = AsyncMock()
    ocg = {"PROJECT_PROFILE": {"project_name": "FinanceHub Pro"}}
    paths = []
    async def fake_commit(project_id, db, path, content, commit_message):
        paths.append((path, content))
        return True
    with patch("app.services.deliverable_generators_impl._commit_via_git", new=fake_commit):
        res = await generate_kind("observability_dashboard", PROJECT_ID, db, ocg)
    assert res.committed is True
    assert any(p[0] == "infra/prometheus.yml" for p in paths)
    assert any(p[0] == "infra/grafana/dashboards/main.json" for p in paths)
    grafana = next(c for p, c in paths if "grafana" in p)
    assert "FinanceHub Pro" in grafana
    # JSON parsável + 3 painéis
    parsed = json.loads(grafana)
    assert len(parsed["panels"]) == 3
