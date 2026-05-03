"""Testes da Fase 32.1+32.2 do MVP 32 — DT-081.

Cobre:
  - Tarefa 1 (Fase 32.1): _load_persona_scores reescrito para ler de ocg_individual
    em vez de GatekeeperPersonaResponse + DocumentRouteMap (que causava AttributeError).
  - Tarefa 2 (Fase 32.2-A): arguider_compactor.compact_arguider_for_prompt
    — truncagem por criticidade, imunidade de críticos e CONF blocking.
  - Tarefa 3 (Fase 32.2-B): _build_user_prompt chama o compactor.

Como rodar:
    docker compose exec backend bash -c "cd /app && \\
      TEST_DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      pytest app/tests/test_mvp32_ocg_updater_dt081.py -v"

Banco alvo: gca_test (conftest.py força — DT-034)
"""
import hashlib
import re
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.models.base import (
    IngestedDocument,
    OCGIndividual,
)
from app.services.arguider_compactor import compact_arguider_for_prompt
from app.tests.factories import (
    create_test_organization,
    create_test_project,
    create_test_user,
)


# =============================================================================
# Helpers
# =============================================================================

_OCG_UPDATER_PATH = (
    Path(__file__).parent.parent / "services" / "ocg_updater_service.py"
)


async def _seed_project_with_docs(db, n_docs: int = 1):
    """Cria usuário + organização + projeto + documento(s) ingeridos."""
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    project = await create_test_project(
        db,
        organization_id=org.id,
        slug=f"mvp32-dt081-{uuid4().hex[:6]}",
    )

    docs = []
    for i in range(n_docs):
        h = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
        doc = IngestedDocument(
            id=uuid4(),
            project_id=project.id,
            uploaded_by=user.id,
            original_filename=f"doc_{i}.pdf",
            filename=f"{uuid4()}.pdf",
            file_type="pdf",
            file_hash=h,
            file_size_bytes=1024,
            arguider_status="completed",
            pii_detected=False,
        )
        db.add(doc)
        docs.append(doc)
    await db.flush()

    return project, docs


async def _seed_ocg_individual_rows(
    db,
    project,
    doc,
    tags: list[str],
    score: int = 75,
    status: str = "completed",
):
    """Insere linhas em ocg_individual com os tags fornecidos."""
    rows = []
    for tag in tags:
        row = OCGIndividual(
            project_id=project.id,
            document_id=doc.id,
            persona_id=tag,
            persona_name=f"Persona {tag}",
            parecer={"score": score, "analise": f"Análise de {tag}"},
            status=status,
        )
        db.add(row)
        rows.append(row)
    await db.flush()
    return rows


def _make_updater_service(db):
    """Instancia OCGUpdaterService com sessão de teste."""
    from app.services.ocg_updater_service import OCGUpdaterService

    svc = OCGUpdaterService.__new__(OCGUpdaterService)
    svc.db = db
    return svc


# =============================================================================
# Testes — Tarefa 1: _load_persona_scores
# =============================================================================


@pytest.mark.asyncio
async def test_documentroutemap_no_longer_referenced(db_session):
    """Guard de regressão: ocg_updater_service.py NÃO deve importar DocumentRouteMap."""
    source = _OCG_UPDATER_PATH.read_text(encoding="utf-8")

    # Matches em imports (linhas que iniciam com from/import)
    import_lines = [
        ln for ln in source.splitlines()
        if re.match(r"^\s*(from|import)\s+", ln)
        and "DocumentRouteMap" in ln
    ]
    assert import_lines == [], (
        f"DocumentRouteMap ainda importado: {import_lines}"
    )

    # Matches em imports de GatekeeperPersonaResponse
    import_gkpr = [
        ln for ln in source.splitlines()
        if re.match(r"^\s*(from|import)\s+", ln)
        and "GatekeeperPersonaResponse" in ln
    ]
    assert import_gkpr == [], (
        f"GatekeeperPersonaResponse ainda importado: {import_gkpr}"
    )


@pytest.mark.asyncio
async def test_load_persona_scores_uses_ocg_individual(db_session):
    """Projeto com rows completed → retorno não-vazio com chaves de pillar."""
    project, [doc] = await _seed_project_with_docs(db_session)

    # Tags mapeadas em PERSONA_TO_PILLAR do consolidador
    tags = ["gp", "arq", "dba", "dev", "qa", "ux", "ui"]
    await _seed_ocg_individual_rows(db_session, project, doc, tags, score=80)

    svc = _make_updater_service(db_session)
    result = await svc._load_persona_scores(project.id)

    assert result != {}, "Esperado dict não-vazio com rows presentes"
    # Deve ter pelo menos 1 chave de pillar (formato da consolidação)
    pillar_keys = [k for k in result if k != "overall_score"]
    assert len(pillar_keys) >= 1, f"Nenhuma chave de pillar em {result}"
    assert "overall_score" in result


