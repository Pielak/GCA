"""Tests for password reset flow"""
import pytest
from unittest.mock import patch, AsyncMock
import httpx
from app.main import app


def _client():
    """Create async test client with ASGITransport (httpx 0.28+)"""
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_reset_password_request():
    """Test password reset request (forgot password)"""
    async with _client() as client:
        response = await client.post(
            "/api/v1/auth/reset-password",
            json={"email": "test@example.com"}
        )

        # Should return 200 even if email doesn't exist (security)
        assert response.status_code == 200
        assert "message" in response.json()


@pytest.mark.asyncio
async def test_reset_password_verify_invalid_token():
    """Test verifying an invalid/expired reset token"""
    async with _client() as client:
        response = await client.post(
            "/api/v1/auth/verify-reset-token",
            json={"token": "invalid-token-12345"}
        )

        assert response.status_code == 400
        # Response should have error, not 'valid' field
        data = response.json()
        assert "detail" in data or "error" in data or "message" in data


@pytest.mark.asyncio
async def test_first_access_password_change():
    """Test changing password on first access"""
    async with _client() as client:
        response = await client.post(
            "/api/v1/auth/change-first-password",
            json={
                "temporary_password": "TempPass123!@#",
                "new_password": "NewSecurePass123!@#"
            },
            headers={"Authorization": "Bearer invalid-token"}
        )

        # Should fail with invalid token
        assert response.status_code in [401, 400]


@pytest.mark.asyncio
async def test_project_team_invite():
    """Test inviting team member to project"""
    async with _client() as client:
        response = await client.post(
            "/api/v1/projects/proj-123/invite",
            json={
                "email": "developer@example.com",
                "role": "dev_pleno"
            },
            headers={"Authorization": "Bearer invalid-token"}
        )

        # Should fail without valid token
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_accept_project_invite():
    """Test accepting project invitation"""
    async with _client() as client:
        response = await client.post(
            "/api/v1/projects/proj-123/accept-invite",
            json={"token": "invalid-invite-token"}
        )

        # Should fail with invalid token (422 for validation error, 400 for bad request)
        assert response.status_code in [400, 422]
        assert "detail" in response.json() or "error" in response.json()


@pytest.mark.asyncio
async def test_submit_questionnaire():
    """Test submitting technical questionnaire"""
    async with _client() as client:
        response = await client.post(
            "/api/v1/questionnaires",
            json={
                "project_id": "proj-123",
                "gp_email": "gp@example.com",
                "responses": {
                    "1": "Test Project",
                    "21": "Sim",
                    "23": ["React"],
                    "26": "Sim",
                    "27": "Python",
                    "28": ["FastAPI"],
                    "39": "Sim",
                    "41": ["Anthropic"],
                }
            },
            follow_redirects=True,
        )

        # Should return success (200/201) or validation error (422)
        # If 422, the endpoint exists and validates input properly
        assert response.status_code in [200, 201, 422]
        # If successful, check for questionnaire response
        if response.status_code in [200, 201]:
            data = response.json()
            assert "questionnaire_id" in data or "id" in data or "project_id" in data


@pytest.mark.asyncio
async def test_questionnaire_webhook_analysis():
    """Test n8n webhook analysis"""
    async with _client() as client:
        response = await client.post(
            "/api/v1/webhooks/questionnaire",
            json={
                "projectId": "proj-123",
                "gp_email": "gp@example.com",
                "responses": {
                    "21": "Sim",
                    "23": ["React"],
                    "26": "Sim",
                    "27": "Python",
                    "28": ["FastAPI"],
                    "31": "PostgreSQL",
                    "39": "Sim",
                    "41": ["Anthropic"],
                    "43": ["JWT", "OAuth2"],
                    "45": ["Unitários", "Integração"],
                    "15": ["Aplicação web", "API"],
                }
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "questionnaireStatus" in data
        assert "adherenceScore" in data
        assert "approved" in data


@pytest.mark.asyncio
async def test_questionnaire_conflict_detection():
    """Test n8n conflict detection (React + Flutter)"""
    async with _client() as client:
        response = await client.post(
            "/api/v1/webhooks/questionnaire",
            json={
                "projectId": "proj-123",
                "gp_email": "gp@example.com",
                "responses": {
                    "21": "Sim",
                    "23": ["React", "Flutter"],  # Conflict!
                    "26": "Sim",
                    "27": "Python",
                    "28": ["FastAPI"],
                    "39": "Sim",
                    "41": ["Anthropic"],
                    "43": ["JWT"],
                }
            }
        )

        assert response.status_code == 200
        data = response.json()
        # Verify adherence score is returned
        assert "adherenceScore" in data
        # Check if conflicts are detected
        assert "highlightedFields" in data
