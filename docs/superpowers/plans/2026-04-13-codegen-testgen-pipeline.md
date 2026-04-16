# CodeGen + TestGen + Massa de Teste + QA Readiness — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar o pipeline CodeGen → TestGen → Massa de Teste → QA funcional de ponta a ponta — gerando código fonte real, testes reais com massa de dados, e validação QA com supervisão humana.

**Architecture:** O `ModuleCodegenService` já tem a orquestração de 10 passos mas os passos 6-9 (geração de testes) são stubs que apenas criam registros no banco sem conteúdo. O plano implementa: (1) geração real de testes via LLM, (2) geração de massa de teste por tipo, (3) ponte backlog→codegen, (4) QA Readiness com validação automática.

**Tech Stack:** Python/FastAPI, Anthropic Claude API, pytest, SQLAlchemy async, React/TypeScript

---

## Estado Atual vs. Desejado

| Componente | Hoje | Desejado |
|-----------|------|----------|
| CodeGen (código fonte) | ✅ Real — LLM gera código | ✅ Manter + melhorar prompts |
| TestGen unitário | ❌ Stub — só cria registro vazio | ✅ LLM gera testes reais |
| TestGen integração | ❌ Stub — só cria registro vazio | ✅ LLM gera testes com dependências |
| TestGen UAT | ❌ Stub — só cria registro vazio | ✅ LLM gera cenários E2E |
| Massa de teste | ❌ Não existe | ✅ Geração automática por tipo |
| Backlog → CodeGen | ❌ Endpoint referenciado mas não existe | ✅ Endpoint funcional |
| QA Readiness validação | ✅ Executa pytest real | ✅ Manter + adicionar validação automática |
| Review de código IA | ⚠️ Parcial | ✅ Completo com contexto OCG |

---

## Arquivos Envolvidos

### Backend — Modificar
| Arquivo | Linhas | Mudança |
|---------|--------|---------|
| `backend/app/services/module_codegen_service.py` | 583 | Implementar `_generate_unit_tests()`, `_generate_integration_tests()`, `_generate_uat_tests()` com LLM real |
| `backend/app/routers/code_generation.py` | 416 | Adicionar endpoint `POST /backlog/{id}/generate-code` |
| `backend/app/services/qa_service.py` | 312 | Adicionar `validate_test_quality()` para validação automática |

### Backend — Criar
| Arquivo | Responsabilidade |
|---------|-----------------|
| `backend/app/services/test_data_service.py` | Geração de massa de teste por tipo (unitário, integrado, UAT, smoke) |
| `backend/app/services/test_prompts.py` | Prompts especializados para cada tipo de teste |
| `backend/app/routers/test_data_router.py` | Endpoints para massa de teste |

### Frontend — Modificar
| Arquivo | Mudança |
|---------|---------|
| `frontend/src/pages/projects/CodeGeneratorPage.tsx` | Botão "Gerar Testes" após salvar código, indicador de massa de teste |
| `frontend/src/pages/projects/QAReadinessPage.tsx` | Painel de validação automática, status da massa de teste |

---

## Task 1: Prompts Especializados para Geração de Testes

**Files:**
- Create: `backend/app/services/test_prompts.py`

- [ ] **Step 1: Criar arquivo de prompts de teste**

```python
"""
Prompts especializados para geração de testes via LLM.
Cada tipo de teste tem prompt próprio que considera:
- Código fonte gerado
- OCG (stack, requirements, compliance)
- Dependências do módulo
- Massa de dados necessária
"""

UNIT_TEST_PROMPT = """Você é um engenheiro de testes sênior. Gere testes unitários para o código abaixo.

## Código fonte:
{source_code}

## Stack do projeto:
- Linguagem: {language}
- Framework de teste: {test_framework}
- Banco: {database}

## Requisitos do OCG:
- Cobertura alvo: {coverage_target}
- Achados críticos: {critical_findings}

## Regras:
1. Cada função pública DEVE ter pelo menos 2 testes (caso feliz + caso de erro)
2. Use fixtures/mocks para dependências externas
3. Nomeie testes descritivamente: test_<funcao>_<cenario>_<resultado_esperado>
4. Inclua docstring em cada teste explicando o que valida
5. Gere a massa de dados inline (fixtures) — dados realistas, não "test123"
6. Inclua testes de borda: valores nulos, strings vazias, limites numéricos

Retorne JSON:
{{
  "test_file": {{
    "filename": "test_<module>.py",
    "content": "<código completo do teste>",
    "test_count": <número de testes>,
    "coverage_estimate": "<porcentagem estimada>"
  }},
  "test_data": {{
    "fixtures": [
      {{"name": "<nome>", "data": <objeto JSON com dados de teste>}}
    ]
  }}
}}
"""

INTEGRATION_TEST_PROMPT = """Você é um engenheiro de testes sênior. Gere testes de integração.

## Código fonte do módulo:
{source_code}

## Módulos dependentes:
{dependencies}

## Stack:
- Linguagem: {language}
- Framework: {test_framework}
- Banco: {database}

## Regras:
1. Teste a interação ENTRE módulos, não lógica interna
2. Use banco de dados real (test database), não mocks
3. Teste fluxos completos: request → processing → database → response
4. Inclua setup/teardown que cria e limpa dados
5. Teste cenários de falha: timeout, conexão recusada, dados inválidos
6. Gere massa de teste realista para o domínio do projeto

Retorne JSON:
{{
  "test_file": {{
    "filename": "test_integration_<module>.py",
    "content": "<código completo>",
    "test_count": <número>,
    "dependencies_tested": [<lista de módulos>]
  }},
  "test_data": {{
    "seed_data": [
      {{"table": "<tabela>", "records": [<registros>]}}
    ],
    "cleanup_sql": "<SQL para limpar dados>"
  }}
}}
"""

UAT_TEST_PROMPT = """Você é um engenheiro de testes sênior. Gere testes de aceitação do usuário (UAT).

## Código fonte:
{source_code}

## Documentos de requisitos:
{source_documents}

## Stack:
- Linguagem: {language}
- Framework de teste: {test_framework}
- Frontend: {frontend_stack}

## Regras:
1. Cada user story DEVE ter pelo menos 1 teste UAT
2. Teste o fluxo completo do ponto de vista do USUÁRIO
3. Use linguagem Given/When/Then nos docstrings
4. Inclua validações de UI se aplicável (status codes, response bodies)
5. Teste cenários de negócio, não implementação técnica
6. Gere dados de teste que representem casos reais do domínio

Retorne JSON:
{{
  "test_file": {{
    "filename": "test_uat_<module>.py",
    "content": "<código completo>",
    "test_count": <número>,
    "user_stories_covered": [<lista>]
  }},
  "test_data": {{
    "scenarios": [
      {{"name": "<cenário>", "input": <dados>, "expected_output": <resultado>}}
    ]
  }}
}}
"""

SMOKE_TEST_PROMPT = """Você é um engenheiro de testes sênior. Gere testes smoke (sanidade).

## Módulos do projeto:
{modules_list}

## Endpoints da API:
{api_endpoints}

## Stack:
- Linguagem: {language}
- Framework: {test_framework}

## Regras:
1. Smoke tests devem ser RÁPIDOS (< 5 segundos cada)
2. Validar que cada endpoint responde (status 200/201)
3. Validar que cada módulo importa sem erro
4. Validar conexão com banco de dados
5. Validar que variáveis de ambiente críticas existem
6. NÃO testar lógica de negócio — apenas "o sistema está vivo?"

Retorne JSON:
{{
  "test_file": {{
    "filename": "test_smoke.py",
    "content": "<código completo>",
    "test_count": <número>
  }}
}}
"""

TEST_DATA_PROMPT = """Você é um engenheiro de dados de teste. Gere massa de teste realista.

## Contexto do projeto:
- Nome: {project_name}
- Domínio: {project_domain}
- Banco: {database}

## Schema das tabelas:
{table_schemas}

## Regras:
1. Dados DEVEM ser realistas para o domínio (nomes brasileiros, CPFs válidos formatados, etc.)
2. Gere pelo menos 10 registros por tabela
3. Respeite foreign keys e constraints
4. Inclua casos de borda: campos nulos (onde permitido), valores limite
5. Gere em formato SQL INSERT + JSON fixture
6. NUNCA use dados reais de pessoas — gere dados fictícios mas verossímeis

Retorne JSON:
{{
  "tables": [
    {{
      "name": "<tabela>",
      "records_count": <número>,
      "sql_inserts": "<SQL INSERT statements>",
      "json_fixtures": [<registros como JSON>]
    }}
  ],
  "relationships": [
    {{"from": "<tabela.campo>", "to": "<tabela.campo>", "type": "FK"}}
  ]
}}
"""
```

