"""Testes de persistência do CodeGen — gate de project-setup + happy-path.

Cobertura:
- Gate estrutural: scaffold/regenerate-file → 412 sem setup completo
  (repo git + llm + questionário), com `missing` contendo o que falta.
- Happy-path scaffold: LLM mockado retorna N arquivos; cada um vira commit
  via GitService.commit_file mockado; resposta inclui commit_summary.
- Happy-path regenerate-file: LLM mockado retorna conteúdo de 1 arquivo;
  GitService.commit_file mockado é chamado com path correto.

Estratégia de mock: patch `anthropic.AsyncAnthropic` (a classe que o
endpoint importa lazy) e `app.services.git_service.GitService.commit_file`.

Histórico: antes eram testes de "400 sem ProjectGitConfig". O gate foi
generalizado — agora `require_project_setup_complete` checa os 3
pré-requisitos juntos e devolve 412 com `missing=[...]`. Tests foram
sincronizados em 2026-04-18 na abertura do MVP 3.
"""
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


async def _add_project_member(db_session, uid, project_id, role="dev"):
    """DT-042: user precisa ser membro com papel que tenha a permissão.

    Testes de gate de setup (412) e happy-path (200) todos precisam passar
    pelo RBAC de CodeGen primeiro. Helper adiciona a membership mínima.
    """
    from app.models.base import ProjectMember
    db_session.add(
        ProjectMember(
            id=uuid4(),
            project_id=project_id,
            user_id=uid,
            role=role,
            is_active=True,
            invited_at=datetime.utcnow(),
            joined_at=datetime.utcnow(),
        )
    )


@pytest.mark.asyncio
async def test_scaffold_412_when_setup_incomplete():
    """Projeto sem setup completo → 412 com `missing` listando o que falta."""
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
            await session.flush()
            await _add_project_member(session, uid, project.id, role="dev")

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as client:
        resp = await client.post(
            "/api/v1/code-generation/scaffold",
            headers={"Authorization": f"Bearer {token}"},
            json={"project_id": str(project.id)},
        )

    assert resp.status_code == 412, resp.text
    body = resp.json()
    assert body["detail"]["code"] == "project_setup_incomplete"
    assert "repositorio_git" in body["detail"]["missing"]

    # Cleanup
    from app.models.base import ProjectMember
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(ProjectMember.__table__.delete().where(ProjectMember.project_id == project.id))
            await session.execute(Project.__table__.delete().where(Project.id == project.id))
            await session.execute(Organization.__table__.delete().where(Organization.id == org.id))
            await session.execute(User.__table__.delete().where(User.id == user.id))


@pytest.mark.asyncio
async def test_regenerate_file_412_when_setup_incomplete():
    """Endpoint de regenerar arquivo único também é barrado pelo gate de setup."""
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
            await session.flush()
            await _add_project_member(session, uid, project.id, role="dev")

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

    assert resp.status_code == 412, resp.text
    body = resp.json()
    assert body["detail"]["code"] == "project_setup_incomplete"
    assert "repositorio_git" in body["detail"]["missing"]

    # Cleanup
    from app.models.base import ProjectMember
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(ProjectMember.__table__.delete().where(ProjectMember.project_id == project.id))
            await session.execute(Project.__table__.delete().where(Project.id == project.id))
            await session.execute(Organization.__table__.delete().where(Organization.id == org.id))
            await session.execute(User.__table__.delete().where(User.id == user.id))


def _build_anthropic_mock(json_payload: dict, output_tokens: int = 100) -> MagicMock:
    """Constrói um mock do AsyncAnthropic que devolve um JSON serializado.

    DT-079 (2026-05-03) substituiu AsyncAnthropic direto por
    `call_codegen_llm`. Helper mantido para retrocompat de testes que ainda
    patcham `anthropic.AsyncAnthropic` (no-op pós-DT-079, mas não quebra).
    Para mockar a porta única, use `_codegen_llm_response`.
    """
    response = MagicMock()
    response.content = [MagicMock(text=json.dumps(json_payload))]
    response.usage = MagicMock(output_tokens=output_tokens)

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


