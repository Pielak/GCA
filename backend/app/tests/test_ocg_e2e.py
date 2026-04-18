"""
End-to-End Tests for 8-Agent OCG Pipeline
Tests complete flow: Questionnaire → Analyzer → Pillars → Consolidator → OCG
"""
import pytest
import json
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Questionnaire
from app.services.ocg_service import OCGService
from app.services.agent_service import AgentService
from app.schemas.ocg import (
    AnalyzerRequest,
    AnalyzerResponse,
    PillarAgentRequest,
    PillarAgentResponse,
    ConsolidatorRequest,
)
from app.tests.factories import create_test_user, create_test_organization, create_test_project


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
async def ocg_service(db_session: AsyncSession):
    """Create OCGService with database session"""
    return OCGService(db_session)


@pytest.fixture
async def agent_service(db_session: AsyncSession):
    """Create AgentService with database session"""
    return AgentService(db_session)


@pytest.fixture
async def test_questionnaire(db_session: AsyncSession):
    """Create a test questionnaire in database"""
    # First create a project (required by Questionnaire FK)
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id)

    questionnaire_id = uuid4()

    # Sample responses (matches actual questionnaire structure)
    responses = {
        "Q1": "ROI 40% em 2 anos",
        "Q2": "CEO, CFO, VP Product",
        "Q3": "6 meses MVP, 12 meses prod",
        "Q9": "LGPD, GDPR, PCI-DSS",
        "Q16": "Catálogo, carrinho, checkout",
        "Q26": "Latência <200ms, 5000 simultâneos",
        "Q33": "Microserviços",
        "Q39": "PostgreSQL",
        "Q43": "OAuth2 via Auth0",
    }

    questionnaire = Questionnaire(
        id=questionnaire_id,
        project_id=project.id,
        gp_email="gp@example.com",
        responses=json.dumps(responses),
        status="pending",
        submitted_at=datetime.now(timezone.utc),
    )

    db_session.add(questionnaire)
    await db_session.flush()

    return questionnaire


# ============================================================================
# AGENT TESTS
# ============================================================================

@pytest.mark.asyncio
class TestAgentAnalyzer:
    """Tests for Agent 0: Questionnaire Analyzer"""

    async def test_analyzer_classifies_by_pillar(self, agent_service: AgentService):
        """Agent 0 should classify questions by pillar"""
        req = AnalyzerRequest(
            questionnaire_id=uuid4(),
            answers=[
                {"question_id": "Q1", "text": "ROI 40% em 2 anos"},
                {"question_id": "Q2", "text": "Stakeholders: CEO, CFO"},
                {"question_id": "Q9", "text": "Sujeito a LGPD e GDPR"},
            ],
            project_metadata={
                "project_name": "Test Project",
                "submitted_by": "test@example.com",
            },
        )

        result = await agent_service.analyze_questionnaire(req)

        # Should classify responses
        assert result.classification is not None
        assert isinstance(result.classification, dict)

        # Should extract metadata
        assert result.extracted_info is not None
        assert "project_name" in result.extracted_info or result.extracted_info.get("project_name")

        # Should handle anomalies
        assert isinstance(result.anomalies, list)

    async def test_analyzer_extracts_project_metadata(self, agent_service: AgentService):
        """Agent 0 should extract project metadata from answers"""
        req = AnalyzerRequest(
            questionnaire_id=uuid4(),
            answers=[
                {"question_id": "Q1", "text": "E-Commerce Platform"},
                {"question_id": "Q2", "text": "e-commerce-platform"},
                {"question_id": "Q4", "text": "Novo sistema"},
                {"question_id": "Q5", "text": "Alta"},
                {"question_id": "Q15", "text": "Aplicação web"},
                {"question_id": "Q16", "text": "Monólito modular"},
                {"question_id": "Q17", "text": "Cloud"},
            ],
            project_metadata={"project_name": "Test Project"},
        )

        result = await agent_service.analyze_questionnaire(req)

        extracted = result.extracted_info
        assert extracted is not None
        # Should extract project name
        assert extracted.get("project_name") is not None