@pytest.mark.asyncio
async def test_load_persona_scores_returns_empty_when_no_rows(db_session):
    """Projeto sem rows ocg_individual → retorna {} e emite log no_ocg_individual_rows."""
    project, _ = await _seed_project_with_docs(db_session)
    svc = _make_updater_service(db_session)

    with patch("app.services.ocg_updater_service.logger") as mock_logger:
        result = await svc._load_persona_scores(project.id)

    assert result == {}, f"Esperado dict vazio, recebeu {result}"
    assert mock_logger.info.called, "logger.info não foi chamado"
    # Verifica que o evento canônico foi emitido
    evento_emitido = any(
        "no_ocg_individual_rows" in str(call)
        for call in mock_logger.info.call_args_list
    )
    assert evento_emitido, (
        f"Evento 'no_ocg_individual_rows' não encontrado nas chamadas: "
        f"{mock_logger.info.call_args_list}"
    )


@pytest.mark.asyncio
async def test_load_persona_scores_normalizes_persona_tag_case(db_session):
    """Row com persona_id='ARQ' (uppercase) é normalizado para 'arq' → mapeamento encontrado."""
    project, [doc] = await _seed_project_with_docs(db_session)

    # Insere com uppercase — como o n8n pode enviar
    await _seed_ocg_individual_rows(db_session, project, doc, ["ARQ"], score=70)

    svc = _make_updater_service(db_session)
    result = await svc._load_persona_scores(project.id)

    # ARQ mapeia para p5_architecture_score no consolidador
    assert result != {}, "Normalização de case falhou — dict vazio inesperado"
    pillar_keys = [k for k in result if k != "overall_score"]
    assert len(pillar_keys) >= 1


@pytest.mark.asyncio
async def test_load_persona_scores_excludes_failed_personas(db_session):
    """Persona com status='failed' não deve entrar no cálculo de pillars."""
    project, [doc] = await _seed_project_with_docs(db_session)

    # Uma linha completed e uma failed com o mesmo projeto
    await _seed_ocg_individual_rows(db_session, project, doc, ["arq"], score=80, status="completed")
    await _seed_ocg_individual_rows(db_session, project, doc, ["qa"], score=20, status="failed")

    svc = _make_updater_service(db_session)
    result = await svc._load_persona_scores(project.id)

    assert result != {}, "Linha 'completed' deveria produzir resultado"
    # overall_score deve refletir apenas arq=80, não qa=20
    assert result.get("overall_score", 0) >= 70, (
        f"Score contaminado pela persona falha: {result}"
    )


@pytest.mark.asyncio
async def test_load_persona_scores_logs_conf_blocking(db_session):
    """CONF com score<60 → log 'conf_blocking_score' deve ser emitido."""
    # Nota: CONF não está em PERSONA_TO_PILLAR padrão — o log é emitido
    # antes da checagem do mapeamento; o check de conf_blocking é feito
    # quando persona_tag_lower == 'conf'. Se conf não está no mapeamento,
    # o score não entra nos pillars mas o log DEVE ser emitido.
    # Verificamos o comportamento do código via mock do logger.
    project, [doc] = await _seed_project_with_docs(db_session)

    # Insere CONF com score<60 — persona que pode não estar no PERSONA_TO_PILLAR
    # mas o log de blocking deve ser emitido de qualquer forma
    conf_row = OCGIndividual(
        project_id=project.id,
        document_id=doc.id,
        persona_id="conf",
        persona_name="Conformidade",
        parecer={"score": 45, "analise": "Conformidade abaixo do threshold"},
        status="completed",
    )
    db_session.add(conf_row)
    await db_session.flush()

    svc = _make_updater_service(db_session)

    from app.services.ocg_consolidator_service import PERSONA_TO_PILLAR

    if "conf" not in PERSONA_TO_PILLAR:
        # CONF não mapeado ainda (MVP 33) — log de blocking é emitido
        # mas resultado pode ser vazio (sem outros scores). OK para este teste.
        with patch("app.services.ocg_updater_service.logger") as mock_logger:
            await svc._load_persona_scores(project.id)
            warning_calls = [
                str(c) for c in mock_logger.warning.call_args_list
            ]
        conf_blocking_logged = any(
            "conf_blocking_score" in str(c)
            for c in mock_logger.warning.call_args_list
        )
        assert conf_blocking_logged, (
            f"Log 'conf_blocking_score' não encontrado: {mock_logger.warning.call_args_list}"
        )
    else:
        # CONF já mapeado — score entra e log é emitido
        with patch("app.services.ocg_updater_service.logger") as mock_logger:
            result = await svc._load_persona_scores(project.id)
        conf_blocking_logged = any(
            "conf_blocking_score" in str(c)
            for c in mock_logger.warning.call_args_list
        )
        assert conf_blocking_logged


