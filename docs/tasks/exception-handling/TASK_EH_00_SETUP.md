# TASK_EH_00 — Setup da infraestrutura canônica de tratamento de exceções

## Objetivo

Criar a base que sustenta a refatoração retroativa: hierarquia de exceções, handlers FastAPI globais, configuração de linter e documento normativo. **Nenhum código existente é alterado nesta task** — só criação de arquivos novos e ajuste de `pyproject.toml` e `backend/app/main.py`.

## Pré-condições

- Branch limpa criada a partir de `master`: `git checkout -b feat/exception-handling-canonical`
- `pytest` e `ruff` rodando sem erro hoje (snapshot do baseline)
- Confirme que `backend/app/core/` existe (criar se não existir)

## Passo 1 — Criar `backend/app/core/exceptions.py`

```python
"""Hierarquia canônica de exceções do GCA.

Toda exceção lançada por código de domínio do GCA DEVE ser subclasse de
GCAException. Exceções de bibliotecas externas (SQLAlchemy, httpx, anthropic, etc)
devem ser capturadas e re-lançadas como subclasse apropriada via `raise ... from e`.
"""
from __future__ import annotations
from typing import Any


class GCAException(Exception):
    """Raiz de toda exceção de domínio do GCA."""

    code: str = "GCA_INTERNAL_ERROR"
    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}
        if cause is not None:
            self.__cause__ = cause

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "context": self.context,
        }


class ValidationError(GCAException):
    """Dados de entrada inválidos (formato, tipo, schema)."""
    code = "GCA_VALIDATION_ERROR"
    http_status = 400


class AuthenticationError(GCAException):
    """Credenciais ausentes ou inválidas."""
    code = "GCA_AUTH_ERROR"
    http_status = 401


class AuthorizationError(GCAException):
    """Usuário autenticado mas sem permissão para o recurso."""
    code = "GCA_FORBIDDEN"
    http_status = 403


class NotFoundError(GCAException):
    """Recurso não encontrado."""
    code = "GCA_NOT_FOUND"
    http_status = 404


class ConflictError(GCAException):
    """Conflito de estado (ex: unique violation, optimistic lock)."""
    code = "GCA_CONFLICT"
    http_status = 409


class DomainError(GCAException):
    """Regra de negócio violada."""
    code = "GCA_DOMAIN_ERROR"
    http_status = 422


class ExternalServiceError(GCAException):
    """Falha em serviço externo (HTTP, DB, fila, etc)."""
    code = "GCA_EXTERNAL_SERVICE"
    http_status = 502


class ConfigurationError(GCAException):
    """Configuração ausente ou inválida (env var, secret, settings)."""
    code = "GCA_CONFIG_ERROR"
    http_status = 500


class LLMError(ExternalServiceError):
    """Falha em chamada a provedor LLM (Anthropic, OpenAI, Gemini)."""
    code = "GCA_LLM_ERROR"


class CryptoError(GCAException):
    """Falha em operação criptográfica (Fernet, RSA, hash)."""
    code = "GCA_CRYPTO_ERROR"
    http_status = 500


class GatekeeperError(DomainError):
    """Código gerado reprovado pelo Gatekeeper."""
    code = "GCA_GATEKEEPER_REJECTED"
```

## Passo 2 — Criar `backend/app/core/error_handlers.py`

```python
"""Handlers globais de exceção para FastAPI."""
from __future__ import annotations
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import GCAException

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Registra handlers globais. Chamar uma vez em main.py após criar o app."""

    @app.exception_handler(GCAException)
    async def gca_exception_handler(request: Request, exc: GCAException) -> JSONResponse:
        logger.exception(
            "gca_exception",
            extra={
                "code": exc.code,
                "context": exc.context,
                "path": str(request.url.path),
                "method": request.method,
            },
        )
        return JSONResponse(
            status_code=exc.http_status,
            content={"error": exc.to_dict()},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_exception",
            extra={
                "path": str(request.url.path),
                "method": request.method,
                "exception_type": type(exc).__name__,
            },
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "GCA_UNHANDLED",
                    "message": "Internal server error",
                    "context": {},
                }
            },
        )
```

## Passo 3 — Integrar handlers em `backend/app/main.py`

Localize a criação do `FastAPI(...)` e adicione **logo após**:

```python
from app.core.error_handlers import register_exception_handlers

app = FastAPI(...)  # já existente
register_exception_handlers(app)  # NOVA LINHA
```

