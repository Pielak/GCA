# TASK_EH_01 — Refatoração retroativa: `backend/app/services/`

## Pré-condição

TASK_EH_00 concluída e commitada. Branch atual: `feat/exception-handling-canonical`.

## Objetivo

Aplicar a convenção `docs/conventions/exception-handling.md` retroativamente em **todo o diretório** `backend/app/services/`. Não alterar lógica de negócio nem assinaturas — apenas fluxo de erro.

## Procedimento estrito

### 1. Inventário inicial

Antes de qualquer alteração, gerar inventário e salvar em `/tmp/eh_services_inventory.md`:

```bash
cd backend
echo "## Bare except" > /tmp/eh_services_inventory.md
grep -rn "except:" app/services/ >> /tmp/eh_services_inventory.md || true

echo -e "\n## Except Exception" >> /tmp/eh_services_inventory.md
grep -rn "except Exception" app/services/ >> /tmp/eh_services_inventory.md || true

echo -e "\n## pass em except" >> /tmp/eh_services_inventory.md
grep -rn -A1 "except.*:" app/services/ | grep -B1 "pass" >> /tmp/eh_services_inventory.md || true

echo -e "\n## logger.error (deveria ser exception)" >> /tmp/eh_services_inventory.md
grep -rn "logger.error\|logging.error" app/services/ >> /tmp/eh_services_inventory.md || true
```

Mostrar contagem de cada categoria antes de começar a refatoração.

### 2. Refatoração arquivo por arquivo

Para cada `.py` em `app/services/`:

**a.** Identificar todas as funções que executam I/O (HTTP, SQL, leitura de arquivo, chamada LLM, subprocess, parsing externo) e que **não** têm try/except. Adicionar try/except específico.

**b.** Para cada `except:` ou `except Exception:`:
   - Trocar por exceção específica do tipo de operação:
     - SQLAlchemy: `SQLAlchemyError`, `IntegrityError`, `OperationalError`
     - httpx: `httpx.HTTPStatusError`, `httpx.RequestError`, `httpx.TimeoutException`
     - Anthropic SDK: `anthropic.APIError`, `anthropic.RateLimitError`, `anthropic.APITimeoutError`
     - OpenAI SDK: `openai.APIError`, `openai.RateLimitError`
     - File I/O: `OSError`, `FileNotFoundError`, `PermissionError`
     - JSON: `json.JSONDecodeError`
     - Crypto/Fernet: `cryptography.fernet.InvalidToken`, `cryptography.exceptions.InvalidSignature`
   - Se a função realmente precisa capturar genérico (raro — só em workers de fila e topo de scheduler), manter `except Exception` mas **com re-raise obrigatório**.

**c.** Dentro do except:
   - Adicionar `logger.exception("evento_snake_case", extra={...contexto relevante...})`
   - Re-lançar como subclasse de `GCAException` apropriada via `raise NovaExc(...) from e`

**d.** Remover qualquer `pass`, `return None`, `return False`, `return []` que estejam mascarando erros silenciosos. Se o caller espera `None` para "não encontrado", lançar `NotFoundError` e o caller trata.

**e.** Trocar `logger.error(f"...{e}")` por `logger.exception("...")` (sem o `{e}` — o stack já vem anexado).

### 3. Mapeamento de exceções → GCAException

Usar esta tabela como guia:

| Exceção original | Re-lançar como |
|---|---|
| `SQLAlchemyError` em SELECT | `ExternalServiceError` |
| `IntegrityError` (unique/FK) | `ConflictError` |
| `NoResultFound` | `NotFoundError` |
| `httpx.HTTPStatusError` 4xx (não-auth) | `ValidationError` ou `DomainError` |
| `httpx.HTTPStatusError` 401/403 | `AuthenticationError` / `AuthorizationError` |
| `httpx.HTTPStatusError` 5xx | `ExternalServiceError` |
| `httpx.RequestError` / `TimeoutException` | `ExternalServiceError` |
| `anthropic.APIError` / `openai.APIError` | `LLMError` |
| `anthropic.RateLimitError` | `LLMError` (com context `{"retry_after": ...}`) |
| `FileNotFoundError` | `NotFoundError` ou `ConfigurationError` (se config) |
| `PermissionError` | `ConfigurationError` |
| `json.JSONDecodeError` | `ValidationError` |
| `InvalidToken` (Fernet) | `CryptoError` |
| `KeyError` em config/env | `ConfigurationError` |
| `ValueError` em parse de input | `ValidationError` |

### 4. Não alterar

- Assinaturas de função (parâmetros, tipo de retorno do happy path)
- Lógica de negócio
- Nomes de funções e classes
- Imports não relacionados a logging/exceptions

### 5. Validação após cada arquivo

```bash
cd backend
ruff check app/services/<arquivo>.py
mypy app/services/<arquivo>.py 2>&1 | tail -20
```

### 6. Validação final

```bash
cd backend
ruff check app/services/
pytest tests/services/ -v --tb=short
mypy app/services/ 2>&1 | tail -50
```

### 7. Ajuste de testes

Se algum teste quebrar porque agora a exceção lançada mudou de tipo (ex: era `Exception`, agora é `ExternalServiceError`):

- **Sempre** ajustar o teste para esperar a nova exceção da hierarquia GCA.
- **Nunca** reverter a refatoração para "passar o teste".
- Se o teste original verificava que a função retornava `None` em caso de erro, o teste deve ser reescrito para verificar que a exceção correta é lançada.

## Relatório final (obrigatório, antes do commit)

Apresente em formato markdown:

1. **Arquivos alterados** (lista com path)
2. **Antes/depois**:
   - Contagem de `except:` (bare)
   - Contagem de `except Exception` sem re-raise
   - Contagem de `pass` em except
   - Contagem de `return None` silencioso em except
   - Contagem de `logger.error` em except (deveria ser `logger.exception`)
3. **Saída de `ruff check app/services/`** (deve estar limpa nas regras BLE/TRY/LOG)
4. **Resultado de `pytest tests/services/`** (X passed, Y failed, Z skipped)
5. **Lista de testes ajustados** (com motivo)
6. **Quaisquer casos ambíguos** onde você não teve certeza qual exceção GCA usar — listar para revisão humana

## Critério de conclusão

- [ ] Zero `except:` bare em `app/services/`
- [ ] Zero `except Exception` sem re-raise em `app/services/`
- [ ] Zero `pass` ou `return None` silencioso em except
- [ ] Todo except chama `logger.exception(...)` antes de re-lançar
- [ ] `ruff check app/services/` limpo nas regras de exceção
- [ ] `pytest tests/services/` passando (testes ajustados quando necessário)
- [ ] Relatório final apresentado

## Não fazer

- Não fazer commit. Pare e aguarde revisão humana.
- Não tocar em `app/api/`, `app/models/`, `app/integrations/` ou `app/codegen/` — cada um tem sua task própria.
