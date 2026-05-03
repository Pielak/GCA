# TASK_EH_05 — Refatoração do CodeGen + propagação do paradigma para código gerado

## Pré-condição

TASK_EH_04 concluída e commitada.

## Objetivo

Esta task tem **dois escopos**:

**A.** Refatorar o módulo `backend/app/codegen/` em si para seguir a convenção (como qualquer outro módulo do GCA).

**B.** Garantir que **todo código gerado pelo CodeGen** siga o mesmo paradigma — via instruções no prompt do agente Desenvolvedor, templates atualizados e check AST do Gatekeeper integrado ao pilar Conformidade.

Esta é a task mais sensível: o GCA é "um sistema que cria sistemas" — qualquer falha aqui propaga o anti-padrão para todo cliente que usar o CodeGen.

---

## Parte A — Refatorar o próprio módulo CodeGen

### A.1 Inventário

```bash
cd backend
grep -rn "except:\|except Exception" app/codegen/ > /tmp/eh_codegen_inventory.md
find app/codegen -name "*.py" -exec grep -l "anthropic\|openai" {} \; >> /tmp/eh_codegen_inventory.md
```

### A.2 Aplicar convenção

Mesmo procedimento das tasks 01–04. Pontos específicos:

- Chamadas LLM no CodeGen → `LLMError`
- Falha de parsing do código gerado (AST) → `GatekeeperError` ou `DomainError`
- Falha de integração com Git (clone, push, branch) → `ExternalServiceError`
- Falha de carregamento de template → `ConfigurationError`
- Reprovação por pilar do Gatekeeper → `GatekeeperError` com contexto `{"pillar": ..., "score": ..., "issues": [...]}`

### A.3 Validação

```bash
cd backend
ruff check app/codegen/
pytest tests/codegen/ -v
```

---

## Parte B — Propagação do paradigma para código gerado

### B.1 Atualizar system prompt do agente Desenvolvedor

Localizar o prompt do agente Desenvolvedor em `backend/app/codegen/prompts/` (nome típico: `developer_agent.py`, `developer_prompt.md`, ou similar). Adicionar **bloco normativo não-negociável** ao final do system prompt:

```text
═══════════════════════════════════════════════════════════════════════
PILAR DE GERAÇÃO — TRATAMENTO DE EXCEÇÕES (obrigatório, verificado por Gatekeeper)
═══════════════════════════════════════════════════════════════════════

Toda função gerada que execute UMA OU MAIS das operações abaixo DEVE ter
tratamento canônico de exceções:

OPERAÇÕES QUE EXIGEM TRY/EXCEPT:
- Chamada HTTP (httpx, requests, aiohttp, fetch)
- Query SQL (SQLAlchemy, asyncpg, raw cursor)
- Leitura/escrita de arquivo (open, Path, fs)
- Chamada a LLM (anthropic, openai, google.generativeai)
- subprocess / exec
- Operações criptográficas (Fernet, RSA, hashlib em fonte externa)
- Parsing de input externo (json.loads, yaml.safe_load, xml)

PADRÃO OBRIGATÓRIO (Python):

    try:
        resultado = operacao(x)
    except ExcecaoEspecifica as e:
        logger.exception("evento_snake_case", extra={"contexto": valor})
        raise SubclasseGCAException(
            "mensagem clara",
            context={"campo": valor},
            cause=e,
        ) from e

PROIBIDO (Gatekeeper bloqueia merge):
- `except:` (bare)
- `except Exception:` sem re-raise
- `pass` dentro de except
- `return None` / `return False` / `return []` mascarando erro
- `logger.error(f"...{e}")` em except (deve ser `logger.exception(...)`)

HIERARQUIA DE EXCEÇÕES:
Quando o projeto-alvo já tiver `core/exceptions.py` com hierarquia GCAException,
USE-A. Quando não tiver, GERE uma `core/exceptions.py` espelhando o padrão GCA
ANTES de gerar qualquer service/repository/integration.

A hierarquia mínima deve conter:
- BaseException de raiz (AppException ou similar)
- ValidationError (HTTP 400)
- AuthenticationError (HTTP 401)
- AuthorizationError (HTTP 403)
- NotFoundError (HTTP 404)
- ConflictError (HTTP 409)
- DomainError (HTTP 422)
- ExternalServiceError (HTTP 502)
- ConfigurationError (HTTP 500)

E handlers globais FastAPI registrados via `register_exception_handlers(app)`.

MAPEAMENTO PADRÃO (lib externa → exceção do projeto):
- SQLAlchemyError em SELECT       → ExternalServiceError
- IntegrityError                  → ConflictError
- NoResultFound / get() == None   → NotFoundError
- httpx 4xx (não-auth)            → ValidationError
- httpx 401/403                   → AuthenticationError/AuthorizationError
- httpx 5xx ou RequestError       → ExternalServiceError
- anthropic/openai APIError       → LLMError (subclasse de ExternalServiceError)
- FileNotFoundError               → NotFoundError ou ConfigurationError
- json.JSONDecodeError            → ValidationError
- KeyError em config              → ConfigurationError

ESTE BLOCO É VERIFICADO POR CHECK AST AUTOMÁTICO. Código que viole as regras
é REJEITADO pelo Gatekeeper (pilar Conformidade) com score 0 nesse pilar,
bloqueando merge mesmo se outros pilares passarem.
═══════════════════════════════════════════════════════════════════════
```

