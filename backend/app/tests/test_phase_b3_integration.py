"""Phase B.3 Integration Tests — Full Passada 1→2 flow with database persistence."""
import pytest
from uuid import uuid4
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import get_db, SessionLocal
from app.models.document_route_map import DocumentRouteMap
from app.models.auditor_output import AuditorOutput
from app.models.gatekeeper_persona_response import GatekeeperPersonaResponse
from app.models.human_answer import HumanAnswer
from app.schemas.chunk import Chunk
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.fixture
def db_session():
    """Get test database session."""
    db = SessionLocal()
    yield db
    # Cleanup
    db.query(GatekeeperPersonaResponse).delete()
    db.query(HumanAnswer).delete()
    db.query(AuditorOutput).delete()
    db.query(DocumentRouteMap).delete()
    db.commit()
    db.close()


@pytest.fixture
def test_client(db_session):
    """Get test client with override DB dependency."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def route_map_with_auditor_output(db_session):
    """Create a route_map with auditor_output for testing."""
    route_map_id = uuid4()

    # Create DocumentRouteMap
    route_map = DocumentRouteMap(
        id=route_map_id,
        project_id=uuid4(),
        ingestion_doc_id=str(uuid4()),
        passada=1,
    )
    db_session.add(route_map)
    db_session.flush()

    # Create chunks
    chunks = [
        {
            "id": "chunk_001",
            "heading_path": "/Requisitos/Escopo",
            "chunk_type": "section",
            "text": "O sistema deve ser um e-commerce com carrinho de compras",
            "first_sentence": "O sistema deve ser um e-commerce com carrinho de compras",
            "position": 0,
            "tags": ["GP", "ARQ"],
            "token_count": 20,
        },
        {
            "id": "chunk_002",
            "heading_path": "/Arquitetura/Stack",
            "chunk_type": "section",
            "text": "Stack: Node.js backend, React frontend, PostgreSQL database",
            "first_sentence": "Stack: Node.js backend, React frontend, PostgreSQL database",
            "position": 1,
            "tags": ["ARQ", "DBA", "DEV"],
            "token_count": 18,
        },
    ]

    # Create AuditorOutput
    auditor_output = AuditorOutput(
        id=uuid4(),
        route_map_id=route_map_id,
        summary="E-commerce com stack moderno",
        chunks=chunks,
        highlights={
            "GP": ["Escopo claro", "Timeline definida"],
            "ARQ": ["Stack apropriado"],
        },
        backlog_to_specialists=[],
    )
    db_session.add(auditor_output)
    db_session.commit()

    return route_map_id, route_map, auditor_output


class TestPhaseB3Integration:
    """Integration tests for full Passada 1→2 flow."""

    @pytest.mark.asyncio
    async def test_passada_1_api_endpoint(self, test_client, route_map_with_auditor_output):
        """Test POST /gatekeeper/passada-1 endpoint with database persistence."""
        route_map_id, _, _ = route_map_with_auditor_output

        # Mock the LLM client to avoid actual API calls
        with patch('app.routers.gatekeeper_passada.AnthropicLLMClient') as mock_llm_class:
            mock_llm = MagicMock()
            mock_llm_class.return_value = mock_llm

            # Mock the parallel evaluator
            with patch('app.routers.gatekeeper_passada.ParallelEvaluator') as mock_evaluator_class:
                from app.services.personas.base import PersonaScore, PersonaOutput

                # Create mock response for all 7 personas
                mock_response = {
                    "gp": PersonaOutput(
                        persona_tag="gp",
                        passada=1,
                        scores=PersonaScore(escopo=85, stack=72, dados=90, implementacao=80, testes=75),
                        approved=True,
                        tentative=True,
                        issues=[],
                        questions=[],
                        justification="Escopo claro e time preparado",
                        input_tokens=1200,
                        output_tokens=340,
                        elapsed_ms=2500,
                    ),
                    "arq": PersonaOutput(
                        persona_tag="arq",
                        passada=1,
                        scores=PersonaScore(escopo=80, stack=88, dados=75, implementacao=82, testes=80),
                        approved=True,
                        tentative=True,
                        issues=[],
                        questions=[],
                        justification="Stack apropriado",
                        input_tokens=1300,
                        output_tokens=360,
                        elapsed_ms=2400,
                    ),
                }

                # Add remaining personas
                for tag in ["dba", "dev", "qa", "ux", "ui"]:
                    mock_response[tag] = PersonaOutput(
                        persona_tag=tag,
                        passada=1,
                        scores=PersonaScore(escopo=82, stack=80, dados=85, implementacao=83, testes=81),
                        approved=True,
                        tentative=True,
                        issues=[],
                        questions=[],
                        justification=f"Análise de {tag}",
                        input_tokens=1100,
                        output_tokens=320,
                        elapsed_ms=2300,
                    )

                mock_evaluator = MagicMock()
                mock_evaluator.run_passada_1 = AsyncMock(return_value=mock_response)
                mock_evaluator_class.return_value = mock_evaluator

                # Call endpoint
                response = test_client.post(
                    "/gatekeeper/passada-1",
                    json={
                        "route_map_id": str(route_map_id),
                        "execute_now": True,
                    }
                )

                # Verify response
                assert response.status_code == 200
                data = response.json()
                assert data["route_map_id"] == str(route_map_id)
                assert "personas_board" in data
                assert data["personas_board"]["passada"] == 1
                assert data["personas_board"]["total_personas"] == 7
                assert data["personas_board"]["approved_count"] == 7
                assert data["total_questions"] == 0

    @pytest.mark.asyncio
    async def test_get_personas_board(self, test_client, db_session, route_map_with_auditor_output):
        """Test GET /gatekeeper/personas-board/{route_map_id} endpoint."""
        from app.services.personas.base import PersonaScore

        route_map_id, _, _ = route_map_with_auditor_output

        # Create mock responses and store in database
        for tag in ["gp", "arq", "dba", "dev", "qa", "ux", "ui"]:
            response = GatekeeperPersonaResponse(
                id=uuid4(),
                route_map_id=route_map_id,
                persona_tag=tag,
                passada=1,
                scores=PersonaScore(
                    escopo=80 + len(tag),
                    stack=82 + len(tag),
                    dados=85 + len(tag),
                    implementacao=83 + len(tag),
                    testes=81 + len(tag),
                ).__dict__,
                approved=True,
                tentative=True,
                issues=[],
                questions=[],
                justification=f"Análise de {tag}",
                input_tokens=1100,
                output_tokens=320,
                elapsed_ms=2300,
            )
            db_session.add(response)
        db_session.commit()

        # Call endpoint
        api_response = test_client.get(
            f"/gatekeeper/personas-board/{route_map_id}?passada=1"
        )

        # Verify response
        assert api_response.status_code == 200
        data = api_response.json()
        assert data["route_map_id"] == str(route_map_id)
        assert data["passada"] == 1
        assert data["total_personas"] == 7
        assert data["approved_count"] == 7
        assert "gp" in data["personas"]
        assert "arq" in data["personas"]
        assert "dba" in data["personas"]

    @pytest.mark.asyncio
    async def test_human_answers_storage(self, test_client, route_map_with_auditor_output, db_session):
        """Test POST /gatekeeper/human-answers endpoint with database persistence."""
        route_map_id, _, _ = route_map_with_auditor_output

        answers = [
            {
                "persona_tag": "gp",
                "question_id": "Q-001",
                "answer_text": "O volume esperado é 10K usuários/mês",
            },
            {
                "persona_tag": "arq",
                "question_id": "Q-002",
                "answer_text": "Escalabilidade horizontal com Kubernetes",
            },
        ]

        # Call endpoint
        response = test_client.post(
            "/gatekeeper/human-answers",
            json={
                "route_map_id": str(route_map_id),
                "human_answers": answers,
            }
        )

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["route_map_id"] == str(route_map_id)
        assert data["answers_stored"] == 2

        # Verify database persistence
        stored_answers = db_session.query(HumanAnswer).filter(
            HumanAnswer.route_map_id == route_map_id
        ).all()
        assert len(stored_answers) == 2
        assert stored_answers[0].persona_tag == "gp"
        assert stored_answers[0].answer_text == "O volume esperado é 10K usuários/mês"
        assert stored_answers[1].persona_tag == "arq"

    @pytest.mark.asyncio
    async def test_passada_1_with_questions(self, test_client, route_map_with_auditor_output):
        """Test Passada 1 that generates questions for human validator."""
        from app.services.personas.base import PersonaScore, PersonaQuestion, PersonaOutput

        route_map_id, _, _ = route_map_with_auditor_output

        with patch('app.routers.gatekeeper_passada.AnthropicLLMClient') as mock_llm_class:
            mock_llm = MagicMock()
            mock_llm_class.return_value = mock_llm

            with patch('app.routers.gatekeeper_passada.ParallelEvaluator') as mock_evaluator_class:
                # Create response with questions
                question1 = PersonaQuestion(
                    id="Q-001",
                    question_text="Qual é o volume esperado de usuários?",
                    rationale="Para dimensionar infraestrutura",
                    answer_type="numeric",
                    severity="critical",
                    chunk_refs=["chunk_001"],
                )

                mock_response = {
                    "gp": PersonaOutput(
                        persona_tag="gp",
                        passada=1,
                        scores=PersonaScore(escopo=70, stack=72, dados=90, implementacao=80, testes=75),
                        approved=False,
                        tentative=True,
                        issues=[],
                        questions=[question1],
                        justification="Faltam detalhes de escala",
                        input_tokens=1200,
                        output_tokens=340,
                        elapsed_ms=2500,
                    ),
                }

                # Add remaining personas without questions
                for tag in ["arq", "dba", "dev", "qa", "ux", "ui"]:
                    mock_response[tag] = PersonaOutput(
                        persona_tag=tag,
                        passada=1,
                        scores=PersonaScore(escopo=80, stack=80, dados=85, implementacao=83, testes=81),
                        approved=True,
                        tentative=True,
                        issues=[],
                        questions=[],
                        justification=f"OK para {tag}",
                        input_tokens=1100,
                        output_tokens=320,
                        elapsed_ms=2300,
                    )

                mock_evaluator = MagicMock()
                mock_evaluator.run_passada_1 = AsyncMock(return_value=mock_response)
                mock_evaluator_class.return_value = mock_evaluator

                # Call endpoint
                response = test_client.post(
                    "/gatekeeper/passada-1",
                    json={
                        "route_map_id": str(route_map_id),
                        "execute_now": True,
                    }
                )

                # Verify response
                assert response.status_code == 200
                data = response.json()
                assert data["total_questions"] == 1
                assert len(data["questions_to_answer"]) == 1
                assert data["questions_to_answer"][0]["question_text"] == "Qual é o volume esperado de usuários?"
                assert data["questions_to_answer"][0]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_error_handling_missing_route_map(self, test_client):
        """Test error handling when route_map doesn't exist."""
        fake_uuid = uuid4()

        response = test_client.post(
            "/gatekeeper/passada-1",
            json={
                "route_map_id": str(fake_uuid),
                "execute_now": True,
            }
        )

        assert response.status_code == 404
        assert "DocumentRouteMap não encontrado" in response.text

    @pytest.mark.asyncio
    async def test_error_handling_missing_auditor_output(self, test_client, db_session):
        """Test error handling when auditor_output doesn't exist."""
        # Create route_map but no auditor_output
        route_map_id = uuid4()
        route_map = DocumentRouteMap(
            id=route_map_id,
            project_id=uuid4(),
            ingestion_doc_id=str(uuid4()),
            passada=1,
        )
        db_session.add(route_map)
        db_session.commit()

        response = test_client.post(
            "/gatekeeper/passada-1",
            json={
                "route_map_id": str(route_map_id),
                "execute_now": True,
            }
        )

        assert response.status_code == 404
        assert "AuditorOutput não encontrado" in response.text

    @pytest.mark.asyncio
    async def test_error_handling_missing_personas_board(self, test_client):
        """Test error handling when trying to fetch non-existent board."""
        fake_uuid = uuid4()

        response = test_client.get(
            f"/gatekeeper/personas-board/{fake_uuid}?passada=1"
        )

        assert response.status_code == 404
        assert "Nenhuma resposta de persona encontrada" in response.text

    @pytest.mark.asyncio
    async def test_full_passada_1_to_2_flow(self, test_client, route_map_with_auditor_output, db_session):
        """Test complete Passada 1 → answer questions → Passada 2 flow."""
        from app.services.personas.base import PersonaScore, PersonaOutput

        route_map_id, _, _ = route_map_with_auditor_output

        with patch('app.routers.gatekeeper_passada.AnthropicLLMClient') as mock_llm_class:
            mock_llm = MagicMock()
            mock_llm_class.return_value = mock_llm

            with patch('app.routers.gatekeeper_passada.ParallelEvaluator') as mock_evaluator_class:
                # Mock Passada 1 response
                passada1_response = {}
                for tag in ["gp", "arq", "dba", "dev", "qa", "ux", "ui"]:
                    passada1_response[tag] = PersonaOutput(
                        persona_tag=tag,
                        passada=1,
                        scores=PersonaScore(escopo=80, stack=82, dados=85, implementacao=83, testes=81),
                        approved=tag != "gp",  # GP not approved to force questions
                        tentative=True,
                        issues=[],
                        questions=[],
                        justification=f"Análise inicial de {tag}",
                        input_tokens=1100,
                        output_tokens=320,
                        elapsed_ms=2300,
                    )

                # Mock Passada 2 response (all approved)
                passada2_response = {}
                for tag in ["gp", "arq", "dba", "dev", "qa", "ux", "ui"]:
                    passada2_response[tag] = PersonaOutput(
                        persona_tag=tag,
                        passada=2,
                        scores=PersonaScore(escopo=85, stack=87, dados=90, implementacao=88, testes=86),
                        approved=True,
                        tentative=False,
                        issues=[],
                        questions=[],
                        justification=f"Análise final com feedback humano de {tag}",
                        input_tokens=1300,
                        output_tokens=380,
                        elapsed_ms=2600,
                    )

                mock_evaluator = MagicMock()
                mock_evaluator.run_passada_1 = AsyncMock(return_value=passada1_response)
                mock_evaluator.run_passada_2 = AsyncMock(return_value=passada2_response)
                mock_evaluator_class.return_value = mock_evaluator

                # Step 1: Run Passada 1
                p1_response = test_client.post(
                    "/gatekeeper/passada-1",
                    json={"route_map_id": str(route_map_id), "execute_now": True}
                )
                assert p1_response.status_code == 200

                # Step 2: Store human answers
                answers_response = test_client.post(
                    "/gatekeeper/human-answers",
                    json={
                        "route_map_id": str(route_map_id),
                        "human_answers": [
                            {
                                "persona_tag": "gp",
                                "question_id": "Q-001",
                                "answer_text": "Volume: 10K usuários/mês",
                            }
                        ],
                    }
                )
                assert answers_response.status_code == 200

                # Step 3: Run Passada 2
                p2_response = test_client.post(
                    "/gatekeeper/passada-2",
                    json={
                        "route_map_id": str(route_map_id),
                        "human_answers": [
                            {
                                "persona_tag": "gp",
                                "question_id": "Q-001",
                                "answer_text": "Volume: 10K usuários/mês",
                            }
                        ],
                    }
                )
                assert p2_response.status_code == 200
                p2_data = p2_response.json()
                assert p2_data["all_approved"] is True
                assert p2_data["personas_board"]["passada"] == 2
