"""
Tests for Initial Questionnaire Router
"""
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import InitialQuestionnaire


class TestInitialQuestionnaireRouter:
    """Test suite for initial questionnaire endpoints"""

    def test_get_initial_questionnaire_empty(
        self,
        async_client: TestClient,
        test_project,
        auth_headers,
    ):
        """Test retrieving non-existent questionnaire creates empty draft"""
        response = async_client.get(
            f"/api/v1/projects/{test_project.id}/initial-questionnaire",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert str(test_project.id) in data["project_id"]
        assert data["status"] == "draft"
        assert data["q1_name"] is None

    def test_auto_save_questionnaire(
        self,
        async_client: TestClient,
        test_project,
        auth_headers,
    ):
        """Test auto-saving questionnaire as draft"""
        response = async_client.patch(
            f"/api/v1/projects/{test_project.id}/initial-questionnaire",
            json={
                "q1_name": "Test Project Name",
                "q1_objective": "Test Objective",
                "q2_type": "novo_sistema",
                "q3_users": "Users",
                "q3_volume": 100,
                "q4_months": 6,
                "submit": False,  # Auto-save, not submit
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "draft"

    def test_submit_questionnaire(
        self,
        async_client: TestClient,
        test_project,
        auth_headers,
    ):
        """Test submitting questionnaire"""
        response = async_client.patch(
            f"/api/v1/projects/{test_project.id}/initial-questionnaire",
            json={
                "q1_name": "Platform Name",
                "q1_objective": "Platform Objective",
                "q2_type": "novo_sistema",
                "q3_users": "Users",
                "q3_volume": 500,
                "q4_months": 6,
                "q5_flows": "Flow 1\nFlow 2",
                "q6_integrations": ["sms", "email"],
                "q7_frequency": "milhares_dia",
                "q8_reports": "Reports",
                "q9_rules": "Rules",
                "q10_performance": "importante_100_500ms",
                "q11_uptime": "99.5",
                "q12_sensitive_data": ["dados_pessoais"],
                "q13_scalability": "modesto",
                "q14_compliance": ["lgpd"],
                "q15_longevity": "medio_prazo",
                "q16_stack": "Python/FastAPI",
                "q17_existing_infra": "AWS",
                "q18_constraints": "None",
                "q19_gca_expectations": ["codigo_completo"],
                "q20_risks": "No risks",
                "submit": True,  # Submit, not just draft
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "submitted"
        assert data["submitted_at"] is not None
        assert data["submitted_by"] is not None

    def test_questionnaire_with_images(
        self,
        async_client: TestClient,
        test_project,
        auth_headers,
    ):
        """Test saving questionnaire with image attachments"""
        response = async_client.patch(
            f"/api/v1/projects/{test_project.id}/initial-questionnaire",
            json={
                "q1_name": "Project with Images",
                "question_images": {
                    "q1": ["https://example.com/image1.png"],
                    "q5": ["https://example.com/image2.jpg"],
                },
                "submit": False,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200

        # Retrieve and verify images
        response = async_client.get(
            f"/api/v1/projects/{test_project.id}/initial-questionnaire",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["question_images"]["q1"] == ["https://example.com/image1.png"]

    def test_questionnaire_jsonb_fields(
        self,
        async_client: TestClient,
        test_project,
        auth_headers,
    ):
        """Test saving JSONB arrays (checklists)"""
        response = async_client.patch(
            f"/api/v1/projects/{test_project.id}/initial-questionnaire",
            json={
                "q6_integrations": ["sms", "google_calendar", "slack"],
                "q12_sensitive_data": ["dados_pessoais", "dados_saude"],
                "q14_compliance": ["lgpd", "gdpr"],
                "q19_gca_expectations": ["codigo_completo", "documentacao"],
                "submit": False,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200

        # Retrieve and verify JSONB fields
        response = async_client.get(
            f"/api/v1/projects/{test_project.id}/initial-questionnaire",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["q6_integrations"] == ["sms", "google_calendar", "slack"]
        assert data["q12_sensitive_data"] == ["dados_pessoais", "dados_saude"]
        assert data["q14_compliance"] == ["lgpd", "gdpr"]
        assert data["q19_gca_expectations"] == ["codigo_completo", "documentacao"]
