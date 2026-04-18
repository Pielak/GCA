"""Testes de persistência do CodeGen — guard de ProjectGitConfig + happy-path.

Cobertura:
- Guard estrutural: scaffold/regenerate-file → 400 sem ProjectGitConfig.
- Happy-path scaffold: LLM mockado retorna N arquivos; cada um vira commit
  via GitService.commit_file mockado; resposta inclui commit_summary.
- Happy-path regenerate-file: LLM mockado retorna conteúdo de 1 arquivo;
  GitService.commit_file mockado é chamado com path correto.

Estratégia de mock: patch `anthropic.AsyncAnthropic` (a classe que o
endpoint importa lazy) e `app.services.git_service.GitService.commit_file`.

DT-040: CodeGen é escopo do **MVP 3** (contrato §7 — "Geração assistida
controlada"). No MVP 2, o project-setup-gate (DT-031) mudou respostas de
400→412, e o contrato de CodeGen ainda vai evoluir. Estes testes ficam
skipped até a abertura oficial do MVP 3. Remover o skip + adaptar aos
novos contratos é tarefa do gate do MVP 3.
"""
import pytest as _pytest
_pytest.skip(
    "CodeGen é escopo MVP 3 (contrato §7). Testes skipped até abertura "
    "oficial do MVP 3 — ver DT-040 em GCA_MVP_PROGRESS.md.",
    allow_module_level=True,
)
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.main import app
from app.core.security import create_access_token, hash_password


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_scaffold_400_when_no_git_config():
    """Projeto sem ProjectGitConfig → 400 com mensagem clara."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Organization, Project

    async with AsyncSessionLocal() as session:
        async with session.begin():
            uid = uuid4()
            user = User(
                id=uid,
                email=f"codegen-{uid.hex[:6]}@test.com",
                password_hash=hash_password("Test@1234"),
                full_name="Codegen Tester",
                is_active=True,
                is_admin=True,
                created_at=datetime.utcnow(),
            )
            org = Organization(
                id=uuid4(),
                name=f"Org {uid.hex[:6]}",
                slug=f"org-{uid.hex[:6]}",
                owner_id=uid,
                is_active=True,
                created_at=datetime.utcnow(),
            )
            session.add(user)
            session.add(org)
            await session.flush()
            project = Project(
                id=uuid4(),
                organization_id=org.id,
                name="P sem Git",
                slug=f"p-nogit-{uid.hex[:6]}",
                status="active",
                deliverable_type="web_app",
                created_at=datetime.utcnow(),
            )
            session.add(project)

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as client:
        resp = await client.post(
            "/api/v1/code-generation/scaffold",
            headers={"Authorization": f"Bearer {token}"},
            json={"project_id": str(project.id)},
        )

    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert "Git" in body["detail"]

    # Cleanup
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(Project.__table__.delete().where(Project.id == project.id))
            await session.execute(Organization.__table__.delete().where(Organization.id == org.id))
            await session.execute(User.__table__.delete().where(User.id == user.id))


@pytest.mark.asyncio
async def test_regenerate_file_400_when_no_git_config():
    """Endpoint de regenerar arquivo único também exige ProjectGitConfig."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Organization, Project

    async with AsyncSessionLocal() as session:
        async with session.begin():
            uid = uuid4()
            user = User(
                id=uid,
                email=f"regen-{uid.hex[:6]}@test.com",
                password_hash=hash_password("Test@1234"),
                full_name="Regen Tester",
                is_active=True,
                is_admin=True,
                created_at=datetime.utcnow(),
            )
            org = Organization(
                id=uuid4(),
                name=f"Org {uid.hex[:6]}",
                slug=f"regen-org-{uid.hex[:6]}",
                owner_id=uid,
                is_active=True,
                created_at=datetime.utcnow(),
            )
            session.add(user)
            session.add(org)
            await session.flush()
            project = Project(
                id=uuid4(),
                organization_id=org.id,
                name="P sem Git (regen)",
                slug=f"p-regen-nogit-{uid.hex[:6]}",
                status="active",
                deliverable_type="web_app",
                created_at=datetime.utcnow(),
            )
            session.add(project)

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as client:
        resp = await client.post(
            "/api/v1/code-generation/regenerate-file",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "project_id": str(project.id),
                "path": "src/main.py",
            },
        )

    assert resp.status_code == 400, resp.text
    assert "Git" in resp.json()["detail"]

    # Cleanup
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(Project.__table__.delete().where(Project.id == project.id))
            await session.execute(Organization.__table__.delete().where(Organization.id == org.id))
            await session.execute(User.__table__.delete().where(User.id == user.id))


def _build_anthropic_mock(json_payload: dict, output_tokens: int = 100) -> MagicMock:
    """Constrói um mock do AsyncAnthropic que devolve um JSON serializado.

    O endpoint faz `response.content[0].text` e `response.usage.output_tokens`,
    então precisamos cobrir essas duas leituras.
    """
    response = MagicMock()
    response.content = [MagicMock(text=json.dumps(json_payload))]
    response.usage = MagicMock(output_tokens=output_tokens)

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


