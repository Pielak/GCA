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