## Passo 4 — Atualizar `pyproject.toml`

Localize a seção `[tool.ruff.lint]` (criar se não existir) e garantir:

```toml
[tool.ruff.lint]
select = [
    "E", "F", "W", "B",
    "BLE",   # blind-except
    "TRY",   # tryceratops
    "LOG",   # logging best-practices
    "G",     # logging-format
    "RET",   # return inconsistente
]
ignore = [
    "TRY003",  # permitir mensagens longas em raise
    "TRY300",  # else-block é estilo, não obrigatório
]

[tool.ruff.lint.per-file-ignores]
"backend/tests/**" = ["BLE", "TRY"]
"backend/alembic/**" = ["BLE", "TRY"]
```

## Passo 5 — Criar `docs/conventions/exception-handling.md`

```markdown
# Convenção canônica de tratamento de exceções — GCA

Documento normativo. Aplica-se a todo código Python do backend e a todo
código gerado pelo CodeGen.

## Regras absolutas

1. **Nunca** usar `except:` (captura `KeyboardInterrupt`, `SystemExit`).
2. **Nunca** usar `except Exception:` sem re-lançar via `raise ... from e`.
3. **Nunca** usar `pass`, `return None` ou logs `debug`/`info` dentro de `except`.
4. **Sempre** usar `logger.exception("evento_snake_case", extra={...})` no except.
5. **Sempre** preservar a causa original com `raise ... from e`.
6. **Sempre** lançar subclasse de `app.core.exceptions.GCAException` em código de domínio.
7. **Nunca** formatar resposta HTTP em service — apenas lançar; o handler global formata.

## Operações que OBRIGATORIAMENTE precisam de try/except

- Chamadas HTTP (httpx, requests, aiohttp)
- Queries SQL (SQLAlchemy session, execute, commit)
- Leitura/escrita de arquivo (open, Path.read_*, Path.write_*)
- Chamadas a LLM (anthropic, openai, google.generativeai)
- subprocess (run, Popen, check_output)
- Operações criptográficas (Fernet, RSA, hashlib quando lê de fonte externa)
- Parsing externo (json.loads de input, yaml.safe_load, xml.etree)

## Padrão de referência

```python
from app.core.exceptions import ExternalServiceError, NotFoundError
import logging

logger = logging.getLogger(__name__)

async def get_user_repo(repo_id: int) -> Repo:
    try:
        repo = await db.get(Repo, repo_id)
    except SQLAlchemyError as e:
        logger.exception("db_get_repo_failed", extra={"repo_id": repo_id})
        raise ExternalServiceError(
            "falha ao consultar banco",
            context={"repo_id": repo_id},
            cause=e,
        ) from e

    if repo is None:
        raise NotFoundError("repo não encontrado", context={"repo_id": repo_id})

    return repo
```

## Anti-padrões (PROIBIDOS)

```python
# ❌ silencioso
try:
    do_thing()
except Exception:
    pass

# ❌ retorna None mascarando erro
try:
    return do_thing()
except Exception:
    return None

# ❌ perde traceback
try:
    do_thing()
except ValueError as e:
    raise DomainError(str(e))  # falta `from e`

# ❌ logger.error não anexa stack
try:
    do_thing()
except ValueError as e:
    logger.error(f"falhou: {e}")  # deveria ser logger.exception(...)
    raise

# ❌ except cego
try:
    do_thing()
except:
    raise
```

## Checagem automática

- `ruff check` bloqueia bare except, blind except sem re-raise, log incorreto.
- O pilar Conformidade do Gatekeeper roda check AST adicional em código gerado.
```

## Passo 6 — Criar check AST do Gatekeeper em `backend/app/gatekeeper/checks/exception_handling.py`

