"""
Esquema de Questionário Técnico Dinâmico — N perguntas com visibilidade condicional.

Cada pergunta tem:
- numero: identificador único (Q1, Q2, ...)
- tipo: tipo de input (text, textarea, dropdown, multiselect, checkbox)
- secao: agrupamento visual (A.1, A.2, B.1, etc)
- pergunta: texto da pergunta
- obrigatoria: bool, se deve ser preenchida quando visível
- opcoes: lista de opções (para dropdown, multiselect, checkbox)
- visibleIf: condições para a pergunta aparecer
  - [] = sempre visível
  - [{"dependsOn": "Q3", "valor": "Sim"}] = apareça se Q3 = "Sim"
  - Múltiplas condições = AND lógico
- revela: lista de números de perguntas que esta pergunta revela

Validação Cruzada:
- Se Q3="Sim" → Q7-Q14 podem ser preenchidas
- Se Q3="Não" → Q7-Q14 devem estar vazias
- Sistema valida automaticamente na submissão

Progresso:
- Contar apenas perguntas visíveis
- progress = (visíveis_preenchidas / visíveis_totais) * 100
- Mínimo 80% para permitir "Validar Escopo"
"""

from typing import Any, Dict, List, Optional

QuestionType = str  # "text" | "textarea" | "dropdown" | "multiselect" | "checkbox"