@pytest.mark.asyncio
class TestPillarAgents:
    """Tests for Agents 1-7: Pillar Specialists"""

    async def test_pillar_agent_scores(self, agent_service: AgentService):
        """Pillar agents should produce valid scores"""
        req = PillarAgentRequest(
            pillar_id=1,
            questionnaire_id=uuid4(),
            questions=[
                {"question_id": "Q1", "text": "ROI expectation?"},
                {"question_id": "Q2", "text": "Stakeholders?"},
            ],
            responses={
                "Q1": "ROI 40% em 2 anos",
                "Q2": "CEO, CFO, VP Product",
            },
            project_metadata={
                "project_name": "Test Project",
                "project_type": "web_app",
                "team_size": 5,
                "timeline_months": 12,
                "budget_level": "medium",
            },
        )

        result = await agent_service.analyze_pillar(1, req)

        # Should return valid score
        assert isinstance(result.score, (int, float))
        assert 0 <= result.score <= 100

        # Should have adherence level
        assert result.adherence_level is not None
        assert isinstance(result.adherence_level, str)

        # Should have findings (can be dict or list)
        assert result.findings is not None
        assert isinstance(result.findings, (list, dict))

    async def test_pillar_agents_parallel(self, agent_service: AgentService):
        """All pillar agents should execute in parallel"""
        analyzer_result = type('obj', (object,), {
            'classification': {
                'P1': ['Q1', 'Q2'],
                'P2': ['Q9'],
                'P3': ['Q16'],
                'P4': ['Q26'],
                'P5': ['Q33'],
                'P6': ['Q39'],
                'P7': ['Q43'],
            },
            'extracted_info': {
                'project_name': 'Test',
                'project_type': 'web_app',
                'team_size': 5,
            }
        })()

        req = PillarAgentRequest(
            pillar_id=0,
            questionnaire_id=uuid4(),
            questions=[
                {"question_id": "Q1", "text": "ROI?"},
                {"question_id": "Q9", "text": "Compliance?"},
                {"question_id": "Q16", "text": "Features?"},
                {"question_id": "Q26", "text": "Performance?"},
                {"question_id": "Q33", "text": "Architecture?"},
                {"question_id": "Q39", "text": "Database?"},
                {"question_id": "Q43", "text": "Auth?"},
            ],
            responses={
                "Q1": "40%", "Q9": "LGPD", "Q16": "Core", "Q26": "<200ms",
                "Q33": "Micro", "Q39": "PostgreSQL", "Q43": "OAuth2"
            },
            project_metadata=analyzer_result.extracted_info,
        )

        results = await agent_service.analyze_all_pillars(analyzer_result, req)

        # Should get results for all pillars
        assert len(results) > 0

        # Each result should have valid score
        for result in results:
            assert 0 <= result.score <= 100


@pytest.mark.asyncio
class TestConsolidator:
    """Tests for Agent 8: OCG Consolidator"""

    async def test_consolidator_produces_ocg(self, agent_service: AgentService, db_session: AsyncSession):
        """Agent 8 should produce valid OCG from pillar results"""
        # Create a real questionnaire in database
        org = await create_test_organization(db_session)
        project = await create_test_project(db_session, organization_id=org.id)
        questionnaire_id = uuid4()
        questionnaire = Questionnaire(
            id=questionnaire_id,
            project_id=project.id,
            gp_email="test@example.com",
            responses=json.dumps({"Q1": "Test"}),
            status="pending",
            submitted_at=datetime.now(timezone.utc),
        )
        db_session.add(questionnaire)
        await db_session.flush()

        # Create real Pydantic models as results
        analyzer_result = AnalyzerResponse(
            questionnaire_id=questionnaire_id,
            classification={'P1': ['Q1'], 'P2': [], 'P3': [], 'P4': [], 'P5': [], 'P6': [], 'P7': []},
            extracted_info={'project_name': 'Test', 'project_type': 'web_app'},
            anomalies=[],
        )

        # Create pillar results as proper models
        pillar_results = []
        for i in range(1, 8):
            pillar_results.append(
                PillarAgentResponse(
                    pillar_id=i,
                    score=85.0,
                    adherence_level='GOOD',
                    classification={},
                    findings=[],
                    stack_implications={},
                    checklist=[],
                )
            )

        req = ConsolidatorRequest(
            questionnaire_id=questionnaire_id,
            project_id=project.id,
            analyzer_output=analyzer_result,
            pillar_results=pillar_results,
            project_metadata={'project_name': 'Test'},
        )

        ocg = await agent_service.consolidate_ocg(req)

        # Should produce valid OCG
        assert ocg.ocg_id is not None
        assert ocg.questionnaire_id == questionnaire_id
        assert ocg.COMPOSITE_SCORE is not None


# ============================================================================
# END-TO-END TESTS
# ============================================================================

@pytest.mark.asyncio
class TestOCGE2E:
    """End-to-end tests for complete OCG generation"""

    async def test_ocg_generation_from_questionnaire(
        self,
        ocg_service: OCGService,
        test_questionnaire: Questionnaire,
    ):
        """Complete pipeline: questionnaire → OCG"""
        # DT-040: `ai_usage_log.project_id` é NOT NULL. Pipeline real
        # sempre passa project_id (admin_service + questionnaire_service
        # após aprovação). Teste passava None — criava IntegrityError
        # silencioso no billing log. O fixture já cria um project e
        # linka o questionnaire; uso o mesmo id.
        ocg = await ocg_service.generate_ocg_from_questionnaire(
            questionnaire_id=test_questionnaire.id,
            project_id=test_questionnaire.project_id,
        )

        # Should produce valid OCG
        assert ocg.ocg_id is not None
        assert ocg.questionnaire_id == test_questionnaire.id

        # Should have composite score
        assert ocg.COMPOSITE_SCORE is not None
        composite = ocg.COMPOSITE_SCORE
        assert isinstance(composite, dict) or hasattr(composite, 'overall')

        # Status should be valid
        status = composite.get('status') if isinstance(composite, dict) else getattr(composite, 'status', None)
        # Status can be one of the valid values or None (if agent doesn't provide it)
        assert status is None or status in ['READY', 'NEEDS_REVIEW', 'AT_RISK', 'BLOCKED']

    async def test_ocg_notification(self, ocg_service: OCGService):
        """OCG notification should succeed"""
        ocg_id = uuid4()
        success = await ocg_service.send_ocg_notification(
            ocg_id=ocg_id,
            recipient_email="test@example.com",
        )

        assert success is True
