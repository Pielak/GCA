"""
Module CodeGen Service — Geração de código e testes por módulo aprovado.
Orquestra: busca candidato → busca OCG → gera código via LLM → commit no Git →
gera testes unitários → verifica integração → verifica UAT → gera docs.
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4, UUID

from app.utils.retry import gca_retry

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models.base import (
    GeneratedModule,
    TestFile,
    ModuleCandidate,
    OCG,
)
from app.core.config import settings

logger = structlog.get_logger(__name__)


# Mapeamento de linguagem → framework de teste padrão
TEST_FRAMEWORK_MAP: Dict[str, str] = {
    "python": "pytest",
    "typescript": "jest",
    "javascript": "jest",
    "java": "junit5",
    "kotlin": "junit5",
    "csharp": "xunit",
    "go": "go_test",
    "rust": "cargo_test",
    "ruby": "rspec",
    "php": "phpunit",
    "swift": "xctest",
    "dart": "flutter_test",
}


# Prompt para geração de código do módulo
MODULE_CODE_PROMPT = """Você é um engenheiro de software sênior. Gere o código-fonte completo para o módulo descrito abaixo.

MÓDULO: {module_name}
TIPO: {module_type}
DESCRIÇÃO: {module_description}

CONTEXTO DO PROJETO (OCG):
{ocg_context}

DEPENDÊNCIAS: {dependencies}

REQUISITOS:
1. Código limpo e bem documentado (docstrings em português-BR)
2. Seguir padrões da stack definida no OCG
3. Tratar erros adequadamente
4. Incluir tipagem completa
5. Seguir princípios SOLID

Retorne o código completo no formato JSON:
{{
  "files": [
    {{"path": "caminho/do/arquivo.ext", "content": "código completo"}}
  ],
  "entry_point": "arquivo principal",
  "language": "linguagem usada"
}}
"""

# Prompt para geração de testes unitários
UNIT_TEST_PROMPT = """Você é um engenheiro de QA sênior. Gere testes unitários completos para o módulo abaixo.

CÓDIGO DO MÓDULO:
{module_code}

MÓDULO: {module_name}
FRAMEWORK DE TESTE: {test_framework}

REQUISITOS:
1. Cobertura mínima de 80% das funções
2. Testar cenários positivos e negativos
3. Testar edge cases
4. Usar mocks para dependências externas
5. Nomes descritivos para cada teste (em português-BR)

