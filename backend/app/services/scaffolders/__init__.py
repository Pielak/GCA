"""
Scaffolders por linguagem/framework — DT-058 Sprint 2.

Cada scaffolder retorna uma lista de `ScaffoldFile(path, content)` que o
caller commita no repo Git. **Não chama LLM** — geração determinística
a partir do `STACK_RECOMMENDATION` do OCG. O LLM continua sendo usado
para o código de negócio (módulos individuais), mas a estrutura
inicial (pom.xml, configs, entrypoint, etc) é determinística para
garantir que o scaffold funcione sempre, independente do provider de IA
configurado pelo cliente.

Padrão: cada `scaffold_<framework>(spec)` retorna `list[ScaffoldFile]`.
"""
from .types import ScaffoldFile, ScaffoldSpec
from .java_spring import scaffold_java_spring
from .java_quarkus import scaffold_java_quarkus
from .go_app import scaffold_go
from .csharp_aspnet import scaffold_csharp_aspnet
from .php_laravel import scaffold_php_laravel
from .kotlin_spring import scaffold_kotlin_spring
from .dispatch import dispatch_scaffold

__all__ = [
    "ScaffoldFile",
    "ScaffoldSpec",
    "scaffold_java_spring",
    "scaffold_java_quarkus",
    "scaffold_go",
    "scaffold_csharp_aspnet",
    "scaffold_php_laravel",
    "scaffold_kotlin_spring",
    "dispatch_scaffold",
]