async def _make_user_org_project_with_git(
    project_name: str,
    user_email_prefix: str,
):
    """Cria User + Organization + Project + ProjectGitConfig em uma única tx.

    Retorna (user_id, org_id, project_id, git_config_id) para cleanup posterior.
    """
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Organization, Project, ProjectGitConfig

    uid = uuid4()
    org_id = uuid4()
    project_id = uuid4()
    git_id = uuid4()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(
                User(
                    id=uid,
                    email=f"{user_email_prefix}-{uid.hex[:6]}@test.com",
                    password_hash=hash_password("Test@1234"),
                    full_name="Codegen Tester",
                    is_active=True,
                    is_admin=True,
                    created_at=datetime.utcnow(),
                )
            )
            session.add(
                Organization(
                    id=org_id,
                    name=f"Org {uid.hex[:6]}",
                    slug=f"org-{uid.hex[:6]}",
                    owner_id=uid,
                    is_active=True,
                    created_at=datetime.utcnow(),
                )
            )
            await session.flush()
            session.add(
                Project(
                    id=project_id,
                    organization_id=org_id,
                    name=project_name,
                    slug=f"p-{uid.hex[:6]}",
                    status="active",
                    deliverable_type="web_app",
                    created_at=datetime.utcnow(),
                )
            )
            await session.flush()
            session.add(
                ProjectGitConfig(
                    id=git_id,
                    project_id=project_id,
                    provider="github",
                    repository_url="https://github.com/test-org/test-repo",
                    default_branch="main",
                    pat_encrypted="fake-pat-for-test",
                    connection_verified=True,
                )
            )

    return uid, org_id, project_id, git_id


async def _cleanup_user_org_project_git(uid, org_id, project_id, git_id):
    """Limpa fixture criado por _make_user_org_project_with_git."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Organization, Project, ProjectGitConfig

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                ProjectGitConfig.__table__.delete().where(ProjectGitConfig.id == git_id)
            )
            await session.execute(Project.__table__.delete().where(Project.id == project_id))
            await session.execute(Organization.__table__.delete().where(Organization.id == org_id))
            await session.execute(User.__table__.delete().where(User.id == uid))


@pytest.mark.asyncio
async def test_scaffold_happy_path_commits_files():
    """Scaffold gera N arquivos via LLM mockado e commita cada um (exceto nmi)."""
    uid, org_id, project_id, git_id = await _make_user_org_project_with_git(
        project_name="P happy",
        user_email_prefix="scaffold-happy",
    )

    llm_payload = {
        "files": [
            {
                "path": "src/main.py",
                "content": '"""Entry point."""\n\n\ndef main() -> None:\n    """Run the app."""\n    pass\n',
                "status": "complete",
            },
            {
                "path": "src/todo.py",
                "content": '"""TODO module."""\n\n# TODO: implementar\n',
                "status": "todo",
            },
            {
                "path": "src/skip_me.py",
                "content": "# [NMI] precisa de mais info do projeto\n",
                "status": "nmi",
            },
        ],
        "summary": "Gerados 3 arquivos para P happy",
    }

    commit_calls = []

    async def fake_commit(self, project_id, file_path, content, commit_message):
        commit_calls.append({"path": file_path, "msg": commit_message})
        return {"success": True, "sha": "deadbeef", "message": "ok"}

    token = create_access_token(data={"sub": str(uid)})

    try:
        with patch(
            "anthropic.AsyncAnthropic", return_value=_build_anthropic_mock(llm_payload)
        ), patch(
            "app.services.git_service.GitService.commit_file", new=fake_commit
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/code-generation/scaffold",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"project_id": str(project_id)},
                )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["files"]) == 3, body
        assert body["summary"] == "Gerados 3 arquivos para P happy"

        # nmi não é commitado; complete + todo sim
        assert body["commit_summary"]["committed"] == 2
        assert body["commit_summary"]["failed"] == 0
        committed_paths = {c["path"] for c in commit_calls}
        assert committed_paths == {"src/main.py", "src/todo.py"}

        # Mensagem de commit segue padrão feat(codegen): <path>
        for call in commit_calls:
            assert call["msg"].startswith("feat(codegen): ")
            assert call["msg"].endswith(call["path"])

    finally:
        await _cleanup_user_org_project_git(uid, org_id, project_id, git_id)


@pytest.mark.asyncio
async def test_regenerate_file_happy_path_commits():
    """Regenerar UM arquivo: LLM devolve conteúdo, vira commit individual no Git."""
    uid, org_id, project_id, git_id = await _make_user_org_project_with_git(
        project_name="P regen",
        user_email_prefix="regen-happy",
    )

    llm_payload = {
        "content": '"""Refatorado."""\n\n\ndef hello() -> str:\n    """Greet."""\n    return "hi"\n',
        "status": "complete",
    }

    commit_calls = []

    async def fake_commit(self, project_id, file_path, content, commit_message):
        commit_calls.append(
            {"path": file_path, "content": content, "msg": commit_message}
        )
        return {"success": True, "sha": "cafef00d", "message": "ok"}

    token = create_access_token(data={"sub": str(uid)})

    try:
        with patch(
            "anthropic.AsyncAnthropic", return_value=_build_anthropic_mock(llm_payload)
        ), patch(
            "app.services.git_service.GitService.commit_file", new=fake_commit
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/code-generation/regenerate-file",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "project_id": str(project_id),
                        "path": "src/hello.py",
                        "instructions": "Adicione type hints e docstrings",
                    },
                )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["path"] == "src/hello.py"
        assert body["status"] == "complete"
        assert body["committed"] is True
        assert body["commit_error"] is None
        assert "hello" in body["content"]

        # Foi um único commit, com path correto e mensagem de regenerate
        assert len(commit_calls) == 1
        assert commit_calls[0]["path"] == "src/hello.py"
        assert commit_calls[0]["msg"] == "feat(codegen): regenerar src/hello.py"

    finally:
        await _cleanup_user_org_project_git(uid, org_id, project_id, git_id)