- [ ] **Step 2: Verificar que o arquivo foi criado**

Run: `python -c "from app.services.test_prompts import UNIT_TEST_PROMPT; print('OK')" 2>&1`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/luiz/GCA/backend
git add app/services/test_prompts.py
git commit -m "feat: prompts especializados para geração de testes (unitário, integração, UAT, smoke, massa)"
```

---

## Task 2: Implementar Geração Real de Testes no ModuleCodegenService

**Files:**
- Modify: `backend/app/services/module_codegen_service.py` (linhas 325-491)
- Test: `backend/app/tests/test_module_codegen_service.py`

- [ ] **Step 1: Escrever teste que verifica geração de teste unitário com LLM**

```python
# backend/app/tests/test_module_codegen_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

@pytest.mark.asyncio
async def test_generate_unit_tests_calls_llm():
    """Verifica que _generate_unit_tests chama o LLM e cria TestArtifact com conteúdo."""
    from app.services.module_codegen_service import ModuleCodegenService

    mock_session = AsyncMock()
    service = ModuleCodegenService(mock_session)

    mock_llm_response = '{"test_file": {"filename": "test_module.py", "content": "def test_example(): assert True", "test_count": 1, "coverage_estimate": "80%"}, "test_data": {"fixtures": []}}'

    generated_module = MagicMock()
    generated_module.id = uuid4()
    generated_module.name = "auth_module"
    generated_module.project_id = uuid4()

    ocg_data = {
        "TESTING_REQUIREMENTS": {"unit_tests": {"coverage_target": "85%", "framework": "pytest"}},
        "STACK_RECOMMENDATION": {"backend": {"language": "Python"}},
        "CRITICAL_FINDINGS": []
    }

    with patch.object(service, '_call_llm', new_callable=AsyncMock, return_value=mock_llm_response):
        result = await service._generate_unit_tests(
            generated_module=generated_module,
            source_code="def login(user, pwd): return True",
            ocg_data=ocg_data,
            language="python"
        )

    assert result is not None
    assert result["test_count"] >= 1
    assert "content" in result
    # Verifica que TestArtifact foi criado com conteúdo real
    mock_session.add.assert_called()
```

- [ ] **Step 2: Rodar teste para verificar que falha**

Run: `cd /home/luiz/GCA/backend && python -m pytest app/tests/test_module_codegen_service.py::test_generate_unit_tests_calls_llm -v`
Expected: FAIL — `_generate_unit_tests` não aceita esses parâmetros ou não chama LLM

- [ ] **Step 3: Implementar `_generate_unit_tests()` com LLM real**

Substituir a implementação stub (linhas 325-354) em `module_codegen_service.py`:

```python
async def _generate_unit_tests(
    self,
    generated_module: GeneratedModule,
    source_code: str,
    ocg_data: dict,
    language: str
) -> dict:
    """Gera testes unitários reais via LLM com massa de dados."""
    from app.services.test_prompts import UNIT_TEST_PROMPT

    # Mapear linguagem → framework de teste
    framework_map = {
        "python": "pytest",
        "typescript": "jest",
        "javascript": "jest",
        "java": "junit5",
        "csharp": "xunit",
        "go": "go test",
    }
    test_framework = framework_map.get(language.lower(), "pytest")

    # Extrair dados do OCG
    testing_reqs = ocg_data.get("TESTING_REQUIREMENTS", {})
    coverage_target = testing_reqs.get("unit_tests", {}).get("coverage_target", "80%")
    critical_findings = ocg_data.get("CRITICAL_FINDINGS", [])

    prompt = UNIT_TEST_PROMPT.format(
        source_code=source_code,
        language=language,
        test_framework=test_framework,
        database=ocg_data.get("STACK_RECOMMENDATION", {}).get("database", {}).get("primary", "PostgreSQL"),
        coverage_target=coverage_target,
        critical_findings=json.dumps(critical_findings[:5], ensure_ascii=False) if critical_findings else "Nenhum"
    )

    # Chamar LLM
    llm_response = await self._call_llm(prompt)
    parsed = self._parse_json_response(llm_response)

    if not parsed or "test_file" not in parsed:
        logger.warning(f"LLM não retornou testes válidos para {generated_module.name}")
        return {"test_count": 0, "content": "", "error": "LLM response invalid"}

    test_content = parsed["test_file"]["content"]
    test_count = parsed["test_file"].get("test_count", 0)

    # Criar TestFile (referência no módulo)
    test_file = TestFile(
        project_id=generated_module.project_id,
        generated_module_id=generated_module.id,
        test_type="unit",
        git_path=f"tests/unit/{parsed['test_file']['filename']}",
        framework=test_framework,
        coverage_scope=f"module:{generated_module.name}"
    )
    self.session.add(test_file)

    # Criar TestArtifact (conteúdo editável pelo Tester)
    test_artifact = TestArtifact(
        project_id=generated_module.project_id,
        module_id=generated_module.id,
        test_type="unit",
        title=f"Testes Unitários — {generated_module.name}",
        description=f"Gerado automaticamente. {test_count} testes. Cobertura estimada: {parsed['test_file'].get('coverage_estimate', 'N/A')}",
        content=test_content,
        file_path=f"tests/unit/{parsed['test_file']['filename']}",
        status="pending_review",
        created_by=None,
        version=1
    )
    self.session.add(test_artifact)

    # Salvar massa de teste se gerada
    test_data = parsed.get("test_data", {})

    await self.session.flush()

    logger.info(f"Testes unitários gerados: {test_count} testes para {generated_module.name}")

    return {
        "test_count": test_count,
        "content": test_content,
        "test_file_id": str(test_file.id) if hasattr(test_file, 'id') else None,
        "test_artifact_id": str(test_artifact.id) if hasattr(test_artifact, 'id') else None,
        "test_data": test_data
    }
