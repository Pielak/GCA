"""DT-058 Sprint 4 — simulação dogfood E2E para 6 linguagens.

Cada teste cria um projeto isolado em `gca_test`, simula o pipeline:
    Questionário (Q23-Q31 com stack específica)
    → OCG.PROJECT_PROFILE populado
    → OCG.STACK_RECOMMENDATION montada via fallback DT-046/047
    → dispatch_scaffold() → arquivos por linguagem
    → validações binárias por linguagem (estrutura + deps + conteúdo)

Rollback automático no fim de cada teste (db_session fixture). Sem
tocar em prod. Sem necessidade de cleanup manual.

Não chama LLM real — usa o stub DT-045 (`AgentService._call_llm`
patchado em conftest) + os fallbacks determinísticos DT-046/047 que
garantem PROJECT_PROFILE/STACK_RECOMMENDATION populados a partir do
questionário sem depender do LLM.
"""
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.services.scaffolders import dispatch_scaffold
from app.services.agent_service import AgentService


# ---------------------------------------------------------------------------
# Stack profiles — overrides do questionário canônico para cada linguagem
# ---------------------------------------------------------------------------

LANGUAGE_PROFILES = {
    "java_spring": {
        "project_name": "Pilot Java Spring",
        "project_slug": "pilot-java-spring",
        "Q27_backend_language": "Java",
        "Q28_backend_framework": ["Spring Boot"],
        "expected_scaffolder": "java_spring",
        "expected_files": {"pom.xml", ".gitignore", "README.md"},
        "expected_pom_strings": ["spring-boot-starter-parent", "spring-boot-starter-web"],
        "language_canonical": "java",
    },
    "java_quarkus": {
        "project_name": "Pilot Java Quarkus",
        "project_slug": "pilot-java-quarkus",
        "Q27_backend_language": "Java",
        "Q28_backend_framework": ["Quarkus"],
        "expected_scaffolder": "java_quarkus",
        "expected_files": {"pom.xml", ".gitignore", "README.md"},
        "expected_pom_strings": ["quarkus-bom", "quarkus-rest-jackson"],
        "language_canonical": "java",
    },
    "kotlin_spring": {
        "project_name": "Pilot Kotlin Spring",
        "project_slug": "pilot-kotlin-spring",
        "Q27_backend_language": "Kotlin",
        "Q28_backend_framework": ["Spring Boot"],
        "expected_scaffolder": "kotlin_spring",
        "expected_files": {"build.gradle.kts", "settings.gradle.kts"},
        "expected_pom_strings": [],  # Kotlin usa Gradle, não Maven
        "language_canonical": "kotlin",
    },
    "go_chi": {
        "project_name": "Pilot Go",
        "project_slug": "pilot-go",
        "Q27_backend_language": "Go",
        "Q28_backend_framework": ["Sem preferência"],
        "expected_scaffolder": "go_app",
        "expected_files": {"go.mod", "cmd/server/main.go"},
        "expected_pom_strings": [],
        "language_canonical": "go",
    },
    "csharp_aspnet": {
        "project_name": "Pilot C-Sharp",
        "project_slug": "pilot-csharp",
        "Q27_backend_language": "C#",
        "Q28_backend_framework": ["ASP.NET"],
        "expected_scaffolder": "csharp_aspnet",
        "expected_files_pattern": ".sln",  # nome dinâmico baseado no slug
        "expected_pom_strings": [],
        "language_canonical": "c#",
    },
    "php_laravel": {
        "project_name": "Pilot PHP",
        "project_slug": "pilot-php",
        "Q27_backend_language": "PHP",
        "Q28_backend_framework": ["Sem preferência"],
        "expected_scaffolder": "php_laravel",
        "expected_files": {"composer.json", "artisan", "public/index.php"},
        "expected_pom_strings": [],
        "language_canonical": "php",
    },
    "nodejs_nestjs": {
        "project_name": "Pilot Node NestJS",
        "project_slug": "pilot-nestjs",
        "Q27_backend_language": "Node.js",
        "Q28_backend_framework": ["NestJS"],
        "expected_scaffolder": "nodejs_nestjs",
        "expected_files": {"package.json", "tsconfig.json", "src/main.ts"},
        "expected_pom_strings": [],
        "language_canonical": "node.js",
    },
}


# ---------------------------------------------------------------------------
# Helper: monta OCG.STACK_RECOMMENDATION a partir do PROJECT_PROFILE via DT-047
# ---------------------------------------------------------------------------