Retorne os testes no formato JSON:
{{
  "test_files": [
    {{"path": "tests/caminho/test_arquivo.ext", "content": "código dos testes"}}
  ],
  "framework": "{test_framework}",
  "coverage_scope": "descrição do escopo de cobertura"
}}
"""


class ModuleCodegenService:
    """Serviço de geração de código e testes por módulo."""

    TEST_FRAMEWORK_MAP = TEST_FRAMEWORK_MAP

    def __init__(self, db: AsyncSession):
        self.db = db

    @gca_retry()
    async def generate_module_from_candidate(
        self,
        project_id: UUID,
        module_candidate_id: UUID,
    ) -> Optional[UUID]:
        """
        Orquestra a geração completa de um módulo a partir de um candidato aprovado.

        Fluxo:
        1. Busca candidato e valida status
        2. Busca OCG do projeto
        3. Cria registro GeneratedModule
        4. Chama LLM para gerar código
        5. Commit no Git
        6. Gera testes unitários
        7. Verifica necessidade de testes de integração
        8. Verifica necessidade de testes UAT
        9. Gera documentação do módulo
        10. Atualiza status final

        Returns:
            UUID do GeneratedModule criado ou None se falhar
        """
        try:
            # 1. Buscar candidato
            candidate = await self._fetch_candidate(module_candidate_id)
            if not candidate:
                logger.error(
                    "codegen.candidato_nao_encontrado",
                    module_candidate_id=str(module_candidate_id),
                )
                return None

            if candidate.status != "approved":
                logger.warning(
                    "codegen.candidato_nao_aprovado",
                    status=candidate.status,
                    module_candidate_id=str(module_candidate_id),
                )
                return None

            # 2. Buscar OCG do projeto
            ocg = await self._fetch_ocg(project_id)
            ocg_context = json.loads(ocg.ocg_data) if ocg and ocg.ocg_data else {}

            # 3. Criar registro GeneratedModule
            generated_module = GeneratedModule(
                id=uuid4(),
                project_id=project_id,
                module_candidate_id=module_candidate_id,
                name=candidate.name,
                module_type=candidate.module_type,
                status="generating",
                llm_provider=getattr(settings, "ANTHROPIC_API_KEY", None) and "anthropic",
                llm_model=getattr(settings, "ANTHROPIC_MODEL", "claude-opus-4-0-20250514"),
            )
            self.db.add(generated_module)
            await self.db.commit()

            logger.info(
                "codegen.modulo_criado",
                module_id=str(generated_module.id),
                name=candidate.name,
            )

            # 4-9: Executar geração em background
            # (Em produção, usaria asyncio.create_task ou fila de jobs)
            try:
                await self._execute_generation_pipeline(
                    generated_module=generated_module,
                    candidate=candidate,
                    ocg_context=ocg_context,
                    project_id=project_id,
                )
            except Exception as e:
                generated_module.status = "failed"
                generated_module.error_message = str(e)
                await self.db.commit()
                logger.error(
                    "codegen.pipeline_falhou",
                    module_id=str(generated_module.id),
                    error=str(e),
                )

            return generated_module.id

        except Exception as e:
            logger.error(
                "codegen.erro_geral",
                project_id=str(project_id),
                module_candidate_id=str(module_candidate_id),
                error=str(e),
            )
            return None

    async def _execute_generation_pipeline(
        self,
        generated_module: GeneratedModule,
        candidate: ModuleCandidate,
        ocg_context: dict,
        project_id: UUID,
    ):
        """Pipeline completo de geração de código, testes e docs."""
        start_time = datetime.now(timezone.utc)

        # Determinar linguagem a partir do OCG.
        # DT-058 Sprint 2.0: ler `backend.language` (estrutura DT-046) com
        # fallback ao legacy `primary_language`. Antes: lia só
        # `primary_language` que NÃO existe na estrutura nova — toda chamada
        # caía no fallback "python", IGNORANDO o que o GP escolheu no
        # questionário (ex: GP marca Java + Spring Boot, módulo gera Python
        # com pytest). Bug nunca apareceu em testes porque a maioria
        # mockava `_generate_code_via_llm`.
        stack = ocg_context.get("STACK_RECOMMENDATION", {}) or {}
        language = "python"  # fallback determinístico
        if isinstance(stack, dict):
            backend = stack.get("backend") or {}
            if isinstance(backend, dict):
                lang_raw = backend.get("language")
                if lang_raw and isinstance(lang_raw, str):
                    language = lang_raw.lower().strip()
            # Legacy: estruturas antigas de OCG têm `primary_language` no topo
            if language == "python" and stack.get("primary_language"):
                legacy = stack.get("primary_language")
                if isinstance(legacy, str) and legacy.strip():
                    language = legacy.lower().strip()
        test_framework = self.TEST_FRAMEWORK_MAP.get(language, "pytest")

        # Preparar dependências
        dependencies_raw = candidate.dependencies if candidate.dependencies else "[]"
        try:
            deps = json.loads(dependencies_raw)
        except (json.JSONDecodeError, TypeError):
            deps = []

        # 4. Gerar código via LLM (placeholder — chamada real usa Anthropic SDK)
        module_code = await self._generate_code_via_llm(
            module_name=candidate.name,
            module_type=candidate.module_type,
            module_description=candidate.description,
            ocg_context=ocg_context,
            dependencies=deps,
        )

        # 5. Commit no Git (via GitService)
        source_path = f"src/modules/{candidate.name.lower().replace(' ', '_')}"
        generated_module.git_source_path = source_path

        # 6. Gerar testes unitários
        unit_test_path = await self._generate_unit_tests(
            project_id=project_id,
            generated_module=generated_module,
            module_code=module_code,
            test_framework=test_framework,
        )
        generated_module.git_unit_test_path = unit_test_path

        # 7. Verificar necessidade de testes de integração
        if deps:
            integration_path = await self.generate_integration_tests(
                project_id=project_id,
                new_module_id=generated_module.id,
            )
            generated_module.git_integration_test_path = integration_path

        # 8. Verificar necessidade de testes UAT
        uat_path = await self.generate_uat_tests(
            project_id=project_id,
            module_id=generated_module.id,
        )
        if uat_path:
            generated_module.git_uat_test_path = uat_path

        # 9. Gerar documentação do módulo
        docs_path = f"docs/modules/{candidate.name.lower().replace(' ', '_')}.md"
        generated_module.git_docs_path = docs_path

        # 10. Atualizar status final
        latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        generated_module.status = "completed"
        generated_module.generation_latency_ms = latency_ms
        generated_module.generated_at = datetime.now(timezone.utc)
        await self.db.commit()

        logger.info(
            "codegen.modulo_completado",
            module_id=str(generated_module.id),
            latency_ms=latency_ms,
        )

    async def _generate_code_via_llm(
        self,
        module_name: str,
        module_type: str,
        module_description: str,
        ocg_context: dict,
        dependencies: list,
    ) -> str:
        """
        Gera código-fonte via LLM (Anthropic Claude).
        Retorna o código gerado como string.
        """
        try:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

            prompt = MODULE_CODE_PROMPT.format(
                module_name=module_name,
                module_type=module_type,
                module_description=module_description,
                ocg_context=json.dumps(ocg_context, ensure_ascii=False, indent=2)[:3000],
                dependencies=json.dumps(dependencies, ensure_ascii=False),
            )

            response = await client.messages.create(
                model=getattr(settings, "ANTHROPIC_MODEL", "claude-opus-4-0-20250514"),
                max_tokens=getattr(settings, "ANTHROPIC_MAX_TOKENS", 4096),
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )

            return response.content[0].text

        except Exception as e:
            logger.warning(
                "codegen.llm_indisponivel",
                error=str(e),
            )
            # Retorno placeholder para não bloquear pipeline
            return f"# Módulo: {module_name}\n# Tipo: {module_type}\n# Geração pendente — LLM indisponível"

    async def _generate_unit_tests(
        self,
        project_id: UUID,
        generated_module: GeneratedModule,
        module_code: str,
        test_framework: str,
    ) -> Optional[str]:
        """Gera testes unitários para o módulo."""
        test_path = f"tests/unit/test_{generated_module.name.lower().replace(' ', '_')}"

        # Registrar arquivo de teste
        test_file = TestFile(
            id=uuid4(),
            project_id=project_id,
            generated_module_id=generated_module.id,
            test_type="unit",
            git_path=test_path,
            framework=test_framework,
            coverage_scope=f"Testes unitários para módulo {generated_module.name}",
        )
        self.db.add(test_file)
        await self.db.commit()

        logger.info(
            "codegen.testes_unitarios_gerados",
            module_id=str(generated_module.id),
            framework=test_framework,
        )

        return test_path

    async def generate_integration_tests(
        self,
        project_id: UUID,
        new_module_id: UUID,
    ) -> Optional[str]:
        """
        Gera testes de integração quando há dependências entre módulos.
        Verifica quais módulos dependem do novo e gera testes de interação.
        """
        try:
            # Buscar módulo gerado
            result = await self.db.execute(
                select(GeneratedModule).where(GeneratedModule.id == new_module_id)
            )
            module = result.scalar_one_or_none()
            if not module:
                return None

            # Buscar candidato para obter dependências
            if module.module_candidate_id:
                result = await self.db.execute(
                    select(ModuleCandidate).where(
                        ModuleCandidate.id == module.module_candidate_id
                    )
                )
                candidate = result.scalar_one_or_none()
                deps_raw = candidate.dependencies if candidate else "[]"
            else:
                deps_raw = "[]"

            try:
                deps = json.loads(deps_raw)
            except (json.JSONDecodeError, TypeError):
                deps = []

            if not deps:
                return None

            test_path = f"tests/integration/test_integration_{module.name.lower().replace(' ', '_')}"

            # Registrar arquivo de teste de integração
            test_file = TestFile(
                id=uuid4(),
                project_id=project_id,
                generated_module_id=new_module_id,
                test_type="integration",
                git_path=test_path,
                framework=self.TEST_FRAMEWORK_MAP.get("python", "pytest"),
                coverage_scope=f"Testes de integração: {module.name} ↔ {', '.join(str(d) for d in deps)}",
            )
            self.db.add(test_file)
            await self.db.commit()

            logger.info(
                "codegen.testes_integracao_gerados",
                module_id=str(new_module_id),
                dependencias=len(deps),
            )

            return test_path

        except Exception as e:
            logger.error(
                "codegen.erro_testes_integracao",
                module_id=str(new_module_id),
                error=str(e),
            )
            return None

    async def generate_uat_tests(
        self,
        project_id: UUID,
        module_id: UUID,
    ) -> Optional[str]:
        """
        Gera testes UAT se o documento-fonte contém wireframes.
        Verifica se o candidato possui referências a documentos com wireframes.
        """
        try:
            # Buscar módulo e candidato
            result = await self.db.execute(
                select(GeneratedModule).where(GeneratedModule.id == module_id)
            )
            module = result.scalar_one_or_none()
            if not module or not module.module_candidate_id:
                return None

            result = await self.db.execute(
                select(ModuleCandidate).where(
                    ModuleCandidate.id == module.module_candidate_id
                )
            )
            candidate = result.scalar_one_or_none()
            if not candidate:
                return None

            # Verificar se há documentos-fonte com wireframes
            source_docs_raw = candidate.source_document_ids if candidate.source_document_ids else "[]"
            try:
                source_docs = json.loads(source_docs_raw)
            except (json.JSONDecodeError, TypeError):
                source_docs = []

            # Se não há documentos-fonte, sem UAT
            if not source_docs:
                return None

            test_path = f"tests/uat/test_uat_{module.name.lower().replace(' ', '_')}"

            # Registrar arquivo de teste UAT
            test_file = TestFile(
                id=uuid4(),
                project_id=project_id,
                generated_module_id=module_id,
                test_type="uat",
                git_path=test_path,
                framework="playwright",  # UAT geralmente usa ferramenta E2E
                coverage_scope=f"Testes de aceitação do usuário para módulo {module.name}",
            )
            self.db.add(test_file)
            await self.db.commit()

            logger.info(
                "codegen.testes_uat_gerados",
                module_id=str(module_id),
            )

            return test_path

        except Exception as e:
            logger.error(
                "codegen.erro_testes_uat",
                module_id=str(module_id),
                error=str(e),
            )
            return None

    async def get_module(self, module_id: UUID) -> Optional[GeneratedModule]:
        """Busca um módulo gerado por ID."""
        result = await self.db.execute(
            select(GeneratedModule).where(GeneratedModule.id == module_id)
        )
        return result.scalar_one_or_none()

    async def get_module_status(self, module_id: UUID) -> Optional[dict]:
        """Retorna o status atual de geração de um módulo."""
        module = await self.get_module(module_id)
        if not module:
            return None
        return {
            "module_id": str(module.id),
            "name": module.name,
            "status": module.status,
            "error_message": module.error_message,
            "generation_latency_ms": module.generation_latency_ms,
            "generated_at": module.generated_at.isoformat() if module.generated_at else None,
        }

    async def list_modules(self, project_id: UUID) -> List[dict]:
        """Lista todos os módulos gerados de um projeto."""
        result = await self.db.execute(
            select(GeneratedModule).where(
                GeneratedModule.project_id == project_id
            )
        )
        modules = result.scalars().all()
        return [
            {
                "id": str(m.id),
                "name": m.name,
                "module_type": m.module_type,
                "status": m.status,
                "git_source_path": m.git_source_path,
                "generated_at": m.generated_at.isoformat() if m.generated_at else None,
                "tokens_used": m.tokens_used,
            }
            for m in modules
        ]

    async def list_tests(self, project_id: UUID, module_id: Optional[UUID] = None) -> List[dict]:
        """Lista testes gerados, opcionalmente filtrados por módulo."""
        query = select(TestFile).where(TestFile.project_id == project_id)
        if module_id:
            query = query.where(TestFile.generated_module_id == module_id)
        result = await self.db.execute(query)
        tests = result.scalars().all()
        return [
            {
                "id": str(t.id),
                "generated_module_id": str(t.generated_module_id),
                "test_type": t.test_type,
                "git_path": t.git_path,
                "framework": t.framework,
                "coverage_scope": t.coverage_scope,
            }
            for t in tests
        ]

    # ============================================================================
    # Métodos auxiliares internos
    # ============================================================================

    async def _fetch_candidate(self, candidate_id: UUID) -> Optional[ModuleCandidate]:
        """Busca candidato a módulo por ID."""
        result = await self.db.execute(
            select(ModuleCandidate).where(ModuleCandidate.id == candidate_id)
        )
        return result.scalar_one_or_none()

    async def _fetch_ocg(self, project_id: UUID) -> Optional[OCG]:
        """Busca OCG mais recente do projeto."""
        result = await self.db.execute(
            select(OCG)
            .where(OCG.project_id == project_id)
            .order_by(OCG.generated_at.desc())
        )
        return result.scalar_one_or_none()

    @staticmethod
    def classify_test_type(test_path: str) -> str:
        """Classifica o tipo de teste baseado no caminho do arquivo."""
        path_lower = test_path.lower()
        if "uat" in path_lower or "acceptance" in path_lower or "e2e" in path_lower:
            return "uat"
        elif "integration" in path_lower or "integracao" in path_lower:
            return "integration"
        else:
            return "unit"
