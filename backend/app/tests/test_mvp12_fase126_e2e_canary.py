"""MVP 12 Fase 12.6 — Canário real da lane E2E.

Contrato §7 MVP 12 Fase 12.6:
- `backend/scripts/seed_e2e.py` cria admin canônico + project UUID fixo
  + membership GP, idempotentemente.
- Lane e2e no CI roda o seed antes dos testes e perde `continue-on-error`.
- Este arquivo valida que o seed é idempotente e cria estado correto.
"""
import asyncio
import importlib
import os
import sys
from datetime import datetime
from uuid import UUID, uuid4

import pytest


# UUID canônico do projeto canário (deve bater com E2E_PROJECT_UUID
# default do script seed_e2e).
CANARY_PROJECT_UUID = UUID("00000000-0000-0000-0000-000000000001")
CANARY_ADMIN_EMAIL = "admin@gca.local"


def _run_seed(monkeypatch):
    """Executa a função seed() do script contra o DATABASE_URL corrente."""
    # O script resolve DATABASE_URL da env; passamos o TEST_DATABASE_URL
    # para não poluir prod.
    test_url = os.environ.get("TEST_DATABASE_URL")
    assert test_url, "TEST_DATABASE_URL é obrigatório para rodar o seed em teste"
    monkeypatch.setenv("DATABASE_URL", test_url)

    # Import dinâmico do script (não fica no sys.modules cached se env mudar)
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "scripts",
        "seed_e2e.py",
    )
    import importlib.util
    spec = importlib.util.spec_from_file_location("seed_e2e", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    asyncio.get_event_loop().run_until_complete(module.seed())


async def _cleanup_canary():
    """Remove os artefatos do canário entre testes."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Organization, Project, ProjectMember

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                ProjectMember.__table__.delete().where(ProjectMember.project_id == CANARY_PROJECT_UUID)
            )
            await session.execute(Project.__table__.delete().where(Project.id == CANARY_PROJECT_UUID))
            from sqlalchemy import select
            res = await session.execute(
                select(User).where(User.email == CANARY_ADMIN_EMAIL)
            )
            admin = res.scalar_one_or_none()
            if admin:
                await session.execute(
                    Organization.__table__.delete().where(Organization.owner_id == admin.id)
                )
                await session.execute(User.__table__.delete().where(User.id == admin.id))


@pytest.mark.asyncio
async def test_seed_creates_canary_state():
    """Executa o seed e valida que admin+project+membership existem."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Project, ProjectMember
    from sqlalchemy import select

    # Estado limpo antes
    await _cleanup_canary()

    try:
        # Rodar o seed
        test_url = os.environ["TEST_DATABASE_URL"]
        os.environ["DATABASE_URL"] = test_url
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "scripts",
            "seed_e2e.py",
        )
        import importlib.util
        spec = importlib.util.spec_from_file_location("seed_e2e_module", script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        await module.seed()

        # Valida estado
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(User).where(User.email == CANARY_ADMIN_EMAIL))
            admin = res.scalar_one_or_none()
            assert admin is not None
            assert admin.is_admin is True
            assert admin.is_active is True
            assert admin.first_access_completed is True

            res = await session.execute(select(Project).where(Project.id == CANARY_PROJECT_UUID))
            proj = res.scalar_one_or_none()
            assert proj is not None
            assert proj.slug == "e2e-canary"
            assert proj.status == "active"

            res = await session.execute(
                select(ProjectMember).where(
                    (ProjectMember.project_id == CANARY_PROJECT_UUID)
                    & (ProjectMember.user_id == admin.id)
                )
            )
            mem = res.scalar_one_or_none()
            assert mem is not None
            assert mem.role == "gp"
            assert mem.accepted_at is not None  # Fase 12.3 canônico
            assert mem.joined_at is not None
            assert mem.is_active is True
    finally:
        os.environ.pop("DATABASE_URL", None)
        await _cleanup_canary()


@pytest.mark.asyncio
async def test_seed_is_idempotent():
    """Rodar o seed duas vezes não cria duplicatas nem dá erro."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Project, ProjectMember
    from sqlalchemy import select, func

    await _cleanup_canary()

    try:
        test_url = os.environ["TEST_DATABASE_URL"]
        os.environ["DATABASE_URL"] = test_url
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "scripts",
            "seed_e2e.py",
        )
        import importlib.util

        # 1ª execução
        spec = importlib.util.spec_from_file_location("seed_e2e_mod1", script_path)
        m1 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m1)
        await m1.seed()

        # 2ª execução (deve ser idempotente)
        spec = importlib.util.spec_from_file_location("seed_e2e_mod2", script_path)
        m2 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m2)
        await m2.seed()

        # Valida: apenas 1 admin, 1 project, 1 membership
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(func.count(User.id)).where(User.email == CANARY_ADMIN_EMAIL)
            )
            assert int(res.scalar()) == 1

            res = await session.execute(
                select(func.count(Project.id)).where(Project.id == CANARY_PROJECT_UUID)
            )
            assert int(res.scalar()) == 1

            res = await session.execute(
                select(func.count(ProjectMember.id)).where(
                    ProjectMember.project_id == CANARY_PROJECT_UUID
                )
            )
            assert int(res.scalar()) == 1
    finally:
        os.environ.pop("DATABASE_URL", None)
        await _cleanup_canary()


def test_ci_workflow_no_continue_on_error_in_e2e():
    """Valida que o CI perdeu `continue-on-error: true` no job e2e (Fase 12.6).

    Skipa automaticamente quando rodado dentro do container backend (onde
    só `backend/` está montado); executado normalmente em ambiente local
    / CI com o repo inteiro disponível.
    """
    import pathlib

    candidates = [pathlib.Path("/home/luiz/GCA/.github/workflows/backend-tests.yml")]
    _file_path = pathlib.Path(__file__).resolve()
    for depth in range(1, 8):
        try:
            candidates.append(_file_path.parents[depth] / ".github" / "workflows" / "backend-tests.yml")
        except IndexError:
            break
    wf_path = next((p for p in candidates if p.exists()), None)
    if wf_path is None:
        pytest.skip("backend-tests.yml não disponível neste ambiente (ok em container)")

    content = wf_path.read_text(encoding="utf-8")
    assert "continue-on-error: true" not in content, (
        "Fase 12.6 removeu continue-on-error: true da lane e2e"
    )
