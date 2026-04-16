"""Testes dos verifiers determinísticos (Fase A.3).

Mocka helpers de Git e queries DB; cobre:
  - dispatcher (verify_kind) com kinds conhecidos e desconhecidos
  - cada verifier individual (file/dir presence, fallback paths)
  - graceful degradation (erro vira status='error', não levanta)
"""
import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.deliverable_verifiers import (
    VerificationResult,
    _verify_adr,
    _verify_ci_pipeline,
    _verify_compliance_checklist,
    _verify_database_design,
    _verify_dockerfile,
    _verify_manifests,
    _verify_manual_only,
    _verify_openapi,
    _verify_sbom,
    verify_kind,
)


PROJECT_ID = uuid4()


# ─────────────────────────── dispatcher ──────────────────────────────

@pytest.mark.asyncio
async def test_verify_kind_unknown_falls_to_manual():
    db = AsyncMock()
    res = await verify_kind("kind_que_nao_existe", PROJECT_ID, db)
    assert res.status == "manual_only"
    assert "Manual" in (res.notes or "") or "manual" in (res.notes or "")


@pytest.mark.asyncio
async def test_verify_kind_business_case_is_manual():
    db = AsyncMock()
    res = await verify_kind("business_case", PROJECT_ID, db)
    assert res.status == "manual_only"


@pytest.mark.asyncio
async def test_verify_kind_routes_to_dockerfile_verifier():
    db = AsyncMock()
    with patch(
        "app.services.deliverable_verifiers._git_file_exists",
        new=AsyncMock(return_value="Dockerfile"),
    ):
        res = await verify_kind("dockerfile", PROJECT_ID, db)
        assert res.status == "verified"
        assert res.method == "git_file_exists"
        assert res.evidence_ref == "Dockerfile"


@pytest.mark.asyncio
async def test_verify_kind_swallows_exceptions():
    """Se o verifier internamente quebrar, dispatcher devolve status='error'
    sem propagar — registry pode logar e seguir."""
    from app.services import deliverable_verifiers as mod
    db = AsyncMock()

    async def raising(_pid, _db):
        raise RuntimeError("boom")

    # Patch direto no dict — o dispatcher faz lookup em _VERIFIERS no
    # momento da chamada, então sobrescrever a entrada surte efeito.
    original = mod._VERIFIERS.get("dockerfile")
    mod._VERIFIERS["dockerfile"] = raising
    try:
        res = await verify_kind("dockerfile", PROJECT_ID, db)
        assert res.status == "error"
        assert "RuntimeError" in (res.notes or "")
    finally:
        mod._VERIFIERS["dockerfile"] = original


# ─────────────────────────── verifiers individuais ───────────────────

@pytest.mark.asyncio
async def test_dockerfile_found_returns_verified():
    db = AsyncMock()
    with patch(
        "app.services.deliverable_verifiers._git_file_exists",
        new=AsyncMock(return_value="docker/Dockerfile"),
    ):
        res = await _verify_dockerfile(PROJECT_ID, db)
        assert res.status == "verified"
        assert res.evidence_ref == "docker/Dockerfile"
        assert res.evidence_type == "file"


@pytest.mark.asyncio
async def test_dockerfile_missing_returns_missing():
    db = AsyncMock()
    with patch(
        "app.services.deliverable_verifiers._git_file_exists",
        new=AsyncMock(return_value=None),
    ):
        res = await _verify_dockerfile(PROJECT_ID, db)
        assert res.status == "missing"
        assert res.evidence_ref is None