def _codegen_llm_response(json_payload: dict) -> str:
    """Constrói o texto cru que `call_codegen_llm` retornaria.

    DT-085 (2026-05-03): porta única `call_codegen_llm` retorna `str` (texto
    do LLM). Endpoints parseiam JSON desse texto. Helper monta a string para
    mockar via `patch("...code_generation.call_codegen_llm", return_value=...)`.
    """
    return json.dumps(json_payload)


async def _make_user_org_project_with_full_setup(
    project_name: str,
    user_email_prefix: str,
    role: str = "dev",
):
    """Cria User + Org + Project + ProjectMember(role) + os 3 pré-requisitos
    do gate de setup: ProjectGitConfig + ProjectSettings(llm) + Questionnaire.

    Abertura do MVP 3 (2026-04-18): `require_project_setup_complete` no
    router do CodeGen exige os 3 juntos. DT-042 adicionou RBAC por ação —
    helper cria membership com `role` (default dev) pra satisfazer ambos.

    Parametrizar `role` permite testar RBAC denial (role="gp" → 403).

    Retorna (user_id, org_id, project_id, git_id, settings_id, q_id)
    para cleanup.

    DT-085 (2026-05-03): também cria OCG maduro (overall_score=100) para
    passar pelo `check_ocg_maturity_gate` introduzido pelo MVP 31. Sem isso,
    todos os endpoints de CodeGen levantam HTTPException 404/409 antes da
    lógica sob teste.
    """
    from app.db.database import AsyncSessionLocal
    from app.models.base import (
        User, Organization, Project, ProjectGitConfig,
        ProjectSettings, Questionnaire, ProjectMember, OCG,
    )

    uid = uuid4()
    org_id = uuid4()
    project_id = uuid4()
    git_id = uuid4()
    settings_id = uuid4()
    q_id = uuid4()
    ocg_id = uuid4()  # DT-085

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
            # Gate de setup: ProjectSettings com setting_type="llm"
            session.add(
                ProjectSettings(
                    id=settings_id,
                    project_id=project_id,
                    setting_type="llm",
                    settings_json=json.dumps({
                        "provider": "anthropic",
                        "model": "claude-sonnet-4-6",
                    }),
                )
            )
            # Gate de setup: Questionnaire submetido (com responses não-vazias)
            session.add(
                Questionnaire(
                    id=q_id,
                    project_id=project_id,
                    gp_email=f"{user_email_prefix}-{uid.hex[:6]}@test.com",
                    responses=json.dumps({"1": "Projeto Teste"}),
                    status="pending",
                    approved=True,
                    submitted_at=datetime.utcnow(),
                )
            )
            # RBAC (DT-042): membership com papel que tem code:write/git:commit.
            session.add(
                ProjectMember(
                    id=uuid4(),
                    project_id=project_id,
                    user_id=uid,
                    role=role,
                    is_active=True,
                    invited_at=datetime.utcnow(),
                    joined_at=datetime.utcnow(),
                )
            )
            # DT-085: OCG maduro para passar pelo check_ocg_maturity_gate (MVP 31).
            # Cascateia via questionnaire_id_fkey ON DELETE CASCADE — sem cleanup
            # explícito necessário (FK ocg.questionnaire_id é CASCADE no DB).
            session.add(
                OCG(
                    id=ocg_id,
                    questionnaire_id=q_id,
                    project_id=project_id,
                    overall_score=100,  # >= SCORE_MATURIDADE (95)
                    status="active",
                    is_blocking=False,
                    ocg_data="{}",
                    version=1,
                )
            )

    return uid, org_id, project_id, git_id, settings_id, q_id


async def _cleanup_user_org_project_full(uid, org_id, project_id, git_id, settings_id, q_id):
    """Limpa fixture criado por _make_user_org_project_with_full_setup.

    DT-085: OCG criado pelo helper cascateia automaticamente via
    `ocg_questionnaire_id_fkey ON DELETE CASCADE` quando questionnaire é
    deletado. Sem cleanup explícito necessário.
    """
    from app.db.database import AsyncSessionLocal
    from app.models.base import (
        User, Organization, Project, ProjectGitConfig,
        ProjectSettings, Questionnaire, ProjectMember,
    )

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                ProjectMember.__table__.delete().where(ProjectMember.project_id == project_id)
            )
            await session.execute(
                Questionnaire.__table__.delete().where(Questionnaire.id == q_id)
            )
            await session.execute(
                ProjectSettings.__table__.delete().where(ProjectSettings.id == settings_id)
            )
            await session.execute(
                ProjectGitConfig.__table__.delete().where(ProjectGitConfig.id == git_id)
            )
            await session.execute(Project.__table__.delete().where(Project.id == project_id))
            await session.execute(Organization.__table__.delete().where(Organization.id == org_id))
            await session.execute(User.__table__.delete().where(User.id == uid))


