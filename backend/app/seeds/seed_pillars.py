"""
Seeding script para os 7 Pilares padrão do GCA
Executar: python -m app.seeds.seed_pillars
"""
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from app.db.database import AsyncSessionLocal
from app.models.pillar import PillarTemplate, CompanyPolicy


PILLARS_DATA = [
    {
        "code": "P1",
        "name": "Requisitos Negociais",
        "description": "Alinhamento com objetivos do negócio, value proposition, ROI esperado, escopo e limites",
        "default_weight": 1.0,
        "is_blocking": False,
        "blocking_threshold": None,
        "default_criteria": {
            "business_alignment": {
                "description": "Alinhamento com objetivos estratégicos",
                "weight": 0.3
            },
            "value_proposition": {
                "description": "Proposição de valor clara e identificável",
                "weight": 0.3
            },
            "roi_definition": {
                "description": "ROI esperado bem definido",
                "weight": 0.2
            },
            "scope_clarity": {
                "description": "Escopo e limites claros",
                "weight": 0.2
            }
        }
    },
    {
        "code": "P2",
        "name": "Regras de Negócio",
        "description": "Lógica de negócio, fluxos de processos, políticas, restrições e integrações com sistemas existentes",
        "default_weight": 1.0,
        "is_blocking": False,
        "blocking_threshold": None,
        "default_criteria": {
            "business_logic": {
                "description": "Lógica de negócio documentada e clara",
                "weight": 0.35
            },
            "process_workflows": {
                "description": "Fluxos de processo bem definidos",
                "weight": 0.3
            },
            "policies_rules": {
                "description": "Políticas e restrições implementadas",
                "weight": 0.2
            },
            "integration_requirements": {
                "description": "Requisitos de integração identificados",
                "weight": 0.15
            }
        }
    },
    {
        "code": "P3",
        "name": "Requisitos Funcionais",
        "description": "Features específicas, user stories, APIs/Endpoints e workflows",
        "default_weight": 1.0,
        "is_blocking": False,
        "blocking_threshold": None,
        "default_criteria": {
            "feature_completeness": {
                "description": "Features implementadas conforme requisito",
                "weight": 0.3
            },
            "user_stories": {
                "description": "User stories bem definidas e aceitação clara",
                "weight": 0.25
            },
            "api_design": {
                "description": "APIs/Endpoints bem documentadas",
                "weight": 0.25
            },
            "workflow_implementation": {
                "description": "Workflows implementados corretamente",
                "weight": 0.2
            }
        }
    },
    {
        "code": "P4",
        "name": "Requisitos Não Funcionais",
        "description": "Performance, escalabilidade, disponibilidade, confiabilidade e resiliência",
        "default_weight": 1.0,
        "is_blocking": False,
        "blocking_threshold": None,
        "default_criteria": {
            "performance": {
                "description": "Tempo resposta e throughput conforme SLA",
                "weight": 0.25
            },
            "scalability": {
                "description": "Suporta crescimento de usuários/dados",
                "weight": 0.25
            },
            "availability": {
                "description": "Uptime conforme SLA",
                "weight": 0.25
            },
            "reliability": {
                "description": "MTBF e MTTR dentro dos limites",
                "weight": 0.25
            }
        }
    },
    {
        "code": "P5",
        "name": "Arquitetura",
        "description": "Stack tecnológico, padrões de design, organização de código e infraestrutura",
        "default_weight": 1.0,
        "is_blocking": False,
        "blocking_threshold": None,
        "default_criteria": {
            "stack_selection": {
                "description": "Stack alinhado com requisitos",
                "weight": 0.3
            },
            "design_patterns": {
                "description": "Padrões de design aplicados corretamente",
                "weight": 0.25
            },
            "code_organization": {
                "description": "Código bem organizado e estruturado",
                "weight": 0.25
            },
            "infrastructure": {
                "description": "Infraestrutura robusta e bem documentada",
                "weight": 0.2
            }
        }
    },
    {
        "code": "P6",
        "name": "Dados/Integrações/Legado",
        "description": "Modelos de dados, integrações com APIs, sistemas legados e migração de dados",
        "default_weight": 1.0,
        "is_blocking": False,
        "blocking_threshold": None,
        "default_criteria": {
            "data_modeling": {
                "description": "Modelo de dados bem estruturado",
                "weight": 0.3
            },
            "integrations": {
                "description": "Integrações funcionando conforme especificado",
                "weight": 0.25
            },
            "legacy_handling": {
                "description": "Sistemas legados integrados ou migrados",
                "weight": 0.25
            },
            "data_migration": {
                "description": "Plano e execução de migração clara",
                "weight": 0.2
            }
        }
    },
    {
        "code": "P7",
        "name": "Segurança/Compliance/QA",
        "description": "LGPD/GDPR, segurança (auth, encryption, secrets), testes (unit, integration, e2e) e quality gates",
        "default_weight": 1.0,
        "is_blocking": True,
        "blocking_threshold": 70.0,
        "default_criteria": {
            "compliance": {
                "description": "Conformidade com LGPD/GDPR/regulamentações",
                "weight": 0.25
            },
            "security": {
                "description": "Segurança implementada (auth, encryption, secrets)",
                "weight": 0.25
            },
            "testing": {
                "description": "Testes completos (unit, integration, e2e)",
                "weight": 0.25
            },
            "quality_gates": {
                "description": "Code review e quality checks passam",
                "weight": 0.25
            }
        }
    }
]