### B.2 Atualizar templates de scaffold

Localizar templates em `backend/app/codegen/templates/` (Jinja2, Cookiecutter, ou strings). Para cada template que gere:

**a.** `core/exceptions.py` — incluir hierarquia base (copiar template do passo B.4)

**b.** `core/error_handlers.py` — incluir registro de handlers FastAPI (copiar template)

**c.** `main.py` — chamar `register_exception_handlers(app)` logo após criar o `FastAPI()`

**d.** `services/*.py` boilerplate — usar try/except canônico já no exemplo gerado

**e.** `pyproject.toml` — incluir regras ruff (BLE, TRY, LOG, G, RET)

### B.3 Integrar check AST ao pilar Conformidade

Localizar o orquestrador do Gatekeeper em `backend/app/gatekeeper/` (típico: `gatekeeper.py`, `evaluator.py`, ou `pillars/conformidade.py`).

Adicionar a chamada ao check criado em TASK_EH_00:

```python
from app.gatekeeper.checks.exception_handling import check_source

class ConformidadePillar:
    BLOCKING_THRESHOLD = 60

    async def evaluate(self, generated_code: str, file_path: str) -> PillarResult:
        issues: list[Issue] = []

        # ... outras checagens existentes do pilar ...

        # NOVO: tratamento de exceções
        eh_issues = check_source(generated_code, filename=file_path)
        for issue in eh_issues:
            issues.append({
                **issue,
                "category": "exception_handling",
                "weight": 25,  # peso alto — anti-padrão crítico
            })

        score = self._compute_score(issues)
        return PillarResult(
            pillar="conformidade",
            score=score,
            blocking=score < self.BLOCKING_THRESHOLD,
            issues=issues,
        )
```

Cada violação `EH001/EH002/EH003/EH004` deve subtrair pelo menos 25 pontos do score, garantindo que mesmo uma única violação derrube o pilar abaixo do threshold de 60 (assumindo score inicial 100).

### B.4 Templates a salvar em `backend/app/codegen/templates/exception_handling/`

Criar três arquivos que são copiados literalmente para projetos gerados:

**Template 1 — `templates/exception_handling/exceptions.py.tmpl`:**

(Conteúdo idêntico ao `backend/app/core/exceptions.py` da TASK_EH_00, com placeholder do prefixo do projeto se necessário — ex: `{{PROJECT_PREFIX}}_VALIDATION_ERROR`)

**Template 2 — `templates/exception_handling/error_handlers.py.tmpl`:**

