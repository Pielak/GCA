"""
Technology Verification Pipeline — Validação profunda pré-OCG

Este serviço é o guardião de qualidade entre o questionário e o OCG.
Nenhum OCG pode ser gerado sem passar por esta verificação.

Pipeline:
  1. Validação de completude (campos obrigatórios)
  2. Compatibilidade de Stack (linguagem ↔ framework ↔ banco ↔ arquitetura)
  3. Consistência cross-pillar (P1-P7 sem contradições)
  4. Viabilidade tecnológica (combinações impossíveis/arriscadas)
  5. Análise de risco por pilar
  6. Geração do bloco A.12 real (Q50-Q54)

Resultado: aprovado para OCG ou devolvido com ações corretivas.
"""

from typing import Dict, Any, List, Tuple, Optional, Set
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class Severity(str, Enum):
    BLOCKER = "blocker"       # Impede geração do OCG
    CRITICAL = "critical"     # Risco alto, requer justificativa
    WARNING = "warning"       # Recomendação forte
    INFO = "info"             # Sugestão


class Category(str, Enum):
    STACK_COMPAT = "stack_compatibility"
    ARCH_CONSISTENCY = "architecture_consistency"
    CROSS_PILLAR = "cross_pillar"
    TECH_FEASIBILITY = "technology_feasibility"
    SECURITY_COMPLIANCE = "security_compliance"
    DATA_CONSISTENCY = "data_consistency"
    COMPLETENESS = "completeness"
    DELIVERY_ALIGNMENT = "delivery_alignment"


class Finding:
    """Achado individual da verificação."""

    def __init__(
        self,
        category: Category,
        severity: Severity,
        rule_id: str,
        title: str,
        description: str,
        affected_questions: List[str],
        suggestion: str,
        pillar: Optional[str] = None,
    ):
        self.category = category
        self.severity = severity
        self.rule_id = rule_id
        self.title = title
        self.description = description
        self.affected_questions = affected_questions
        self.suggestion = suggestion
        self.pillar = pillar

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "rule_id": self.rule_id,
            "title": self.title,
            "description": self.description,
            "affected_questions": self.affected_questions,
            "suggestion": self.suggestion,
            "pillar": self.pillar,
        }


# ============================================================================
# MATRIZES DE COMPATIBILIDADE
# ============================================================================

# Linguagem → Frameworks válidos
LANGUAGE_FRAMEWORK_MATRIX: Dict[str, Set[str]] = {
    "Python": {"FastAPI", "Django", "Flask", "Sem preferência"},
    "Node.js": {"NestJS", "Express", "Sem preferência"},
    "Java": {"Spring Boot", "Quarkus", "Sem preferência"},
    "C#": {"ASP.NET", "Sem preferência"},
    "Go": {"Sem preferência"},
    "PHP": {"Sem preferência"},
    "Kotlin": {"Spring Boot", "Quarkus", "Sem preferência"},
}

# Framework → Bancos recomendados (não bloqueante, mas warning)
FRAMEWORK_DB_RECOMMENDED: Dict[str, Set[str]] = {
    "FastAPI": {"PostgreSQL", "MySQL", "MongoDB", "SQLite"},
    "Django": {"PostgreSQL", "MySQL", "SQLite"},
    "Flask": {"PostgreSQL", "MySQL", "MongoDB", "SQLite"},
    "NestJS": {"PostgreSQL", "MySQL", "MongoDB"},
    "Express": {"PostgreSQL", "MySQL", "MongoDB"},
    "Spring Boot": {"PostgreSQL", "MySQL", "Oracle", "SQL Server"},
    "ASP.NET": {"SQL Server", "PostgreSQL", "MySQL"},
    "Quarkus": {"PostgreSQL", "MySQL", "Oracle"},
}

# Frontend Stack → Linguagens válidas
FRONTEND_LANGUAGE_MATRIX: Dict[str, Set[str]] = {
    "React": {"TypeScript", "JavaScript"},
    "Vue": {"TypeScript", "JavaScript"},
    "Angular": {"TypeScript"},
    "Next.js": {"TypeScript", "JavaScript"},
    "Vite + React": {"TypeScript", "JavaScript"},
    "Electron": {"TypeScript", "JavaScript"},
    "Flutter": {"Outra"},  # Dart
    "React Native": {"TypeScript", "JavaScript"},
}

# Arquitetura → Modelos de execução compatíveis
ARCH_EXECUTION_MATRIX: Dict[str, Set[str]] = {
    "Monólito": {"Stand-alone", "On-premises", "Cloud", "Containerizado"},
    "Monólito modular": {"Stand-alone", "On-premises", "Cloud", "Containerizado"},
    "Microserviços": {"Cloud", "Containerizado", "Híbrido"},
    "Event-driven": {"Cloud", "Containerizado", "Híbrido"},
    "Hexagonal": {"Stand-alone", "On-premises", "Cloud", "Containerizado"},
    "Clean Architecture": {"Stand-alone", "On-premises", "Cloud", "Containerizado"},
    "Serverless": {"Cloud"},
    "Desktop local": {"Stand-alone", "Offline com sincronização posterior"},
}

# Entregável → Requer frontend/backend
DELIVERABLE_REQUIREMENTS: Dict[str, Dict[str, bool]] = {
    "Executável desktop": {"frontend": True, "backend": False},
    "Aplicação web": {"frontend": True, "backend": True},
    "API": {"frontend": False, "backend": True},
    "Microserviço": {"frontend": False, "backend": True},
    "Aplicativo mobile": {"frontend": True, "backend": True},
    "Dashboard": {"frontend": True, "backend": True},
    "Job/Worker": {"frontend": False, "backend": True},
    "CLI": {"frontend": False, "backend": True},
    "Biblioteca/SDK": {"frontend": False, "backend": True},
}

# Combinações de banco + perfil de uso arriscadas
DB_USAGE_RISKS: Dict[str, Set[str]] = {
    "SQLite": {"Transacional"},  # SQLite não é ideal para transacional pesado
    "MongoDB": {"Transacional"},  # MongoDB não é ACID completo por padrão
}

# Bancos inadequados para arquiteturas específicas
DB_ARCH_INCOMPATIBLE: Dict[str, Set[str]] = {
    "SQLite": {"Microserviços", "Event-driven", "Serverless"},
    # MongoDB com event store é ok, mas relacional com event store é warning
}

# Frontend stack → Tipo de entregável compatível
FRONTEND_DELIVERABLE_MATRIX: Dict[str, Set[str]] = {
    "Electron": {"Executável desktop"},
    "Flutter": {"Aplicativo mobile", "Aplicação web"},
    "React Native": {"Aplicativo mobile"},
    "React": {"Aplicação web", "Dashboard", "Painel administrativo", "Portal autenticado"},
    "Vue": {"Aplicação web", "Dashboard", "Painel administrativo", "Portal autenticado"},
    "Angular": {"Aplicação web", "Dashboard", "Painel administrativo", "Portal autenticado"},
    "Next.js": {"Aplicação web", "Dashboard", "Portal autenticado"},
    "Vite + React": {"Aplicação web", "Dashboard", "Painel administrativo", "Portal autenticado"},
}


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        return [value]
    return []


