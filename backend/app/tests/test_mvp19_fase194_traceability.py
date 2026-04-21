"""MVP 19 Fase 19.4 — testes da matriz de rastreabilidade.

Valida:
- `build_traceability_matrix` consolida requisitos × test_specs × código gerado
  por `module_candidate_id` (LEFT JOIN semântico em Python).
- Requisitos sem spec ou sem código aparecem com arrays vazios (LEFT JOIN).
- Ordenação IEEE 830: RF → RNF → BR → uncategorized; dentro da categoria,
  `created_at` ASC.
- IDs são 1-based dentro da categoria (RF-001, RF-002, RNF-001…).
- Sumário agregado: total, by_category, with_test_spec, with_generated_code,
  fully_traced.
- Renderer markdown emite tabela com tabela cover + rows; pipe escape.
- Integração ERS: Seção 4 do build_ers_markdown contém a tabela; projeto
  vazio mostra placeholder "Nenhum requisito registrado ainda".
- Projeto sem requisitos: rows=[], summary total=0, placeholder no markdown.
"""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.core.security import hash_password
from app.models.base import (
    ArguiderAnalysis,
    GeneratedModule,
    IngestedDocument,
    ModuleCandidate,
    Organization,
    Project,
    TestSpec,
    User,
)
from app.services.ers_doc_generator_service import build_ers_markdown
from app.services.traceability_service import (
    build_traceability_matrix,
    render_traceability_markdown,
)


# ===========================================================================
# Helpers
# ===========================================================================

async def _make_user(db) -> User:
    uid = uuid4()
    user = User(
        id=uid,
        email=f"trace-{uid.hex[:6]}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="Trace Tester",
        is_active=True,
        is_admin=True,
        created_at=datetime.utcnow(),
    )
    db.add(user)
    await db.flush()
    return user