async def seed_pillars():
    """Seed os 7 pilares padrão do GCA"""

    async with AsyncSessionLocal() as session:
        print("🌱 Iniciando seeding dos 7 Pilares...")

        for pillar_data in PILLARS_DATA:
            # Cria pillar
            pillar = PillarTemplate(
                id=uuid4(),
                code=pillar_data["code"],
                name=pillar_data["name"],
                description=pillar_data["description"],
                default_weight=pillar_data["default_weight"],
                is_blocking=pillar_data["is_blocking"],
                blocking_threshold=pillar_data["blocking_threshold"],
                default_criteria=pillar_data["default_criteria"]
            )

            session.add(pillar)

            print(f"  ✓ {pillar.code} - {pillar.name}")

        await session.commit()

        print("\n✅ Seeding dos 7 Pilares concluído!")
        print("\nPilares criados:")
        for pillar_data in PILLARS_DATA:
            blocking = " [BLOQUEANTE]" if pillar_data["is_blocking"] else ""
            print(f"  {pillar_data['code']}: {pillar_data['name']}{blocking}")


async def seed_company_policies():
    """Seed políticas padrão da empresa (optionalmente bloqueantes)"""

    async with AsyncSessionLocal() as session:
        print("\n🌱 Iniciando seeding de políticas da empresa...")

        policies = [
            {
                "policy_name": "Require HTTPS in production",
                "pillar_code": "P7",
                "description": "Toda comunicação em produção deve usar HTTPS",
                "validation_rules": {"require_https": True},
                "severity": "error"
            },
            {
                "policy_name": "Minimum RBAC levels",
                "pillar_code": "P1",
                "description": "Mínimo de 3 níveis RBAC por projeto",
                "validation_rules": {"min_rbac_levels": 3},
                "severity": "warning"
            },
            {
                "policy_name": "LGPD compliance required",
                "pillar_code": "P7",
                "description": "Conformidade LGPD obrigatória em production",
                "validation_rules": {"require_lgpd_compliance": True},
                "severity": "error"
            },
        ]

        # TODO: Implementar após entender como buscas de PillarTemplate
        # Por enquanto, apenas log
        print("  ℹ️  Políticas da empresa - implementar depois")
        print("  Exemplo: HTTPS obrigatório, LGPD compliance, etc")


async def main():
    """Main seeding function"""
    try:
        await seed_pillars()
        await seed_company_policies()
        print("\n🎉 Seeding concluído com sucesso!")

    except Exception as e:
        print(f"\n❌ Erro durante seeding: {str(e)}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