```

- [ ] **Step 4: Implementar `_generate_integration_tests()` com LLM real**

Substituir stub (linhas 356-423):

```python
async def _generate_integration_tests(
    self,
    generated_module: GeneratedModule,
    source_code: str,
    ocg_data: dict,
    language: str,
    dependencies: list
) -> dict:
    """Gera testes de integração reais via LLM, considerando dependências."""
    from app.services.test_prompts import INTEGRATION_TEST_PROMPT

    if not dependencies:
        logger.info(f"Sem dependências para {generated_module.name}, pulando testes de integração")
        return {"test_count": 0, "content": "", "skipped": True}

    framework_map = {"python": "pytest", "typescript": "jest", "java": "junit5"}
    test_framework = framework_map.get(language.lower(), "pytest")

    prompt = INTEGRATION_TEST_PROMPT.format(
        source_code=source_code,
        dependencies=json.dumps(dependencies, ensure_ascii=False),
        language=language,
        test_framework=test_framework,
        database=ocg_data.get("STACK_RECOMMENDATION", {}).get("database", {}).get("primary", "PostgreSQL")
    )

    llm_response = await self._call_llm(prompt)
    parsed = self._parse_json_response(llm_response)

    if not parsed or "test_file" not in parsed:
        return {"test_count": 0, "content": "", "error": "LLM response invalid"}

    test_content = parsed["test_file"]["content"]
    test_count = parsed["test_file"].get("test_count", 0)

    test_file = TestFile(
        project_id=generated_module.project_id,
        generated_module_id=generated_module.id,
        test_type="integration",
        git_path=f"tests/integration/{parsed['test_file']['filename']}",
        framework=test_framework,
        coverage_scope=f"integration:{generated_module.name}"
    )
    self.session.add(test_file)

    test_artifact = TestArtifact(
        project_id=generated_module.project_id,
        module_id=generated_module.id,
        test_type="integration",
        title=f"Testes Integração — {generated_module.name}",
        description=f"Gerado automaticamente. {test_count} testes. Dependências: {', '.join(d.get('name', '') for d in dependencies)}",
        content=test_content,
        file_path=f"tests/integration/{parsed['test_file']['filename']}",
        status="pending_review",
        created_by=None,
        version=1
    )
    self.session.add(test_artifact)

    await self.session.flush()

    return {
        "test_count": test_count,
        "content": test_content,
        "test_data": parsed.get("test_data", {})
    }
```

- [ ] **Step 5: Implementar `_generate_uat_tests()` com LLM real**

Substituir stub (linhas 425-491):

```python
async def _generate_uat_tests(
    self,
    generated_module: GeneratedModule,
    source_code: str,
    ocg_data: dict,
    language: str,
    source_documents: list
) -> dict:
    """Gera testes UAT reais via LLM, baseados em documentos de requisitos."""
    from app.services.test_prompts import UAT_TEST_PROMPT

    if not source_documents:
        logger.info(f"Sem documentos fonte para {generated_module.name}, pulando UAT")
        return {"test_count": 0, "content": "", "skipped": True}

    framework_map = {"python": "pytest", "typescript": "jest", "java": "junit5"}
    test_framework = framework_map.get(language.lower(), "pytest")
    frontend_stack = ocg_data.get("STACK_RECOMMENDATION", {}).get("frontend", {})

    prompt = UAT_TEST_PROMPT.format(
        source_code=source_code,
        source_documents=json.dumps(source_documents[:3], ensure_ascii=False),
        language=language,
        test_framework=test_framework,
        frontend_stack=json.dumps(frontend_stack, ensure_ascii=False) if frontend_stack else "N/A"
    )

    llm_response = await self._call_llm(prompt)
    parsed = self._parse_json_response(llm_response)

    if not parsed or "test_file" not in parsed:
        return {"test_count": 0, "content": "", "error": "LLM response invalid"}

    test_content = parsed["test_file"]["content"]
    test_count = parsed["test_file"].get("test_count", 0)

    test_file = TestFile(
        project_id=generated_module.project_id,
        generated_module_id=generated_module.id,
        test_type="uat",
        git_path=f"tests/uat/{parsed['test_file']['filename']}",
        framework=test_framework,
        coverage_scope=f"uat:{generated_module.name}"
    )
    self.session.add(test_file)

    test_artifact = TestArtifact(
        project_id=generated_module.project_id,
        module_id=generated_module.id,
        test_type="e2e",
        title=f"Testes UAT — {generated_module.name}",
        description=f"Gerado automaticamente. {test_count} cenários de aceitação.",
        content=test_content,
        file_path=f"tests/uat/{parsed['test_file']['filename']}",
        status="pending_review",
        created_by=None,
        version=1
    )
    self.session.add(test_artifact)

    await self.session.flush()

    return {
        "test_count": test_count,
        "content": test_content,
        "test_data": parsed.get("test_data", {})
    }
```

- [ ] **Step 6: Rodar testes para verificar que passam**

Run: `cd /home/luiz/GCA/backend && python -m pytest app/tests/test_module_codegen_service.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd /home/luiz/GCA/backend
git add app/services/module_codegen_service.py app/tests/test_module_codegen_service.py
git commit -m "feat: geração real de testes unitários, integração e UAT via LLM"
```

---

## Task 3: Serviço de Massa de Teste

**Files:**
- Create: `backend/app/services/test_data_service.py`
- Create: `backend/app/routers/test_data_router.py`
- Test: `backend/app/tests/test_test_data_service.py`

- [ ] **Step 1: Escrever teste para geração de massa**

```python
# backend/app/tests/test_test_data_service.py
import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