def _build_project_metadata_from_profile(language: str, framework: list) -> dict:
    """Replica o `project_metadata` que `ocg_service.generate_ocg_from_questionnaire`
    monta a partir das respostas do questionário."""
    return {
        "project_name": "Pilot Project",
        "project_type": "Novo sistema",
        "criticality": "Alta",
        "has_frontend": True,
        "frontend_stack": ["React", "Vite + React"],
        "frontend_language": "TypeScript",
        "frontend_type": ["Web SPA"],
        "has_backend": True,
        "backend_language": language,
        "backend_framework": framework,
        "backend_type": ["REST API"],
        "database": "PostgreSQL",
        "database_profile": ["Transacional"],
        "uses_redis": True,
        "redis_purpose": ["Cache de leitura"],
        "uses_ai": True,
        "ai_provider": ["Anthropic"],
        "security_controls": ["JWT", "HTTPS", "Cripto repouso"],
        "test_types": ["Unitários", "Integração", "E2E", "Segurança"],
        "quality_gate": True,
        "qa_evidence": True,
        "pipeline_deliverables": ["Arquitetura", "Stack", "Doc técnico"],
        "output_formats": ["Painel GCA", "Markdown", "PDF"],
        "architecture": ["Monólito modular"],
        "execution_model": ["Containerizado"],
        "multi_tenant": "Não",
        "high_availability": "Sim",
        "async_processing": "Sim",
    }


def _build_stack_via_dt047(language: str, framework: list) -> dict:
    """Usa o helper DT-047 (sem LLM) pra montar STACK_RECOMMENDATION
    canônica como o consolidator faria."""
    metadata = _build_project_metadata_from_profile(language, framework)
    return AgentService._stack_from_metadata(metadata)


# ---------------------------------------------------------------------------
# Testes parametrizados — 1 por linguagem
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "profile_key",
    sorted(LANGUAGE_PROFILES.keys()),
    ids=lambda k: k,
)
def test_dispatch_produces_scaffolder_for_language(profile_key):
    """Pra cada linguagem do questionário Q27/Q28, dispatch_scaffold rota
    pro scaffolder esperado e gera arquivos com a estrutura mínima.

    Não persiste nada no DB — dispatch_scaffold é função pura. Valida
    que o caminho `questionário Q27 → OCG.STACK → dispatch → arquivos`
    resolve binariamente pra cada uma das 6 stacks suportadas.
    """
    profile = LANGUAGE_PROFILES[profile_key]
    stack = _build_stack_via_dt047(
        profile["Q27_backend_language"], profile["Q28_backend_framework"]
    )

    # Sanity: `_stack_from_metadata` produziu a estrutura DT-046 esperada
    assert stack["backend"]["enabled"] is True
    backend_lang = stack["backend"]["language"].lower().strip()
    assert backend_lang == profile["language_canonical"], (
        f"Esperava backend.language='{profile['language_canonical']}', "
        f"got '{backend_lang}'"
    )

    # Reconstroi o STACK_RECOMMENDATION como o OCG persistiria + chama
    # dispatch_scaffold com nome/slug do projeto.
    result = dispatch_scaffold(
        stack,
        profile["project_name"],
        profile["project_slug"],
    )

    assert result is not None, f"Scaffolder não encontrado para {profile_key}"
    name, files = result

    assert name == profile["expected_scaffolder"], (
        f"Esperava scaffolder='{profile['expected_scaffolder']}', got '{name}'"
    )
    assert len(files) >= 3, f"Scaffolder produziu poucos arquivos: {len(files)}"

    paths = {f.path for f in files}

    # Arquivos esperados podem ser set fixo OU pattern (csharp tem nome dinâmico)
    if "expected_files" in profile:
        for expected in profile["expected_files"]:
            assert expected in paths, (
                f"{profile_key}: arquivo '{expected}' faltando. "
                f"Gerados: {sorted(paths)}"
            )
    elif "expected_files_pattern" in profile:
        pattern = profile["expected_files_pattern"]
        assert any(pattern in p for p in paths), (
            f"{profile_key}: nenhum arquivo contém '{pattern}'. "
            f"Gerados: {sorted(paths)}"
        )

    # Conteúdo do POM (se aplicável)
    if profile.get("expected_pom_strings"):
        pom = next(f for f in files if f.path == "pom.xml")
        for expected_str in profile["expected_pom_strings"]:
            assert expected_str in pom.content, (
                f"{profile_key}: pom.xml não contém '{expected_str}'"
            )


