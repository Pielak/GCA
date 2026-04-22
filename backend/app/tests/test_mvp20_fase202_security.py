"""MVP 20 Fase 20.2 — testes de Security Adapters + service + P7.

Cobre:
- Migration 036 + modelo.
- Porta + registry.
- SonarAdapter: severity mapping, fetch com mock HTTP, auth, erros.
- SnykAdapter: severity mapping, fetch com mock HTTP, auth.
- GitleaksAdapter: modo consume report (JSON direto); modo local sem
  binário levanta ConfigError claro.
- Service: upsert idempotente, preserva accepted_risk em re-sync.
- Recálculo P7 determinístico: fórmula canônica + clamp + None quando vazio.
- Risk acceptance: GP + justification obrigatória.
"""
import json
from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from app.core.security import hash_password
from app.models.base import (
    Organization,
    Project,
    SecurityFinding,
    User,
)
from app.services.adapters.gitleaks_adapter import GitleaksAdapter
from app.services.adapters.snyk_adapter import SnykAdapter
from app.services.adapters.sonar_adapter import SonarAdapter
from app.services.ports.security_scanner_port import (
    FindingPayload,
    ScannerAPIError,
    ScannerAuthError,
    ScannerConfig,
    ScannerConfigError,
    _clear_scanner_registry_for_tests,
    get_scanner,
    register_scanner,
    registered_scanners,
)
from app.services.security_findings_service import (
    _upsert_finding,
    accept_risk,
    compute_p7_score_from_findings,
    count_open_findings_by_severity,
    list_findings,
    register_builtin_scanners,
    sync_scanner,
)


# ===========================================================================
# Helpers
# ===========================================================================


async def _make_user(db) -> User:
    uid = uuid4()
    user = User(
        id=uid, email=f"sec-{uid.hex[:6]}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="Sec Tester", is_active=True, is_admin=True,
        created_at=datetime.utcnow(),
    )
    db.add(user)
    await db.flush()
    return user


async def _make_project(db, user) -> Project:
    org = Organization(
        id=uuid4(), name=f"Org {uuid4().hex[:6]}",
        slug=f"org-sec-{uuid4().hex[:6]}", owner_id=user.id,
        is_active=True, created_at=datetime.utcnow(),
    )
    db.add(org)
    project = Project(
        id=uuid4(), organization_id=org.id, name="Sec Proj",
        slug=f"sec-{uuid4().hex[:6]}", description="t",
        deliverable_type="web_app", status="active",
        created_at=datetime.utcnow(),
    )
    db.add(project)
    await db.flush()
    return project


@pytest.fixture(autouse=True)
def _registry_setup():
    _clear_scanner_registry_for_tests()
    register_builtin_scanners()
    yield
    _clear_scanner_registry_for_tests()


# ===========================================================================
# Migration + modelo
# ===========================================================================


@pytest.mark.asyncio
async def test_migration_036_tabela_security_findings_existe(db_session):
    result = await db_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'security_findings'"
        )
    )
    cols = {r[0] for r in result.fetchall()}
    assert {
        "id", "project_id", "source_scanner", "external_id",
        "severity", "status", "title", "accepted_risk_justification",
    }.issubset(cols)


@pytest.mark.asyncio
async def test_migration_036_unique_idempotencia(db_session):
    result = await db_session.execute(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname = 'uniq_security_finding_scanner_external_id'"
        )
    )
    row = result.fetchone()
    assert row is not None
    assert "UNIQUE" in row[0].upper()


# ===========================================================================
# Registry
# ===========================================================================


def test_register_builtin_scanners_registra_3_adapters():
    _clear_scanner_registry_for_tests()
    register_builtin_scanners()
    assert set(registered_scanners()) == {"sonar", "snyk", "gitleaks"}


# ===========================================================================
# SonarAdapter
# ===========================================================================


def test_sonar_severity_mapping():
    adapter = SonarAdapter()
    assert adapter.normalize_severity("BLOCKER") == "critical"
    assert adapter.normalize_severity("CRITICAL") == "high"
    assert adapter.normalize_severity("MAJOR") == "medium"
    assert adapter.normalize_severity("MINOR") == "low"
    assert adapter.normalize_severity("INFO") == "info"
    assert adapter.normalize_severity("UNKNOWN") == "low"  # fallback