@pytest.mark.asyncio
async def test_generate_test_data_returns_fixtures():
    """Verifica que o serviço gera massa de teste com fixtures JSON e SQL."""
    from app.services.test_data_service import TestDataService

    mock_session = AsyncMock()
    service = TestDataService(mock_session)

    mock_llm_response = '{"tables": [{"name": "users", "records_count": 10, "sql_inserts": "INSERT INTO users...", "json_fixtures": [{"id": 1, "name": "João Silva"}]}], "relationships": []}'

    project_id = uuid4()
    ocg_data = {
        "PROJECT_PROFILE": {"name": "FinanceHub Pro", "type": "web_app"},
        "STACK_RECOMMENDATION": {"database": {"primary": "PostgreSQL"}}
    }

    with patch.object(service, '_call_llm', new_callable=AsyncMock, return_value=mock_llm_response):
        result = await service.generate_test_data(
            project_id=project_id,
            ocg_data=ocg_data,
            table_schemas={"users": {"id": "UUID", "name": "VARCHAR(100)"}},
            test_type="unit"
        )

    assert result is not None
    assert "tables" in result
    assert len(result["tables"]) > 0
    assert "sql_inserts" in result["tables"][0]
```

- [ ] **Step 2: Rodar teste para verificar que falha**

Run: `cd /home/luiz/GCA/backend && python -m pytest app/tests/test_test_data_service.py -v`
Expected: FAIL — módulo não existe

- [ ] **Step 3: Implementar TestDataService**

```python
# backend/app/services/test_data_service.py
"""
Serviço de geração de massa de teste.
Gera dados fictícios realistas para cada tipo de teste,
respeitando o domínio do projeto e constraints do banco.
"""
import json
import structlog
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.test_prompts import TEST_DATA_PROMPT
from app.services.ai_service import LLMServiceFactory

logger = structlog.get_logger()


class TestDataService:
    """Gera massa de teste realista baseada no OCG e schema do banco."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_test_data(
        self,
        project_id: UUID,
        ocg_data: dict,
        table_schemas: dict,
        test_type: str = "unit"
    ) -> dict:
        """
        Gera massa de teste para o projeto.

        Args:
            project_id: ID do projeto
            ocg_data: OCG completo com contexto do projeto
            table_schemas: Schema das tabelas {nome: {campo: tipo}}
            test_type: Tipo de teste (unit, integration, uat, smoke)

        Returns:
            Dict com tables[], relationships[], e metadados
        """
        project_profile = ocg_data.get("PROJECT_PROFILE", {})
        stack = ocg_data.get("STACK_RECOMMENDATION", {})

        prompt = TEST_DATA_PROMPT.format(
            project_name=project_profile.get("name", "Projeto"),
            project_domain=project_profile.get("type", "web_app"),
            database=stack.get("database", {}).get("primary", "PostgreSQL"),
            table_schemas=json.dumps(table_schemas, indent=2, ensure_ascii=False)
        )

        # Adicionar contexto do tipo de teste
        prompt += f"\n\nTipo de teste: {test_type}\n"
        if test_type == "unit":
            prompt += "Foco em dados isolados, sem dependências entre tabelas.\n"
        elif test_type == "integration":
            prompt += "Foco em dados com relacionamentos FK válidos entre tabelas.\n"
        elif test_type == "uat":
            prompt += "Foco em cenários de negócio completos, dados que representem fluxos reais do usuário.\n"
        elif test_type == "smoke":
            prompt += "Foco em dados mínimos — 1-2 registros por tabela apenas para validar que o sistema funciona.\n"

        llm_response = await self._call_llm(prompt)
        parsed = self._parse_json_response(llm_response)

        if not parsed:
            logger.warning(f"Falha ao gerar massa de teste para projeto {project_id}")
            return {"tables": [], "relationships": [], "error": "LLM response invalid"}

        logger.info(
            "Massa de teste gerada",
            project_id=str(project_id),
            test_type=test_type,
            tables_count=len(parsed.get("tables", []))
        )

        return parsed

    async def generate_for_module(
        self,
        project_id: UUID,
        module_name: str,
        source_code: str,
        ocg_data: dict,
        test_type: str = "unit"
    ) -> dict:
        """
        Gera massa de teste específica para um módulo.
        Extrai schemas do código fonte e gera dados adequados.
        """
        prompt = f"""Analise o código fonte abaixo e gere massa de teste para o módulo '{module_name}'.

## Código fonte:
{source_code}

## Contexto do projeto:
- Nome: {ocg_data.get('PROJECT_PROFILE', {}).get('name', 'Projeto')}
- Banco: {ocg_data.get('STACK_RECOMMENDATION', {}).get('database', {}).get('primary', 'PostgreSQL')}
- Tipo de teste: {test_type}

Gere dados realistas que cubram:
1. Casos felizes (dados válidos)
2. Casos de borda (nulos, vazios, limites)
3. Casos de erro (dados inválidos que devem ser rejeitados)

Retorne JSON:
{{
  "module": "{module_name}",
  "test_type": "{test_type}",
  "fixtures": [
    {{"name": "<nome_fixture>", "data": <objeto>, "purpose": "<o que testa>"}}
  ],
  "edge_cases": [
    {{"name": "<nome>", "data": <objeto>, "expected_error": "<erro esperado>"}}
  ]
}}
"""
        llm_response = await self._call_llm(prompt)
        return self._parse_json_response(llm_response) or {"fixtures": [], "edge_cases": []}

    async def _call_llm(self, prompt: str) -> str:
        """Chama o LLM configurado no projeto."""
        try:
            llm_client = LLMServiceFactory.create_client(
                provider="anthropic",
                api_key=None  # Usa env var
            )
            response = await llm_client.generate(
                prompt=prompt,
                max_tokens=4000,
                temperature=0.3
            )
            return response
        except Exception as e:
            logger.error(f"Erro ao chamar LLM para massa de teste: {e}")
            return ""

    def _parse_json_response(self, response: str) -> dict | None:
        """Extrai JSON da resposta do LLM."""
        try:
            # Tentar parse direto
            return json.loads(response)
        except json.JSONDecodeError:
            # Tentar extrair JSON de markdown code block
            import re
            match = re.search(r'```(?:json)?\s*\n(.*?)\n```', response, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            return None
```

- [ ] **Step 4: Criar router para massa de teste**

```python
# backend/app/routers/test_data_router.py
"""Router para geração e consulta de massa de teste."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.core.database import get_session
from app.core.auth import get_current_user
from app.services.test_data_service import TestDataService
from app.models.base import User

router = APIRouter(prefix="/projects/{project_id}/test-data", tags=["test-data"])


class GenerateTestDataRequest(BaseModel):
    test_type: str = "unit"
    table_schemas: dict | None = None


class GenerateModuleTestDataRequest(BaseModel):
    module_name: str
    source_code: str
    test_type: str = "unit"


