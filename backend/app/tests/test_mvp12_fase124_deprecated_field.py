"""MVP 12 Fase 12.4 — Deprecar `ProjectRequest.initial_password_hash`.

Contrato §7 MVP 12 Fase 12.4:
- Coluna marcada como deprecada no modelo (comentário).
- Escritas removidas em `admin_service.approve_project_request` e
  `onboarding_service.approve_project_request`.
- Coluna ainda existe no DB (backward-compat — remoção física em V2
  via MVP 7 contrato de release destrutiva).
"""
import pytest


def test_column_exists_but_has_deprecated_marker_in_docstring():
    """Coluna permanece no modelo; docstring canônico documenta status."""
    import inspect
    from app.models.onboarding import ProjectRequest

    src = inspect.getsource(ProjectRequest)
    assert "initial_password_hash" in src
    assert "deprecated" in src.lower() or "DEPRECADA" in src


def test_admin_service_no_longer_writes_initial_password_hash():
    """Busca no código-fonte confirma remoção da escrita."""
    import inspect
    from app.services import admin_service

    src = inspect.getsource(admin_service)
    # Não deve haver atribuição ativa (apenas comentário histórico
    # com `request.initial_password_hash =` é aceitável em comentários
    # dentro da função, mas a nossa remoção deixou o campo fora).
    # Heurística: uma linha sem # prefix que contenha `initial_password_hash = hash_password`
    lines = src.splitlines()
    active_writes = [
        ln for ln in lines
        if "initial_password_hash = hash_password" in ln and not ln.strip().startswith("#")
    ]
    assert active_writes == [], f"Escrita ativa encontrada: {active_writes}"


def test_onboarding_service_no_longer_writes_initial_password_hash():
    import inspect
    from app.services import onboarding_service

    src = inspect.getsource(onboarding_service)
    lines = src.splitlines()
    active_writes = [
        ln for ln in lines
        if "initial_password_hash = hash_password" in ln and not ln.strip().startswith("#")
    ]
    assert active_writes == [], f"Escrita ativa encontrada: {active_writes}"
