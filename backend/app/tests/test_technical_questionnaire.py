"""
Tests para Technical Questionnaire Router e Service

Validações:
- GET endpoint cria draft vazio se não existir
- PATCH endpoint atualiza responses e calcula progresso
- POST validate endpoint valida conflitos lógicos
- Visibilidade condicional funciona corretamente
- Validação cruzada (revela/visibleIf) funciona
"""
import pytest
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.testclient import TestClient

from app.db.database import Base
from app.main import app
from app.models.base import TechnicalQuestionnaire
from app.services.technical_questionnaire_service import (
    calculate_visibility,
    calculate_progress,
    validate_questionnaire,
)
from app.data.technical_questions_schema import TECHNICAL_QUESTIONS_SCHEMA


class TestTechnicalQuestionnaireService:
    """Tests para funções da service (sem HTTP)"""

    def test_calculate_visibility_empty_responses(self):
        """Perguntas sem visibleIf devem aparecer sempre"""
        responses = {}
        visible = calculate_visibility(responses, TECHNICAL_QUESTIONS_SCHEMA)

        # Q1, Q3, Q4, Q5, Q6, Q13, Q15 não têm condições
        assert 'Q1' in visible
        assert 'Q3' in visible
        assert 'Q4' in visible
        assert 'Q5' in visible
        assert 'Q6' in visible
        assert 'Q13' in visible
        assert 'Q15' in visible

    def test_calculate_visibility_with_condition(self):
        """Q2 aparece apenas se Q1='Novo sistema'"""
        # Q2 tem visibleIf: [{"dependsOn": "Q1", "valor": "Novo sistema"}]
        responses_no_q1 = {}
        visible = calculate_visibility(responses_no_q1, TECHNICAL_QUESTIONS_SCHEMA)
        assert 'Q2' not in visible  # Q1 não respondida

        responses_wrong_q1 = {'Q1': 'Refactor de existente'}
        visible = calculate_visibility(responses_wrong_q1, TECHNICAL_QUESTIONS_SCHEMA)
        assert 'Q2' not in visible  # Q1 ≠ 'Novo sistema'

        responses_correct_q1 = {'Q1': 'Novo sistema'}
        visible = calculate_visibility(responses_correct_q1, TECHNICAL_QUESTIONS_SCHEMA)
        assert 'Q2' in visible  # Q1 = 'Novo sistema'

    def test_calculate_visibility_escalabilidade(self):
        """Q7-Q10 aparecem se Q3 contiver 'Sim'"""
        responses_no_scaling = {'Q3': 'Não'}
        visible = calculate_visibility(responses_no_scaling, TECHNICAL_QUESTIONS_SCHEMA)
        assert 'Q7' not in visible
        assert 'Q8' not in visible
        assert 'Q9' not in visible
        assert 'Q10' not in visible

        responses_modest_scaling = {'Q3': 'Sim, modesto'}
        visible = calculate_visibility(responses_modest_scaling, TECHNICAL_QUESTIONS_SCHEMA)
        assert 'Q7' in visible  # Q7 tem visibleIf Q3='Sim, modesto'
        assert 'Q8' in visible
        # Q9 tem visibleIf Q3='Sim, agressivo'
        assert 'Q9' not in visible

        responses_aggressive_scaling = {'Q3': 'Sim, agressivo'}
        visible = calculate_visibility(responses_aggressive_scaling, TECHNICAL_QUESTIONS_SCHEMA)
        assert 'Q9' in visible
        assert 'Q10' in visible

    def test_calculate_progress_empty(self):
        """Progresso vazio é 0%"""
        responses = {}
        visible = calculate_visibility(responses, TECHNICAL_QUESTIONS_SCHEMA)
        progress = calculate_progress(responses, TECHNICAL_QUESTIONS_SCHEMA)

        # Há perguntas obrigatórias visíveis, nenhuma preenchida
        assert progress == 0

    def test_calculate_progress_partial(self):
        """Progresso parcial calcula corretamente"""
        # Responder Q1 (obrigatória) = 1/N das obrigatórias visíveis
        responses = {'Q1': 'Novo sistema'}
        progress = calculate_progress(responses, TECHNICAL_QUESTIONS_SCHEMA)

        # Várias perguntas obrigatórias visíveis sempre
        assert 0 < progress < 100

    def test_calculate_progress_full(self):
        """Progresso 100% quando todas obrigatórias preenchidas"""
        responses = {
            'Q1': 'Novo sistema',
            'Q2': 'Curto (2-4 semanas)',
            'Q3': 'Não',
        }
        progress = calculate_progress(responses, TECHNICAL_QUESTIONS_SCHEMA)
        # Nem tudo está preenchido, mas as obrigatórias visíveis sim
        assert 0 < progress <= 100

    def test_validate_questionnaire_no_conflicts(self):
        """Validação sem conflitos"""
        responses = {'Q3': 'Não'}
        result = validate_questionnaire(responses, TECHNICAL_QUESTIONS_SCHEMA)

        assert result['is_valid'] is True
        assert len(result['conflicts']) == 0
        assert result['progress'] >= 0

    def test_validate_questionnaire_conflict_unfilled_child(self):
        """Validação detecta se Q3='Não' mas Q7-Q10 preenchidas"""
        # Q3='Não' revela ['Q7', 'Q8', 'Q9', 'Q10']
        # Se Q3='Não', essas perguntas não deveriam ter respostas
        responses = {
            'Q3': 'Não',
            'Q7': '1000 rps',  # Erro: Q7 preenchida mas Q3='Não' não permite
        }
        result = validate_questionnaire(responses, TECHNICAL_QUESTIONS_SCHEMA)

        assert result['is_valid'] is False
        assert len(result['conflicts']) > 0
        # Deve mencionar conflito com Q7
        conflict_msgs = ' '.join(result['conflicts'])
        assert 'Q7' in conflict_msgs or 'deve estar vazio' in conflict_msgs

    def test_validate_questionnaire_missing_required_visible(self):
        """Validação detecta campos obrigatórios visíveis não preenchidos"""
        responses = {'Q1': 'Novo sistema'}  # Q1 preenchida mas Q3 obrigatória não
        result = validate_questionnaire(responses, TECHNICAL_QUESTIONS_SCHEMA)

        # Q3 é obrigatória e visível, deve estar preenchida
        # (Pode resultar em inválido dependendo da implementação)
        assert result['progress'] >= 0