# =============================================================================
# Testes — Tarefa 2: compact_arguider_for_prompt
# =============================================================================

def _build_arguider_analysis(n_findings: int = 30, conf_score: int = 80) -> Dict[str, Any]:
    """Monta arguider_analysis de teste com n findings."""
    findings = []
    criticidades = ["alta", "media", "baixa"]
    for i in range(n_findings):
        findings.append({
            "id": f"F{i:03d}",
            "titulo": f"Finding {i}",
            "criticidade": criticidades[i % 3],
            "source_persona": "ARQ",
            "score": 70,
            "descricao": "Detalhe do finding " * 10,  # texto longo
        })

    return {
        "overall_score": 72,
        "blocked": False,
        "blocking_reason": None,
        "personas_executed": ["GP", "ARQ", "DBA"],
        "personas_failed": [],
        "personas_excluded_count": 0,
        "ocg_individual": {
            "GP": {
                "score": 75,
                "approved": True,
                "blocking": False,
                "findings": [{"x": 1}] * 5,
            },
            "ARQ": {
                "score": 68,
                "approved": False,
                "blocking": False,
                "findings": [{"x": 1}] * 12,
            },
            "CONF": {
                "score": conf_score,
                "approved": conf_score >= 60,
                "blocking": conf_score < 60,
                "findings": [{"x": 1}] * 3,
            },
        },
        "ocg_global_delta": {
            "p1_business_score": 75,
            "p5_architecture_score": 68,
        },
        "consolidated_findings": findings,
        "consolidated_recommendations": [f"Recomendação {i}" for i in range(15)],
    }


def test_compact_arguider_truncates_to_max_findings():
    """50 findings input → compacted tem no máximo 20."""
    analysis = _build_arguider_analysis(n_findings=50)
    result = compact_arguider_for_prompt(analysis, max_findings=20)

    assert len(result["consolidated_findings"]) <= 20
    assert result["_compactor_meta"]["findings_total"] == 50
    assert result["_compactor_meta"]["findings_dropped"] == 30


def test_compact_arguider_critical_findings_immune():
    """Finding com criticidade='critica' SEMPRE incluso, mesmo com max_findings=1."""
    analysis = _build_arguider_analysis(n_findings=0)
    analysis["consolidated_findings"] = [
        {"id": "C001", "criticidade": "critica", "source_persona": "ARQ", "score": 10},
        {"id": "C002", "criticidade": "critica", "source_persona": "DEV", "score": 20},
        {"id": "N001", "criticidade": "baixa", "source_persona": "UX", "score": 80},
        {"id": "N002", "criticidade": "media", "source_persona": "QA", "score": 70},
    ]
    result = compact_arguider_for_prompt(analysis, max_findings=1)

    ids_kept = {f["id"] for f in result["consolidated_findings"]}
    assert "C001" in ids_kept, "Finding crítico C001 foi descartado"
    assert "C002" in ids_kept, "Finding crítico C002 foi descartado"


def test_compact_arguider_conf_blocking_immune():
    """Finding com source_persona='CONF' e score<60 SEMPRE incluso."""
    analysis = _build_arguider_analysis(n_findings=0)
    analysis["consolidated_findings"] = [
        {"id": "CONF01", "criticidade": "baixa", "source_persona": "CONF", "score": 45},
        {"id": "CONF02", "criticidade": "media", "source_persona": "CONF", "score": 58},
        {"id": "CONF03", "criticidade": "baixa", "source_persona": "CONF", "score": 65},  # score >= 60
        {"id": "N001", "criticidade": "baixa", "source_persona": "ARQ", "score": 80},
    ]
    result = compact_arguider_for_prompt(analysis, max_findings=1)

    ids_kept = {f["id"] for f in result["consolidated_findings"]}
    # CONF01 e CONF02 têm score<60 — imunes
    assert "CONF01" in ids_kept, "CONF01 (score=45) deveria ser imune"
    assert "CONF02" in ids_kept, "CONF02 (score=58) deveria ser imune"