_SCAFFOLD_LLM_PAYLOAD = {
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


@pytest.mark.asyncio
async def test_scaffold_preview_returns_files_no_commits():
    """MVP 3: POST /scaffold (dry_run default=True) retorna files mas NÃO commita."""
    uid, org_id, project_id, git_id, settings_id, q_id = await _make_user_org_project_with_full_setup(
        project_name="P preview",
        user_email_prefix="scaffold-preview",
    )

    commit_calls = []

    async def fake_commit(self, project_id, file_path, content, commit_message):
        commit_calls.append({"path": file_path, "msg": commit_message})
        return {"success": True, "sha": "deadbeef", "message": "ok"}

    token = create_access_token(data={"sub": str(uid)})

    try:
        # DT-079/085: porta única call_codegen_llm em vez de AsyncAnthropic.
        with patch(
            "app.services.codegen_llm.call_codegen_llm",
            new=AsyncMock(return_value=_codegen_llm_response(_SCAFFOLD_LLM_PAYLOAD)),
        ), patch(
            "app.services.git_service.GitService.commit_file", new=fake_commit
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/code-generation/scaffold",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"project_id": str(project_id)},  # dry_run default = True
                )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["dry_run"] is True
        assert body["commit_summary"] is None
        assert len(body["files"]) == 3, body
        assert body["summary"] == "Gerados 3 arquivos para P happy"
        # Zero commits — preview não toca no Git
        assert commit_calls == []

    finally:
        await _cleanup_user_org_project_full(uid, org_id, project_id, git_id, settings_id, q_id)


@pytest.mark.asyncio
async def test_scaffold_apply_commits_reviewed_files():
    """MVP 3: POST /scaffold/apply commita files pré-gerados (no-LLM path)."""
    uid, org_id, project_id, git_id, settings_id, q_id = await _make_user_org_project_with_full_setup(
        project_name="P apply",
        user_email_prefix="scaffold-apply",
    )

    commit_calls = []

    async def fake_commit(self, project_id, file_path, content, commit_message):
        commit_calls.append({"path": file_path, "msg": commit_message})
        return {"success": True, "sha": "deadbeef", "message": "ok"}

    token = create_access_token(data={"sub": str(uid)})

    try:
        with patch("app.services.git_service.GitService.commit_file", new=fake_commit):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/code-generation/scaffold/apply",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "project_id": str(project_id),
                        "files": _SCAFFOLD_LLM_PAYLOAD["files"],
                    },
                )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["committed"] == 2  # complete + todo
        assert body["failed"] == 0
        assert body["skipped_nmi"] == 1
        committed_paths = {c["path"] for c in commit_calls}
        assert committed_paths == {"src/main.py", "src/todo.py"}

        # Pattern de commit mantido
        for call in commit_calls:
            assert call["msg"].startswith("feat(codegen): ")
            assert call["msg"].endswith(call["path"])

    finally:
        await _cleanup_user_org_project_full(uid, org_id, project_id, git_id, settings_id, q_id)


