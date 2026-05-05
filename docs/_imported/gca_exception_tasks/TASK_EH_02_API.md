# TASK_EH_02 — Refatoração retroativa: `backend/app/api/`

## Pré-condição

TASK_EH_01 concluída e commitada.

## Objetivo

Aplicar a convenção em endpoints FastAPI. **Característica especial deste módulo**: como os handlers globais (registrados em TASK_EH_00) já capturam `GCAException`, os endpoints devem ficar **mais enxutos** após a refatoração — não mais inflados.

## Procedimento

### 1. Inventário

```bash
cd backend
grep -rn "except:\|except Exception\|HTTPException" app/api/ > /tmp/eh_api_inventory.md
```

### 2. Padrão alvo nos endpoints

**Antes (típico anti-padrão atual):**

```python
@router.get("/repos/{repo_id}")
async def get_repo(repo_id: int, db: Session = Depends(get_db)):
    try:
        repo = await repo_service.get(db, repo_id)
        if repo is None:
            raise HTTPException(404, "not found")
        return repo
    except Exception as e:
        logger.error(f"erro: {e}")
        raise HTTPException(500, "internal error")
```

**Depois (canônico):**

```python
@router.get("/repos/{repo_id}", response_model=RepoOut)
async def get_repo(repo_id: int, db: Session = Depends(get_db)) -> RepoOut:
    return await repo_service.get(db, repo_id)
```

O service lança `NotFoundError` ou `ExternalServiceError`; o handler global formata o JSON. Endpoint não precisa de try/except.

### 3. Quando endpoint PODE ter try/except

Apenas em três situações:

**a.** Tradução de exceção de framework não-GCA que vaza para o endpoint (ex: `pydantic.ValidationError` em parsing manual de query string complexa) — converter para `ValidationError` GCA.

**b.** Endpoint que orquestra múltiplos services e precisa de tratamento composto (ex: rollback manual de operação distribuída) — usar except específico, logar contexto agregado, re-lançar.

**c.** Endpoint de upload/streaming onde recursos precisam de cleanup explícito — usar `try/finally` (sem except), ou `async with`.

### 4. Eliminar HTTPException manuais

Onde houver `raise HTTPException(status_code=X, detail=...)` no endpoint:

- Se o motivo é "não encontrado" → mover lógica para service e lançar `NotFoundError`
- Se o motivo é "input inválido" → usar Pydantic validation no schema, ou lançar `ValidationError` no service
- Se o motivo é "sem permissão" → lançar `AuthorizationError` no dependency de auth
- Se o motivo é genérico 500 → remover; deixar o handler global capturar

**Exceção**: `HTTPException` pode ficar em **dependencies de autenticação** do FastAPI quando exigido pelo OAuth2/JWT flow para retornar `WWW-Authenticate` header corretamente. Documentar no código com comentário.

### 5. Validação

```bash
cd backend
ruff check app/api/
pytest tests/api/ -v --tb=short
```

### 6. Teste de integração obrigatório

Adicionar (ou atualizar) em `backend/tests/api/test_error_responses.py`:

```python
"""Garante que erros de domínio retornam JSON canônico."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_not_found_returns_canonical_envelope(client: AsyncClient):
    resp = await client.get("/api/repos/999999")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "GCA_NOT_FOUND"
    assert "message" in body["error"]


@pytest.mark.asyncio
async def test_validation_error_returns_400(client: AsyncClient):
    resp = await client.post("/api/repos", json={"invalid": "payload"})
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_unhandled_returns_500_envelope(client: AsyncClient, monkeypatch):
    # forçar erro não-GCA em algum endpoint conhecido
    # ... (adaptar ao endpoint real)
    pass
```

## Relatório final

1. Arquivos alterados
2. Antes/depois:
   - Contagem de `try/except` em endpoints
   - Contagem de `HTTPException` manual
   - Linhas removidas (esperar redução líquida)
3. Saída de `ruff check app/api/`
4. Resultado de `pytest tests/api/`
5. Lista de endpoints que ainda têm try/except, com justificativa (a/b/c do passo 3)

## Critério de conclusão

- [ ] Endpoints não capturam `Exception` genérico
- [ ] `HTTPException` manual reduzido a casos justificados (auth dependencies)
- [ ] Erros retornam envelope canônico `{"error": {"code", "message", "context"}}`
- [ ] Teste `test_error_responses.py` passando
- [ ] Pare. Não commite.