```python
"""Check AST para o pilar Conformidade do Gatekeeper.

Detecta violações da convenção docs/conventions/exception-handling.md
em código Python (escrito ou gerado pelo CodeGen).
"""
from __future__ import annotations
import ast
from typing import TypedDict


class Issue(TypedDict):
    line: int
    code: str
    message: str
    severity: str


def _has_raise(node: ast.ExceptHandler) -> bool:
    """True se o except contém um `raise` (re-lançamento ou novo)."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Raise):
            return True
    return False


def _is_only_pass(node: ast.ExceptHandler) -> bool:
    return len(node.body) == 1 and isinstance(node.body[0], ast.Pass)


def _is_only_return_none(node: ast.ExceptHandler) -> bool:
    if len(node.body) != 1:
        return False
    stmt = node.body[0]
    if not isinstance(stmt, ast.Return):
        return False
    return stmt.value is None or (
        isinstance(stmt.value, ast.Constant) and stmt.value.value is None
    )


def check_source(source: str, filename: str = "<string>") -> list[Issue]:
    """Analisa código-fonte Python e retorna lista de violações."""
    issues: list[Issue] = []
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        return [{
            "line": e.lineno or 0,
            "code": "EH000",
            "message": f"syntax error: {e.msg}",
            "severity": "error",
        }]

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue

        # EH001 — bare except
        if node.type is None:
            issues.append({
                "line": node.lineno,
                "code": "EH001",
                "message": "bare `except:` é proibido — capture exceção específica",
                "severity": "error",
            })
            continue

        # EH002 — except Exception sem raise
        is_blind = (
            isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException")
        )
        if is_blind and not _has_raise(node):
            issues.append({
                "line": node.lineno,
                "code": "EH002",
                "message": "`except Exception` sem re-raise — re-lance via `raise ... from e`",
                "severity": "error",
            })

        # EH003 — pass silencioso
        if _is_only_pass(node):
            issues.append({
                "line": node.lineno,
                "code": "EH003",
                "message": "`except: pass` mascara erro — logue e re-lance",
                "severity": "error",
            })

        # EH004 — return None silencioso
        if _is_only_return_none(node):
            issues.append({
                "line": node.lineno,
                "code": "EH004",
                "message": "`return None` silencioso em except — logue e re-lance",
                "severity": "error",
            })

    return issues


def check_file(path: str) -> list[Issue]:
    with open(path, encoding="utf-8") as f:
        return check_source(f.read(), filename=path)
```

E o teste em `backend/tests/gatekeeper/test_exception_handling_check.py`:

```python
from app.gatekeeper.checks.exception_handling import check_source


def test_bare_except_detected():
    code = "try:\n    x()\nexcept:\n    pass\n"
    issues = check_source(code)
    codes = {i["code"] for i in issues}
    assert "EH001" in codes


def test_blind_except_without_raise_detected():
    code = "try:\n    x()\nexcept Exception:\n    print('oops')\n"
    issues = check_source(code)
    assert any(i["code"] == "EH002" for i in issues)


def test_blind_except_with_raise_passes():
    code = (
        "try:\n    x()\nexcept Exception as e:\n"
        "    logger.exception('failed')\n    raise\n"
    )
    issues = check_source(code)
    assert not any(i["code"] == "EH002" for i in issues)


def test_pass_silencioso_detected():
    code = "try:\n    x()\nexcept ValueError:\n    pass\n"
    issues = check_source(code)
    assert any(i["code"] == "EH003" for i in issues)


def test_return_none_silencioso_detected():
    code = "def f():\n    try:\n        return x()\n    except ValueError:\n        return None\n"
    issues = check_source(code)
    assert any(i["code"] == "EH004" for i in issues)


def test_specific_except_with_raise_passes():
    code = (
        "try:\n    x()\nexcept ValueError as e:\n"
        "    logger.exception('bad value')\n"
        "    raise DomainError('invalid') from e\n"
    )
    issues = check_source(code)
    assert issues == []
```

## Passo 7 — Validação

```bash
cd backend
ruff check app/core/exceptions.py app/core/error_handlers.py
pytest tests/gatekeeper/test_exception_handling_check.py -v
ruff check .  # snapshot completo — anote quantas violações existem hoje
```

Salve o output de `ruff check .` em `docs/conventions/baseline_violations.txt` para comparação posterior.

## Critério de conclusão

- [ ] `backend/app/core/exceptions.py` criado
- [ ] `backend/app/core/error_handlers.py` criado
- [ ] `backend/app/main.py` chamando `register_exception_handlers(app)`
- [ ] `pyproject.toml` com regras ruff atualizadas
- [ ] `docs/conventions/exception-handling.md` criado
- [ ] `backend/app/gatekeeper/checks/exception_handling.py` criado
- [ ] `backend/tests/gatekeeper/test_exception_handling_check.py` passando (6 testes)
- [ ] Baseline de violações salvo em `docs/conventions/baseline_violations.txt`
- [ ] Aplicação sobe sem erro (`uvicorn app.main:app`)

## Não fazer

- Não refatorar nenhum service, api, model, integration ou codegen nesta task.
- Não fazer commit ainda — pare e aguarde revisão.
