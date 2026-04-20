"""MVP 12 Fase 12.5 — Remover/redirecionar TODOs SMTP de fluxo deprecado.

Contrato §7 MVP 12 Fase 12.5:
- `POST /onboarding/{id}/step-3/team` retorna 410 Gone — fluxo legado
  sem consumer no frontend. Caminho canônico: `/api/v1/projects/{id}/
  invite`.
- TODOs "Criar OCG inicial" e "Criar pillar_configuration padrão" em
  `complete_step_5_stack` são substituídos por comentário canônico
  apontando que o OCG nasce do questionário (contrato §5).
- Endpoints permanecem para compat retroativa (dados antigos), mas o
  trabalho não avança silenciosamente.
"""
from uuid import uuid4

import httpx
import pytest

from app.main import app


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_setup_team_returns_410_gone_with_migration_hint():
    """Endpoint legado retorna 410 Gone apontando o caminho canônico."""
    onboarding_id = uuid4()
    payload = {
        "members": [
            {
                "email": "mvp12-f125@test.com",
                "name": "Test",
                "role": "dev",
                "responsibility": "backend",
            }
        ]
    }
    async with _client() as client:
        resp = await client.post(
            f"/api/v1/onboarding/{onboarding_id}/step-3/team",
            json=payload,
        )
    assert resp.status_code == 410, resp.text
    body = resp.json()
    detail = body.get("detail", "").lower()
    assert "deprecado" in detail
    assert "invite" in detail  # aponta para o endpoint canônico


def test_onboarding_service_todos_substituidos_por_comentario_canonico():
    """Os TODOs históricos em complete_step_5_stack não devem mais existir."""
    import inspect
    from app.services import onboarding_service

    src = inspect.getsource(onboarding_service.OnboardingService.complete_step_5_stack_selection)
    # Heurística: linha com `# TODO: Criar OGC inicial` ou
    # `# TODO: Criar pillar_configuration` ainda presente?
    assert "# TODO: Criar OGC inicial" not in src
    assert "# TODO: Criar pillar_configuration" not in src
    # E o comentário canônico de Fase 12.5 está presente
    assert "Fase 12.5" in src or "MVP 12" in src
