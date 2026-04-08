"""
Mock Project Seeder
Popula banco de dados com projeto mock realista para testes e demos
"""
import asyncio
import sys
from uuid import uuid4
from datetime import datetime, timezone

sys.path.insert(0, '/app')

from app.db.database import AsyncSessionLocal
from app.models.base import User
from app.models.onboarding import ProjectRequest, ProjectRequestStatus, OnboardingProgress
from app.models.tenant import Artifact, ArtifactEvaluation, ArtifactType, ArtifactStatus
from app.models.pillar import PillarTemplate
from app.core.security import hash_password
import structlog

logger = structlog.get_logger(__name__)


async def create_mock_project():
    """Create a complete mock project with artifacts and evaluations"""

    try:
        async with AsyncSessionLocal() as session:
            # 1. Create admin and GP users
            admin = User(
                id=uuid4(),
                email="admin@gca-mock.com",
                password_hash=hash_password("admin123"),
                full_name="Admin Mock",
                is_active=True,
                is_admin=True
            )
            session.add(admin)

            gp = User(
                id=uuid4(),
                email="gp@gca-mock.com",
                password_hash=hash_password("gp123"),
                full_name="GP Mock",
                is_active=True
            )
            session.add(gp)

            evaluator = User(
                id=uuid4(),
                email="evaluator@gca-mock.com",
                password_hash=hash_password("eval123"),
                full_name="Evaluator Mock",
                is_active=True
            )
            session.add(evaluator)

            await session.commit()

            admin_id = admin.id
            gp_id = gp.id
            evaluator_id = evaluator.id

            print(f"✅ Created users:")
            print(f"   Admin: {admin_id}")
            print(f"   GP: {gp_id}")
            print(f"   Evaluator: {evaluator_id}")

            # 2. Create project request
            project = ProjectRequest(
                id=uuid4(),
                gp_id=gp_id,
                project_name="E-Commerce Platform",
                project_slug="ecommerce-platform",
                description="Mock e-commerce platform for testing GCA",
                schema_name="proj_ecommerce-platform",
                status=ProjectRequestStatus.APPROVED,
                approved_by=admin_id,
                approved_at=datetime.now(timezone.utc),
                requested_at=datetime.now(timezone.utc)
            )
            session.add(project)
            await session.commit()

            project_id = project.id
            schema_name = project.schema_name

            print(f"✅ Created project: {project_id}")
            print(f"   Slug: ecommerce-platform")
            print(f"   Schema: {schema_name}")

            # 3. Create onboarding progress
            onboarding = OnboardingProgress(
                id=uuid4(),
                project_id=project_id,
                gp_id=gp_id
            )
            session.add(onboarding)
            await session.commit()

            print(f"✅ Created onboarding progress")

            # 4. Create mock artifacts with different statuses
            artifacts_data = [
                {
                    "name": "System Requirements",
                    "type": ArtifactType.REQUIREMENTS,
                    "description": "Complete functional and non-functional requirements",
                    "content": "# System Requirements\n\n## Functional Requirements\n- User registration\n- Product catalog\n- Shopping cart\n- Order management\n\n## Non-Functional\n- 99.9% uptime\n- <2s response time\n- Support 10k concurrent users",
                    "status": ArtifactStatus.APPROVED,
                    "evaluation": {
                        "p1_score": 85,  # Business alignment
                        "p2_score": 90,  # Business logic
                        "p3_score": 88,  # Functional
                        "p4_score": 85,  # Non-functional
                        "p5_score": 82,  # Architecture
                        "p6_score": 80,  # Data
                        "p7_score": 85,  # Compliance/Security
                        "status": "approved"
                    }
                },
                {
                    "name": "System Architecture Diagram",
                    "type": ArtifactType.ARCHITECTURE,
                    "description": "Microservices architecture with API gateway",
                    "content": "# Architecture\n\nMicroservices:\n- User Service\n- Product Service\n- Order Service\n- Payment Service\n- Notification Service",
                    "status": ArtifactStatus.APPROVED,
                    "evaluation": {
                        "p1_score": 80,
                        "p2_score": 85,
                        "p3_score": 90,
                        "p4_score": 88,
                        "p5_score": 92,  # High for architecture
                        "p6_score": 85,
                        "p7_score": 88,
                        "status": "approved"
                    }
                },
                {
                    "name": "Data Model Specification",
                    "type": ArtifactType.DOCUMENT,
                    "description": "Database schema and relationships",
                    "content": "# Data Models\n\nUsers, Products, Orders, OrderItems, Payments",
                    "status": ArtifactStatus.UNDER_REVIEW,
                    "evaluation": {
                        "p1_score": 75,
                        "p2_score": 70,
                        "p3_score": 65,
                        "p4_score": 70,
                        "p5_score": 75,
                        "p6_score": 78,  # Data focused
                        "p7_score": 72,
                        "status": "needs_review"
                    }
                },
                {
                    "name": "Security & Compliance Plan",
                    "type": ArtifactType.DOCUMENT,
                    "description": "Security measures and compliance checklist",
                    "content": "# Security Plan\n\n## LGPD Compliance\n- Data encryption\n- User consent management\n- Right to be forgotten",
                    "status": ArtifactStatus.DRAFT,
                    "evaluation": {
                        "p1_score": 70,
                        "p2_score": 65,
                        "p3_score": 60,
                        "p4_score": 65,
                        "p5_score": 70,
                        "p6_score": 68,
                        "p7_score": 55,  # CRITICAL: < 70 = BLOCKED
                        "status": "blocked"
                    }
                },
                {
                    "name": "API Documentation",
                    "type": ArtifactType.DOCUMENT,
                    "description": "OpenAPI/Swagger specification",
                    "content": "# API Endpoints\n\nGET /api/products\nPOST /api/orders\nGET /api/orders/{id}",
                    "status": ArtifactStatus.APPROVED,
                    "evaluation": {
                        "p1_score": 82,
                        "p2_score": 80,
                        "p3_score": 85,
                        "p4_score": 80,
                        "p5_score": 88,
                        "p6_score": 82,
                        "p7_score": 86,
                        "status": "approved"
                    }
                }
            ]

            artifacts = []
            for artifact_data in artifacts_data:
                artifact = Artifact(
                    id=uuid4(),
                    name=artifact_data["name"],
                    type=artifact_data["type"],
                    description=artifact_data["description"],
                    content=artifact_data["content"],
                    status=artifact_data["status"],
                    created_by=gp_id
                )
                session.add(artifact)
                await session.commit()

                # Create evaluation
                eval_data = artifact_data["evaluation"]
                evaluation = ArtifactEvaluation(
                    id=uuid4(),
                    artifact_id=artifact.id,
                    p1_business_score=eval_data["p1_score"],
                    p2_rules_score=eval_data["p2_score"],
                    p3_functional_score=eval_data["p3_score"],
                    p4_nonfunctional_score=eval_data["p4_score"],
                    p5_architecture_score=eval_data["p5_score"],
                    p6_data_score=eval_data["p6_score"],
                    p7_security_score=eval_data["p7_score"],
                    p7_blocked=(eval_data["p7_score"] < 70),
                    final_score=sum([
                        eval_data["p1_score"],
                        eval_data["p2_score"],
                        eval_data["p3_score"],
                        eval_data["p4_score"],
                        eval_data["p5_score"],
                        eval_data["p6_score"],
                        eval_data["p7_score"]
                    ]) / 7,
                    final_status=eval_data["status"],
                    code_generation_allowed=(eval_data["p7_score"] >= 70),
                    evaluation_details={"all_pillars": eval_data},
                    feedback=f"Evaluation for {artifact_data['name']}",
                    evaluated_by=evaluator_id
                )
                session.add(evaluation)

                # Update artifact with evaluation
                artifact.evaluation_id = evaluation.id
                artifact.last_evaluation_date = datetime.now(timezone.utc)

                artifacts.append({
                    "name": artifact_data["name"],
                    "status": eval_data["status"],
                    "p7_score": eval_data["p7_score"]
                })

                await session.commit()

            print(f"\n✅ Created {len(artifacts)} artifacts with evaluations:")
            for artifact in artifacts:
                status_emoji = "🟢" if artifact["status"] == "approved" else "🟡" if artifact["status"] == "needs_review" else "🔴"
                p7_icon = "⚠️" if artifact["p7_score"] < 70 else "✅"
                print(f"   {status_emoji} {artifact['name']}")
                print(f"      P7 Score: {artifact['p7_score']} {p7_icon}")

            # 5. Summary stats
            print(f"\n📊 Summary:")
            print(f"   Project ID: {project_id}")
            print(f"   Schema: {schema_name}")
            print(f"   Artifacts: {len(artifacts)}")
            print(f"   - Approved: {sum(1 for a in artifacts if a['status'] == 'approved')}")
            print(f"   - Needs Review: {sum(1 for a in artifacts if a['status'] == 'needs_review')}")
            print(f"   - Blocked: {sum(1 for a in artifacts if a['status'] == 'blocked')}")
            print(f"   - P7 Blocked: {sum(1 for a in artifacts if a['p7_score'] < 70)}")

            # 6. Return data for use in tests
            return {
                "project_id": str(project_id),
                "schema_name": schema_name,
                "admin_id": str(admin_id),
                "gp_id": str(gp_id),
                "evaluator_id": str(evaluator_id),
                "artifacts_count": len(artifacts),
                "approved_count": sum(1 for a in artifacts if a['status'] == 'approved'),
                "blocked_count": sum(1 for a in artifacts if a['status'] == 'blocked')
            }

    except Exception as e:
        logger.error("seed.mock_project_failed", error=str(e))
        raise


async def main():
    print("\n╔════════════════════════════════════════════════════════════════╗")
    print("║    SEEDING MOCK PROJECT FOR GCA TESTING                       ║")
    print("╚════════════════════════════════════════════════════════════════╝\n")

    result = await create_mock_project()

    print(f"\n✨ Mock project successfully seeded!")
    print(f"\n📝 Use this data in tests:")
    print(f"   Project ID: {result['project_id']}")
    print(f"   Schema: {result['schema_name']}")

    return result


if __name__ == "__main__":
    asyncio.run(main())