@pytest.mark.asyncio
async def test_sonar_fetch_findings_mock():
    def handler(request):
        return httpx.Response(200, json={
            "total": 2, "p": 1, "ps": 100,
            "issues": [
                {
                    "key": "ABC-1", "severity": "BLOCKER", "rule": "py:S1234",
                    "message": "SQL injection risk",
                    "component": "my-proj:src/db.py",
                    "textRange": {"startLine": 42, "endLine": 45},
                },
                {
                    "key": "ABC-2", "severity": "MINOR", "rule": "py:S5678",
                    "message": "Unused import",
                    "component": "my-proj:src/utils.py",
                    "textRange": {"startLine": 1, "endLine": 1},
                },
            ],
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = SonarAdapter(client=client)
    config = ScannerConfig(
        credentials={"token": "test"},
        base_url="https://sonar.example.com",
        project_key="my-proj",
    )
    findings = await adapter.fetch_findings(config)
    assert len(findings) == 2
    assert findings[0].external_id == "ABC-1"
    assert findings[0].severity == "critical"
    assert findings[0].file_path == "src/db.py"
    assert findings[0].line_start == 42
    assert findings[1].severity == "low"


@pytest.mark.asyncio
async def test_sonar_401_levanta_auth_error():
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(401, json={})
    ))
    adapter = SonarAdapter(client=client)
    config = ScannerConfig(
        credentials={"token": "x"}, base_url="https://s", project_key="p",
    )
    with pytest.raises(ScannerAuthError):
        await adapter.fetch_findings(config)


@pytest.mark.asyncio
async def test_sonar_sem_token_levanta_config_error():
    adapter = SonarAdapter()
    config = ScannerConfig(
        credentials={}, base_url="https://s", project_key="p",
    )
    with pytest.raises(ScannerConfigError):
        await adapter.fetch_findings(config)


# ===========================================================================
# SnykAdapter
# ===========================================================================


def test_snyk_severity_mapping():
    adapter = SnykAdapter()
    assert adapter.normalize_severity("critical") == "critical"
    assert adapter.normalize_severity("high") == "high"
    assert adapter.normalize_severity("medium") == "medium"
    assert adapter.normalize_severity("low") == "low"
    assert adapter.normalize_severity("unknown") == "low"


