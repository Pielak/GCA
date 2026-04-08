"""
Testes de Settings — Fase 0.4
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.routers.settings_router import SmtpSettingsRequest, LlmSettingsRequest, N8nSettingsRequest


class TestSettingsModels:
    def test_smtp_request_defaults(self):
        req = SmtpSettingsRequest(
            host="smtp.gmail.com", username="test", password="pass",
            from_email="test@test.com",
        )
        assert req.port == 587
        assert req.use_tls is True
        assert req.from_name == "GCA"

    def test_llm_request(self):
        req = LlmSettingsRequest(provider="anthropic", api_key="sk-test")
        assert req.model_preference is None

    def test_n8n_request(self):
        req = N8nSettingsRequest(webhook_url="http://localhost:5678/webhook")
        assert req.api_token is None
        assert req.workflow_id is None

    def test_llm_invalid_provider_caught_at_endpoint(self):
        # Pydantic aceita qualquer string, validação é no endpoint
        req = LlmSettingsRequest(provider="invalid", api_key="key")
        assert req.provider == "invalid"