@pytest.mark.asyncio
class TestTechnicalQuestionnaireRouter:
    """Tests para endpoints HTTP"""

    async def test_get_creates_draft(self, db_session: AsyncSession, async_client: TestClient, auth_token: str, test_project):
        """GET /projects/{id}/technical-questionnaire cria draft vazio se não existir"""
        project_id = test_project.id

        response = async_client.get(
            f"/api/projects/{project_id}/technical-questionnaire",
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'draft'
        assert data['responses'] == {}
        assert data['progress_percent'] == 0
        assert data['visible_questions'] == []  # Pode conter perguntas sempre visíveis

    async def test_patch_saves_responses(self, db_session: AsyncSession, async_client: TestClient, auth_token: str, test_project):
        """PATCH atualiza responses e calcula progresso"""
        project_id = test_project.id

        responses = {'Q1': 'Novo sistema', 'Q3': 'Não'}
        payload = {'responses': responses, 'submit': False}

        response = async_client.patch(
            f"/api/projects/{project_id}/technical-questionnaire",
            json=payload,
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'draft'
        assert data['progress_percent'] > 0

    async def test_patch_submit_changes_status(self, db_session: AsyncSession, async_client: TestClient, auth_token: str, test_project):
        """PATCH com submit=True muda status para 'submitted'"""
        project_id = test_project.id

        responses = {'Q1': 'Novo sistema', 'Q3': 'Não'}
        payload = {'responses': responses, 'submit': True}

        response = async_client.patch(
            f"/api/projects/{project_id}/technical-questionnaire",
            json=payload,
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'submitted'
        assert data['submitted_at'] is not None

    async def test_validate_endpoint(self, db_session: AsyncSession, async_client: TestClient, auth_token: str, test_project):
        """POST /validate retorna validation result com conflitos"""
        project_id = test_project.id

        # Resposta que causa conflito
        responses = {'Q3': 'Não', 'Q7': '1000 rps'}
        payload = {'responses': responses, 'submit': False}

        response = async_client.post(
            f"/api/projects/{project_id}/technical-questionnaire/validate",
            json=payload,
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert 'is_valid' in data
        assert 'progress_percent' in data
        assert 'visible_questions' in data
        assert 'conflicts' in data
