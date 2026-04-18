"""DT-058 Sprint 2 — tipos compartilhados entre scaffolders."""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ScaffoldFile:
    """Um arquivo a ser criado no repo do projeto.

    `path` é relativo à raiz do repo (ex: `pom.xml`,
    `src/main/java/com/example/Application.java`). `content` é o
    conteúdo final, não-formatado pelo LLM. `executable` marca scripts
    que precisam de bit +x quando o caller fizer commit.
    """
    path: str
    content: str
    executable: bool = False


@dataclass
class ScaffoldSpec:
    """Entrada para o scaffolder — extraída do OCG por
    `code_generation_service` antes de chamar o scaffolder específico.

    Mantém apenas o necessário para gerar a estrutura inicial. Não
    carrega referência ao OCG nem ao project_id — scaffolders são
    funções puras, sem efeitos colaterais.
    """
    project_name: str
    project_slug: str
    package: str = "com.example.app"  # ex: com.acme.financehub
    java_version: str = "21"
    framework_version: Optional[str] = None  # ex: "3.3.0" para Spring Boot
    database: Optional[str] = None  # ex: "PostgreSQL"
    requires_security: bool = False  # se OCG.security_controls inclui auth
    requires_redis: bool = False
    extra_dependencies: List[str] = field(default_factory=list)