@pytest.mark.asyncio
async def test_scaffold_legacy_dry_run_false_commits_directly():
    """Legacy: POST /scaffold dry_run=False ainda commita direto (scripts)."""
    uid, org_id, project_id, git_id, settings_id, q_id = await _make_user_org_project_with_full_setup(
        project_name="P legacy",
        user_email_prefix="scaffold-legacy",
    )

    commit_calls = []

    async def fake_commit(self, project_id, file_path, content, commit_message):
        commit_calls.append({"path": file_path, "msg": commit_message})
        return {"success": True, "sha": "deadbeef", "message": "ok"}

    token = create_access_token(data={"sub": str(uid)})

    try:
        # DT-079/085: porta única call_codegen_llm em vez de AsyncAnthropic.
        with patch(
            "app.services.codegen_llm.call_codegen_llm",
            new=AsyncMock(return_value=_codegen_llm_response(_SCAFFOLD_LLM_PAYLOAD)),
        ), patch(
            "app.services.git_service.GitService.commit_file", new=fake_commit
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/code-generation/scaffold",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"project_id": str(project_id), "dry_run": False},
                )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["dry_run"] is False
        assert body["commit_summary"]["committed"] == 2
        assert body["commit_summary"]["failed"] == 0
        committed_paths = {c["path"] for c in commit_calls}
        assert committed_paths == {"src/main.py", "src/todo.py"}

    finally:
        await _cleanup_user_org_project_full(uid, org_id, project_id, git_id, settings_id, q_id)


@pytest.mark.asyncio
async def test_regenerate_file_happy_path_commits():
    """Regenerar UM arquivo: LLM devolve conteúdo, vira commit individual no Git."""
    uid, org_id, project_id, git_id, settings_id, q_id = await _make_user_org_project_with_full_setup(
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
        # DT-079/085: porta única call_codegen_llm em vez de AsyncAnthropic.
        with patch(
            "app.services.codegen_llm.call_codegen_llm",
            new=AsyncMock(return_value=_codegen_llm_response(llm_payload)),
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
        await _cleanup_user_org_project_full(uid, org_id, project_id, git_id, settings_id, q_id)


# ============================================================================
# DT-042 + Emenda RBAC 2026-04-19: GP agora É SOBERANO do projeto
# (contrato §4.1 emendado). GP tem code:write + git:commit via union de Dev.
# Testes invertidos: GP deve passar (não mais 403).
# ============================================================================


@pytest.mark.asyncio
async def test_scaffold_rbac_gp_now_allowed_after_emenda():
    """Emenda 2026-04-19: GP tem code:write — scaffold NÃO retorna 403."""
    uid, org_id, project_id, git_id, settings_id, q_id = await _make_user_org_project_with_full_setup(
        project_name="P gp-now-allowed",
        user_email_prefix="scaffold-gp",
        role="gp",
    )

    token = create_access_token(data={"sub": str(uid)})

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/code-generation/scaffold",
                headers={"Authorization": f"Bearer {token}"},
                json={"project_id": str(project_id)},
            )

        # Não 403 — GP é soberano do projeto. Outros erros (400/422/500) são
        # aceitáveis pra este teste pois só checamos que o guard de RBAC
        # não barra mais.
        assert resp.status_code != 403, f"GP foi bloqueado indevidamente: {resp.text}"

    finally:
        await _cleanup_user_org_project_full(uid, org_id, project_id, git_id, settings_id, q_id)


@pytest.mark.asyncio
async def test_scaffold_apply_rbac_gp_now_allowed_after_emenda():
    """Emenda 2026-04-19: GP tem git:commit — scaffold/apply NÃO retorna 403."""
    uid, org_id, project_id, git_id, settings_id, q_id = await _make_user_org_project_with_full_setup(
        project_name="P gp-apply-allowed",
        user_email_prefix="apply-gp",
        role="gp",
    )

    token = create_access_token(data={"sub": str(uid)})

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/code-generation/scaffold/apply",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "project_id": str(project_id),
                    "files": [{"path": "x.py", "content": '"""x"""\n', "status": "complete"}],
                },
            )

        assert resp.status_code != 403, f"GP foi bloqueado indevidamente: {resp.text}"

    finally:
        await _cleanup_user_org_project_full(uid, org_id, project_id, git_id, settings_id, q_id)


# ============================================================================
# DT-043: adequação do provedor ao CodeGen (contrato §7 + §6.2).
# CodeGen é ALTA criticidade → premium (anthropic/openai) recomendado;
# média/baixa (deepseek/grok/gemini/qwen/ollama) dispara warning.
# Decisão não-bloqueante — response traz `provider_warning` ou None.
# ============================================================================