class TechnologyVerificationService:
    """Pipeline de verificação de tecnologia pré-OCG."""

    def __init__(self, responses: Dict[str, Any]):
        from app.schemas.questionnaire import extract_named_fields
        self.raw = responses
        self.r = extract_named_fields(responses)
        self.findings: List[Finding] = []
        self._extract_fields()

    def _extract_fields(self):
        """Extrai todos os campos necessários para análise."""
        r = self.r

        # A.1
        self.project_name = r.get("project_name", "")
        self.is_existing = r.get("is_existing_project", "Não")
        self.initiative_type = _as_list(r.get("initiative_type", []))
        self.criticality = r.get("criticality", "")
        self.info_classification = r.get("information_classification", "")

        # A.2
        self.existing_system = r.get("existing_system_name", "")
        self.main_repo = r.get("main_repository", "")
        self.access_level = r.get("repository_access_level", "")
        self.change_objectives = _as_list(r.get("change_objective", []))
        self.authorize_n8n = r.get("authorize_n8n_analysis", "")
        self.n8n_scope = _as_list(r.get("n8n_analysis_scope", []))

        # A.3
        self.deliverables = _as_list(r.get("main_deliverable", []))
        self.arch_profiles = _as_list(r.get("architectural_profile", []))
        self.exec_model = r.get("execution_model", "")
        self.multi_tenant = r.get("multi_tenant", "Não")
        self.high_availability = r.get("high_availability", "Não")
        self.async_processing = r.get("async_processing", "Não")

        # A.4
        self.has_frontend = r.get("has_frontend", "Não")
        self.frontend_types = _as_list(r.get("frontend_type", []))
        self.frontend_stacks = _as_list(r.get("frontend_stack", []))
        self.frontend_lang = r.get("frontend_language", "")
        self.frontend_reqs = _as_list(r.get("frontend_requirements", []))

        # A.5
        self.has_backend = r.get("has_backend", "Não")
        self.backend_lang = r.get("backend_language", "")
        self.backend_frameworks = _as_list(r.get("backend_framework", []))
        self.backend_types = _as_list(r.get("backend_type", []))
        self.backend_reqs = _as_list(r.get("backend_requirements", []))

        # A.6
        self.primary_db = r.get("primary_database", "")
        self.db_usage = _as_list(r.get("database_usage_profile", []))
        self.needs_redis = r.get("needs_redis", "Não")
        self.redis_purposes = _as_list(r.get("redis_purpose", []))
        self.needs_messaging = r.get("needs_messaging", "Não")
        self.messaging_purposes = _as_list(r.get("messaging_purpose", []))
        self.uses_n8n = r.get("uses_n8n", "Não")
        self.n8n_purposes = _as_list(r.get("n8n_purpose", []))

        # A.7
        self.uses_ai = r.get("uses_ai", "Não")
        self.ai_purposes = _as_list(r.get("ai_purpose", []))
        self.ai_providers = _as_list(r.get("ai_provider", []))
        self.ai_restrictions = _as_list(r.get("ai_restrictions", []))
        self.security_controls = _as_list(r.get("security_controls", []))
        self.observability = _as_list(r.get("observability", []))

        # A.8
        self.test_types = _as_list(r.get("test_types", []))
        self.quality_gate = r.get("automated_quality_gate", "Não")
        self.formal_qa = r.get("formal_qa_evidence", "Não")
        self.pipeline_deliverables = _as_list(r.get("pipeline_deliverables", []))
        self.output_formats = _as_list(r.get("output_format", []))

    # ========================================================================
    # PIPELINE PRINCIPAL
    # ========================================================================

    def run_full_pipeline(self) -> Dict[str, Any]:
        """Executa o pipeline completo de verificação."""
        logger.info("technology_verification.start", project=self.project_name)

        # Fase 1: Completude
        self._check_completeness()

        # Fase 2: Compatibilidade de stack
        self._check_language_framework_compat()
        self._check_frontend_language_compat()
        self._check_framework_db_compat()
        self._check_frontend_deliverable_compat()

        # Fase 3: Consistência arquitetural
        self._check_arch_execution_compat()
        self._check_arch_conflicts()
        self._check_deliverable_requirements()
        self._check_db_arch_compat()
        self._check_db_usage_risks()

        # Fase 4: Viabilidade tecnológica
        self._check_tech_feasibility()

        # Fase 5: Consistência cross-pillar
        self._check_cross_pillar_p1_p5()
        self._check_cross_pillar_p3_p4()
        self._check_cross_pillar_p5_p7()
        self._check_cross_pillar_p2_p7()
        self._check_cross_pillar_p3_p6()

        # Fase 6: Segurança e compliance
        self._check_security_compliance()

        # Fase 7: Coerência de entregáveis
        self._check_delivery_alignment()

        # Fase 8: Validações específicas de projeto existente
        if self.is_existing == "Sim":
            self._check_existing_project()

        # Gerar resultado
        result = self._build_result()

        logger.info(
            "technology_verification.complete",
            project=self.project_name,
            findings=len(self.findings),
            blockers=result["summary"]["blockers"],
            approved=result["approved_for_ocg"],
        )

        return result

    # ========================================================================
    # FASE 1: COMPLETUDE
    # ========================================================================

    def _check_completeness(self):
        """Verifica campos obrigatórios."""

        if not self.project_name:
            self._add(Category.COMPLETENESS, Severity.BLOCKER, "COMP-001",
                      "Nome do projeto ausente",
                      "Campo obrigatório Q1 (project_name) não preenchido.",
                      ["1"], "Informe o nome do projeto.")

        if not self.criticality:
            self._add(Category.COMPLETENESS, Severity.BLOCKER, "COMP-002",
                      "Criticidade não definida",
                      "Campo obrigatório Q5 (criticality) não preenchido.",
                      ["5"], "Selecione o nível de criticidade do projeto.")

        if not self.info_classification:
            self._add(Category.COMPLETENESS, Severity.BLOCKER, "COMP-003",
                      "Classificação da informação ausente",
                      "Campo obrigatório Q6 (information_classification) não preenchido.",
                      ["6"], "Selecione a classificação da informação.")

        if not self.deliverables:
            self._add(Category.COMPLETENESS, Severity.BLOCKER, "COMP-004",
                      "Entregável principal não definido",
                      "Q15 não preenchido — sem entregável, não há como definir arquitetura.",
                      ["15"], "Selecione pelo menos um entregável principal.")

        if self.has_frontend == "Sim" and not self.frontend_stacks:
            self._add(Category.COMPLETENESS, Severity.BLOCKER, "COMP-005",
                      "Frontend habilitado sem stack",
                      "Q21='Sim' mas Q23 (frontend_stack) está vazio.",
                      ["21", "23"], "Selecione a stack de frontend ou desabilite o frontend.")

        if self.has_backend == "Sim" and not self.backend_lang:
            self._add(Category.COMPLETENESS, Severity.BLOCKER, "COMP-006",
                      "Backend habilitado sem linguagem",
                      "Q26='Sim' mas Q27 (backend_language) está vazio.",
                      ["26", "27"], "Selecione a linguagem do backend.")

        if self.has_backend == "Sim" and not self.backend_frameworks:
            self._add(Category.COMPLETENESS, Severity.WARNING, "COMP-007",
                      "Backend sem framework definido",
                      "Q28 (backend_framework) vazio. O framework será inferido pela linguagem, mas recomenda-se especificar.",
                      ["28"], "Selecione o framework ou marque 'Sem preferência'.")

        if self.uses_ai != "Sim":
            self._add(Category.COMPLETENESS, Severity.BLOCKER, "COMP-008",
                      "IA é obrigatória em projetos GCA",
                      "Q39 deve ser 'Sim'. O GCA é uma plataforma de codificação assistida por IA.",
                      ["39"], "Marque 'Sim' e selecione provedor (Q41) e finalidade (Q40).")

        if self.uses_ai == "Sim" and not self.ai_providers:
            self._add(Category.COMPLETENESS, Severity.BLOCKER, "COMP-009",
                      "IA habilitada sem provedor",
                      "Q39='Sim' mas Q41 (ai_provider) está vazio.",
                      ["39", "41"], "Selecione pelo menos um provedor de IA.")

        if not self.security_controls:
            self._add(Category.COMPLETENESS, Severity.BLOCKER, "COMP-010",
                      "Nenhum controle de segurança selecionado",
                      "Q43 está vazio. Todo projeto precisa de controles de segurança.",
                      ["43"], "Selecione pelo menos JWT ou OAuth2 + criptografia.")

        if not self.test_types:
            self._add(Category.COMPLETENESS, Severity.BLOCKER, "COMP-011",
                      "Nenhum tipo de teste definido",
                      "Q45 está vazio. Projetos sem testes não passam pela verificação.",
                      ["45"], "Selecione pelo menos: Unitários, Integração, E2E.")

    # ========================================================================
    # FASE 2: COMPATIBILIDADE DE STACK
    # ========================================================================

    def _check_language_framework_compat(self):
        """Verifica se linguagem ↔ framework são compatíveis."""
        if not self.backend_lang or not self.backend_frameworks:
            return

        valid = LANGUAGE_FRAMEWORK_MATRIX.get(self.backend_lang, set())
        if not valid:
            return

        for fw in self.backend_frameworks:
            if fw == "Sem preferência":
                continue
            if fw not in valid:
                self._add(
                    Category.STACK_COMPAT, Severity.BLOCKER, "STACK-001",
                    f"{self.backend_lang} + {fw} são incompatíveis",
                    f"A linguagem '{self.backend_lang}' (Q27) não suporta o framework "
                    f"'{fw}' (Q28). Frameworks válidos para {self.backend_lang}: "
                    f"{', '.join(sorted(valid - {'Sem preferência'}))}.",
                    ["27", "28"],
                    f"Altere o framework para um compatível com {self.backend_lang} "
                    f"ou mude a linguagem.",
                    pillar="P5",
                )

    def _check_frontend_language_compat(self):
        """Verifica se stack frontend ↔ linguagem frontend são compatíveis."""
        if not self.frontend_stacks or not self.frontend_lang:
            return

        for stack in self.frontend_stacks:
            valid_langs = FRONTEND_LANGUAGE_MATRIX.get(stack, set())
            if not valid_langs:
                continue
            if self.frontend_lang not in valid_langs:
                self._add(
                    Category.STACK_COMPAT, Severity.BLOCKER, "STACK-002",
                    f"{stack} + {self.frontend_lang} são incompatíveis",
                    f"O framework '{stack}' (Q23) não funciona com "
                    f"'{self.frontend_lang}' (Q24). Linguagens válidas para {stack}: "
                    f"{', '.join(sorted(valid_langs))}.",
                    ["23", "24"],
                    f"Altere a linguagem para uma compatível com {stack}.",
                    pillar="P5",
                )

    def _check_framework_db_compat(self):
        """Verifica se framework ↔ banco de dados são compatíveis."""
        if not self.backend_frameworks or not self.primary_db:
            return
        if self.primary_db == "Sem preferência":
            return

        for fw in self.backend_frameworks:
            recommended = FRAMEWORK_DB_RECOMMENDED.get(fw)
            if not recommended:
                continue
            if self.primary_db not in recommended:
                self._add(
                    Category.STACK_COMPAT, Severity.WARNING, "STACK-003",
                    f"{fw} + {self.primary_db}: combinação incomum",
                    f"O framework '{fw}' (Q28) normalmente é usado com "
                    f"{', '.join(sorted(recommended))}. '{self.primary_db}' (Q31) "
                    f"pode funcionar, mas requer configuração adicional e pode ter "
                    f"menor suporte da comunidade/ORM.",
                    ["28", "31"],
                    f"Considere usar um banco mais comum com {fw} ou justifique a escolha.",
                    pillar="P6",
                )

    def _check_frontend_deliverable_compat(self):
        """Verifica se stack frontend é compatível com o tipo de entregável."""
        if not self.frontend_stacks or not self.deliverables:
            return

        for stack in self.frontend_stacks:
            valid_deliverables = FRONTEND_DELIVERABLE_MATRIX.get(stack)
            if not valid_deliverables:
                continue

            # Verifica se pelo menos um entregável é compatível com a stack
            compatible = any(d in valid_deliverables for d in self.deliverables)
            if not compatible:
                self._add(
                    Category.STACK_COMPAT, Severity.CRITICAL, "STACK-004",
                    f"{stack} não é adequado para {', '.join(self.deliverables)}",
                    f"A stack '{stack}' (Q23) foi projetada para "
                    f"{', '.join(sorted(valid_deliverables))}. "
                    f"O entregável selecionado ({', '.join(self.deliverables)}) (Q15) "
                    f"não se encaixa nessa stack.",
                    ["15", "23"],
                    f"Altere a stack de frontend ou o tipo de entregável.",
                    pillar="P5",
                )

    # ========================================================================
    # FASE 3: CONSISTÊNCIA ARQUITETURAL
    # ========================================================================

    def _check_arch_execution_compat(self):
        """Verifica se perfil arquitetural ↔ modelo de execução são compatíveis."""
        if not self.arch_profiles or not self.exec_model:
            return

        for arch in self.arch_profiles:
            valid_exec = ARCH_EXECUTION_MATRIX.get(arch)
            if not valid_exec:
                continue
            if self.exec_model not in valid_exec:
                self._add(
                    Category.ARCH_CONSISTENCY, Severity.BLOCKER, "ARCH-001",
                    f"{arch} + {self.exec_model}: incompatível",
                    f"A arquitetura '{arch}' (Q16) não funciona com o modelo de execução "
                    f"'{self.exec_model}' (Q17). Modelos válidos: "
                    f"{', '.join(sorted(valid_exec))}.",
                    ["16", "17"],
                    f"Altere o modelo de execução para um compatível com {arch}.",
                    pillar="P5",
                )

    def _check_arch_conflicts(self):
        """Detecta arquiteturas mutuamente excludentes."""
        mutually_exclusive = [
            ({"Monólito", "Monólito modular"}, {"Microserviços", "Serverless"}),
            ({"Desktop local"}, {"Serverless", "Microserviços", "Event-driven"}),
        ]

        for group_a, group_b in mutually_exclusive:
            has_a = group_a & set(self.arch_profiles)
            has_b = group_b & set(self.arch_profiles)
            if has_a and has_b:
                self._add(
                    Category.ARCH_CONSISTENCY, Severity.BLOCKER, "ARCH-002",
                    f"Arquiteturas conflitantes: {', '.join(has_a)} + {', '.join(has_b)}",
                    f"As arquiteturas {', '.join(has_a)} e {', '.join(has_b)} "
                    f"são mutuamente excludentes. Não é possível ser monolítico "
                    f"e distribuído ao mesmo tempo.",
                    ["16"],
                    "Escolha UMA direção arquitetural principal.",
                    pillar="P5",
                )

        # Monólito modular + Clean Architecture = ok (complementares)
        # Mas Monólito + Hexagonal precisa de cuidado
        if "Monólito" in self.arch_profiles and len(self.arch_profiles) > 1:
            extras = set(self.arch_profiles) - {"Monólito"}
            complementary = {"Hexagonal", "Clean Architecture"}
            non_complementary = extras - complementary
            if non_complementary:
                self._add(
                    Category.ARCH_CONSISTENCY, Severity.WARNING, "ARCH-003",
                    f"Monólito com perfis adicionais: {', '.join(non_complementary)}",
                    f"'Monólito' combinado com {', '.join(non_complementary)} pode "
                    f"gerar ambiguidade na geração do OCG. Apenas Hexagonal e "
                    f"Clean Architecture são complementares naturais do monólito.",
                    ["16"],
                    "Revise se os perfis adicionais são realmente necessários.",
                    pillar="P5",
                )

    def _check_deliverable_requirements(self):
        """Verifica se frontend/backend estão habilitados conforme o entregável."""
        for deliv in self.deliverables:
            reqs = DELIVERABLE_REQUIREMENTS.get(deliv, {})

            if reqs.get("frontend") and self.has_frontend != "Sim":
                self._add(
                    Category.DELIVERY_ALIGNMENT, Severity.BLOCKER, "DELIV-001",
                    f"'{deliv}' requer frontend habilitado",
                    f"O entregável '{deliv}' (Q15) precisa de frontend, "
                    f"mas Q21='Não'.",
                    ["15", "21"],
                    "Habilite o frontend (Q21='Sim') ou remova este entregável.",
                    pillar="P3",
                )

            if reqs.get("backend") and self.has_backend != "Sim":
                self._add(
                    Category.DELIVERY_ALIGNMENT, Severity.BLOCKER, "DELIV-002",
                    f"'{deliv}' requer backend habilitado",
                    f"O entregável '{deliv}' (Q15) precisa de backend, "
                    f"mas Q26='Não'.",
                    ["15", "26"],
                    "Habilite o backend (Q26='Sim') ou remova este entregável.",
                    pillar="P3",
                )

    def _check_db_arch_compat(self):
        """Verifica se banco de dados é adequado para a arquitetura."""
        if not self.primary_db:
            return

        incompatible = DB_ARCH_INCOMPATIBLE.get(self.primary_db, set())
        conflicting = incompatible & set(self.arch_profiles)
        if conflicting:
            self._add(
                Category.DATA_CONSISTENCY, Severity.BLOCKER, "DATA-001",
                f"{self.primary_db} é inadequado para {', '.join(conflicting)}",
                f"O banco '{self.primary_db}' (Q31) não suporta arquitetura "
                f"{', '.join(conflicting)} (Q16). {self.primary_db} é single-file "
                f"e não suporta acesso concorrente de múltiplos serviços.",
                ["31", "16"],
                "Use PostgreSQL, MySQL ou outro banco cliente-servidor.",
                pillar="P6",
            )

    def _check_db_usage_risks(self):
        """Verifica riscos no perfil de uso do banco."""
        if not self.primary_db or not self.db_usage:
            return

        risks = DB_USAGE_RISKS.get(self.primary_db, set())
        risky_usages = risks & set(self.db_usage)
        if risky_usages:
            if self.primary_db == "SQLite":
                self._add(
                    Category.DATA_CONSISTENCY, Severity.CRITICAL, "DATA-002",
                    f"SQLite com perfil {', '.join(risky_usages)}: risco alto",
                    "SQLite não foi projetado para carga transacional pesada. "
                    "Suporta apenas um writer por vez, sem concorrência real.",
                    ["31", "32"],
                    "Para perfil transacional, use PostgreSQL ou MySQL.",
                    pillar="P6",
                )
            elif self.primary_db == "MongoDB":
                self._add(
                    Category.DATA_CONSISTENCY, Severity.WARNING, "DATA-003",
                    "MongoDB com perfil transacional: atenção",
                    "MongoDB suporta transações multi-documento desde v4.0, mas "
                    "não é tão robusto quanto bancos relacionais para workloads "
                    "ACID pesados. Considere se as operações realmente precisam "
                    "de transações ou se eventual consistency é aceitável.",
                    ["31", "32"],
                    "Avalie se PostgreSQL seria mais adequado ou documente "
                    "a estratégia de consistência.",
                    pillar="P6",
                )

    # ========================================================================
    # FASE 4: VIABILIDADE TECNOLÓGICA
    # ========================================================================

    def _check_tech_feasibility(self):
        """Combinações tecnologicamente inviáveis ou arriscadas."""

        # Java/Kotlin no mainframe com frontend moderno = não faz sentido no contexto GCA
        # (mainframe não é opção direta, mas "Desktop local" + Java + web app = estranho)

        # Electron + Python: já coberto, mas reforço
        if "Electron" in self.frontend_stacks and self.backend_lang == "Python":
            # Já verificado em STACK, mas aqui com mais contexto
            pass

        # Electron + backend separado = não faz sentido (Electron embute o backend)
        if "Electron" in self.frontend_stacks and self.has_backend == "Sim":
            if self.backend_lang not in ("Node.js", ""):
                self._add(
                    Category.TECH_FEASIBILITY, Severity.CRITICAL, "TECH-001",
                    f"Electron + backend {self.backend_lang}: arquitetura questionável",
                    f"Electron embute Node.js como runtime. Usar backend "
                    f"separado em {self.backend_lang} (Q27) com Electron (Q23) "
                    f"cria complexidade desnecessária. O backend roda dentro do "
                    f"Electron ou é um servidor separado?",
                    ["23", "27"],
                    "Use Node.js como backend dentro do Electron ou separe "
                    "em web app (React) + API ({}).".format(self.backend_lang),
                    pillar="P5",
                )

        # React Native + Desktop = incompatível
        if "React Native" in self.frontend_stacks:
            if "Executável desktop" in self.deliverables:
                self._add(
                    Category.TECH_FEASIBILITY, Severity.BLOCKER, "TECH-002",
                    "React Native não gera executáveis desktop",
                    "React Native (Q23) é para iOS/Android. Para desktop, "
                    "use Electron ou uma solução nativa.",
                    ["15", "23"],
                    "Use Electron para desktop ou React Native apenas para mobile.",
                    pillar="P5",
                )

        # Flutter web + TypeScript = incompatível (Flutter usa Dart)
        if "Flutter" in self.frontend_stacks:
            if self.frontend_lang in ("TypeScript", "JavaScript"):
                self._add(
                    Category.TECH_FEASIBILITY, Severity.BLOCKER, "TECH-003",
                    "Flutter usa Dart, não TypeScript/JavaScript",
                    f"Flutter (Q23) utiliza Dart como linguagem. "
                    f"'{self.frontend_lang}' (Q24) não é compatível.",
                    ["23", "24"],
                    "Altere Q24 para 'Outra' (Dart) ou mude a stack.",
                    pillar="P5",
                )

        # gRPC no frontend SPA sem BFF
        if "gRPC" in self.backend_types and self.has_frontend == "Sim":
            if "BFF" not in self.backend_types:
                web_frontends = {"React", "Vue", "Angular", "Next.js", "Vite + React"}
                if web_frontends & set(self.frontend_stacks):
                    self._add(
                        Category.TECH_FEASIBILITY, Severity.WARNING, "TECH-004",
                        "gRPC + Frontend Web sem BFF",
                        "Browsers não suportam gRPC nativo. É necessário "
                        "gRPC-Web ou um BFF (Backend for Frontend) que traduza "
                        "gRPC para REST/GraphQL.",
                        ["29", "23"],
                        "Adicione 'BFF' ao tipo de backend (Q29) ou use REST API.",
                        pillar="P5",
                    )

        # Serverless + Container = conflito
        if "Serverless" in self.arch_profiles:
            if self.exec_model == "Containerizado":
                self._add(
                    Category.TECH_FEASIBILITY, Severity.CRITICAL, "TECH-005",
                    "Serverless e Containerizado são abordagens distintas",
                    "Serverless (Q16) implica funções efêmeras gerenciadas pelo "
                    "provedor. Containerizado (Q17) implica containers persistentes. "
                    "Embora existam containers serverless (Fargate, Cloud Run), "
                    "a abordagem é fundamentalmente diferente.",
                    ["16", "17"],
                    "Defina: é serverless (Lambda/Functions) ou container "
                    "(Docker/K8s)? Se Cloud Run/Fargate, escolha 'Cloud'.",
                    pillar="P5",
                )

        # WebSocket + Serverless = problemático
        if "WebSocket" in self.backend_types and "Serverless" in self.arch_profiles:
            self._add(
                Category.TECH_FEASIBILITY, Severity.CRITICAL, "TECH-006",
                "WebSocket + Serverless: limitações severas",
                "Funções serverless são stateless e efêmeras. WebSockets "
                "requerem conexões persistentes. AWS API Gateway WebSocket "
                "existe mas tem custo alto e complexidade de gerenciamento.",
                ["16", "29"],
                "Use containers ou VM para WebSocket, ou substitua por "
                "Server-Sent Events (SSE) / polling.",
                pillar="P5",
            )

        # Multi-tenant + SQLite = impossível
        if self.multi_tenant == "Sim" and self.primary_db == "SQLite":
            self._add(
                Category.TECH_FEASIBILITY, Severity.BLOCKER, "TECH-007",
                "Multi-tenant com SQLite é inviável",
                "SQLite é single-file, single-writer. Multi-tenant requer "
                "isolamento de dados, schemas separados ou row-level security — "
                "nenhum suportado pelo SQLite.",
                ["18", "31"],
                "Use PostgreSQL (com schemas) ou MySQL para multi-tenant.",
                pillar="P6",
            )

        # Async processing sem backend adequado
        if self.async_processing == "Sim":
            if self.has_backend != "Sim":
                self._add(
                    Category.TECH_FEASIBILITY, Severity.BLOCKER, "TECH-008",
                    "Processamento assíncrono sem backend",
                    "Q20='Sim' mas Q26='Não'. Processamento assíncrono "
                    "requer um backend para orquestrar workers/filas.",
                    ["20", "26"],
                    "Habilite o backend ou desabilite processamento assíncrono.",
                    pillar="P5",
                )

            if self.needs_redis != "Sim" and self.needs_messaging != "Sim" \
               and self.uses_n8n != "Sim":
                self._add(
                    Category.TECH_FEASIBILITY, Severity.WARNING, "TECH-009",
                    "Processamento assíncrono sem mecanismo de fila",
                    "Q20='Sim' mas não há Redis (Q33), mensageria (Q35) "
                    "ou n8n (Q37) para gerenciar filas de trabalho.",
                    ["20", "33", "35", "37"],
                    "Habilite Redis (para filas leves) ou mensageria "
                    "(para processamento robusto).",
                    pillar="P5",
                )

        # High availability + Stand-alone = conflito
        if self.high_availability == "Sim" and self.exec_model == "Stand-alone":
            self._add(
                Category.TECH_FEASIBILITY, Severity.BLOCKER, "TECH-010",
                "Alta disponibilidade incompatível com Stand-alone",
                "Stand-alone (Q17) significa instância única. Alta disponibilidade "
                "(Q19) requer redundância (múltiplas instâncias, failover).",
                ["17", "19"],
                "Altere para 'Cloud', 'Containerizado' ou 'Híbrido'.",
                pillar="P4",
            )

    # ========================================================================
    # FASE 5: CONSISTÊNCIA CROSS-PILLAR
    # ========================================================================

    def _check_cross_pillar_p1_p5(self):
        """P1 (Business) vs P5 (Architecture): complexidade alinhada?"""
        # Projeto com criticidade crítica + monólito simples = risco
        if self.criticality == "Crítica" and "Monólito" in self.arch_profiles:
            if "Monólito modular" not in self.arch_profiles:
                self._add(
                    Category.CROSS_PILLAR, Severity.WARNING, "XPILLAR-001",
                    "Criticidade 'Crítica' com monólito simples",
                    "Projetos com criticidade Crítica (Q5) geralmente requerem "
                    "arquiteturas mais resilientes. Um monólito simples (Q16) "
                    "é um ponto único de falha.",
                    ["5", "16"],
                    "Considere 'Monólito modular' ou arquitetura mais distribuída.",
                    pillar="P1/P5",
                )

        # Projeto POC/MVP com arquitetura complexa = overengineering
        if "POC/MVP" in self.initiative_type:
            complex_archs = {"Microserviços", "Event-driven", "Hexagonal"}
            if complex_archs & set(self.arch_profiles):
                self._add(
                    Category.CROSS_PILLAR, Severity.WARNING, "XPILLAR-002",
                    "POC/MVP com arquitetura complexa: overengineering",
                    f"O tipo de iniciativa é POC/MVP (Q4), mas a arquitetura "
                    f"selecionada ({', '.join(complex_archs & set(self.arch_profiles))}) "
                    f"é complexa demais para validação rápida.",
                    ["4", "16"],
                    "Para POC/MVP, prefira 'Monólito' ou 'Monólito modular'.",
                    pillar="P1/P5",
                )

    def _check_cross_pillar_p3_p4(self):
        """P3 (Features) vs P4 (NFR): escopo vs. performance."""
        # Alta disponibilidade sem observabilidade
        if self.high_availability in ("Sim", "Futuramente") and not self.observability:
            self._add(
                Category.CROSS_PILLAR, Severity.CRITICAL, "XPILLAR-003",
                "Alta disponibilidade sem observabilidade",
                "Não é possível garantir alta disponibilidade (Q19) sem "
                "observabilidade (Q44). Como saber se o sistema está disponível "
                "sem health checks, métricas e alertas?",
                ["19", "44"],
                "Selecione pelo menos: Health checks, Métricas, Alertas.",
                pillar="P4",
            )

        # Alta disponibilidade sem testes de resiliência
        if self.high_availability == "Sim":
            resilience_tests = {"Resiliência/Recuperação", "Backup/Restore",
                                "Performance/Carga", "Stress/Soak"}
            if not (resilience_tests & set(self.test_types)):
                self._add(
                    Category.CROSS_PILLAR, Severity.WARNING, "XPILLAR-004",
                    "Alta disponibilidade sem testes de resiliência",
                    "Q19='Sim' mas nenhum teste de resiliência, performance ou "
                    "stress foi selecionado (Q45).",
                    ["19", "45"],
                    "Adicione: Resiliência/Recuperação, Performance/Carga.",
                    pillar="P4",
                )

        # Multi-tenant sem RBAC
        if self.multi_tenant == "Sim" and "RBAC" not in self.backend_reqs:
            self._add(
                Category.CROSS_PILLAR, Severity.BLOCKER, "XPILLAR-005",
                "Multi-tenant sem RBAC",
                "Multi-tenant (Q18) requer controle de acesso baseado em roles "
                "(RBAC) para isolar dados entre tenants.",
                ["18", "30"],
                "Adicione 'RBAC' aos requisitos de backend (Q30).",
                pillar="P3/P7",
            )

    def _check_cross_pillar_p5_p7(self):
        """P5 (Architecture) vs P7 (Security): segurança da arquitetura."""
        # Microserviços sem criptografia em trânsito
        if "Microserviços" in self.arch_profiles:
            if "Criptografia em trânsito" not in self.security_controls:
                self._add(
                    Category.CROSS_PILLAR, Severity.CRITICAL, "XPILLAR-006",
                    "Microserviços sem criptografia em trânsito",
                    "Microserviços (Q16) comunicam pela rede. Sem criptografia "
                    "em trânsito (Q43), dados trafegam em plain text entre serviços.",
                    ["16", "43"],
                    "Adicione 'Criptografia em trânsito' (mTLS ou TLS).",
                    pillar="P5/P7",
                )

        # Cloud sem vault de segredos
        if self.exec_model in ("Cloud", "Híbrido"):
            if "Vault de segredos" not in self.security_controls:
                self._add(
                    Category.CROSS_PILLAR, Severity.WARNING, "XPILLAR-007",
                    "Deploy em cloud sem vault de segredos",
                    "Ambientes cloud (Q17) devem usar vault (AWS Secrets Manager, "
                    "HashiCorp Vault) para gerenciar credenciais. Sem vault (Q43), "
                    "segredos ficam em variáveis de ambiente ou arquivos.",
                    ["17", "43"],
                    "Adicione 'Vault de segredos' aos controles.",
                    pillar="P5/P7",
                )

        # IA sem restrições de dados
        if self.uses_ai == "Sim" and not self.ai_restrictions:
            if self.info_classification in ("Confidencial", "Restrita"):
                self._add(
                    Category.CROSS_PILLAR, Severity.BLOCKER, "XPILLAR-008",
                    "IA com dados confidenciais sem restrições",
                    f"Classificação '{self.info_classification}' (Q6) com IA "
                    f"habilitada (Q39) mas sem restrições de IA (Q42). "
                    f"Dados confidenciais podem ser enviados ao provedor sem proteção.",
                    ["6", "39", "42"],
                    "Selecione: Mascaramento e/ou Anonimização (Q42).",
                    pillar="P2/P7",
                )

    def _check_cross_pillar_p2_p7(self):
        """P2 (Compliance) vs P7 (Security): conformidade legal."""
        # Dados confidenciais/restritos sem criptografia
        if self.info_classification in ("Confidencial", "Restrita"):
            has_transit = "Criptografia em trânsito" in self.security_controls
            has_rest = "Criptografia em repouso" in self.security_controls
            has_audit = "Trilhas de auditoria" in self.security_controls

            if not has_transit:
                self._add(
                    Category.SECURITY_COMPLIANCE, Severity.BLOCKER, "SEC-001",
                    f"'{self.info_classification}' sem criptografia em trânsito",
                    "LGPD/GDPR exigem proteção de dados em trânsito para "
                    "dados classificados como confidenciais ou restritos.",
                    ["6", "43"],
                    "Adicione 'Criptografia em trânsito' (Q43).",
                    pillar="P7",
                )

            if not has_rest:
                self._add(
                    Category.SECURITY_COMPLIANCE, Severity.BLOCKER, "SEC-002",
                    f"'{self.info_classification}' sem criptografia em repouso",
                    "Dados confidenciais/restritos devem ser criptografados "
                    "at rest (banco, backups, logs).",
                    ["6", "43"],
                    "Adicione 'Criptografia em repouso' (Q43).",
                    pillar="P7",
                )

            if not has_audit:
                self._add(
                    Category.SECURITY_COMPLIANCE, Severity.CRITICAL, "SEC-003",
                    f"'{self.info_classification}' sem trilhas de auditoria",
                    "Compliance exige rastreabilidade de acessos e modificações "
                    "em dados classificados.",
                    ["6", "43"],
                    "Adicione 'Trilhas de auditoria' (Q43).",
                    pillar="P7",
                )

        # Nenhum mecanismo de autenticação
        auth_controls = {"JWT", "OAuth2", "SSO", "MFA"}
        if not (auth_controls & set(self.security_controls)):
            self._add(
                Category.SECURITY_COMPLIANCE, Severity.BLOCKER, "SEC-004",
                "Nenhum mecanismo de autenticação selecionado",
                "Todo sistema deve ter pelo menos um método de autenticação. "
                "Nenhum controle de auth encontrado em Q43.",
                ["43"],
                "Selecione pelo menos: JWT ou OAuth2.",
                pillar="P7",
            )

        # Criticidade Alta/Crítica sem MFA
        if self.criticality in ("Alta", "Crítica"):
            if "MFA" not in self.security_controls:
                self._add(
                    Category.SECURITY_COMPLIANCE, Severity.WARNING, "SEC-005",
                    "Criticidade alta sem MFA",
                    f"Projeto com criticidade '{self.criticality}' (Q5) "
                    f"deveria considerar MFA para acessos administrativos.",
                    ["5", "43"],
                    "Considere adicionar MFA para maior segurança.",
                    pillar="P7",
                )

    def _check_cross_pillar_p3_p6(self):
        """P3 (Features) vs P6 (Data): funcionalidades vs. dados."""
        # App persistente sem banco
        persistent_deliverables = {"API", "Aplicação web", "Microserviço",
                                    "Dashboard", "Aplicativo mobile"}
        if persistent_deliverables & set(self.deliverables) and not self.primary_db:
            self._add(
                Category.DATA_CONSISTENCY, Severity.BLOCKER, "DATA-004",
                "Aplicação persistente sem banco de dados",
                f"Entregável ({', '.join(persistent_deliverables & set(self.deliverables))}) "
                f"requer persistência de dados, mas Q31 está vazio.",
                ["15", "31"],
                "Selecione um banco de dados principal.",
                pillar="P6",
            )

        # Redis habilitado sem finalidade
        if self.needs_redis == "Sim" and not self.redis_purposes:
            self._add(
                Category.DATA_CONSISTENCY, Severity.WARNING, "DATA-005",
                "Redis habilitado sem finalidade definida",
                "Q33='Sim' mas Q34 está vazio. Para que o Redis será usado?",
                ["33", "34"],
                "Selecione pelo menos uma finalidade para o Redis.",
                pillar="P6",
            )

        # Mensageria habilitada sem finalidade
        if self.needs_messaging == "Sim" and not self.messaging_purposes:
            self._add(
                Category.DATA_CONSISTENCY, Severity.WARNING, "DATA-006",
                "Mensageria habilitada sem finalidade definida",
                "Q35='Sim' mas Q36 está vazio. Para que a mensageria será usada?",
                ["35", "36"],
                "Selecione pelo menos uma finalidade para a mensageria.",
                pillar="P6",
            )

        # n8n habilitado sem finalidade
        if self.uses_n8n == "Sim" and not self.n8n_purposes:
            self._add(
                Category.DATA_CONSISTENCY, Severity.WARNING, "DATA-007",
                "n8n habilitado sem finalidade definida",
                "Q37='Sim' mas Q38 está vazio.",
                ["37", "38"],
                "Selecione pelo menos uma finalidade para o n8n.",
                pillar="P3",
            )

        # Microserviços sem mensageria
        if "Microserviços" in self.arch_profiles:
            if self.needs_messaging != "Sim":
                self._add(
                    Category.CROSS_PILLAR, Severity.CRITICAL, "XPILLAR-009",
                    "Microserviços sem mensageria",
                    "Microserviços (Q16) precisam de comunicação assíncrona "
                    "entre serviços. Sem mensageria (Q35), a comunicação será "
                    "apenas síncrona (HTTP), criando acoplamento temporal.",
                    ["16", "35"],
                    "Habilite mensageria ou justifique comunicação puramente síncrona.",
                    pillar="P5/P6",
                )

    # ========================================================================
    # FASE 6: SEGURANÇA E COMPLIANCE
    # ========================================================================

    def _check_security_compliance(self):
        """Verificações adicionais de segurança."""
        # Testes de segurança obrigatórios para criticidade Alta/Crítica
        if self.criticality in ("Alta", "Crítica"):
            security_tests = {"Segurança", "SAST/SCA", "DAST"}
            has_security_tests = security_tests & set(self.test_types)
            if not has_security_tests:
                self._add(
                    Category.SECURITY_COMPLIANCE, Severity.CRITICAL, "SEC-006",
                    "Criticidade alta sem testes de segurança",
                    f"Projeto com criticidade '{self.criticality}' (Q5) deveria "
                    f"incluir testes de segurança (SAST, DAST, Segurança).",
                    ["5", "45"],
                    "Adicione: Segurança, SAST/SCA e/ou DAST.",
                    pillar="P7",
                )

        # Quality gate obrigatório para criticidade Crítica
        if self.criticality == "Crítica" and self.quality_gate != "Sim":
            self._add(
                Category.SECURITY_COMPLIANCE, Severity.CRITICAL, "SEC-007",
                "Criticidade Crítica sem quality gate automatizado",
                "Projetos de criticidade Crítica (Q5) devem ter quality gate "
                "automatizado (Q46) para impedir deploy de código com falhas.",
                ["5", "46"],
                "Habilite quality gate automatizado (Q46='Sim').",
                pillar="P7",
            )

        # IA com dados confidenciais deve ter restrições
        if self.uses_ai == "Sim" and self.info_classification in ("Confidencial", "Restrita"):
            if "Bloqueio total" not in self.ai_restrictions:
                if "Mascaramento" not in self.ai_restrictions and \
                   "Anonimização" not in self.ai_restrictions:
                    self._add(
                        Category.SECURITY_COMPLIANCE, Severity.BLOCKER, "SEC-008",
                        "Dados confidenciais enviados à IA sem proteção",
                        f"Classificação '{self.info_classification}' (Q6) com IA (Q39) "
                        f"requer mascaramento ou anonimização (Q42) antes do envio.",
                        ["6", "39", "42"],
                        "Selecione 'Mascaramento' ou 'Anonimização' em Q42.",
                        pillar="P2/P7",
                    )

    # ========================================================================
    # FASE 7: COERÊNCIA DE ENTREGÁVEIS
    # ========================================================================

    def _check_delivery_alignment(self):
        """Verifica se os entregáveis do pipeline são coerentes."""
        # Se tem backend + frontend, deve ter doc técnico
        if self.has_backend == "Sim" and self.has_frontend == "Sim":
            if "Documento técnico consolidado" not in self.pipeline_deliverables:
                self._add(
                    Category.DELIVERY_ALIGNMENT, Severity.INFO, "ALIGN-001",
                    "Projeto full-stack sem documento técnico nos entregáveis",
                    "Projetos com frontend + backend devem gerar documentação "
                    "técnica consolidada para alinhamento entre equipes.",
                    ["48"],
                    "Considere adicionar 'Documento técnico consolidado' em Q48.",
                    pillar="P3",
                )

        # Testes definidos mas sem plano de testes nos entregáveis
        if self.test_types and "Plano de testes" not in self.pipeline_deliverables:
            self._add(
                Category.DELIVERY_ALIGNMENT, Severity.INFO, "ALIGN-002",
                "Testes definidos sem plano de testes nos entregáveis",
                "Q45 define tipos de teste mas Q48 não inclui 'Plano de testes'.",
                ["45", "48"],
                "Considere adicionar 'Plano de testes' em Q48.",
                pillar="P3",
            )

        # Segurança definida mas sem plano de segurança
        if self.security_controls and "Plano de segurança" not in self.pipeline_deliverables:
            if self.criticality in ("Alta", "Crítica"):
                self._add(
                    Category.DELIVERY_ALIGNMENT, Severity.WARNING, "ALIGN-003",
                    "Controles de segurança sem plano de segurança nos entregáveis",
                    f"Criticidade '{self.criticality}' com controles de segurança "
                    f"definidos, mas sem 'Plano de segurança' em Q48.",
                    ["43", "48"],
                    "Adicione 'Plano de segurança' em Q48.",
                    pillar="P7",
                )

        # Observabilidade definida sem plano de observabilidade
        if self.observability and "Plano de observabilidade" not in self.pipeline_deliverables:
            if self.high_availability in ("Sim", "Futuramente"):
                self._add(
                    Category.DELIVERY_ALIGNMENT, Severity.INFO, "ALIGN-004",
                    "Observabilidade sem plano nos entregáveis",
                    "Observabilidade definida (Q44) com alta disponibilidade, "
                    "mas sem 'Plano de observabilidade' em Q48.",
                    ["44", "48"],
                    "Considere adicionar 'Plano de observabilidade' em Q48.",
                    pillar="P4",
                )

    # ========================================================================
    # FASE 8: PROJETO EXISTENTE
    # ========================================================================

    def _check_existing_project(self):
        """Validações específicas para projetos existentes."""
        if not self.main_repo:
            self._add(
                Category.COMPLETENESS, Severity.BLOCKER, "EXIST-001",
                "Projeto existente sem repositório principal",
                "Q3='Sim' mas Q8 (main_repository) está vazio. Impossível "
                "analisar projeto existente sem acesso ao código.",
                ["3", "8"],
                "Informe a URL do repositório principal.",
            )

        if not self.access_level:
            self._add(
                Category.COMPLETENESS, Severity.BLOCKER, "EXIST-002",
                "Nível de acesso ao repositório não definido",
                "Q10 (repository_access_level) é obrigatório para projeto existente.",
                ["3", "10"],
                "Selecione o nível de acesso disponível.",
            )

        if not self.change_objectives:
            self._add(
                Category.COMPLETENESS, Severity.WARNING, "EXIST-003",
                "Objetivo de alteração não definido",
                "Q11 (change_objective) ajuda os agentes a focar a análise.",
                ["3", "11"],
                "Selecione pelo menos um objetivo de alteração.",
            )

        # Se autoriza n8n mas não definiu escopo
        if self.authorize_n8n == "Sim" and not self.n8n_scope:
            self._add(
                Category.COMPLETENESS, Severity.WARNING, "EXIST-004",
                "Análise n8n autorizada sem escopo definido",
                "Q12='Sim' mas Q13 (n8n_analysis_scope) está vazio.",
                ["12", "13"],
                "Selecione o escopo da análise n8n.",
            )

    # ========================================================================
    # RESULTADO
    # ========================================================================

    def _add(self, category: Category, severity: Severity, rule_id: str,
             title: str, description: str, questions: List[str],
             suggestion: str, pillar: Optional[str] = None):
        self.findings.append(Finding(
            category=category,
            severity=severity,
            rule_id=rule_id,
            title=title,
            description=description,
            affected_questions=questions,
            suggestion=suggestion,
            pillar=pillar,
        ))

    def _build_result(self) -> Dict[str, Any]:
        """Monta o resultado final da verificação."""
        from app.schemas.questionnaire import (
            QUESTION_FIELD_MAP, EXISTING_PROJECT_QUESTIONS, AGENT_RESPONSE_QUESTIONS,
        )

        # Classificar findings
        blockers = [f for f in self.findings if f.severity == Severity.BLOCKER]
        criticals = [f for f in self.findings if f.severity == Severity.CRITICAL]
        warnings = [f for f in self.findings if f.severity == Severity.WARNING]
        infos = [f for f in self.findings if f.severity == Severity.INFO]

        # Campos destacados (todas as perguntas afetadas)
        highlighted = set()
        for f in self.findings:
            highlighted.update(f.affected_questions)

        # Score de aderência
        score = 100
        score -= len(blockers) * 10
        score -= len(criticals) * 5
        score -= len(warnings) * 2
        score -= len(infos) * 0  # Info não penaliza
        adherence_score = max(0, min(100, score))

        # Aprovação: sem blockers E score >= 70
        approved = len(blockers) == 0 and adherence_score >= 70

        # Percentual de completude (Q52)
        gp_questions = set(QUESTION_FIELD_MAP.keys()) - AGENT_RESPONSE_QUESTIONS
        if self.is_existing != "Sim":
            gp_questions -= EXISTING_PROJECT_QUESTIONS
        answered = sum(
            1 for q in gp_questions
            if self.raw.get(q) or self.r.get(QUESTION_FIELD_MAP.get(q, ""))
        )
        total_expected = len(gp_questions)
        completion_pct = round((answered / total_expected) * 100) if total_expected else 0

        # Status do questionário (Q53)
        if blockers:
            q_status = "Inconsistente - revisar"
        elif criticals or not approved:
            q_status = "Pendente de ajustes"
        else:
            q_status = "OK para ingestão"

        # Agentes validadores (Q54)
        validating_agents = self._determine_validating_agents()

        # Observações (Q51) — texto consolidado com contexto real
        observations = self._build_observations(blockers, criticals, warnings, infos)

        # Restrições (Q50) — texto consolidado
        restrictions = self._build_restrictions()

        # Agrupar findings por categoria
        by_category = {}
        for f in self.findings:
            cat = f.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(f.to_dict())

        # Agrupar por pilar
        by_pillar = {}
        for f in self.findings:
            if f.pillar:
                for p in f.pillar.split("/"):
                    if p not in by_pillar:
                        by_pillar[p] = []
                    by_pillar[p].append(f.to_dict())

        return {
            "approved_for_ocg": approved,
            "adherence_score": adherence_score,
            "completion_percentage": completion_pct,
            "questionnaire_status": q_status,

            "summary": {
                "blockers": len(blockers),
                "criticals": len(criticals),
                "warnings": len(warnings),
                "infos": len(infos),
                "total_findings": len(self.findings),
                "highlighted_questions": sorted(highlighted),
            },

            "findings": [f.to_dict() for f in self.findings],
            "findings_by_category": by_category,
            "findings_by_pillar": by_pillar,

            # A.12 — Retorno real dos agentes (Q50-Q54)
            "agent_response": {
                "restrictions": restrictions,                     # Q50
                "observations": observations,                     # Q51
                "completion_percentage": completion_pct,           # Q52
                "questionnaire_status": q_status,                 # Q53
                "validating_agents": validating_agents,           # Q54
            },

            # Legado (compatibilidade com formato anterior)
            "status": "OK" if approved else ("Incompleto" if blockers else "Pendente"),
            "adherenceScore": adherence_score,
            "approved": approved,
            "validations": {
                "logicConflicts": [f.to_dict() for f in self.findings
                                   if f.category in (Category.STACK_COMPAT,
                                                      Category.ARCH_CONSISTENCY,
                                                      Category.TECH_FEASIBILITY)],
                "gaps": [f.to_dict() for f in self.findings
                         if f.category == Category.COMPLETENESS],
                "incompatibilities": [f.to_dict() for f in self.findings
                                      if f.category in (Category.CROSS_PILLAR,
                                                         Category.SECURITY_COMPLIANCE,
                                                         Category.DATA_CONSISTENCY)],
                "delivery_alignment": [f.to_dict() for f in self.findings
                                        if f.category == Category.DELIVERY_ALIGNMENT],
            },
            "observations": observations,
            "restrictions": restrictions,
            "highlightedFields": sorted(highlighted),
        }

    def _determine_validating_agents(self) -> List[str]:
        """Determina quais agentes validadores participaram com base nos achados."""
        agents = set()

        pillar_agent_map = {
            "P1": "Negócio",
            "P2": "Compliance",
            "P3": "Desenvolvimento",
            "P4": "Infraestrutura",
            "P5": "Arquitetura",
            "P6": "Desenvolvimento",
            "P7": "Segurança",
        }

        # Agentes baseados nos findings
        for f in self.findings:
            if f.pillar:
                for p in f.pillar.split("/"):
                    agent = pillar_agent_map.get(p)
                    if agent:
                        agents.add(agent)

        # Agentes baseados nos campos preenchidos
        if self.criticality or self.initiative_type:
            agents.add("Negócio")
        if self.arch_profiles or self.frontend_stacks or self.backend_frameworks:
            agents.add("Arquitetura")
        if self.backend_lang or self.frontend_lang:
            agents.add("Desenvolvimento")
        if self.test_types:
            agents.add("QA")
        if self.security_controls:
            agents.add("Segurança")
        if self.exec_model or self.needs_redis or self.needs_messaging:
            agents.add("Infraestrutura")
        if self.info_classification or self.ai_restrictions:
            agents.add("Compliance")

        # Ordenar conforme enum AgentesValidadores
        order = ["Negócio", "Arquitetura", "Desenvolvimento", "QA",
                 "Segurança", "Infraestrutura", "Compliance"]
        return [a for a in order if a in agents]

    def _build_observations(self, blockers, criticals, warnings, infos) -> str:
        """Gera texto de observações real baseado na análise."""
        parts = []

        if not self.findings:
            parts.append("✅ Questionário consistente. Stack alinhada com a arquitetura "
                         "proposta. Sem conflitos ou gaps detectados. Aprovado para "
                         "geração do OCG.")
            return " ".join(parts)

        # Resumo geral
        if blockers:
            parts.append(
                f"⛔ BLOQUEADO: {len(blockers)} problema(s) crítico(s) impedem "
                f"a geração do OCG."
            )
        elif criticals:
            parts.append(
                f"⚠️ ATENÇÃO: {len(criticals)} achado(s) de risco alto requerem "
                f"revisão antes do OCG."
            )
        else:
            parts.append("✅ Nenhum bloqueador encontrado.")

        if warnings:
            parts.append(f"📋 {len(warnings)} recomendação(ões) para melhorar a qualidade.")

        # Detalhes dos blockers
        if blockers:
            parts.append("\n\n🔴 BLOQUEADORES:")
            for i, b in enumerate(blockers, 1):
                parts.append(f"  {i}. [{b.rule_id}] {b.title} — {b.suggestion}")

        # Detalhes dos criticals
        if criticals:
            parts.append("\n\n🟠 RISCOS ALTOS:")
            for i, c in enumerate(criticals, 1):
                parts.append(f"  {i}. [{c.rule_id}] {c.title} — {c.suggestion}")

        # Resumo dos warnings
        if warnings:
            parts.append("\n\n🟡 RECOMENDAÇÕES:")
            for i, w in enumerate(warnings, 1):
                parts.append(f"  {i}. [{w.rule_id}] {w.title}")

        return "\n".join(parts)

    def _build_restrictions(self) -> str:
        """Gera texto de restrições real baseado na análise."""
        restrictions = []

        # Restrições de compliance
        if self.info_classification in ("Confidencial", "Restrita"):
            restrictions.append(
                f"🔒 Classificação '{self.info_classification}': criptografia "
                f"end-to-end obrigatória, trilhas de auditoria, backups criptografados."
            )

        # Restrições de IA
        if self.uses_ai == "Sim":
            external = {"Anthropic", "OpenAI", "Gemini"}
            if external & set(self.ai_providers):
                restrictions.append(
                    "🤖 IA com provedor externo: dados sensíveis devem ser "
                    "mascarados/anonimizados antes do envio. Conformidade LGPD/GDPR."
                )

        # Restrições de criticidade
        if self.criticality == "Crítica":
            restrictions.append(
                "🚨 Criticidade Crítica: SLA 99.9%+, disaster recovery obrigatório, "
                "quality gate automatizado, testes de resiliência mandatórios."
            )
        elif self.criticality == "Alta":
            restrictions.append(
                "⚡ Criticidade Alta: plano de rollback obrigatório, monitoramento "
                "contínuo, testes de integração antes de cada deploy."
            )

        # Restrições de arquitetura
        if "Microserviços" in self.arch_profiles:
            restrictions.append(
                "🏗️ Microserviços: service mesh ou mTLS obrigatório entre serviços, "
                "circuit breaker, observabilidade distribuída (tracing)."
            )

        # Restrições de multi-tenant
        if self.multi_tenant == "Sim":
            restrictions.append(
                "🏢 Multi-tenant: isolamento de dados por tenant obrigatório "
                "(schema-per-tenant ou row-level security), RBAC mandatório."
            )

        # Restrições de modo offline
        if self.exec_model == "Offline com sincronização posterior":
            restrictions.append(
                "📴 Modo offline: estratégia de conflict resolution obrigatória, "
                "versionamento de dados local, sync queue com retry."
            )

        if not restrictions:
            return "Nenhuma restrição técnica adicional identificada."

        return "\n".join(restrictions)
