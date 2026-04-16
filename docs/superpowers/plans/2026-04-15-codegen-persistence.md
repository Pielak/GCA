# CodeGen Persistence — Plano de Implementação

> **Para workers agênticos:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development ou superpowers:executing-plans. Steps usam checkbox (`- [ ]`).

**Goal:** CodeGen grava os arquivos gerados no repo Git do projeto, árvore de arquivos é atualizada, navegação não perde o código.

**Architecture:** Hoje `POST /api/v1/code-generation/scaffold` só retorna JSON. A mudança: depois de gerar via LLM, iterar `files` e chamar `git_service.commit_file` por arquivo (mesma infra usada no scaffold inicial do projeto). Se o projeto não tiver `ProjectGitConfig` conectado, retornar 400 claro. Frontend invalida a árvore após sucesso. Sem novo schema, sem novo storage — reaproveita o que já existe.

**Tech Stack:** FastAPI, GitService (GitHub/GitLab API), React.

---

## File Structure

**Backend — modificar:**
- `backend/app/routers/code_generation.py:381-384` — antes do `return ScaffoldResponse`, commitar cada arquivo e incluir `commit_summary` no payload
- `backend/app/routers/code_generation.py:140-150` (aprox.) — check early de `ProjectGitConfig` conectado; retornar 400 se não

**Frontend — modificar:**
- `frontend/src/pages/projects/CodeGeneratorPage.tsx` — após sucesso do scaffold, chamar `loadTree()` para refetch; exibir `commit_summary` em toast

**Testes — criar:**
- `backend/app/tests/test_codegen_persistence.py` — 2 testes: 400 sem git config; arquivos commitados quando config existe (mockando git_service)

---

### Task 1: Backend — commit após geração + guard de Git config

**Files:**
- Modify: `backend/app/routers/code_generation.py`

- [ ] **Step 1: Guard de ProjectGitConfig logo após buscar projeto**

Em `/home/luiz/GCA/backend/app/routers/code_generation.py`, localize o bloco após `project = await db.get(Project, project_id)` (linha ~133) e ANTES da lógica de buscar OCG/docs. Adicione:

```python
    # Guard: projeto precisa ter Git conectado para receber os commits
    from sqlalchemy import select as _select
    from app.models.base import ProjectGitConfig
    git_config = (
        await db.execute(
            _select(ProjectGitConfig).where(ProjectGitConfig.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not git_config or not getattr(git_config, "is_connected", True) or not git_config.repo_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Repositório Git do projeto não configurado. "
                "Configure em Admin → Projetos antes de gerar código."
            ),
        )
```

Nota: verificar o nome real do campo em ProjectGitConfig que indica conexão ativa — pode ser `is_connected`, `connected`, ou simplesmente presença de `access_token`/`repo_url`. Rode `grep -n "class ProjectGitConfig" -A 20 /home/luiz/GCA/backend/app/models/base.py` antes de escolher. Se o nome for diferente de `is_connected`, ajuste.

- [ ] **Step 2: Commit de cada arquivo antes do return**

Localize o bloco final do endpoint `generate_scaffold` antes do `return ScaffoldResponse(...)` (linha ~381). Substitua o bloco `return ScaffoldResponse(...)` por:

```python
        # Persistir cada arquivo no repositório Git do projeto
        from app.services.git_service import GitService
        git_service = GitService(db)

        commit_results = []
        committed = 0
        failed = 0
        for f in files:
            if f.get("status") == "nmi":
                # nmi = "not my intention / não gerado" — pula
                continue
            path = f.get("path") or f.get("file_path")
            content = f.get("content") or ""
            if not path or not content:
                continue
            result = await git_service.commit_file(
                project_id=project_id,
                file_path=path,
                content=content,
                commit_message=f"feat(codegen): {path}",
            )
            if result.get("success"):
                committed += 1
                commit_results.append({"path": path, "status": "ok"})
            else:
                failed += 1
                commit_results.append({"path": path, "status": "error", "error": result.get("message")})

        logger.info(
            "scaffold.commits_finished",
            project_id=str(project_id),
            committed=committed,
            failed=failed,
        )

        response = ScaffoldResponse(
            files=[ScaffoldFileItem(**f) for f in files],
            summary=summary,
        )
        # Anexar sumário de commits como campo extra (modelo aceita via dict)
        response_dict = response.model_dump()
        response_dict["commit_summary"] = {
            "committed": committed,
            "failed": failed,
            "results": commit_results,
        }
        return response_dict
```

