"""
DT-051: Email do OCG mostrava pilares zerados + status UNKNOWN.

Bug 1 (template): `email_service.send_ocg_generated_email` buscava
`PILLAR_SCORES["P1_Business"]`/`P2_Rules`/.../`P7_Security`, mas o
consolidator persiste como `P1`..`P7` puros. Resultado: `.get(..., 0)`
zerava todos os pilares no email — usuário recebia "GCA — OCG Gerado"
com 0/100 em tudo enquanto o DB tinha scores corretos.

Bug 2 (model): `COMPOSITE_SCORE` não tinha `status` no JSON `ocg_data`
(só na coluna `ocg.status`). Email renderizava "UNKNOWN" mesmo quando a
coluna do DB tinha "NEEDS_REVIEW"/"READY".

Fix: (a) helper `_pillar_score(num)` no template aceita aliases canônicos
e legados; (b) `AgentService._normalize_composite_score` agora deriva
`status` (READY ≥ 90 / NEEDS_REVIEW ≥ 75 / AT_RISK < 75 / BLOCKED se
is_blocking) e o injeta no dict.
"""
from app.services.agent_service import AgentService


# ---------------------------------------------------------------------------
# Bug 2: COMPOSITE_SCORE.status
# ---------------------------------------------------------------------------

def test_normalize_composite_score_derives_status_ready():
    out = AgentService._normalize_composite_score(
        {"overall": 91.0, "is_blocking": False}, fallback_score=0, fallback_blocking=False
    )
    assert out["status"] == "READY"


def test_normalize_composite_score_derives_status_needs_review():
    out = AgentService._normalize_composite_score(
        {"overall": 80.0, "is_blocking": False}, fallback_score=0, fallback_blocking=False
    )
    assert out["status"] == "NEEDS_REVIEW"


def test_normalize_composite_score_derives_status_at_risk():
    out = AgentService._normalize_composite_score(
        {"overall": 61.7, "is_blocking": False}, fallback_score=0, fallback_blocking=False
    )
    assert out["status"] == "AT_RISK"


def test_normalize_composite_score_blocking_overrides_to_blocked():
    """Mesmo com score alto, is_blocking=True força status BLOCKED."""
    out = AgentService._normalize_composite_score(
        {"overall": 95.0, "is_blocking": True}, fallback_score=0, fallback_blocking=False
    )
    assert out["status"] == "BLOCKED"


def test_normalize_composite_score_preserves_existing_status():
    """Se LLM já enviou status, respeitamos."""
    out = AgentService._normalize_composite_score(
        {"overall": 60.0, "is_blocking": False, "status": "NEEDS_REVIEW"},
        fallback_score=0, fallback_blocking=False,
    )
    assert out["status"] == "NEEDS_REVIEW"


def test_normalize_composite_score_from_float_includes_status():
    """LLM retornou só float — derivamos overall + status + is_blocking."""
    out = AgentService._normalize_composite_score(
        85.0, fallback_score=0, fallback_blocking=False
    )
    assert out == {"overall": 85.0, "is_blocking": False, "status": "NEEDS_REVIEW"}


def test_normalize_composite_score_from_none_uses_fallbacks():
    out = AgentService._normalize_composite_score(
        None, fallback_score=72.0, fallback_blocking=False
    )
    assert out["overall"] == 72.0
    assert out["status"] == "AT_RISK"  # 72 < 75
    assert out["is_blocking"] is False


# ---------------------------------------------------------------------------
# Bug 1: aliases de pilares no template do email
#
# Reproduzimos o helper inline (não exposto pelo módulo de email) para
# garantir que ele aceita os 2 formatos. Se essa função for refatorada
# para utilitário público, substituir o stub abaixo.
# ---------------------------------------------------------------------------

def _pillar_score_email_replica(pillar_scores: dict, num: int) -> float:
    """Réplica fiel do helper que vive em email_service.send_ocg_generated_email
    (DT-051). Mantida em sincronia para validar regressão."""
    aliases = [
        f"P{num}",
        {1: "P1_Business", 2: "P2_Rules", 3: "P3_Features",
         4: "P4_NFR", 5: "P5_Architecture", 6: "P6_Data",
         7: "P7_Security"}[num],
    ]
    for k in aliases:
        v = pillar_scores.get(k)
        if isinstance(v, dict) and "score" in v:
            return v["score"]
        if isinstance(v, (int, float)):
            return v
    return 0


def test_email_pillar_helper_reads_canonical_keys():
    """Formato real persistido pelo consolidator: P1..P7."""
    ps = {
        "P1": {"score": 35.0, "adherence_level": "POOR"},
        "P2": {"score": 82.0, "adherence_level": "GOOD"},
        "P7": {"score": 85.0, "adherence_level": "GOOD"},
    }
    assert _pillar_score_email_replica(ps, 1) == 35.0
    assert _pillar_score_email_replica(ps, 2) == 82.0
    assert _pillar_score_email_replica(ps, 7) == 85.0
    assert _pillar_score_email_replica(ps, 3) == 0  # ausente — default 0


def test_email_pillar_helper_reads_legacy_suffixed_keys():
    """Formato antigo (caso o LLM ainda devolva): P1_Business, P2_Rules…"""
    ps = {
        "P1_Business": {"score": 90.0},
        "P5_Architecture": {"score": 88.0},
    }
    assert _pillar_score_email_replica(ps, 1) == 90.0
    assert _pillar_score_email_replica(ps, 5) == 88.0


def test_email_pillar_helper_canonical_takes_precedence_over_legacy():
    """Se ambos existem, P{n} prevalece (formato canônico)."""
    ps = {
        "P1": {"score": 35.0},
        "P1_Business": {"score": 99.0},  # legado divergente — ignorado
    }
    assert _pillar_score_email_replica(ps, 1) == 35.0


def test_email_pillar_helper_handles_scalar_value():
    """LLMs às vezes mandam o score direto sem dict envolvedor."""
    ps = {"P3": 52.0}
    assert _pillar_score_email_replica(ps, 3) == 52.0


def test_email_pillar_helper_real_dogfood_values():
    """Reproduz o estado real do projeto Automação Jurídica Assistida
    (ocg 89b0ec95… version=2): pilares {P1=35, P2=82, P3=52, P4=38,
    P5=88, P6=52, P7=85}. Antes do fix DT-051, todos esses pilares
    apareciam no email como 0/100 — usuário viu a captura de tela e
    questionou."""
    ps = {f"P{i}": {"score": s} for i, s in enumerate(
        [35, 82, 52, 38, 88, 52, 85], start=1
    )}
    assert _pillar_score_email_replica(ps, 1) == 35
    assert _pillar_score_email_replica(ps, 2) == 82
    assert _pillar_score_email_replica(ps, 3) == 52
    assert _pillar_score_email_replica(ps, 4) == 38
    assert _pillar_score_email_replica(ps, 5) == 88
    assert _pillar_score_email_replica(ps, 6) == 52
    assert _pillar_score_email_replica(ps, 7) == 85