(Conteúdo idêntico ao `backend/app/core/error_handlers.py` da TASK_EH_00)

**Template 3 — `templates/exception_handling/ruff_rules.toml.tmpl`:**

```toml
[tool.ruff.lint]
select = ["E", "F", "W", "B", "BLE", "TRY", "LOG", "G", "RET"]
ignore = ["TRY003", "TRY300"]
```

### B.5 Teste end-to-end de propagação

Criar `backend/tests/codegen/test_generated_code_compliance.py`:

```python
"""Garante que código gerado pelo CodeGen segue a convenção de exceções."""
import pytest
from app.codegen.orchestrator import CodeGenOrchestrator
from app.gatekeeper.checks.exception_handling import check_source


@pytest.mark.asyncio
async def test_generated_service_with_db_call_has_try_except():
    orchestrator = CodeGenOrchestrator()
    code = await orchestrator.generate(
        spec="Crie um service que busque usuário por ID no banco PostgreSQL",
        target_layer="service",
    )
    issues = check_source(code)
    assert issues == [], f"código gerado violou convenção: {issues}"
    assert "try:" in code
    assert "raise" in code
    assert "from e" in code


@pytest.mark.asyncio
async def test_generated_http_client_has_proper_mapping():
    orchestrator = CodeGenOrchestrator()
    code = await orchestrator.generate(
        spec="Cliente HTTP que chama API externa /users",
        target_layer="integration",
    )
    issues = check_source(code)
    assert issues == []
    # esperar mapeamento httpx → ExternalServiceError
    assert "ExternalServiceError" in code or "AppException" in code


@pytest.mark.asyncio
async def test_gatekeeper_rejects_code_with_bare_except():
    bad_code = "def f():\n    try:\n        x()\n    except:\n        pass\n"
    from app.gatekeeper.pillars.conformidade import ConformidadePillar
    pillar = ConformidadePillar()
    result = await pillar.evaluate(bad_code, "test.py")
    assert result.blocking is True
    assert result.score < 60
```

### B.6 Validação final integrada

```bash
cd backend
ruff check app/codegen/
pytest tests/codegen/ -v
pytest tests/gatekeeper/ -v

# Smoke test: gerar um service real e validar
python -m app.codegen.cli generate --spec "service de busca de produto por id" --layer service > /tmp/generated.py
python -c "from app.gatekeeper.checks.exception_handling import check_source; import sys; print(check_source(open('/tmp/generated.py').read()))"
# deve imprimir: []
```

---

## Relatório final

1. **Parte A** — arquivos do CodeGen alterados, antes/depois, ruff, pytest
2. **Parte B**:
   - Diff do system prompt do agente Desenvolvedor
   - Lista de templates atualizados
   - Confirmação de integração no pilar Conformidade
   - Resultado de `test_generated_code_compliance.py`
   - Output do smoke test (geração real + validação)
3. **Casos limite identificados**:
   - Código gerado em outras linguagens (TypeScript, Java, Go, Rust) — esta task só cobre Python; abrir TASK_EH_06 para multilinguagem se aplicável
   - Templates legados que ainda não foram convertidos
4. **Plano de migração de projetos já gerados**: para cada projeto cliente que foi criado **antes** desta refatoração, o CodeGen agora deve oferecer comando `gca refactor exceptions` que aplica a convenção retroativamente.

## Critério de conclusão

- [ ] Módulo `app/codegen/` refatorado e ruff/pytest limpos
- [ ] System prompt do agente Desenvolvedor com bloco normativo
- [ ] Templates de scaffold gerando hierarquia + handlers + ruff rules
- [ ] Check AST integrado ao pilar Conformidade com peso ≥25
- [ ] Smoke test: código gerado real passa em `check_source` com lista vazia
- [ ] Documentado: comando de migração para projetos legados (mesmo que ainda não implementado)
- [ ] Pare. Não commite. Aguarde revisão final antes de mergear toda a branch `feat/exception-handling-canonical`.