@pytest.mark.asyncio
async def test_snyk_fetch_findings_mock():
    def handler(request):
        return httpx.Response(200, json={
            "data": [
                {
                    "id": "snyk-1",
                    "attributes": {
                        "title": "Prototype pollution",
                        "effective_severity_level": "high",
                        "key": "PROTO-123",
                        "description": "A vuln",
                        "status": "open",
                        "classes": [{"source": "CWE", "id": "CWE-1321"}],
                        "coordinates": [],
                    },
                },
                {
                    "id": "snyk-2",
                    "attributes": {
                        "title": "Resolved issue",
                        "effective_severity_level": "low",
                        "key": "FIX-1",
                        "status": "resolved",
                        "classes": [],
                        "coordinates": [],
                    },
                },
            ],
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = SnykAdapter(client=client)
    config = ScannerConfig(
        credentials={"api_token": "t"},
        base_url="https://api.snyk.io",
        project_key="org-123",
    )
    findings = await adapter.fetch_findings(config)
    assert len(findings) == 2
    assert findings[0].external_id == "snyk-1"
    assert findings[0].severity == "high"
    assert findings[0].cwe_id == "CWE-1321"
    assert findings[1].status_hint == "fixed"


# ===========================================================================
# GitleaksAdapter
# ===========================================================================


def test_gitleaks_severity_override_private_key():
    adapter = GitleaksAdapter()
    assert adapter.normalize_severity("private-key") == "critical"
    assert adapter.normalize_severity("aws-access-token") == "critical"
    assert adapter.normalize_severity("unknown-rule") == "high"  # fallback high


@pytest.mark.asyncio
async def test_gitleaks_modo_consume_report_dict():
    adapter = GitleaksAdapter()
    report = [
        {
            "RuleID": "aws-access-token",
            "Commit": "abc123",
            "File": "src/config.py",
            "StartLine": 10, "EndLine": 10,
            "Fingerprint": "fp-1",
            "Secret": "AKIAIOSFODNN7EXAMPLE",
        },
        {
            "RuleID": "generic-api-key",
            "Commit": "def456",
            "File": ".env",
            "StartLine": 3, "EndLine": 3,
            "Fingerprint": "fp-2",
        },
    ]
    config = ScannerConfig(
        credentials={}, base_url="", project_key="",
        extra={"report_json": report},
    )
    findings = await adapter.fetch_findings(config)
    assert len(findings) == 2
    assert findings[0].severity == "critical"  # aws-access-token
    assert findings[0].external_id == "fp-1"
    assert findings[0].cwe_id == "CWE-798"
    assert findings[1].severity == "high"  # generic-api-key


@pytest.mark.asyncio
async def test_gitleaks_modo_consume_report_string_json():
    adapter = GitleaksAdapter()
    report_str = json.dumps([
        {"RuleID": "slack-bot-token", "File": "f", "StartLine": 1,
         "Fingerprint": "fp-x"},
    ])
    config = ScannerConfig(
        credentials={}, base_url="", project_key="",
        extra={"report_json": report_str},
    )
    findings = await adapter.fetch_findings(config)
    assert len(findings) == 1
    assert findings[0].rule_id == "slack-bot-token"


@pytest.mark.asyncio
async def test_gitleaks_sem_config_levanta_config_error():
    adapter = GitleaksAdapter()
    config = ScannerConfig(credentials={}, base_url="", project_key="")
    with pytest.raises(ScannerConfigError):
        await adapter.fetch_findings(config)


@pytest.mark.asyncio
async def test_gitleaks_report_json_invalido_levanta_api_error():
    adapter = GitleaksAdapter()
    config = ScannerConfig(
        credentials={}, base_url="", project_key="",
        extra={"report_json": "{not-valid-json"},
    )
    with pytest.raises(ScannerAPIError):
        await adapter.fetch_findings(config)


# ===========================================================================
# Service — upsert idempotente
# ===========================================================================


@pytest.mark.asyncio
async def test_upsert_cria_finding_novo(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    payload = FindingPayload(
        external_id="F-1", severity="high",
        title="SQLi risk", description="d",
        file_path="src/x.py", line_start=10,
        cwe_id="CWE-89", rule_id="py:S1234",
    )
    finding = await _upsert_finding(db_session, project.id, "sonar", payload)
    assert finding.id is not None
    assert finding.status == "open"
    assert finding.first_seen_at == finding.last_seen_at


@pytest.mark.asyncio
async def test_upsert_atualiza_last_seen_at_em_re_sync(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    p1 = FindingPayload(external_id="F-2", severity="high", title="v1")
    first = await _upsert_finding(db_session, project.id, "sonar", p1)
    first_seen = first.first_seen_at

    p2 = FindingPayload(external_id="F-2", severity="high", title="v1-updated")
    second = await _upsert_finding(db_session, project.id, "sonar", p2)

    assert first.id == second.id
    assert second.first_seen_at == first_seen  # preserva origem
    assert second.last_seen_at >= first_seen  # re-sync atualizou


@pytest.mark.asyncio
async def test_upsert_transiciona_open_para_fixed_quando_scanner_reporta(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    p1 = FindingPayload(external_id="F-3", severity="low", title="x")
    first = await _upsert_finding(db_session, project.id, "sonar", p1)
    assert first.status == "open"

    p2 = FindingPayload(external_id="F-3", severity="low", title="x",
                         status_hint="fixed")
    second = await _upsert_finding(db_session, project.id, "sonar", p2)
    assert second.status == "fixed"
    assert second.fixed_at is not None


@pytest.mark.asyncio
async def test_upsert_preserva_accepted_risk_em_re_sync(db_session):
    """Se GP aceitou risco, scanner re-reportar NÃO reverte pra open."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    p1 = FindingPayload(external_id="F-4", severity="medium", title="x")
    finding = await _upsert_finding(db_session, project.id, "sonar", p1)

    # GP aceita o risco.
    await accept_risk(
        db_session, finding.id,
        project_id=project.id, gp_user_id=user.id,
        justification="Não aplicável no contexto deste projeto — mitigação em load balancer.",
    )

    # Scanner re-reporta.
    p2 = FindingPayload(external_id="F-4", severity="medium", title="x")
    after_resync = await _upsert_finding(db_session, project.id, "sonar", p2)

    assert after_resync.status == "accepted_risk"  # preservado


# ===========================================================================
# sync_scanner (integração adapter + service)
# ===========================================================================


@pytest.mark.asyncio
async def test_sync_scanner_com_mock_sonar(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    # Registra Sonar com HTTP mock — substitui adapter registrado.
    def handler(request):
        return httpx.Response(200, json={
            "total": 1, "issues": [
                {"key": "K1", "severity": "MAJOR", "rule": "r",
                 "message": "t", "component": "p:file.py",
                 "textRange": {"startLine": 1, "endLine": 1}},
            ],
        })
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    _clear_scanner_registry_for_tests()
    register_scanner(SonarAdapter(client=client))

    config = ScannerConfig(
        credentials={"token": "t"}, base_url="https://s",
        project_key="p",
    )
    summary = await sync_scanner(db_session, project.id, "sonar", config)
    assert summary["total_fetched"] == 1
    assert summary["inserted"] == 1
    assert summary["updated"] == 0

    # Re-sync: insert=0, update=1.
    summary2 = await sync_scanner(db_session, project.id, "sonar", config)
    assert summary2["inserted"] == 0
    assert summary2["updated"] == 1


# ===========================================================================
# Recálculo P7
# ===========================================================================


@pytest.mark.asyncio
async def test_compute_p7_sem_findings_retorna_none(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    score = await compute_p7_score_from_findings(db_session, project.id)
    assert score is None  # caller usa heurística pré-20


@pytest.mark.asyncio
async def test_compute_p7_com_findings_aplica_formula_canonica(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    # 1 high (10) + 2 medium (3×2=6) + 3 low (1×3=3) = 19 penalty → 81
    payloads = [
        FindingPayload(external_id="H1", severity="high", title="x"),
        FindingPayload(external_id="M1", severity="medium", title="x"),
        FindingPayload(external_id="M2", severity="medium", title="x"),
        FindingPayload(external_id="L1", severity="low", title="x"),
        FindingPayload(external_id="L2", severity="low", title="x"),
        FindingPayload(external_id="L3", severity="low", title="x"),
    ]
    for p in payloads:
        await _upsert_finding(db_session, project.id, "sonar", p)

    score = await compute_p7_score_from_findings(db_session, project.id)
    assert score == 81


@pytest.mark.asyncio
async def test_compute_p7_clamp_em_zero(db_session):
    """Muitos criticals → score nunca fica negativo."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    for i in range(10):  # 10 × 25 = 250 penalty
        await _upsert_finding(
            db_session, project.id, "sonar",
            FindingPayload(external_id=f"C{i}", severity="critical", title="x"),
        )
    score = await compute_p7_score_from_findings(db_session, project.id)
    assert score == 0


@pytest.mark.asyncio
async def test_compute_p7_ignora_accepted_risk(db_session):
    """Findings aceitos não contam pro score."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    f = await _upsert_finding(
        db_session, project.id, "sonar",
        FindingPayload(external_id="C1", severity="critical", title="x"),
    )
    await accept_risk(
        db_session, f.id, project_id=project.id, gp_user_id=user.id,
        justification="Risco mitigado em camada externa documentada em ADR-042.",
    )

    score = await compute_p7_score_from_findings(db_session, project.id)
    assert score is None  # zero open → None (scanner não configurado lógica)


# ===========================================================================
# accept_risk
# ===========================================================================


@pytest.mark.asyncio
async def test_accept_risk_exige_justificativa_minima(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)

    f = await _upsert_finding(
        db_session, project.id, "sonar",
        FindingPayload(external_id="X-1", severity="medium", title="x"),
    )
    with pytest.raises(ValueError):
        await accept_risk(
            db_session, f.id, project_id=project.id, gp_user_id=user.id,
            justification="curto",  # < 10 chars
        )


@pytest.mark.asyncio
async def test_accept_risk_rejeita_finding_de_outro_projeto(db_session):
    """Compartimentalização §2.2 — finding do projeto B não pode ser aceito
    no contexto do projeto A."""
    user = await _make_user(db_session)
    proj_a = await _make_project(db_session, user)
    proj_b = await _make_project(db_session, user)

    f_b = await _upsert_finding(
        db_session, proj_b.id, "sonar",
        FindingPayload(external_id="B-1", severity="high", title="x"),
    )
    with pytest.raises(ValueError):
        await accept_risk(
            db_session, f_b.id, project_id=proj_a.id, gp_user_id=user.id,
            justification="justificativa suficiente aqui",
        )


# ===========================================================================
# count + list
# ===========================================================================


@pytest.mark.asyncio
async def test_list_findings_filtra_por_projeto(db_session):
    user = await _make_user(db_session)
    proj_a = await _make_project(db_session, user)
    proj_b = await _make_project(db_session, user)

    await _upsert_finding(
        db_session, proj_a.id, "sonar",
        FindingPayload(external_id="A-1", severity="high", title="x"),
    )
    await _upsert_finding(
        db_session, proj_b.id, "sonar",
        FindingPayload(external_id="B-1", severity="high", title="x"),
    )

    a_list = await list_findings(db_session, proj_a.id)
    b_list = await list_findings(db_session, proj_b.id)
    assert len(a_list) == 1 and a_list[0].external_id == "A-1"
    assert len(b_list) == 1 and b_list[0].external_id == "B-1"


@pytest.mark.asyncio
async def test_count_open_findings_agrupado(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    for sev in ["high", "high", "low", "critical"]:
        await _upsert_finding(
            db_session, project.id, "sonar",
            FindingPayload(external_id=f"{sev}-{uuid4()}", severity=sev, title="x"),
        )
    counts = await count_open_findings_by_severity(db_session, project.id)
    assert counts["critical"] == 1
    assert counts["high"] == 2
    assert counts["low"] == 1
    assert counts["medium"] == 0
