"""MVP 35 — Catálogo de 30 regras seed agrupadas em 5 temas.

Schema canônico DSL:
    {
        "id": "RULE_ID",                          # único, prefixo por tema
        "theme": "nosql_acid|stack|fe_be|compliance|infra",
        "when": {                                  # AND implícito entre keys
            "Q4": "valor",                         # igualdade scalar
            "Q5_contains": "valor",                # inclusão em lista (multiselect)
        },
        "verdict": "ok|warning|conflict",          # severidade lógica
        "severity": "info|warning|error",          # cor UI
        "message": "...",                          # PT-BR amigável
        "suggestions": ["alt1", "alt2"],           # opções de correção
        "affected_fields": ["Q4", "Q5"],           # campos a destacar na UI
    }

Operadores (parseados pelo RulesEvaluator):
    - "Qx": "valor"           — eq scalar
    - "Qx_contains": "valor"  — substring/elemento em lista
    - "when_any": [{...}, {...}]  — OR opcional ao lado de when (futuro)

Ordem das regras: agrupadas por tema, ID sequencial.
"""
from typing import Any

# 5 temas × 6 regras médias = 30 regras seed
RULES_CATALOG: list[dict[str, Any]] = [
    # =========================================================================
    # TEMA 1 — NoSQL × ACID (5 regras)
    # =========================================================================
    {
        "id": "NOSQL_001_MONGODB_ACID",
        "theme": "nosql_acid",
        "when": {"Q4": "NoSQL (MongoDB, DynamoDB)", "Q13_contains": "PCI-DSS"},
        "verdict": "conflict",
        "severity": "error",
        "message": "MongoDB/DynamoDB não garantem ACID multi-documento, requisito comum de PCI-DSS para auditoria financeira.",
        "suggestions": ["SQL relacional", "Postgres com extensão de auditoria"],
        "affected_fields": ["Q4", "Q13"],
    },
    {
        "id": "NOSQL_002_HIPAA_NOSQL",
        "theme": "nosql_acid",
        "when": {"Q4": "NoSQL (MongoDB, DynamoDB)", "Q13_contains": "HIPAA"},
        "verdict": "warning",
        "severity": "warning",
        "message": "HIPAA exige trilha de auditoria forte. NoSQL precisa configuração adicional (ex: MongoDB Atlas com auditoria) para conformidade.",
        "suggestions": ["SQL relacional com triggers de auditoria", "MongoDB Atlas Enterprise"],
        "affected_fields": ["Q4", "Q13"],
    },
    {
        "id": "NOSQL_003_GRAPH_FOR_TRANSACTIONS",
        "theme": "nosql_acid",
        "when": {"Q4": "Graph DB", "Q15_contains": "PCI-DSS"},
        "verdict": "warning",
        "severity": "warning",
        "message": "Graph DB é otimizado para relações, não transações financeiras. PCI-DSS espera consistência forte multi-row.",
        "suggestions": ["SQL relacional para core financeiro", "Graph apenas para análise relacional secundária"],
        "affected_fields": ["Q4", "Q15"],
    },
    {
        "id": "NOSQL_004_KAFKA_NO_DB",
        "theme": "nosql_acid",
        "when": {"Q9": "Sim, Kafka", "Q4": "Não decidido"},
        "verdict": "conflict",
        "severity": "error",
        "message": "Kafka é log distribuído, não banco. Você precisa de um SGBD para o estado do domínio.",
        "suggestions": ["SQL relacional", "NoSQL (MongoDB, DynamoDB)"],
        "affected_fields": ["Q4", "Q9"],
    },
    {
        "id": "NOSQL_005_DW_OLTP",
        "theme": "nosql_acid",
        "when": {"Q4": "Data warehouse", "Q3": "Sim, agressivo"},
        "verdict": "conflict",
        "severity": "error",
        "message": "Data warehouse é otimizado para analítica (OLAP), não transacional alta-escala (OLTP).",
        "suggestions": ["SQL relacional para OLTP", "DW como destino de ETL secundário"],
        "affected_fields": ["Q3", "Q4"],
    },

    # =========================================================================
    # TEMA 2 — Stack runtime (6 regras)
    # =========================================================================
    {
        "id": "STACK_001_PHP_REALTIME",
        "theme": "stack",
        "when": {"Q5_contains": "PHP/Laravel", "Q14": "<100ms"},
        "verdict": "warning",
        "severity": "warning",
        "message": "PHP/Laravel não é otimizado para latência sub-100ms. Considere Go/Rust/Node para hot path.",
        "suggestions": ["Go", "Node.js/NestJS", "Rust"],
        "affected_fields": ["Q5", "Q14"],
    },
    {
        "id": "STACK_002_RUBY_HIGH_RPS",
        "theme": "stack",
        "when": {"Q5_contains": "Ruby/Rails", "Q3": "Sim, agressivo"},
        "verdict": "warning",
        "severity": "warning",
        "message": "Ruby/Rails tem throughput limitado por GIL. Para escalabilidade agressiva, considere Go ou Java/Spring.",
        "suggestions": ["Go", "Java/Spring", "Node.js/NestJS"],
        "affected_fields": ["Q5", "Q3"],
    },
    {
        "id": "STACK_003_NODE_CPU_BOUND",
        "theme": "stack",
        "when": {"Q5_contains": "Node.js/Express", "Q15_contains": "HIPAA"},
        "verdict": "warning",
        "severity": "warning",
        "message": "Node.js single-threaded sofre com workloads CPU-bound (criptografia HIPAA). Considere worker threads ou Go/Rust.",
        "suggestions": ["Go", "Java/Spring", "Node.js/NestJS com worker_threads"],
        "affected_fields": ["Q5", "Q15"],
    },
    {
        "id": "STACK_004_PYTHON_LOW_LATENCY",
        "theme": "stack",
        "when": {"Q5_contains": "Python/Django", "Q14": "<50ms"},
        "verdict": "warning",
        "severity": "warning",
        "message": "Django ORM tem overhead pra latência <50ms. Considere FastAPI ou Go.",
        "suggestions": ["Python/FastAPI", "Go"],
        "affected_fields": ["Q5", "Q14"],
    },
    {
        "id": "STACK_005_RUST_PROTOTYPE",
        "theme": "stack",
        "when": {"Q5_contains": "Rust", "Q2": "Curto (2-4 semanas)"},
        "verdict": "warning",
        "severity": "warning",
        "message": "Rust tem curva de aprendizado alta. Em prazo curto (2-4 semanas), considere Go ou Python para velocidade de entrega.",
        "suggestions": ["Go", "Python/FastAPI", "Node.js/NestJS"],
        "affected_fields": ["Q5", "Q2"],
    },
    {
        "id": "STACK_006_DOTNET_LINUX_CONTAINER",
        "theme": "stack",
        "when": {"Q5_contains": "C#/.NET", "Q9": "Sim, Kafka"},
        "verdict": "ok",
        "severity": "info",
        "message": ".NET 6+ tem cliente Kafka maduro (Confluent.Kafka). Setup viável.",
        "suggestions": [],
        "affected_fields": ["Q5", "Q9"],
    },

    # =========================================================================
    # TEMA 3 — Frontend × Backend (5 regras)
    # =========================================================================
    {
        "id": "FEBE_001_NEXT_REST_ONLY",
        "theme": "fe_be",
        "when": {"Q6_contains": "Next.js", "Q12": "REST API"},
        "verdict": "ok",
        "severity": "info",
        "message": "Next.js + REST funciona, mas você está deixando server components/SSR de lado.",
        "suggestions": [],
        "affected_fields": ["Q6", "Q12"],
    },
    {
        "id": "FEBE_002_ANGULAR_GRPC",
        "theme": "fe_be",
        "when": {"Q6_contains": "Angular", "Q12": "gRPC"},
        "verdict": "warning",
        "severity": "warning",
        "message": "Angular sem gRPC-Web ou proxy não conversa com gRPC nativo. Você precisa de Envoy/gRPC-Web na infra.",
        "suggestions": ["REST API", "GraphQL"],
        "affected_fields": ["Q6", "Q12"],
    },
    {
        "id": "FEBE_003_VUE_SSR_HEAVY",
        "theme": "fe_be",
        "when": {"Q6_contains": "Vue", "Q3": "Sim, agressivo"},
        "verdict": "warning",
        "severity": "warning",
        "message": "Vue puro sem Nuxt não tem SSR otimizado. Para escala agressiva com SEO, considere Nuxt.",
        "suggestions": ["Nuxt", "Next.js"],
        "affected_fields": ["Q6", "Q3"],
    },
    {
        "id": "FEBE_004_EMBER_NEW_PROJECT",
        "theme": "fe_be",
        "when": {"Q6_contains": "Ember", "Q1": "Novo sistema"},
        "verdict": "warning",
        "severity": "warning",
        "message": "Ember tem ecosistema reduzido em 2026. Para projeto novo, prefira React/Vue/Angular pela base de devs disponível.",
        "suggestions": ["React", "Vue", "Angular"],
        "affected_fields": ["Q6", "Q1"],
    },
    {
        "id": "FEBE_005_SVELTE_ENTERPRISE",
        "theme": "fe_be",
        "when": {"Q6_contains": "Svelte", "Q15_contains": "SOC 2"},
        "verdict": "warning",
        "severity": "warning",
        "message": "Svelte tem libs de auth/audit menos maduras que React/Angular. Para SOC 2, valide cobertura antes.",
        "suggestions": ["React", "Angular"],
        "affected_fields": ["Q6", "Q15"],
    },

    # =========================================================================
    # TEMA 4 — Compliance × PII (6 regras)
    # =========================================================================
    {
        "id": "COMP_001_LGPD_NO_TLS",
        "theme": "compliance",
        "when": {"Q15_contains": "LGPD"},
        "verdict": "warning",
        "severity": "warning",
        "message": "LGPD exige TLS em trânsito + criptografia em repouso para dados pessoais. Confirme em Q13.",
        "suggestions": ["Adicionar 'Encriptação (TLS)' em Q13"],
        "affected_fields": ["Q13", "Q15"],
    },
    {
        "id": "COMP_002_HIPAA_NO_AUTH",
        "theme": "compliance",
        "when": {"Q13_contains": "HIPAA", "Q5_contains": "PHP/Laravel"},
        "verdict": "warning",
        "severity": "warning",
        "message": "HIPAA exige BAA com cloud provider. Stack PHP/Laravel é viável mas requer hardening explícito + Vault de segredos.",
        "suggestions": ["Documentar BAA em Q13", "Adicionar HashiCorp Vault na infra"],
        "affected_fields": ["Q13"],
    },
    {
        "id": "COMP_003_PCIDSS_NO_TOKEN",
        "theme": "compliance",
        "when": {"Q13_contains": "PCI-DSS", "Q11_contains": "Payment Gateway"},
        "verdict": "ok",
        "severity": "info",
        "message": "PCI-DSS + Payment Gateway: garanta que dados de cartão são tokenizados pelo gateway, nunca tocam seu app.",
        "suggestions": [],
        "affected_fields": ["Q11", "Q13"],
    },
    {
        "id": "COMP_004_GDPR_DATA_LOCATION",
        "theme": "compliance",
        "when": {"Q15_contains": "GDPR"},
        "verdict": "warning",
        "severity": "warning",
        "message": "GDPR exige residência de dados na UE ou cláusulas contratuais (SCCs). Confirme localização do provider.",
        "suggestions": ["Documentar região no projeto", "Adicionar SCCs ao contrato"],
        "affected_fields": ["Q15"],
    },
    {
        "id": "COMP_005_SOC2_NO_AUDIT",
        "theme": "compliance",
        "when": {"Q15_contains": "SOC 2", "Q13_contains": "Nenhum específico"},
        "verdict": "conflict",
        "severity": "error",
        "message": "SOC 2 exige logs de auditoria + controle de acesso. Q13 marcado 'Nenhum específico' contradiz.",
        "suggestions": ["Adicionar 'RBAC' + 'Encriptação (TLS)' em Q13"],
        "affected_fields": ["Q13", "Q15"],
    },
    {
        "id": "COMP_006_LGPD_GDPR_DOUBLE",
        "theme": "compliance",
        "when": {"Q15_contains": "LGPD", "Q15_contains": "GDPR"},
        "verdict": "ok",
        "severity": "info",
        "message": "LGPD + GDPR: trate como GDPR (regra mais estrita) e LGPD é coberta automaticamente.",
        "suggestions": [],
        "affected_fields": ["Q15"],
    },

    # =========================================================================
    # TEMA 5 — Infra × escala/custo (8 regras)
    # =========================================================================
    {
        "id": "INFRA_001_K8S_LOW_TRAFFIC",
        "theme": "infra",
        "when": {"Q3": "Não", "Q9": "Sim, Kafka"},
        "verdict": "warning",
        "severity": "warning",
        "message": "Kafka tem custo operacional alto. Sem necessidade de escala (Q3=Não), considere SQS/SNS ou RabbitMQ.",
        "suggestions": ["Sim, SQS/SNS", "Sim, RabbitMQ"],
        "affected_fields": ["Q3", "Q9"],
    },
    {
        "id": "INFRA_002_SLA_VS_NO_SCALE",
        "theme": "infra",
        "when": {"Q10": "99.99%", "Q3": "Não"},
        "verdict": "conflict",
        "severity": "error",
        "message": "SLA 99.99% (52min/ano de downtime) exige redundância. Sem escala horizontal, single-point-of-failure mata o SLA.",
        "suggestions": ["Mudar Q3 para 'Sim, modesto'", "Aceitar SLA 99.5% ou 99.0%"],
        "affected_fields": ["Q3", "Q10"],
    },
    {
        "id": "INFRA_003_BUGFIX_NEW_STACK",
        "theme": "infra",
        "when": {"Q1": "Manutenção/bugfix", "Q5_contains": "Rust"},
        "verdict": "warning",
        "severity": "warning",
        "message": "Manutenção de sistema legacy raramente justifica reescrita em Rust. Mantenha stack original salvo razão arquitetural forte.",
        "suggestions": ["Manter stack legacy"],
        "affected_fields": ["Q1", "Q5"],
    },
    {
        "id": "INFRA_004_GRAPHQL_KAFKA",
        "theme": "infra",
        "when": {"Q12": "GraphQL", "Q9": "Sim, Kafka"},
        "verdict": "ok",
        "severity": "info",
        "message": "GraphQL Subscriptions + Kafka como source-of-truth de eventos é padrão event-driven moderno.",
        "suggestions": [],
        "affected_fields": ["Q9", "Q12"],
    },
    {
        "id": "INFRA_005_NO_CACHE_HIGH_RPS",
        "theme": "infra",
        "when": {"Q3": "Sim, agressivo", "Q8_contains": "Nenhuma"},
        "verdict": "warning",
        "severity": "warning",
        "message": "Escala agressiva sem cache mata o banco rapidamente. Considere Redis pelo menos para leituras hot.",
        "suggestions": ["Redis", "CDN"],
        "affected_fields": ["Q3", "Q8"],
    },
    {
        "id": "INFRA_006_LATENCY_NO_CDN",
        "theme": "infra",
        "when": {"Q14": "<100ms", "Q8_contains": "Nenhuma"},
        "verdict": "warning",
        "severity": "warning",
        "message": "Latência sub-100ms exige cache (Redis/CDN). Q8='Nenhuma' contradiz objetivo.",
        "suggestions": ["Redis", "CDN"],
        "affected_fields": ["Q8", "Q14"],
    },
    {
        "id": "INFRA_007_NO_INTEGRATION_NO_PROTOCOL",
        "theme": "infra",
        "when": {"Q11_contains": "Nenhum", "Q12": "gRPC"},
        "verdict": "warning",
        "severity": "warning",
        "message": "Sem integrações externas (Q11=Nenhum), gRPC é overkill. REST/GraphQL bastam.",
        "suggestions": ["REST API", "GraphQL"],
        "affected_fields": ["Q11", "Q12"],
    },
    {
        "id": "INFRA_008_SHORT_DEADLINE_NEW_SYSTEM",
        "theme": "infra",
        "when": {"Q1": "Novo sistema", "Q2": "Curto (2-4 semanas)"},
        "verdict": "warning",
        "severity": "warning",
        "message": "Novo sistema em 2-4 semanas é prazo agressivo. MVP enxuto + frameworks high-productivity (Rails/Django/NestJS) são caminho realista.",
        "suggestions": ["Python/Django", "Ruby/Rails", "Node.js/NestJS"],
        "affected_fields": ["Q1", "Q2"],
    },
]