def test_compact_arguider_summarizes_ocg_individual():
    """ocg_individual com 9 personas + 100 findings/persona → summary tem só score/approved/blocking/findings_count."""
    analysis = _build_arguider_analysis(n_findings=0)
    # Adicionar persona com muitos findings
    analysis["ocg_individual"]["DEV"] = {
        "score": 82,
        "approved": True,
        "blocking": False,
        "findings": [{"detalhe": "x" * 200}] * 100,  # 100 findings grandes
        "analise_completa": "x" * 5000,  # campo extra verboso
    }

    result = compact_arguider_for_prompt(analysis)

    dev_summary = result["ocg_individual_summary"].get("DEV", {})
    assert dev_summary.get("score") == 82
    assert dev_summary.get("approved") is True
    assert dev_summary.get("blocking") is False
    assert dev_summary.get("findings_count") == 100
    # Campo verboso NÃO deve aparecer no summary
    assert "analise_completa" not in dev_summary


def test_compact_arguider_preserves_ocg_global_delta_integral():
    """ocg_global_delta passa intocado para o payload compactado."""
    delta = {
        "p1_business_score": 90,
        "p5_architecture_score": 85,
        "p6_data_score": 78,
        "extra_field": "valor qualquer",
    }
    analysis = _build_arguider_analysis(n_findings=5)
    analysis["ocg_global_delta"] = delta

    result = compact_arguider_for_prompt(analysis)

    assert result["ocg_global_delta"] == delta, (
        f"ocg_global_delta foi alterado: {result['ocg_global_delta']}"
    )


def test_compact_arguider_meta_reports_dropped_count():
    """Metadata reporta corretamente o número de findings descartados."""
    analysis = _build_arguider_analysis(n_findings=35)
    result = compact_arguider_for_prompt(analysis, max_findings=20)

    meta = result["_compactor_meta"]
    assert meta["findings_total"] == 35
    assert meta["findings_kept"] + meta["findings_dropped"] == 35
    assert meta["findings_dropped"] >= 0


def test_compact_arguider_empty_input():
    """Input vazio retorna dict vazio (sem exceção)."""
    assert compact_arguider_for_prompt({}) == {}
    assert compact_arguider_for_prompt(None) == {}  # type: ignore[arg-type]


def test_compact_arguider_does_not_mutate_input():
    """Função não muta o dict de entrada."""
    import copy
    analysis = _build_arguider_analysis(n_findings=25)
    original = copy.deepcopy(analysis)

    compact_arguider_for_prompt(analysis, max_findings=10)

    assert analysis == original, "Input foi mutado indevidamente"


def test_compact_arguider_recommendations_capped_at_10():
    """consolidated_recommendations é truncado no máximo 10 itens."""
    analysis = _build_arguider_analysis(n_findings=0)
    analysis["consolidated_recommendations"] = [f"Rec {i}" for i in range(20)]

    result = compact_arguider_for_prompt(analysis)

    assert len(result["consolidated_recommendations"]) == 10


# =============================================================================
# Teste — Tarefa 3: _build_user_prompt usa o compactor
# =============================================================================

def test_build_user_prompt_calls_compactor():
    """_build_user_prompt deve incluir '_compactor_meta' no prompt serializado."""
    from app.services.ocg_updater_service import OCGUpdaterService

    svc = OCGUpdaterService.__new__(OCGUpdaterService)
    svc.db = MagicMock()

    analysis = _build_arguider_analysis(n_findings=25)
    current_ocg: Dict[str, Any] = {"PILLAR_SCORES": {"P1": {"score": 70}}}

    prompt = svc._build_user_prompt(current_ocg, analysis)

    assert "_compactor_meta" in prompt, (
        "Prompt não contém '_compactor_meta' — compactor não foi chamado"
    )


# =============================================================================
# Teste de regressão — guard AttributeError DocumentRouteMap
# =============================================================================

def test_attributeerror_documentroutemap_regression():
    """Guard contra reintrodução do bug DT-081 (AttributeError: DocumentRouteMap.project_id).

    O bug ocorria porque DocumentRouteMap não tinha coluna project_id e a query
    antiga tentava filtrar por ela. Este teste garante que o módulo importa
    sem erros e que DocumentRouteMap não está referenciado em import statements.
    """
    # Importação deve funcionar sem erros
    from app.services import ocg_updater_service  # noqa: F401

    source = _OCG_UPDATER_PATH.read_text(encoding="utf-8")

    # Nenhuma linha de import deve referenciar document_route_map
    bad_imports = [
        ln for ln in source.splitlines()
        if re.match(r"^\s*(from|import)\s+", ln)
        and "document_route_map" in ln.lower()
    ]
    assert bad_imports == [], (
        f"Regressão DT-081: import de document_route_map detectado: {bad_imports}"
    )