async def _make_setup_with_provider(
    project_name: str,
    user_email_prefix: str,
    provider: str,
):
    """Variante do full_setup que permite forçar o provider em ProjectSettings."""
    uid, org_id, project_id, git_id, settings_id, q_id = await _make_user_org_project_with_full_setup(
        project_name=project_name,
        user_email_prefix=user_email_prefix,
        role="dev",
    )
    # Atualiza o provider do ProjectSettings (fixture default = anthropic).
    from app.db.database import AsyncSessionLocal
    from sqlalchemy import text as _text

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                _text("UPDATE project_settings SET settings_json=:sj WHERE id=:sid"),
                {
                    "sj": json.dumps({"provider": provider, "model": f"{provider}-test"}),
                    "sid": str(settings_id),
                },
            )
    return uid, org_id, project_id, git_id, settings_id, q_id


@pytest.mark.asyncio
async def test_scaffold_premium_provider_has_no_warning():
    """DT-043: provider anthropic (premium) → provider_warning=None."""
    uid, org_id, project_id, git_id, settings_id, q_id = await _make_setup_with_provider(
        project_name="P premium",
        user_email_prefix="premium",
        provider="anthropic",
    )

    token = create_access_token(data={"sub": str(uid)})

    try:
        # DT-079/085: porta única call_codegen_llm em vez de AsyncAnthropic.
        with patch(
            "app.services.codegen_llm.call_codegen_llm",
            new=AsyncMock(return_value=_codegen_llm_response(_SCAFFOLD_LLM_PAYLOAD)),
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
        assert body["provider_warning"] is None

    finally:
        await _cleanup_user_org_project_full(uid, org_id, project_id, git_id, settings_id, q_id)


@pytest.mark.asyncio
async def test_scaffold_medium_provider_triggers_warning():
    """DT-043: provider deepseek (média/baixa) → provider_warning preenchido, não bloqueia."""
    uid, org_id, project_id, git_id, settings_id, q_id = await _make_setup_with_provider(
        project_name="P deepseek",
        user_email_prefix="deepseek",
        provider="deepseek",
    )

    token = create_access_token(data={"sub": str(uid)})

    try:
        # DT-079/085: porta única call_codegen_llm em vez de AsyncAnthropic.
        with patch(
            "app.services.codegen_llm.call_codegen_llm",
            new=AsyncMock(return_value=_codegen_llm_response(_SCAFFOLD_LLM_PAYLOAD)),
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/code-generation/scaffold",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"project_id": str(project_id)},
                )

        # 200 — não bloqueia, só avisa
        assert resp.status_code == 200, resp.text
        body = resp.json()
        warning = body["provider_warning"]
        assert warning is not None
        assert warning["provider"] == "deepseek"
        assert warning["criticality"] == "medium_low"
        assert "premium" in warning["recommended"].lower()
        # Preview ainda funciona (files retornados)
        assert len(body["files"]) == 3

    finally:
        await _cleanup_user_org_project_full(uid, org_id, project_id, git_id, settings_id, q_id)


@pytest.mark.asyncio
async def test_scaffold_rbac_blocks_non_member_non_admin():
    """DT-042: user não-membro e não-admin → 403 pelo resolve_user_roles."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User

    # User avulso, sem membership, sem is_admin
    async with AsyncSessionLocal() as session:
        async with session.begin():
            uid = uuid4()
            user = User(
                id=uid,
                email=f"stranger-{uid.hex[:6]}@test.com",
                password_hash=hash_password("Test@1234"),
                full_name="Stranger",
                is_active=True,
                is_admin=False,  # não-admin
                created_at=datetime.utcnow(),
            )
            session.add(user)

    # Projeto de outra pessoa (com setup completo)
    uid_owner, org_id, project_id, git_id, settings_id, q_id = await _make_user_org_project_with_full_setup(
        project_name="P other",
        user_email_prefix="owner-other",
        role="dev",
    )

    token = create_access_token(data={"sub": str(uid)})

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/code-generation/scaffold",
                headers={"Authorization": f"Bearer {token}"},
                json={"project_id": str(project_id)},
            )

        # resolve_user_roles_in_project levanta 403 antes de bater em _require_code_action
        assert resp.status_code == 403, resp.text

    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(User.__table__.delete().where(User.id == uid))
        await _cleanup_user_org_project_full(uid_owner, org_id, project_id, git_id, settings_id, q_id)
