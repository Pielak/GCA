"""MVP 14 Fase 14.2 — Auditoria do TODO em gatekeeper_service.

Contrato §7 MVP 14 Fase 14.2:
- Auditar `gatekeeper_service` TODO de create_task.
- Se código ativo, migrar para Celery.
- Se apenas comentário morto, remover e documentar estado real.

Resultado: TODO era comment sem código ativo. Removido.
Substituído por comentário canônico explicando que CodeGen
pós-approve é manual por design (fluxo canônico via POST /scaffold
ou /regenerate-file).
"""
import inspect


def test_gatekeeper_service_sem_todo_create_task():
    from app.services import gatekeeper_service
    src = inspect.getsource(gatekeeper_service)
    assert "TODO FASE 3" not in src
    assert "TODO" not in inspect.getsource(gatekeeper_service.GatekeeperService.approve_module) or \
        "asyncio.create_task" not in inspect.getsource(gatekeeper_service.GatekeeperService.approve_module)


def test_gatekeeper_service_sem_asyncio_create_task():
    from app.services import gatekeeper_service
    src = inspect.getsource(gatekeeper_service)
    active = [
        line for line in src.splitlines()
        if "asyncio.create_task" in line and not line.strip().startswith("#")
    ]
    assert active == [], f"create_task ativo em gatekeeper_service: {active}"


def test_approve_module_tem_comentario_canonico_14_2():
    """Garante que o comentário canônico está presente."""
    from app.services import gatekeeper_service
    src = inspect.getsource(gatekeeper_service.GatekeeperService.approve_module)
    assert "Fase 14.2" in src
    assert "CodeGen pós-approve" in src or "canônico" in src