Se `ScaffoldResponse` for pydantic v2 e não aceitar campos extras, mudar retorno final para `JSONResponse(content=response_dict)` importando `from fastapi.responses import JSONResponse` no topo.

- [ ] **Step 3: Restart + smoke test**

```bash
cd /home/luiz/GCA && docker compose restart backend
until docker compose logs backend --tail 10 2>&1 | grep -q "Application startup complete"; do sleep 2; done
docker compose logs backend --tail 30 2>&1 | grep -iE "error|traceback" | head -5 || echo "SEM ERROS"

# Testar 400 num projeto sem Git
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"pielak.ctba@gmail.com","password":"Topazio01#"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
PROJECT_ID=$(docker compose exec -T postgres psql -U gca -d gca -tA -c "SELECT p.id FROM projects p LEFT JOIN project_git_configs c ON c.project_id=p.id WHERE c.id IS NULL LIMIT 1;")
if [ -n "$PROJECT_ID" ]; then
  curl -s -o /dev/null -w "%{http_code}\n" -X POST "http://localhost:8000/api/v1/code-generation/scaffold" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"project_id\":\"$PROJECT_ID\"}"
fi
```

Esperado: 400 (projeto sem Git).

- [ ] **Step 4: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/routers/code_generation.py
git commit -m "feat(codegen): commitar arquivos gerados no repo Git do projeto + guard de Git config

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Frontend — refetch árvore + toast de commit

**Files:**
- Modify: `frontend/src/pages/projects/CodeGeneratorPage.tsx`

- [ ] **Step 1: Localizar onde o scaffold response é processado**

Procure por `scaffold/` na chamada (aprox. linha 231 conforme investigação anterior):

```bash
grep -nE "code-generation/scaffold|setScaffoldFiles|scaffoldFiles" /home/luiz/GCA/frontend/src/pages/projects/CodeGeneratorPage.tsx | head -15
```

- [ ] **Step 2: Após setScaffoldFiles, refetch da árvore e toast**

Na função que chama o endpoint de scaffold (localize pelo grep acima), logo após o `setScaffoldFiles(...)`, adicione:

```typescript
      // Após commitar no Git, refetch da árvore
      await loadTree()
      const cs = (res.data?.commit_summary || (res as any).commit_summary) as { committed?: number; failed?: number } | undefined
      if (cs) {
        const msg = `Commitados ${cs.committed || 0} arquivos no repositório${cs.failed ? `, ${cs.failed} falharam` : ''}.`
        toast.success(msg)
      }
```

Se o arquivo usar outro mecanismo de toast (buscar por `toast.` no topo para confirmar), ajuste para o que estiver em uso. Se não houver sistema de toast, use `alert(msg)`.

- [ ] **Step 3: Tratar erro 400 sem Git**

No `catch` da chamada de scaffold, garantir que 400 é exibido com mensagem clara:

```typescript
      } catch (err: any) {
        const detail = err?.response?.data?.detail || 'Falha ao gerar código'
        toast.error(detail)
      }
```

- [ ] **Step 4: Rebuild + validar**

```bash
cd /home/luiz/GCA && docker compose restart frontend
until docker compose logs frontend --tail 5 2>&1 | grep -q "Local:  "; do sleep 3; done
echo "READY"
```

Teste manual:
1. Abrir CodeGeneratorPage de projeto COM Git → clicar "Gerar Código" → toast deve mostrar contagem de commits; árvore (sidebar esquerda) deve expandir mostrando arquivos novos.
2. Navegar pra outra página e voltar → árvore ainda tem os arquivos (lendo do Git, não React state).

- [ ] **Step 5: Commit**