def get_rules_by_theme(theme: str) -> list[dict[str, Any]]:
    """Filtra regras por tema canônico."""
    return [r for r in RULES_CATALOG if r["theme"] == theme]


def get_rule_by_id(rule_id: str) -> dict[str, Any] | None:
    """Lookup por ID. Retorna None se não encontrado."""
    for r in RULES_CATALOG:
        if r["id"] == rule_id:
            return r
    return None


def all_rule_ids() -> list[str]:
    """Lista de todos os IDs (para validação de unicidade)."""
    return [r["id"] for r in RULES_CATALOG]


# Auto-validação na importação: IDs únicos, temas válidos
_VALID_THEMES = {"nosql_acid", "stack", "fe_be", "compliance", "infra"}
_VALID_VERDICTS = {"ok", "warning", "conflict"}
_VALID_SEVERITIES = {"info", "warning", "error"}


def _validate_catalog() -> None:
    ids = all_rule_ids()
    if len(ids) != len(set(ids)):
        dups = [x for x in ids if ids.count(x) > 1]
        raise ValueError(f"Duplicate rule IDs: {set(dups)}")
    for r in RULES_CATALOG:
        if r["theme"] not in _VALID_THEMES:
            raise ValueError(f"Invalid theme {r['theme']!r} in {r['id']}")
        if r["verdict"] not in _VALID_VERDICTS:
            raise ValueError(f"Invalid verdict {r['verdict']!r} in {r['id']}")
        if r["severity"] not in _VALID_SEVERITIES:
            raise ValueError(f"Invalid severity {r['severity']!r} in {r['id']}")
        if not isinstance(r["when"], dict) or not r["when"]:
            raise ValueError(f"Empty/invalid 'when' in {r['id']}")
        if not isinstance(r["affected_fields"], list) or not r["affected_fields"]:
            raise ValueError(f"Empty 'affected_fields' in {r['id']}")


_validate_catalog()