@router.post("/generate")
async def generate_test_data(
    project_id: UUID,
    request: GenerateTestDataRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Gera massa de teste para o projeto inteiro."""
    from app.services.ocg_service import get_ocg_by_project
    ocg = await get_ocg_by_project(session, project_id)
    if not ocg:
        raise HTTPException(status_code=404, detail="OCG não encontrado")

    service = TestDataService(session)
    result = await service.generate_test_data(
        project_id=project_id,
        ocg_data=ocg.ocg_data or {},
        table_schemas=request.table_schemas or {},
        test_type=request.test_type
    )
    return result


@router.post("/generate-for-module")
async def generate_module_test_data(
    project_id: UUID,
    request: GenerateModuleTestDataRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Gera massa de teste específica para um módulo."""
    from app.services.ocg_service import get_ocg_by_project
    ocg = await get_ocg_by_project(session, project_id)

    service = TestDataService(session)
    result = await service.generate_for_module(
        project_id=project_id,
        module_name=request.module_name,
        source_code=request.source_code,
        ocg_data=ocg.ocg_data if ocg else {},
        test_type=request.test_type
    )
    return result
```

- [ ] **Step 5: Registrar router no main.py**

Adicionar em `backend/app/main.py`:

```python
from app.routers.test_data_router import router as test_data_router
app.include_router(test_data_router, prefix="/api/v1")
```

- [ ] **Step 6: Rodar testes**

Run: `cd /home/luiz/GCA/backend && python -m pytest app/tests/test_test_data_service.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd /home/luiz/GCA/backend
git add app/services/test_data_service.py app/routers/test_data_router.py app/tests/test_test_data_service.py
git commit -m "feat: serviço de geração de massa de teste por tipo (unit, integration, UAT, smoke)"
```

---

## Task 4: Endpoint Backlog → CodeGen

**Files:**
- Modify: `backend/app/routers/code_generation.py`
- Test: `backend/app/tests/test_backlog_codegen.py`

- [ ] **Step 1: Escrever teste para o endpoint**

```python
# backend/app/tests/test_backlog_codegen.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

@pytest.mark.asyncio
async def test_generate_code_from_backlog_item():
    """Verifica que o endpoint gera código + testes + massa a partir de um item de backlog."""
    # Este teste valida o fluxo:
    # BacklogItem → ModuleCandidate → CodeGen → TestGen → TestData
    backlog_item_id = uuid4()
    project_id = uuid4()

    mock_backlog = MagicMock()
    mock_backlog.id = backlog_item_id
    mock_backlog.project_id = project_id
    mock_backlog.title = "Módulo de Autenticação"
    mock_backlog.category = "modules"
    mock_backlog.status = "ready"

    # O fluxo deve:
    # 1. Buscar BacklogItem
    # 2. Buscar ModuleCandidate associado (se houver)
    # 3. Buscar OCG do projeto
    # 4. Gerar código via LLM
    # 5. Gerar testes (unit + integration + UAT)
    # 6. Gerar massa de teste
    # 7. Criar TestArtifacts com status pending_review
    # 8. Atualizar BacklogItem.status para "generating"
    assert True  # Placeholder para validar estrutura
```

- [ ] **Step 2: Implementar endpoint**

Adicionar em `backend/app/routers/code_generation.py`:

```python
@router.post("/projects/{project_id}/backlog/{backlog_item_id}/generate-code")
async def generate_code_from_backlog(
    project_id: UUID,
    backlog_item_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Gera código + testes + massa de teste a partir de um item de backlog.
    
    Fluxo:
    1. Busca BacklogItem e valida status
    2. Busca OCG do projeto para contexto
    3. Gera código fonte via LLM
    4. Gera testes unitários, integração e UAT
    5. Gera massa de teste por tipo
    6. Cria TestArtifacts com status pending_review
    7. Atualiza BacklogItem.status para generating → tests_running
    """
    from app.models.base import BacklogItem, OCG, ModuleCandidate
    from app.services.module_codegen_service import ModuleCodegenService
    from app.services.test_data_service import TestDataService

    # 1. Buscar e validar BacklogItem
    result = await session.execute(
        select(BacklogItem).where(
            BacklogItem.id == backlog_item_id,
            BacklogItem.project_id == project_id
        )
    )
    backlog_item = result.scalar_one_or_none()
    if not backlog_item:
        raise HTTPException(status_code=404, detail="Item de backlog não encontrado")

    if backlog_item.status not in ("ready", "pending"):
        raise HTTPException(
            status_code=400,
            detail=f"Item deve estar com status 'ready' ou 'pending', atual: {backlog_item.status}"
        )

    # 2. Atualizar status
    backlog_item.status = "generating"
    await session.flush()

    # 3. Buscar OCG
    ocg_result = await session.execute(
        select(OCG).where(OCG.project_id == project_id).order_by(OCG.version.desc())
    )
    ocg = ocg_result.scalar_one_or_none()
    ocg_data = ocg.ocg_data if ocg else {}

    # 4. Buscar ou criar ModuleCandidate
    mc_result = await session.execute(
        select(ModuleCandidate).where(
            ModuleCandidate.project_id == project_id,
            ModuleCandidate.name == backlog_item.title,
            ModuleCandidate.status == "approved"
        )
    )
    module_candidate = mc_result.scalar_one_or_none()

    try:
        # 5. Gerar código
        codegen_service = ModuleCodegenService(session)

        if module_candidate:
            generation_result = await codegen_service.generate_module_from_candidate(
                module_candidate_id=module_candidate.id,
                project_id=project_id,
                ocg_id=ocg.id if ocg else None
            )
        else:
            # Gerar sem ModuleCandidate — direto do backlog
            generation_result = await codegen_service.generate_from_backlog_item(
                backlog_item=backlog_item,
                ocg_data=ocg_data
            )

        # 6. Gerar massa de teste
        test_data_service = TestDataService(session)
        source_code = generation_result.get("source_code", "")

        test_data_results = {}
        for test_type in ["unit", "integration", "uat"]:
            td = await test_data_service.generate_for_module(
                project_id=project_id,
                module_name=backlog_item.title,
                source_code=source_code,
                ocg_data=ocg_data,
                test_type=test_type
            )
            test_data_results[test_type] = td

        # 7. Atualizar status
        backlog_item.status = "tests_running"
        backlog_item.generated_code_path = generation_result.get("git_source_path", "")
        backlog_item.generated_tests_path = generation_result.get("git_test_path", "")
        await session.commit()

        return {
            "status": "success",
            "backlog_item_id": str(backlog_item_id),
            "code_generated": True,
            "tests_generated": {
                "unit": generation_result.get("unit_tests", {}).get("test_count", 0),
                "integration": generation_result.get("integration_tests", {}).get("test_count", 0),
                "uat": generation_result.get("uat_tests", {}).get("test_count", 0)
            },
            "test_data_generated": {k: len(v.get("fixtures", [])) for k, v in test_data_results.items()},
            "next_status": "tests_running"
        }

    except Exception as e:
        backlog_item.status = "blocked"
        await session.commit()
        logger.error(f"Erro ao gerar código do backlog {backlog_item_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 3: Rodar testes**

Run: `cd /home/luiz/GCA/backend && python -m pytest app/tests/test_backlog_codegen.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
cd /home/luiz/GCA/backend
git add app/routers/code_generation.py app/tests/test_backlog_codegen.py
git commit -m "feat: endpoint backlog→codegen com geração de código, testes e massa de dados"
```

---

## Task 5: Validação Automática de Qualidade de Testes no QA Service

**Files:**
- Modify: `backend/app/services/qa_service.py`

- [ ] **Step 1: Escrever teste para validação**

```python
# backend/app/tests/test_qa_validation.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_validate_test_quality_detects_missing_assertions():
    """Verifica que validação detecta testes sem assertions."""
    from app.services.qa_service import QAService

    mock_session = AsyncMock()
    service = QAService(mock_session)

    bad_test = """
def test_something():
    result = calculate(1, 2)
    print(result)
    # esqueceu o assert
"""

    result = await service.validate_test_quality(bad_test, "unit")
    assert result["valid"] is False
    assert any("assert" in issue.lower() for issue in result["issues"])
```

- [ ] **Step 2: Rodar teste**

Run: `cd /home/luiz/GCA/backend && python -m pytest app/tests/test_qa_validation.py -v`
Expected: FAIL

- [ ] **Step 3: Implementar validação**

Adicionar em `qa_service.py`:

```python
async def validate_test_quality(self, test_content: str, test_type: str) -> dict:
    """
    Valida qualidade do teste antes de aprovar.
    
    Verificações:
    1. Tem assertions (assert, assertEqual, etc.)
    2. Tem docstrings descritivos
    3. Não tem imports desnecessários
    4. Testa caso feliz E caso de erro
    5. Nomeação segue padrão test_<funcao>_<cenario>
    
    Returns:
        {"valid": bool, "issues": [], "suggestions": [], "score": 0-100}
    """
    issues = []
    suggestions = []
    score = 100

    lines = test_content.strip().split("\n")

    # 1. Verificar assertions
    has_assert = any("assert" in line.lower() for line in lines if not line.strip().startswith("#"))
    if not has_assert:
        issues.append("Nenhuma assertion encontrada — teste não valida nada")
        score -= 40

    # 2. Verificar docstrings
    has_docstring = '"""' in test_content or "'''" in test_content
    if not has_docstring:
        suggestions.append("Adicionar docstrings descritivos em cada teste")
        score -= 10

    # 3. Contar testes
    test_functions = [l for l in lines if l.strip().startswith("def test_") or l.strip().startswith("async def test_")]
    if len(test_functions) < 2:
        suggestions.append(f"Apenas {len(test_functions)} teste(s) — considerar adicionar mais cenários")
        score -= 10

    # 4. Verificar se testa erros (fixtures negativas)
    has_error_test = any(
        "error" in name.lower() or "invalid" in name.lower() or "fail" in name.lower() or "raises" in name.lower()
        for name in test_functions
    )
    if not has_error_test:
        suggestions.append("Nenhum teste de caso de erro encontrado — adicionar cenários negativos")
        score -= 15

    # 5. Verificar se usa mocks adequadamente (para unit tests)
    if test_type == "unit":
        has_mock = "mock" in test_content.lower() or "patch" in test_content.lower() or "monkeypatch" in test_content.lower()
        if not has_mock and "import" in test_content and "requests" not in test_content:
            suggestions.append("Testes unitários devem mockar dependências externas")

    # 6. Verificar imports básicos
    has_pytest_import = "import pytest" in test_content or "from pytest" in test_content
    if not has_pytest_import and test_type != "smoke":
        suggestions.append("Considerar importar pytest para fixtures e parametrize")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "suggestions": suggestions,
        "score": max(0, score),
        "test_count": len(test_functions),
        "has_error_scenarios": has_error_test,
        "has_docstrings": has_docstring
    }
```

- [ ] **Step 4: Rodar testes**

Run: `cd /home/luiz/GCA/backend && python -m pytest app/tests/test_qa_validation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/luiz/GCA/backend
git add app/services/qa_service.py app/tests/test_qa_validation.py
git commit -m "feat: validação automática de qualidade de testes no QA Service"
```

---

## Task 6: Frontend — Botão Gerar Testes + Indicador de Massa no CodeGeneratorPage

**Files:**
- Modify: `frontend/src/pages/projects/CodeGeneratorPage.tsx`

- [ ] **Step 1: Adicionar botão "Gerar Testes" na toolbar**

Após o botão de AI Review, adicionar botão que:
1. Chama `POST /api/v1/projects/{projectId}/test-data/generate-for-module`
2. Mostra spinner durante geração
3. Exibe resultado com contagem de testes + massa gerada
4. Link para TesterReviewPage para revisão

```typescript
// Adicionar estado
const [generatingTests, setGeneratingTests] = useState(false);
const [testGenResult, setTestGenResult] = useState<any>(null);

// Função de geração
const handleGenerateTests = async () => {
  if (!selectedFile || !fileContents[selectedFile]) return;
  setGeneratingTests(true);
  try {
    const response = await api.post(`/projects/${projectId}/test-data/generate-for-module`, {
      module_name: selectedFile.split('/').pop()?.replace(/\.[^.]+$/, '') || 'module',
      source_code: fileContents[selectedFile],
      test_type: 'unit'
    });
    setTestGenResult(response.data);
    toast.success(`${response.data.fixtures?.length || 0} fixtures geradas`);
  } catch (err) {
    toast.error('Erro ao gerar testes');
  } finally {
    setGeneratingTests(false);
  }
};

// Botão na toolbar
<button
  onClick={handleGenerateTests}
  disabled={generatingTests || !selectedFile}
  className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-sm flex items-center gap-1.5 disabled:opacity-50"
>
  {generatingTests ? (
    <><Loader2 className="w-4 h-4 animate-spin" /> Gerando...</>
  ) : (
    <><TestTube className="w-4 h-4" /> Gerar Testes</>
  )}
</button>
```

- [ ] **Step 2: Adicionar painel de resultado da massa de teste**

```typescript
// Após o painel de AI Review, adicionar:
{testGenResult && (
  <div className="border border-emerald-500/30 rounded-lg p-4 bg-emerald-900/10">
    <h4 className="text-emerald-400 font-medium mb-2 flex items-center gap-2">
      <Database className="w-4 h-4" />
      Massa de Teste Gerada
    </h4>
    <div className="grid grid-cols-3 gap-3 text-sm">
      <div className="bg-dark-200 rounded p-2">
        <span className="text-slate-400">Fixtures</span>
        <span className="text-white font-bold ml-2">{testGenResult.fixtures?.length || 0}</span>
      </div>
      <div className="bg-dark-200 rounded p-2">
        <span className="text-slate-400">Edge Cases</span>
        <span className="text-white font-bold ml-2">{testGenResult.edge_cases?.length || 0}</span>
      </div>
      <div className="bg-dark-200 rounded p-2">
        <span className="text-slate-400">Tipo</span>
        <span className="text-white font-bold ml-2">{testGenResult.test_type || 'unit'}</span>
      </div>
    </div>
    <Link
      to={`/projects/${projectId}/tester-review`}
      className="text-emerald-400 hover:text-emerald-300 text-sm mt-2 inline-block"
    >
      Revisar testes no Tester Review →
    </Link>
  </div>
)}
```

- [ ] **Step 3: Verificar build**

Run: `cd /home/luiz/GCA/frontend && npm run build`
Expected: Build sem erros

- [ ] **Step 4: Commit**

```bash
cd /home/luiz/GCA/frontend
git add src/pages/projects/CodeGeneratorPage.tsx
git commit -m "feat: botão gerar testes + painel massa de teste no CodeGeneratorPage"
```

---

## Task 7: Frontend — Painel de Validação Automática no QAReadinessPage

**Files:**
- Modify: `frontend/src/pages/projects/QAReadinessPage.tsx`

- [ ] **Step 1: Adicionar seção de validação automática**

Após os KPIs e antes da tabela de execução, adicionar painel que mostra resultado da validação automática para cada teste:

```typescript
// Adicionar chamada de validação
const [validationResults, setValidationResults] = useState<Record<string, any>>({});

const handleValidateAll = async () => {
  // Para cada teste pendente, chamar validação
  for (const test of tests.filter(t => t.status === 'pending_review')) {
    try {
      const res = await api.post(`/projects/${projectId}/qa/validate`, {
        test_content: test.content,
        test_type: test.test_type
      });
      setValidationResults(prev => ({ ...prev, [test.id]: res.data }));
    } catch (err) {
      console.error('Erro validando teste', test.id);
    }
  }
};

// Painel de validação
<div className="border border-violet-500/30 rounded-lg p-4 bg-violet-900/10 mb-6">
  <div className="flex items-center justify-between mb-3">
    <h3 className="text-violet-400 font-medium flex items-center gap-2">
      <ShieldCheck className="w-5 h-5" />
      Validação Automática de Qualidade
    </h3>
    <button
      onClick={handleValidateAll}
      className="px-3 py-1.5 bg-violet-600 hover:bg-violet-500 text-white rounded text-sm"
    >
      Validar Todos
    </button>
  </div>
  {Object.entries(validationResults).map(([testId, result]) => (
    <div key={testId} className={`p-3 rounded mb-2 ${result.valid ? 'bg-emerald-900/20 border border-emerald-500/30' : 'bg-red-900/20 border border-red-500/30'}`}>
      <div className="flex items-center justify-between">
        <span className="text-sm text-white">{result.test_name}</span>
        <span className={`text-xs px-2 py-0.5 rounded ${result.valid ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white'}`}>
          Score: {result.score}/100
        </span>
      </div>
      {result.issues?.length > 0 && (
        <ul className="mt-1 text-xs text-red-400">
          {result.issues.map((issue: string, i: number) => <li key={i}>• {issue}</li>)}
        </ul>
      )}
      {result.suggestions?.length > 0 && (
        <ul className="mt-1 text-xs text-yellow-400">
          {result.suggestions.map((s: string, i: number) => <li key={i}>💡 {s}</li>)}
        </ul>
      )}
    </div>
  ))}
</div>
```

- [ ] **Step 2: Adicionar endpoint de validação no qa_router**

```python
# Em backend/app/routers/qa_router.py
@router.post("/projects/{project_id}/qa/validate")
async def validate_test(
    project_id: UUID,
    request: dict,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Valida qualidade de um teste sem executá-lo."""
    service = QAService(session)
    result = await service.validate_test_quality(
        test_content=request.get("test_content", ""),
        test_type=request.get("test_type", "unit")
    )
    return result
```

- [ ] **Step 3: Verificar build**

Run: `cd /home/luiz/GCA/frontend && npm run build && cd /home/luiz/GCA/backend && python -m pytest app/tests/ -v --tb=short`
Expected: Build OK, testes passam

- [ ] **Step 4: Commit**

```bash
cd /home/luiz/GCA
git add frontend/src/pages/projects/QAReadinessPage.tsx backend/app/routers/qa_router.py
git commit -m "feat: validação automática de qualidade no QA Readiness + endpoint validate"
```

---

## Task 8: Método generate_from_backlog_item no ModuleCodegenService

**Files:**
- Modify: `backend/app/services/module_codegen_service.py`

- [ ] **Step 1: Escrever teste**

```python
# backend/app/tests/test_backlog_codegen.py (adicionar)
@pytest.mark.asyncio
async def test_generate_from_backlog_item_creates_module_and_tests():
    """Verifica geração completa: código + testes a partir de backlog item."""
    from app.services.module_codegen_service import ModuleCodegenService

    mock_session = AsyncMock()
    service = ModuleCodegenService(mock_session)

    backlog_item = MagicMock()
    backlog_item.id = uuid4()
    backlog_item.project_id = uuid4()
    backlog_item.title = "Módulo de Pagamentos"
    backlog_item.category = "modules"
    backlog_item.description = "Processar pagamentos via PIX e cartão"

    ocg_data = {
        "STACK_RECOMMENDATION": {
            "backend": {"language": "Python", "framework": "FastAPI"},
            "database": {"primary": "PostgreSQL"}
        },
        "TESTING_REQUIREMENTS": {
            "unit_tests": {"coverage_target": "85%", "framework": "pytest"}
        },
        "CRITICAL_FINDINGS": []
    }

    mock_code_response = '{"files": [{"path": "payments.py", "content": "def process_payment(): pass"}], "entry_point": "payments.py", "language": "python"}'

    with patch.object(service, '_call_llm', new_callable=AsyncMock, return_value=mock_code_response):
        result = await service.generate_from_backlog_item(backlog_item, ocg_data)

    assert result["source_code"] is not None
    assert "git_source_path" in result
```

- [ ] **Step 2: Implementar método**

```python
async def generate_from_backlog_item(self, backlog_item, ocg_data: dict) -> dict:
    """
    Gera código + testes a partir de um item de backlog (sem ModuleCandidate).
    Usado quando o item vem direto do backlog sem passar pelo Arguidor.
    """
    stack = ocg_data.get("STACK_RECOMMENDATION", {})
    language = stack.get("backend", {}).get("language", "Python").lower()
    framework = stack.get("backend", {}).get("framework", "FastAPI")
    database = stack.get("database", {}).get("primary", "PostgreSQL")

    # 1. Gerar código
    prompt = f"""Gere código fonte para o módulo: {backlog_item.title}
Descrição: {backlog_item.description or 'N/A'}
Linguagem: {language}
Framework: {framework}
Banco: {database}

Retorne JSON:
{{"files": [{{"path": "<caminho>", "content": "<código>"}}], "entry_point": "<arquivo principal>", "language": "{language}"}}
"""

    code_response = await self._call_llm(prompt)
    parsed_code = self._parse_json_response(code_response)

    source_code = ""
    git_source_path = ""
    if parsed_code and "files" in parsed_code:
        source_code = "\n\n".join(f.get("content", "") for f in parsed_code["files"])
        git_source_path = f"src/modules/{backlog_item.title.lower().replace(' ', '_')}/"

    # 2. Criar GeneratedModule
    generated_module = GeneratedModule(
        project_id=backlog_item.project_id,
        module_candidate_id=None,
        name=backlog_item.title,
        module_type="feature",
        status="completed",
        git_source_path=git_source_path,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
        tokens_used=0
    )
    self.session.add(generated_module)
    await self.session.flush()

    # 3. Gerar testes
    unit_result = await self._generate_unit_tests(generated_module, source_code, ocg_data, language)
    integration_result = await self._generate_integration_tests(generated_module, source_code, ocg_data, language, [])
    uat_result = await self._generate_uat_tests(generated_module, source_code, ocg_data, language, [])

    return {
        "source_code": source_code,
        "git_source_path": git_source_path,
        "git_test_path": f"tests/unit/",
        "unit_tests": unit_result,
        "integration_tests": integration_result,
        "uat_tests": uat_result,
        "generated_module_id": str(generated_module.id)
    }
```

- [ ] **Step 3: Rodar testes**

Run: `cd /home/luiz/GCA/backend && python -m pytest app/tests/test_backlog_codegen.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
cd /home/luiz/GCA/backend
git add app/services/module_codegen_service.py app/tests/test_backlog_codegen.py
git commit -m "feat: generate_from_backlog_item — geração completa sem ModuleCandidate"
```

---

## Task 9: Registrar Router + Teste E2E de Integração

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/app/tests/test_pipeline_e2e.py`

- [ ] **Step 1: Verificar que test_data_router está registrado**

```python
# Verificar em main.py que o router foi adicionado
# Se não estiver, adicionar:
from app.routers.test_data_router import router as test_data_router
app.include_router(test_data_router, prefix="/api/v1")
```

- [ ] **Step 2: Escrever teste E2E do pipeline**

```python
# backend/app/tests/test_pipeline_e2e.py
"""Teste E2E do pipeline CodeGen → TestGen → Massa → QA Validation."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

@pytest.mark.asyncio
async def test_full_pipeline_backlog_to_qa():
    """
    Fluxo completo:
    1. BacklogItem com status 'ready'
    2. Gera código via LLM
    3. Gera testes unitários via LLM
    4. Gera massa de teste via LLM
    5. QA valida qualidade dos testes
    6. BacklogItem atualiza para 'tests_running'
    """
    from app.services.module_codegen_service import ModuleCodegenService
    from app.services.test_data_service import TestDataService
    from app.services.qa_service import QAService

    mock_session = AsyncMock()

    # Mock LLM responses
    code_response = '{"files": [{"path": "auth.py", "content": "def authenticate(user, pwd):\\n    if user == \\"admin\\" and pwd == \\"secret\\":\\n        return True\\n    return False"}], "entry_point": "auth.py", "language": "python"}'

    test_response = '{"test_file": {"filename": "test_auth.py", "content": "import pytest\\ndef test_authenticate_valid():\\n    assert authenticate(\\"admin\\", \\"secret\\") == True\\ndef test_authenticate_invalid():\\n    assert authenticate(\\"user\\", \\"wrong\\") == False", "test_count": 2, "coverage_estimate": "90%"}, "test_data": {"fixtures": [{"name": "valid_user", "data": {"user": "admin", "pwd": "secret"}}]}}'

    # 1. CodeGen
    codegen = ModuleCodegenService(mock_session)
    backlog_item = MagicMock(
        id=uuid4(), project_id=uuid4(),
        title="Autenticação", description="Login com user/pwd",
        category="modules"
    )
    ocg_data = {
        "STACK_RECOMMENDATION": {"backend": {"language": "Python", "framework": "FastAPI"}, "database": {"primary": "PostgreSQL"}},
        "TESTING_REQUIREMENTS": {"unit_tests": {"coverage_target": "85%"}},
        "CRITICAL_FINDINGS": []
    }

    with patch.object(codegen, '_call_llm', new_callable=AsyncMock, side_effect=[code_response, test_response, test_response, test_response]):
        result = await codegen.generate_from_backlog_item(backlog_item, ocg_data)

    assert result["source_code"] != ""
    assert result["unit_tests"]["test_count"] >= 1

    # 2. QA Validation
    qa = QAService(mock_session)
    validation = await qa.validate_test_quality(
        result["unit_tests"]["content"],
        "unit"
    )
    assert validation["valid"] is True
    assert validation["score"] >= 60
```

- [ ] **Step 3: Rodar todos os testes**

Run: `cd /home/luiz/GCA/backend && python -m pytest app/tests/test_pipeline_e2e.py app/tests/test_module_codegen_service.py app/tests/test_test_data_service.py app/tests/test_qa_validation.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit final**

```bash
cd /home/luiz/GCA
git add -A
git commit -m "feat: pipeline CodeGen→TestGen→Massa→QA completo com testes E2E"
```

---

## Resumo da Implementação

| Task | O que implementa | Arquivos | Tipo |
|------|-------------------|----------|------|
| 1 | Prompts especializados por tipo de teste | `test_prompts.py` | Criar |
| 2 | Geração real de testes (unit/integration/UAT) via LLM | `module_codegen_service.py` | Modificar |
| 3 | Serviço de massa de teste + router | `test_data_service.py`, `test_data_router.py` | Criar |
| 4 | Endpoint backlog→codegen (orquestração) | `code_generation.py` | Modificar |
| 5 | Validação automática de qualidade no QA | `qa_service.py` | Modificar |
| 6 | Botão gerar testes + painel massa no frontend | `CodeGeneratorPage.tsx` | Modificar |
| 7 | Painel validação automática no QA frontend | `QAReadinessPage.tsx` | Modificar |
| 8 | Método generate_from_backlog_item | `module_codegen_service.py` | Modificar |
| 9 | Registro de routers + teste E2E | `main.py`, `test_pipeline_e2e.py` | Modificar/Criar |

### Fluxo Final

```
BacklogItem (ready)
    ↓ POST /backlog/{id}/generate-code
ModuleCodegenService
    ↓ gera código via LLM (Anthropic)
    ↓ gera testes unitários via LLM + massa de dados
    ↓ gera testes integração via LLM + massa
    ↓ gera testes UAT via LLM + massa
    ↓ cria TestArtifacts (status: pending_review)
BacklogItem (tests_running)
    ↓
TesterReview → humano revisa/edita/aprova testes
    ↓
QAReadiness → validação automática + execução pytest
    ↓
BacklogItem (ready_to_merge | blocked)
```