@pytest.mark.asyncio
async def test_openapi_falls_back_to_fastapi_inferred():
    """Sem openapi.{yaml,json}, mas com app/main.py (FastAPI) → 'present'
    com nota explicativa."""
    db = AsyncMock()
    # Primeira busca (openapi files) → None; segunda (main.py) → 'app/main.py'
    call_count = {"n": 0}
    async def fake(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return None
        return "app/main.py"
    with patch("app.services.deliverable_verifiers._git_file_exists", new=fake):
        res = await _verify_openapi(PROJECT_ID, db)
        assert res.status == "present"
        assert "FastAPI" in (res.notes or "")


@pytest.mark.asyncio
async def test_openapi_explicit_file_wins_over_inferred():
    db = AsyncMock()
    with patch(
        "app.services.deliverable_verifiers._git_file_exists",
        new=AsyncMock(return_value="openapi.yaml"),
    ):
        res = await _verify_openapi(PROJECT_ID, db)
        assert res.status == "verified"
        assert res.evidence_ref == "openapi.yaml"


@pytest.mark.asyncio
async def test_manifests_finds_pyproject():
    db = AsyncMock()
    with patch(
        "app.services.deliverable_verifiers._git_file_exists",
        new=AsyncMock(return_value="pyproject.toml"),
    ):
        res = await _verify_manifests(PROJECT_ID, db)
        assert res.status == "verified"


@pytest.mark.asyncio
async def test_database_design_finds_migrations_dir():
    """Diretório migrations/ com >0 arquivos → verified."""
    db = AsyncMock()
    with patch(
        "app.services.deliverable_verifiers._git_dir_count",
        new=AsyncMock(return_value=15),
    ):
        res = await _verify_database_design(PROJECT_ID, db)
        assert res.status == "verified"
        assert "15 arquivos" in res.evidence_ref


@pytest.mark.asyncio
async def test_database_design_falls_back_to_schema_sql():
    db = AsyncMock()
    # dir_count vazio em ambas tentativas, depois acha schema.sql
    with patch("app.services.deliverable_verifiers._git_dir_count", new=AsyncMock(return_value=0)), \
         patch("app.services.deliverable_verifiers._git_file_exists", new=AsyncMock(return_value="schema.sql")):
        res = await _verify_database_design(PROJECT_ID, db)
        assert res.status == "verified"
        assert res.evidence_ref == "schema.sql"


@pytest.mark.asyncio
async def test_adr_with_no_files_returns_missing():
    db = AsyncMock()
    with patch("app.services.deliverable_verifiers._git_dir_count", new=AsyncMock(return_value=0)):
        res = await _verify_adr(PROJECT_ID, db)
        assert res.status == "missing"


@pytest.mark.asyncio
async def test_sbom_finds_file():
    db = AsyncMock()
    with patch(
        "app.services.deliverable_verifiers._git_file_exists",
        new=AsyncMock(return_value="sbom.json"),
    ):
        res = await _verify_sbom(PROJECT_ID, db)
        assert res.status == "verified"
        assert res.evidence_ref == "sbom.json"


@pytest.mark.asyncio
async def test_ci_pipeline_finds_github_workflows():
    db = AsyncMock()
    with patch(
        "app.services.deliverable_verifiers._git_dir_count",
        new=AsyncMock(return_value=3),
    ):
        res = await _verify_ci_pipeline(PROJECT_ID, db)
        assert res.status == "verified"
        assert "3 jobs" in res.evidence_ref


@pytest.mark.asyncio
async def test_ci_pipeline_falls_back_to_gitlab():
    db = AsyncMock()
    with patch("app.services.deliverable_verifiers._git_dir_count", new=AsyncMock(return_value=0)), \
         patch("app.services.deliverable_verifiers._git_file_exists", new=AsyncMock(return_value=".gitlab-ci.yml")):
        res = await _verify_ci_pipeline(PROJECT_ID, db)
        assert res.status == "verified"
        assert res.evidence_ref == ".gitlab-ci.yml"


@pytest.mark.asyncio
async def test_manual_only_always_returns_manual():
    db = AsyncMock()
    res = await _verify_manual_only(PROJECT_ID, db)
    assert res.status == "manual_only"
    assert res.method == "manual_only"


# ─────────────────────────── compliance checklist (DB) ───────────────

@pytest.mark.asyncio
async def test_compliance_checklist_all_resolved_returns_verified(monkeypatch):
    """Mock OCG.ocg_data com todos items != PENDENTE → verified."""
    from app.models.base import OCG

    class FakeOCG:
        def __init__(self):
            self.ocg_data = json.dumps({
                "COMPLIANCE_CHECKLIST": [
                    {"item": "X", "status": "DONE"},
                    {"item": "Y", "status": "APPROVED"},
                ]
            })

    fake = FakeOCG()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=AsyncMock(scalar_one_or_none=lambda: fake))
    res = await _verify_compliance_checklist(PROJECT_ID, db)
    assert res.status == "verified"
    assert "2/2" in res.evidence_ref


@pytest.mark.asyncio
async def test_compliance_checklist_partial_returns_present():
    class FakeOCG:
        def __init__(self):
            self.ocg_data = json.dumps({
                "COMPLIANCE_CHECKLIST": [
                    {"item": "X", "status": "DONE"},
                    {"item": "Y", "status": "PENDENTE"},
                    {"item": "Z", "status": "PENDENTE"},
                ]
            })

    fake = FakeOCG()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=AsyncMock(scalar_one_or_none=lambda: fake))
    res = await _verify_compliance_checklist(PROJECT_ID, db)
    assert res.status == "present"
    assert "1/3" in res.evidence_ref
    assert "2 pendentes" in (res.notes or "")


@pytest.mark.asyncio
async def test_compliance_checklist_no_ocg_returns_missing():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=AsyncMock(scalar_one_or_none=lambda: None))
    res = await _verify_compliance_checklist(PROJECT_ID, db)
    assert res.status == "missing"