# ---------------------------------------------------------------------------
# Teste E2E em DB isolado — projeto persistido + questionário + cleanup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("profile_key", sorted(LANGUAGE_PROFILES.keys()), ids=lambda k: k)
async def test_full_pipeline_with_real_project_in_isolated_db(
    profile_key, db_session
):
    """Cria projeto real em `gca_test` (isolado), persiste questionnaire +
    OCG sintético, valida que o consolidator path produz STACK que o
    dispatch resolve corretamente.

    Rollback automático no fim do teste — `gca_test` fica intacto pro
    próximo run. Zero impacto em `gca` (prod).
    """
    from app.tests.factories import create_test_organization, create_test_project
    from app.models.base import OCG, Questionnaire

    profile = LANGUAGE_PROFILES[profile_key]
    org = await create_test_organization(db_session)
    project = await create_test_project(
        db_session,
        organization_id=org.id,
        name=profile["project_name"],
        slug=profile["project_slug"],
    )

    # Cria Questionnaire mínimo
    q_id = uuid4()
    responses = {
        "1": profile["project_name"],
        "2": profile["project_slug"],
        "27": profile["Q27_backend_language"],
        "28": profile["Q28_backend_framework"],
    }
    q = Questionnaire(
        id=q_id,
        project_id=project.id,
        gp_email="pilot@example.com",
        responses=json.dumps(responses),
        status="approved",
        adherence_score=95,
        approved=True,
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(q)
    await db_session.flush()

    # Monta OCG sintético com STACK via DT-047 helper (sem chamar consolidator real)
    stack = _build_stack_via_dt047(
        profile["Q27_backend_language"], profile["Q28_backend_framework"]
    )
    architecture = AgentService._architecture_from_metadata(
        _build_project_metadata_from_profile(
            profile["Q27_backend_language"], profile["Q28_backend_framework"]
        )
    )
    ocg_data = {
        "ocg_id": str(uuid4()),
        "questionnaire_id": str(q_id),
        "project_id": str(project.id),
        "PROJECT_PROFILE": _build_project_metadata_from_profile(
            profile["Q27_backend_language"], profile["Q28_backend_framework"]
        ),
        "STACK_RECOMMENDATION": stack,
        "ARCHITECTURE_OVERVIEW": architecture,
        "PILLAR_SCORES": {f"P{i}": {"score": 80} for i in range(1, 8)},
        "COMPOSITE_SCORE": {"overall": 80, "status": "READY", "is_blocking": False},
        "CRITICAL_FINDINGS": [],
        "TESTING_REQUIREMENTS": {},
        "COMPLIANCE_CHECKLIST": [],
        "DELIVERABLES": [],
        "RISK_ANALYSIS": {},
        "APPROVAL_STATUS": {"status": "READY"},
    }
    ocg = OCG(
        id=uuid4(),
        questionnaire_id=q_id,
        project_id=project.id,
        p1_business_score=80, p2_rules_score=80, p3_features_score=80,
        p4_nfr_score=80, p5_architecture_score=80, p6_data_score=80, p7_security_score=80,
        overall_score=80,
        status="READY",
        is_blocking=False,
        ocg_data=json.dumps(ocg_data),
        generated_at=datetime.now(timezone.utc),
    )
    db_session.add(ocg)
    await db_session.flush()

    # ASSERTIONS — validar que o pipeline persistido resolve o dispatch
    # corretamente para a linguagem deste piloto.
    persisted_stack = json.loads(ocg.ocg_data)["STACK_RECOMMENDATION"]
    result = dispatch_scaffold(
        persisted_stack, project.name, project.slug
    )
    assert result is not None
    scaffolder_name, files = result
    assert scaffolder_name == profile["expected_scaffolder"], (
        f"Pipeline E2E para {profile_key} deveria rotear pra "
        f"{profile['expected_scaffolder']}, got {scaffolder_name}"
    )
    assert len(files) >= 3

    # Cleanup acontece automaticamente: db_session faz rollback.
    # Próximo teste começa com DB limpo. `gca` (prod) intacta.


# ---------------------------------------------------------------------------
# Sumário global — 1 teste que valida que TODAS as 6 linguagens funcionam
# ---------------------------------------------------------------------------

def test_all_supported_languages_have_working_scaffolder():
    """Garante que cada linguagem em LANGUAGE_PROFILES tem scaffolder
    funcional. Falha imediata se alguma quebrar — fail-fast pra
    regressão de cobertura."""
    failed = []
    for key, profile in LANGUAGE_PROFILES.items():
        stack = _build_stack_via_dt047(
            profile["Q27_backend_language"], profile["Q28_backend_framework"]
        )
        result = dispatch_scaffold(stack, profile["project_name"], profile["project_slug"])
        if result is None:
            failed.append(f"{key}: dispatch retornou None")
            continue
        name, files = result
        if name != profile["expected_scaffolder"]:
            failed.append(f"{key}: scaffolder='{name}' (esperava '{profile['expected_scaffolder']}')")
        if len(files) < 3:
            failed.append(f"{key}: só {len(files)} arquivos gerados")

    assert not failed, "Linguagens com problemas:\n" + "\n".join(failed)
