"""MVP 33 — Expansão do PERSONA_TO_PILLAR para 12 personas LLM (Conjunto B).

Antes (MVP ≤32): 7 personas mapeadas (gp, arq, dba, dev, qa, ux, ui).
Depois (MVP 33): 11 personas mapeadas — adiciona seg, conf, lgpd, neg.
AUD continua fora (router/classificador, não validador).

Cobertura:
  - Mapeamento canônico das 4 personas novas → pillars corretos.
  - Fallback `_load_persona_scores` agrega scores das 4 personas novas.
  - AUD continua sem mapeamento (skip silencioso).
  - Não-regressão: as 7 personas antigas continuam mapeando como antes.

Como rodar:
    docker compose exec backend bash -c "cd /app && \\
      TEST_DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      pytest app/tests/test_mvp33_persona_pillar_expansion.py -v"
"""
import hashlib
from uuid import uuid4

import pytest

from app.models.base import IngestedDocument, OCGIndividual
from app.services.ocg_consolidator_service import PERSONA_TO_PILLAR
from app.tests.factories import (
    create_test_organization,
    create_test_project,
    create_test_user,
)


# =============================================================================
# Mapping canônico (testes puros — sem DB)
# =============================================================================


def test_mapping_inclui_4_personas_novas():
    """SEG, CONF, LGPD, NEG agora mapeiam para pillars canônicos."""
    assert PERSONA_TO_PILLAR["seg"] == "p7_security_score"
    assert PERSONA_TO_PILLAR["conf"] == "p2_rules_score"
    assert PERSONA_TO_PILLAR["lgpd"] == "p2_rules_score"
    assert PERSONA_TO_PILLAR["neg"] == "p1_business_score"


def test_mapping_aud_continua_fora():
    """AUD é router/classificador, não validador — não deve estar no mapping."""
    assert "aud" not in PERSONA_TO_PILLAR


def test_mapping_nao_quebra_personas_antigas():
    """Não-regressão: as 7 personas pré-MVP 33 mantêm o mapeamento original."""
    legado = {
        "gp": "p1_business_score",
        "arq": "p5_architecture_score",
        "dev": "p5_architecture_score",
        "dba": "p6_data_score",
        "qa": "p4_nfr_score",
        "ux": "p3_features_score",
        "ui": "p3_features_score",
    }
    for tag, pillar in legado.items():
        assert PERSONA_TO_PILLAR[tag] == pillar, (
            f"Persona '{tag}' regrediu: esperava '{pillar}', recebeu '{PERSONA_TO_PILLAR[tag]}'"
        )


def test_mapping_cobre_11_personas():
    """Cobertura: 11 personas mapeadas (12 do Conjunto B menos AUD)."""
    assert len(PERSONA_TO_PILLAR) == 11, (
        f"Esperava 11 personas mapeadas, encontrou {len(PERSONA_TO_PILLAR)}: "
        f"{sorted(PERSONA_TO_PILLAR.keys())}"
    )


def test_mapping_cobre_todos_pillars_relevantes():
    """Validador: cada pillar canônico (P1-P7) tem ao menos 1 persona, exceto onde
    o produto não tem persona (todos os 7 estão cobertos no MVP 33)."""
    pillars_cobertos = set(PERSONA_TO_PILLAR.values())
    esperados = {
        "p1_business_score",
        "p2_rules_score",
        "p3_features_score",
        "p4_nfr_score",
        "p5_architecture_score",
        "p6_data_score",
        "p7_security_score",
    }
    assert pillars_cobertos == esperados, (
        f"Pillars não-cobertos: {esperados - pillars_cobertos}"
    )


# =============================================================================
# Fallback `_load_persona_scores` agrega as 4 personas novas
# =============================================================================


async def _seed_project_with_doc(db):
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    project = await create_test_project(
        db, organization_id=org.id, slug=f"mvp33-{uuid4().hex[:6]}"
    )
    h = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    doc = IngestedDocument(
        id=uuid4(),
        project_id=project.id,
        uploaded_by=user.id,
        original_filename="doc.pdf",
        filename=f"{uuid4()}.pdf",
        file_type="pdf",
        file_hash=h,
        file_size_bytes=1024,
        arguider_status="completed",
        pii_detected=False,
    )
    db.add(doc)
    await db.flush()
    return project, doc