async def _make_project(db, user) -> Project:
    org = Organization(
        id=uuid4(),
        name=f"Org {uuid4().hex[:6]}",
        slug=f"org-trace-{uuid4().hex[:6]}",
        owner_id=user.id,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(org)
    project = Project(
        id=uuid4(),
        organization_id=org.id,
        name="Projeto Rastreabilidade",
        slug=f"trace-{uuid4().hex[:6]}",
        description="Projeto de teste para matriz.",
        deliverable_type="web_app",
        status="active",
        created_at=datetime.utcnow(),
    )
    db.add(project)
    await db.flush()
    return project


async def _make_arguider_analysis(db, project: Project, user: User) -> ArguiderAnalysis:
    doc = IngestedDocument(
        id=uuid4(),
        project_id=project.id,
        filename=f"{uuid4().hex}.pdf",
        original_filename="req.pdf",
        file_type="pdf",
        file_hash="0" * 64,
        file_size_bytes=100,
        uploaded_by=user.id,
    )
    db.add(doc)
    await db.flush()
    analysis = ArguiderAnalysis(
        id=uuid4(),
        document_id=doc.id,
        project_id=project.id,
        llm_model="claude-3-5-sonnet",
        tokens_used=1000,
        latency_ms=500,
    )
    db.add(analysis)
    await db.flush()
    return analysis


async def _make_module(
    db, project, analysis, *, name, category, priority="medium", offset_s=0,
) -> ModuleCandidate:
    mc = ModuleCandidate(
        project_id=project.id,
        arguider_analysis_id=analysis.id,
        name=name,
        description=f"Desc de {name}",
        module_type="feature",
        priority=priority,
        requirement_category=category,
        created_at=datetime.utcnow() + timedelta(seconds=offset_s),
    )
    db.add(mc)
    await db.flush()
    return mc


async def _make_spec(
    db, project, module, *, spec_type="unit", status="approved",
) -> TestSpec:
    spec = TestSpec(
        project_id=project.id,
        module_id=module.id if module else None,
        spec_type=spec_type,
        content=f"# Spec {spec_type} para {module.name if module else 'global'}",
        status=status,
    )
    db.add(spec)
    await db.flush()
    return spec


async def _make_generated_module(
    db, project, module, *,
    name, status="completed",
    source_path=None, unit_test_path=None,
) -> GeneratedModule:
    gm = GeneratedModule(
        project_id=project.id,
        module_candidate_id=module.id if module else None,
        name=name,
        module_type="feature",
        status=status,
        git_source_path=source_path,
        git_unit_test_path=unit_test_path,
        generated_at=datetime.utcnow(),
    )
    db.add(gm)
    await db.flush()
    return gm


# ===========================================================================
# build_traceability_matrix
# ===========================================================================

@pytest.mark.asyncio
async def test_matriz_projeto_vazio_retorna_rows_vazia(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    matrix = await build_traceability_matrix(db_session, project.id)
    assert matrix["rows"] == []
    assert matrix["summary"]["total_requirements"] == 0
    assert matrix["summary"]["fully_traced"] == 0


@pytest.mark.asyncio
async def test_matriz_requisito_sem_spec_nem_codigo_aparece_com_arrays_vazios(db_session):
    """LEFT JOIN semântico: requisito existe mesmo sem artefatos."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    analysis = await _make_arguider_analysis(db_session, project, user)
    await _make_module(db_session, project, analysis, name="Login", category="functional")

    matrix = await build_traceability_matrix(db_session, project.id)
    assert len(matrix["rows"]) == 1
    row = matrix["rows"][0]
    assert row["requirement_id"] == "RF-001"
    assert row["name"] == "Login"
    assert row["test_specs"] == []
    assert row["generated_modules"] == []


@pytest.mark.asyncio
async def test_matriz_id_1_based_dentro_da_categoria(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    analysis = await _make_arguider_analysis(db_session, project, user)
    await _make_module(db_session, project, analysis, name="A", category="functional", offset_s=1)
    await _make_module(db_session, project, analysis, name="B", category="functional", offset_s=2)
    await _make_module(db_session, project, analysis, name="NFR1", category="non_functional", offset_s=3)
    await _make_module(db_session, project, analysis, name="BR1", category="business_rule", offset_s=4)

    matrix = await build_traceability_matrix(db_session, project.id)
    ids = [r["requirement_id"] for r in matrix["rows"]]
    # RF → RNF → BR na ordem IEEE 830.
    assert ids == ["RF-001", "RF-002", "RNF-001", "BR-001"]


@pytest.mark.asyncio
async def test_matriz_ordena_rf_antes_de_rnf_antes_de_br_antes_de_none(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    analysis = await _make_arguider_analysis(db_session, project, user)
    # Cria fora de ordem de categoria pra ver que a ordem canônica é aplicada.
    await _make_module(db_session, project, analysis, name="SemCat", category=None, offset_s=1)
    await _make_module(db_session, project, analysis, name="Regra", category="business_rule", offset_s=2)
    await _make_module(db_session, project, analysis, name="Latência", category="non_functional", offset_s=3)
    await _make_module(db_session, project, analysis, name="Login", category="functional", offset_s=4)

    matrix = await build_traceability_matrix(db_session, project.id)
    cats = [r["category"] for r in matrix["rows"]]
    assert cats == ["functional", "non_functional", "business_rule", None]


@pytest.mark.asyncio
async def test_matriz_correlaciona_test_specs_do_mesmo_modulo(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    analysis = await _make_arguider_analysis(db_session, project, user)
    mod = await _make_module(
        db_session, project, analysis, name="Login", category="functional",
    )
    await _make_spec(db_session, project, mod, spec_type="unit", status="approved")
    await _make_spec(db_session, project, mod, spec_type="integration", status="draft")

    matrix = await build_traceability_matrix(db_session, project.id)
    row = matrix["rows"][0]
    types = sorted(s["spec_type"] for s in row["test_specs"])
    assert types == ["integration", "unit"]
    statuses = {s["spec_type"]: s["status"] for s in row["test_specs"]}
    assert statuses["unit"] == "approved"
    assert statuses["integration"] == "draft"


@pytest.mark.asyncio
async def test_matriz_correlaciona_generated_modules_do_mesmo_candidate(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    analysis = await _make_arguider_analysis(db_session, project, user)
    mod = await _make_module(
        db_session, project, analysis, name="Login", category="functional",
    )
    await _make_generated_module(
        db_session, project, mod,
        name="login_module",
        source_path="src/auth/login.py",
        unit_test_path="tests/test_login.py",
    )

    matrix = await build_traceability_matrix(db_session, project.id)
    row = matrix["rows"][0]
    assert len(row["generated_modules"]) == 1
    g = row["generated_modules"][0]
    assert g["name"] == "login_module"
    assert g["git_source_path"] == "src/auth/login.py"
    assert g["git_unit_test_path"] == "tests/test_login.py"
    assert g["status"] == "completed"
    assert g["generated_at"] is not None


@pytest.mark.asyncio
async def test_matriz_spec_sem_module_id_nao_aparece_em_requisito(db_session):
    """Spec global (module_id NULL) não deve ser atribuído a nenhum requisito."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    analysis = await _make_arguider_analysis(db_session, project, user)
    mod = await _make_module(
        db_session, project, analysis, name="Login", category="functional",
    )
    # Spec global (security sem module_id).
    await _make_spec(db_session, project, None, spec_type="security")
    # Spec do módulo.
    await _make_spec(db_session, project, mod, spec_type="unit")

    matrix = await build_traceability_matrix(db_session, project.id)
    row = matrix["rows"][0]
    assert [s["spec_type"] for s in row["test_specs"]] == ["unit"]


@pytest.mark.asyncio
async def test_matriz_summary_agrega_contadores_corretamente(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    analysis = await _make_arguider_analysis(db_session, project, user)

    m1 = await _make_module(db_session, project, analysis, name="A", category="functional", offset_s=1)
    m2 = await _make_module(db_session, project, analysis, name="B", category="functional", offset_s=2)
    m3 = await _make_module(db_session, project, analysis, name="C", category="non_functional", offset_s=3)
    await _make_module(db_session, project, analysis, name="D", category=None, offset_s=4)

    # A: com spec E código → fully_traced
    await _make_spec(db_session, project, m1, spec_type="unit")
    await _make_generated_module(db_session, project, m1, name="a_mod", source_path="src/a.py")
    # B: só spec
    await _make_spec(db_session, project, m2, spec_type="integration")
    # C: só código
    await _make_generated_module(db_session, project, m3, name="c_mod")
    # D: nada

    matrix = await build_traceability_matrix(db_session, project.id)
    s = matrix["summary"]
    assert s["total_requirements"] == 4
    assert s["by_category"] == {
        "functional": 2, "non_functional": 1, "business_rule": 0, "uncategorized": 1,
    }
    assert s["with_test_spec"] == 2
    assert s["with_generated_code"] == 2
    assert s["fully_traced"] == 1


@pytest.mark.asyncio
async def test_matriz_categoria_desconhecida_vai_para_uncategorized(db_session):
    """Se o banco tiver algum valor fora da whitelist, cai em uncategorized."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    analysis = await _make_arguider_analysis(db_session, project, user)
    await _make_module(
        db_session, project, analysis, name="X", category="valor_estranho",
    )

    matrix = await build_traceability_matrix(db_session, project.id)
    assert matrix["summary"]["by_category"]["uncategorized"] == 1
    assert matrix["rows"][0]["requirement_id"].startswith("REQ-")


# ===========================================================================
# Renderer markdown
# ===========================================================================

def test_render_matriz_vazia_emite_placeholder():
    matrix = {"rows": [], "summary": {"total_requirements": 0}}
    out = "\n".join(render_traceability_markdown(matrix))
    assert "Nenhum requisito registrado ainda" in out


def test_render_matriz_com_rows_emite_tabela_markdown():
    matrix = {
        "rows": [
            {
                "requirement_id": "RF-001",
                "module_candidate_id": str(uuid4()),
                "name": "Login",
                "category": "functional",
                "priority": "high",
                "status": "sugerido",
                "test_specs": [
                    {"id": str(uuid4()), "spec_type": "unit", "status": "approved"}
                ],
                "generated_modules": [
                    {
                        "id": str(uuid4()),
                        "name": "login_mod",
                        "status": "completed",
                        "git_source_path": "src/auth/login.py",
                        "git_unit_test_path": None,
                        "git_integration_test_path": None,
                        "git_uat_test_path": None,
                        "git_docs_path": None,
                        "generated_at": "2026-04-21T00:00:00+00:00",
                    }
                ],
            }
        ],
        "summary": {
            "total_requirements": 1,
            "by_category": {
                "functional": 1, "non_functional": 0,
                "business_rule": 0, "uncategorized": 0,
            },
            "with_test_spec": 1,
            "with_generated_code": 1,
            "fully_traced": 1,
        },
    }
    out = "\n".join(render_traceability_markdown(matrix))
    assert "| ID | Requisito | Categoria | Test Specs | Código gerado |" in out
    assert "| **RF-001** | Login |" in out
    assert "src/auth/login.py" in out
    assert "unit" in out
    # Sumário no topo.
    assert "Rastreamento completo" in out


def test_render_matriz_nomes_com_pipe_sao_escapados():
    matrix = {
        "rows": [{
            "requirement_id": "RF-001",
            "module_candidate_id": str(uuid4()),
            "name": "Login | SSO",
            "category": "functional",
            "priority": "medium",
            "status": "sugerido",
            "test_specs": [],
            "generated_modules": [],
        }],
        "summary": {
            "total_requirements": 1,
            "by_category": {"functional": 1, "non_functional": 0,
                            "business_rule": 0, "uncategorized": 0},
            "with_test_spec": 0,
            "with_generated_code": 0,
            "fully_traced": 0,
        },
    }
    out = "\n".join(render_traceability_markdown(matrix))
    # Pipe no nome deve ter sido escapado.
    assert "Login \\| SSO" in out


def test_render_matriz_nome_longo_truncado():
    nome = "A" * 200
    matrix = {
        "rows": [{
            "requirement_id": "RF-001",
            "module_candidate_id": str(uuid4()),
            "name": nome,
            "category": "functional",
            "priority": "low",
            "status": "sugerido",
            "test_specs": [],
            "generated_modules": [],
        }],
        "summary": {
            "total_requirements": 1,
            "by_category": {"functional": 1, "non_functional": 0,
                            "business_rule": 0, "uncategorized": 0},
            "with_test_spec": 0,
            "with_generated_code": 0,
            "fully_traced": 0,
        },
    }
    out = "\n".join(render_traceability_markdown(matrix))
    assert "…" in out  # truncado
    assert "A" * 200 not in out  # não vazou o nome cheio


# ===========================================================================
# Integração ERS — Seção 4 deixou de ser placeholder
# ===========================================================================

@pytest.mark.asyncio
async def test_ers_secao_4_usa_matriz_real_quando_ha_requisitos(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    analysis = await _make_arguider_analysis(db_session, project, user)
    mod = await _make_module(db_session, project, analysis, name="Login", category="functional")
    await _make_spec(db_session, project, mod, spec_type="unit")
    await _make_generated_module(db_session, project, mod, name="login_mod", source_path="src/auth/login.py")

    md = await build_ers_markdown(db_session, project.id)
    assert "## 4. Matriz de Rastreabilidade" in md
    # Seção 4 deve conter a tabela gerada, não mais o placeholder antigo.
    assert "será populada na Fase 19.4" not in md
    assert "| ID | Requisito | Categoria | Test Specs | Código gerado |" in md
    assert "**RF-001**" in md
    assert "Login" in md
    assert "src/auth/login.py" in md


@pytest.mark.asyncio
async def test_ers_secao_4_sem_requisitos_mostra_placeholder_da_matriz(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    md = await build_ers_markdown(db_session, project.id)
    assert "## 4. Matriz de Rastreabilidade" in md
    assert "Nenhum requisito registrado ainda" in md


# ===========================================================================
# Ordenação determinística
# ===========================================================================

@pytest.mark.asyncio
async def test_matriz_rodar_duas_vezes_retorna_mesmo_resultado(db_session):
    """Idempotência da query — mesmos dados → mesma matriz."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    analysis = await _make_arguider_analysis(db_session, project, user)
    for i in range(3):
        await _make_module(
            db_session, project, analysis,
            name=f"M{i}", category="functional", offset_s=i,
        )

    m1 = await build_traceability_matrix(db_session, project.id)
    m2 = await build_traceability_matrix(db_session, project.id)
    ids1 = [r["requirement_id"] for r in m1["rows"]]
    ids2 = [r["requirement_id"] for r in m2["rows"]]
    assert ids1 == ids2
    assert ids1 == ["RF-001", "RF-002", "RF-003"]