```bash
cd /home/luiz/GCA && git add frontend/src/pages/projects/CodeGeneratorPage.tsx
git commit -m "feat(codegen): refetch árvore após scaffold + toast de commit summary

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Testes

**Files:**
- Create: `backend/app/tests/test_codegen_persistence.py`

- [ ] **Step 1: Escrever testes**

Conteúdo exato de `/home/luiz/GCA/backend/app/tests/test_codegen_persistence.py`:

```python
"""Testes de persistência do CodeGen."""
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from app.main import app
from app.core.security import create_access_token


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_scaffold_400_when_no_git_config():
    """Projeto sem ProjectGitConfig → 400 com mensagem clara."""
    # Gerar user + project sem config
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Organization, Project
    from app.core.security import hash_password
    from datetime import datetime

    async with AsyncSessionLocal() as session:
        async with session.begin():
            uid = uuid4()
            user = User(
                id=uid, email=f"codegen-{uid.hex[:6]}@test.com",
                password_hash=hash_password("Test@1234"),
                full_name="Codegen Tester", is_active=True, is_admin=True,
                created_at=datetime.utcnow(),
            )
            org = Organization(
                id=uuid4(), name="Org", slug=f"org-{uid.hex[:6]}",
                owner_id=uid, is_active=True, created_at=datetime.utcnow(),
            )
            project = Project(
                id=uuid4(), organization_id=org.id, name="P",
                slug=f"p-{uid.hex[:6]}", status="active",
                created_at=datetime.utcnow(),
            )
            session.add_all([user, org, project])

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as client:
        resp = await client.post(
            "/api/v1/code-generation/scaffold",
            headers={"Authorization": f"Bearer {token}"},
            json={"project_id": str(project.id)},
        )
    assert resp.status_code == 400
    assert "Git" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_scaffold_commits_files_when_git_configured():
    """Projeto COM ProjectGitConfig → git_service.commit_file é chamado por arquivo."""
    # Mock do git_service para evitar chamada real à API do GitHub
    with patch("app.services.git_service.GitService.commit_file", new=AsyncMock(return_value={"success": True})) as mock_commit:
        # Mock da geração LLM para retornar 2 arquivos fictícios
        with patch("app.routers.code_generation._call_llm_for_scaffold", new=AsyncMock(return_value={
            "files": [
                {"path": "src/main.py", "content": "print('hi')", "status": "complete"},
                {"path": "src/utils.py", "content": "def x(): pass", "status": "complete"},
            ],
            "summary": "2 arquivos",
        })):
            # Setup com ProjectGitConfig conectado
            from app.db.database import AsyncSessionLocal
            from app.models.base import User, Organization, Project, ProjectGitConfig
            from app.core.security import hash_password
            from datetime import datetime

            async with AsyncSessionLocal() as session:
                async with session.begin():
                    uid = uuid4()
                    user = User(
                        id=uid, email=f"cg2-{uid.hex[:6]}@test.com",
                        password_hash=hash_password("Test@1234"),
                        full_name="CG2", is_active=True, is_admin=True,
                        created_at=datetime.utcnow(),
                    )
                    org = Organization(
                        id=uuid4(), name="Org2", slug=f"org2-{uid.hex[:6]}",
                        owner_id=uid, is_active=True, created_at=datetime.utcnow(),
                    )
                    project = Project(
                        id=uuid4(), organization_id=org.id, name="P2",
                        slug=f"p2-{uid.hex[:6]}", status="active",
                        created_at=datetime.utcnow(),
                    )
                    config = ProjectGitConfig(
                        project_id=project.id,
                        provider="github",
                        repo_url="https://github.com/test/repo",
                        access_token="fake",
                    )
                    session.add_all([user, org, project, config])

            token = create_access_token(data={"sub": str(user.id)})
            async with _client() as client:
                resp = await client.post(
                    "/api/v1/code-generation/scaffold",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"project_id": str(project.id)},
                )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body.get("commit_summary", {}).get("committed") == 2
            assert mock_commit.await_count == 2
```

Nota: o segundo teste mocka `_call_llm_for_scaffold` — se o nome real da função de geração for diferente, ajuste. Se não houver função separada (LLM chamado inline), talvez seja mais simples mockar `AIService.generate` ou similar. Rode `grep -n "def.*scaffold\|llm\|generate" /home/luiz/GCA/backend/app/routers/code_generation.py` para localizar.

- [ ] **Step 2: Rodar**

```bash
cd /home/luiz/GCA && docker compose exec -T backend python -m pytest app/tests/test_codegen_persistence.py -v 2>&1 | tail -20
```

- [ ] **Step 3: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/tests/test_codegen_persistence.py
git commit -m "test(codegen): cobertura de persistência (400 sem git + commit por arquivo)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- ✅ CodeGen commita arquivos → Task 1 step 2
- ✅ Guard se Git não configurado → Task 1 step 1
- ✅ Árvore reflete arquivos novos → Task 2 step 2 (refetch)
- ✅ Código não se perde na navegação → consequência direta dos commits

**Placeholder scan:** nenhum. Pontos de incerteza (nome exato de `is_connected`, função LLM) têm instrução de verificação antes da edição.

**Type consistency:**
- `commit_file(project_id, file_path, content, commit_message)` — assinatura confirmada em git_service.py:172-178
- `response_dict["commit_summary"]` é opcional; frontend lê via `res.data?.commit_summary` com fallback