def _make_updater_service(db):
    from app.services.ocg_updater_service import OCGUpdaterService

    svc = OCGUpdaterService.__new__(OCGUpdaterService)
    svc.db = db
    return svc


@pytest.mark.asyncio
async def test_fallback_agrega_seg_em_p7(db_session):
    """SEG sozinho → fallback produz p7_security_score."""
    project, doc = await _seed_project_with_doc(db_session)
    db_session.add(OCGIndividual(
        project_id=project.id,
        document_id=doc.id,
        persona_id="SEG",
        persona_name="Segurança",
        parecer={"score": 70},
        status="completed",
    ))
    await db_session.flush()

    svc = _make_updater_service(db_session)
    result = await svc._load_persona_scores(project.id)

    assert "p7_security_score" in result, f"P7 ausente em {result}"
    assert result["p7_security_score"]["score"] == 70.0


@pytest.mark.asyncio
async def test_fallback_agrega_conf_e_lgpd_em_p2(db_session):
    """CONF + LGPD compartilham P2 — média deve ser calculada."""
    project, doc = await _seed_project_with_doc(db_session)
    for tag, score in [("CONF", 60), ("LGPD", 80)]:
        db_session.add(OCGIndividual(
            project_id=project.id,
            document_id=doc.id,
            persona_id=tag,
            persona_name=f"Persona {tag}",
            parecer={"score": score},
            status="completed",
        ))
    await db_session.flush()

    svc = _make_updater_service(db_session)
    result = await svc._load_persona_scores(project.id)

    assert "p2_rules_score" in result, f"P2 ausente em {result}"
    # Média 60 + 80 = 70
    assert result["p2_rules_score"]["score"] == 70.0


@pytest.mark.asyncio
async def test_fallback_agrega_neg_e_gp_em_p1(db_session):
    """NEG + GP compartilham P1 — média deve ser calculada."""
    project, doc = await _seed_project_with_doc(db_session)
    for tag, score in [("GP", 80), ("NEG", 70)]:
        db_session.add(OCGIndividual(
            project_id=project.id,
            document_id=doc.id,
            persona_id=tag,
            persona_name=f"Persona {tag}",
            parecer={"score": score},
            status="completed",
        ))
    await db_session.flush()

    svc = _make_updater_service(db_session)
    result = await svc._load_persona_scores(project.id)

    assert "p1_business_score" in result, f"P1 ausente em {result}"
    # Média 80 + 70 = 75
    assert result["p1_business_score"]["score"] == 75.0


@pytest.mark.asyncio
async def test_fallback_aud_continua_ignorado(db_session):
    """AUD não é validador — fallback deve ignorar (resultado vazio)."""
    project, doc = await _seed_project_with_doc(db_session)
    db_session.add(OCGIndividual(
        project_id=project.id,
        document_id=doc.id,
        persona_id="AUD",
        persona_name="Auditor",
        parecer={"score": 90},  # mesmo com score alto, AUD não vira pillar
        status="completed",
    ))
    await db_session.flush()

    svc = _make_updater_service(db_session)
    result = await svc._load_persona_scores(project.id)

    assert result == {}, f"AUD deveria ser ignorado, mas produziu {result}"


@pytest.mark.asyncio
async def test_fallback_cobre_todas_11_personas(db_session):
    """Cenário canônico: 11 personas (todas exceto AUD) → 7 pillars."""
    project, doc = await _seed_project_with_doc(db_session)
    todas_validadoras = ["GP", "NEG", "CONF", "LGPD", "UX", "UI", "QA",
                         "ARQ", "DEV", "DBA", "SEG"]
    for tag in todas_validadoras:
        db_session.add(OCGIndividual(
            project_id=project.id,
            document_id=doc.id,
            persona_id=tag,
            persona_name=f"Persona {tag}",
            parecer={"score": 75},
            status="completed",
        ))
    await db_session.flush()

    svc = _make_updater_service(db_session)
    result = await svc._load_persona_scores(project.id)

    pillars = {k for k in result.keys() if k != "overall_score"}
    assert pillars == {
        "p1_business_score", "p2_rules_score", "p3_features_score",
        "p4_nfr_score", "p5_architecture_score", "p6_data_score",
        "p7_security_score",
    }, f"Pillars cobertos: {pillars}"
    assert result["overall_score"] == 75.0  # todos com score 75
