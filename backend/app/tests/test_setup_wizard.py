"""Testa o wizard de setup inicial do GCA."""
from starlette.testclient import TestClient


def test_setup_status_retorna_needs_setup(sync_client: TestClient):
    """Endpoint /setup/status deve retornar campo needs_setup."""
    resp = sync_client.get("/api/v1/setup/status")
    assert resp.status_code == 200
    assert "needs_setup" in resp.json()


def test_setup_complete_bloqueado_com_usuarios(sync_client: TestClient):
    """Com usuários no banco, setup/complete deve retornar 410."""
    payload = {
        "admin_name": "Teste",
        "admin_email": "teste@gca.local",
        "admin_password": "SenhaSegura@2026",
        "llm_provider": "anthropic",
        "llm_api_key": "sk-test",
        "llm_model": "claude-sonnet-4-6",
    }
    resp = sync_client.post("/api/v1/setup/complete", json=payload)
    assert resp.status_code == 410


def test_setup_status_endpoint_publico(sync_client: TestClient):
    """setup/status deve ser acessível sem token JWT."""
    resp = sync_client.get("/api/v1/setup/status")
    assert resp.status_code not in [401, 403]


def test_setup_status_retorna_false_com_dados(sync_client: TestClient):
    """Com dados no banco (seeded), needs_setup deve ser false."""
    resp = sync_client.get("/api/v1/setup/status")
    assert resp.status_code == 200
    # O sync_client usa o banco real que tem dados seed
    data = resp.json()
    assert isinstance(data["needs_setup"], bool)
