# TASK_EH_03 — Refatoração retroativa: `backend/app/models/` e camada de persistência

## Pré-condição

TASK_EH_02 concluída e commitada.

## Objetivo

Aplicar a convenção em models SQLAlchemy, repositórios e queries. **Característica especial**: este módulo é onde mais aparecem `try/except` mascarando `IntegrityError`, `OperationalError` e `NoResultFound`. Mapeamento correto aqui evita corrupção de dados.

## Escopo

- `backend/app/models/` (SQLAlchemy models, mixins)
- `backend/app/repositories/` (se existir)
- Qualquer arquivo que faça `db.execute`, `db.commit`, `db.refresh`, `session.add` fora de services

## Procedimento

### 1. Inventário

```bash
cd backend
grep -rn "except:\|except Exception\|except SQLAlchemy\|except Integrity" app/models/ app/repositories/ 2>/dev/null > /tmp/eh_models_inventory.md
grep -rn "session.commit\|db.commit\|session.flush" app/models/ app/repositories/ 2>/dev/null >> /tmp/eh_models_inventory.md
```

### 2. Padrão para repositórios

**Antes:**

```python
def create_repo(db: Session, data: dict) -> Repo | None:
    try:
        repo = Repo(**data)
        db.add(repo)
        db.commit()
        db.refresh(repo)
        return repo
    except Exception as e:
        db.rollback()
        logger.error(f"erro: {e}")
        return None
```

**Depois:**

```python
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app.core.exceptions import ConflictError, ExternalServiceError

def create_repo(db: Session, data: dict) -> Repo:
    repo = Repo(**data)
    db.add(repo)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.exception("repo_create_integrity_violation", extra={"data": data})
        raise ConflictError(
            "repositório já existe ou viola constraint",
            context={"data": data},
            cause=e,
        ) from e
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("repo_create_db_error", extra={"data": data})
        raise ExternalServiceError(
            "falha ao persistir repositório",
            context={"data": data},
            cause=e,
        ) from e
    db.refresh(repo)
    return repo
```

### 3. Padrão para SELECT

```python
from sqlalchemy.exc import SQLAlchemyError
from app.core.exceptions import ExternalServiceError, NotFoundError

def get_repo(db: Session, repo_id: int) -> Repo:
    try:
        repo = db.get(Repo, repo_id)
    except SQLAlchemyError as e:
        logger.exception("repo_get_db_error", extra={"repo_id": repo_id})
        raise ExternalServiceError(
            "falha ao consultar repositório",
            context={"repo_id": repo_id},
            cause=e,
        ) from e

    if repo is None:
        raise NotFoundError("repositório não encontrado", context={"repo_id": repo_id})
    return repo
```

Note: assinatura mudou de `Repo | None` para `Repo`. Callers que dependiam do `None` precisam ser atualizados para tratar `NotFoundError` (geralmente isso já acontece no service, ou a propagação até o handler global já está correta).

### 4. Padrão para UPDATE / DELETE

Mesmo de CREATE: `IntegrityError` → `ConflictError`, `SQLAlchemyError` → `ExternalServiceError`. Se o registro alvo não existe antes do UPDATE, lançar `NotFoundError`.

### 5. Bulk operations e flush

Em operações bulk com `flush()`:

```python
try:
    db.bulk_save_objects(items)
    db.flush()
except IntegrityError as e:
    db.rollback()
    logger.exception("bulk_insert_integrity", extra={"count": len(items)})
    raise ConflictError("violação em insert em massa", cause=e) from e
except SQLAlchemyError as e:
    db.rollback()
    logger.exception("bulk_insert_db_error", extra={"count": len(items)})
    raise ExternalServiceError("falha em insert em massa", cause=e) from e
```

### 6. Listeners e event handlers SQLAlchemy

Listeners (`@event.listens_for(...)`) **não devem** capturar exceções genericamente — deixe propagar para que a transação faça rollback. Se houver lógica que precisa rodar mesmo em erro, usar `after_rollback` event.

### 7. Models propriamente ditos

Em `app/models/*.py`, classes `Mapped` puras geralmente **não têm** try/except. Se houver, é provavelmente em métodos de domínio (`@hybrid_property`, validators) — manter padrão da convenção.

Validators do SQLAlchemy (`@validates`) devem lançar `ValidationError` em vez de `ValueError`:

```python
from sqlalchemy.orm import validates
from app.core.exceptions import ValidationError

class User(Base):
    email: Mapped[str]

    @validates("email")
    def validate_email(self, key, value):
        if "@" not in value:
            raise ValidationError("email inválido", context={"email": value})
        return value
```

### 8. Validação

```bash
cd backend
ruff check app/models/ app/repositories/ 2>/dev/null
pytest tests/models/ tests/repositories/ -v 2>/dev/null
mypy app/models/ 2>&1 | tail -20
```

### 9. Verificação de regressão funcional

Rodar suite completa:

```bash
pytest -q
```

Esperar quebras pontuais em testes que esperavam `None` para "não encontrado". Ajustar testes para esperar `NotFoundError`.

## Relatório final

1. Arquivos alterados
2. Antes/depois das contagens (mesmo template das tasks anteriores)
3. **Lista de assinaturas alteradas** (de `T | None` para `T`) — revisão manual necessária
4. **Lista de callers que precisaram ser atualizados** em consequência das assinaturas
5. Saída de ruff e pytest
6. Quaisquer casos onde o repositório original retornava lista vazia mascarando erro de DB — agora deve lançar `ExternalServiceError`

## Critério de conclusão

- [ ] Toda operação de DB com `commit()`, `flush()`, `execute()` está em try/except específico
- [ ] `IntegrityError` mapeado para `ConflictError`
- [ ] `SQLAlchemyError` genérico mapeado para `ExternalServiceError`
- [ ] `db.rollback()` chamado em todos os paths de erro de write
- [ ] Funções "get" lançam `NotFoundError` em vez de retornar `None`
- [ ] `@validates` lançam `ValidationError`
- [ ] `pytest -q` verde (após ajuste de testes)
- [ ] Pare. Não commite.