def question(
    numero: str,
    pergunta: str,
    tipo: QuestionType,
    secao: str,
    obrigatoria: bool = True,
    opcoes: Optional[List[str]] = None,
    visible_if: Optional[List[Dict[str, Any]]] = None,
    revela: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Factory para criar uma pergunta com estrutura padrão."""
    return {
        "numero": numero,
        "pergunta": pergunta,
        "tipo": tipo,
        "secao": secao,
        "obrigatoria": obrigatoria,
        "opcoes": opcoes or [],
        "visibleIf": visible_if or [],
        "revela": revela or [],
    }


# =============================================================================
# SCHEMA DE PERGUNTAS TÉCNICAS
# =============================================================================
# Seção A: Contexto Técnico (A.1-A.3)
# Seção B: Arquitetura (B.1-B.3)
# Seção C: Integração (C.1-C.2)
# Seção D: Escalabilidade (D.1-D.2)
# =============================================================================

TECHNICAL_QUESTIONS_SCHEMA: List[Dict[str, Any]] = [
    # =========================================================================
    # SEÇÃO A: CONTEXTO TÉCNICO
    # =========================================================================
    question(
        numero="Q1",
        pergunta="Qual é o escopo principal do projeto técnico?",
        tipo="dropdown",
        secao="A.1",
        obrigatoria=True,
        opcoes=[
            "Novo sistema",
            "Refactor de existente",
            "Feature/módulo novo",
            "Manutenção/bugfix",
            "Outro",
        ],
        visible_if=[],
        revela=["Q2", "Q3"],
    ),
    question(
        numero="Q2",
        pergunta="Qual é o prazo esperado para entrega?",
        tipo="dropdown",
        secao="A.1",
        obrigatoria=True,
        opcoes=[
            "Curto (2-4 semanas)",
            "Médio (1-3 meses)",
            "Longo (3-6 meses)",
            "Indefinido",
        ],
        visible_if=[{"dependsOn": "Q1", "valor": "Novo sistema"}],
        revela=[],
    ),
    question(
        numero="Q3",
        pergunta="O projeto exigirá escalabilidade horizontal?",
        tipo="dropdown",
        secao="A.1",
        obrigatoria=True,
        opcoes=["Não", "Sim, modesto", "Sim, agressivo"],
        visible_if=[],
        revela=["Q7", "Q8", "Q9", "Q10"],
    ),
    question(
        numero="Q4",
        pergunta="Qual é o modelo de armazenamento de dados preferido?",
        tipo="dropdown",
        secao="A.2",
        obrigatoria=False,
        opcoes=[
            "SQL relacional",
            "NoSQL (MongoDB, DynamoDB)",
            "Graph DB",
            "Data warehouse",
            "Não decidido",
        ],
        visible_if=[],
        revela=[],
    ),
    # =========================================================================
    # SEÇÃO B: ARQUITETURA
    # =========================================================================
    question(
        numero="Q5",
        pergunta="Qual é o stack tecnológico preferido? (Backend)",
        tipo="multiselect",
        secao="B.1",
        obrigatoria=False,
        opcoes=[
            "Python/FastAPI",
            "Python/Django",
            "Node.js/Express",
            "Node.js/NestJS",
            "Java/Spring",
            "Go",
            "C#/.NET",
            "Ruby/Rails",
            "PHP/Laravel",
            "Rust",
            "Outro",
        ],
        visible_if=[],
        revela=[],
    ),
    question(
        numero="Q6",
        pergunta="Qual é o stack tecnológico preferido? (Frontend)",
        tipo="multiselect",
        secao="B.1",
        obrigatoria=False,
        opcoes=[
            "React",
            "Vue",
            "Angular",
            "Svelte",
            "Next.js",
            "Nuxt",
            "Remix",
            "SvelteKit",
            "Ember",
            "Outro",
        ],
        visible_if=[],
        revela=[],
    ),
    question(
        numero="Q7",
        pergunta="Qual é o volume esperado de requisições por segundo?",
        tipo="text",
        secao="B.2",
        obrigatoria=True,
        opcoes=[],
        visible_if=[{"dependsOn": "Q3", "valor": "Sim, modesto"}],
        revela=["Q11"],
    ),
    question(
        numero="Q8",
        pergunta="Quais tecnologias de cache são necessárias?",
        tipo="multiselect",
        secao="B.2",
        obrigatoria=False,
        opcoes=["Redis", "Memcached", "CDN", "Nenhuma"],
        visible_if=[{"dependsOn": "Q3", "valor": "Sim, modesto"}],
        revela=[],
    ),
    question(
        numero="Q9",
        pergunta="O projeto precisa de message queue (fila de mensagens)?",
        tipo="dropdown",
        secao="B.2",
        obrigatoria=False,
        opcoes=["Não", "Sim, SQS/SNS", "Sim, RabbitMQ", "Sim, Kafka"],
        visible_if=[{"dependsOn": "Q3", "valor": "Sim, agressivo"}],
        revela=["Q12"],
    ),
    question(
        numero="Q10",
        pergunta="Qual é o SLA esperado de uptime?",
        tipo="dropdown",
        secao="B.3",
        obrigatoria=False,
        opcoes=["99.0%", "99.5%", "99.9%", "99.99%", "Não crítico"],
        visible_if=[{"dependsOn": "Q3", "valor": "Sim, agressivo"}],
        revela=[],
    ),
    # =========================================================================
    # SEÇÃO C: INTEGRAÇÃO
    # =========================================================================
    question(
        numero="Q11",
        pergunta="Quais sistemas externos precisam ser integrados?",
        tipo="multiselect",
        secao="C.1",
        obrigatoria=False,
        opcoes=[
            "CRM (Salesforce, HubSpot)",
            "ERP (SAP, Oracle)",
            "Payment Gateway",
            "Email/SMS",
            "Analytics",
            "Nenhum",
        ],
        visible_if=[],
        revela=[],
    ),
    question(
        numero="Q12",
        pergunta="Qual é o protocolo de integração preferido?",
        tipo="dropdown",
        secao="C.1",
        obrigatoria=False,
        opcoes=["REST API", "GraphQL", "gRPC", "Webhooks", "Não decidido"],
        visible_if=[{"dependsOn": "Q9", "valor": "Sim, Kafka"}],
        revela=[],
    ),
    question(
        numero="Q13",
        pergunta="Há requisitos de segurança específicos?",
        tipo="multiselect",
        secao="C.2",
        obrigatoria=False,
        opcoes=[
            "OAuth 2.0",
            "JWT",
            "mTLS",
            "RBAC",
            "Encriptação (TLS)",
            "2FA/MFA",
            "HIPAA",
            "PCI-DSS",
            "Nenhum específico",
            "Outro",
        ],
        visible_if=[],
        revela=[],
    ),
    # =========================================================================
    # SEÇÃO D: ESCALABILIDADE E PERFORMANCE
    # =========================================================================
    question(
        numero="Q14",
        pergunta="Qual é o tempo máximo aceitável de latência?",
        tipo="text",
        secao="D.1",
        obrigatoria=False,
        opcoes=[],
        visible_if=[{"dependsOn": "Q3", "valor": "Sim, agressivo"}],
        revela=[],
    ),
    question(
        numero="Q15",
        pergunta="Há restrições de compliance (LGPD, GDPR, etc)?",
        tipo="multiselect",
        secao="D.2",
        obrigatoria=False,
        opcoes=["LGPD", "GDPR", "HIPAA", "SOC 2", "Nenhuma"],
        visible_if=[],
        revela=[],
    ),
]


def validate_schema() -> None:
    """Valida integridade do schema (verificações estáticas)."""
    numeros = set()
    dependencias = {}

    for q in TECHNICAL_QUESTIONS_SCHEMA:
        numero = q["numero"]
        numeros.add(numero)

        if q["visibleIf"]:
            for condition in q["visibleIf"]:
                dependencias.setdefault(condition["dependsOn"], []).append(numero)

        if q["revela"]:
            for revelado in q["revela"]:
                if revelado not in numeros and revelado not in [
                    q2["numero"] for q2 in TECHNICAL_QUESTIONS_SCHEMA
                ]:
                    raise ValueError(f"Q {numero} revela {revelado} que não existe no schema")

    # Validar que todas as dependências existem
    for dependsOn in dependencias:
        if dependsOn not in numeros:
            raise ValueError(f"Pergunta depende de {dependsOn} que não existe no schema")


# Executar validação ao importar
validate_schema()
