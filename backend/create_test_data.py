#!/usr/bin/env python3
"""Create realistic test data for Phase B.4 E2E testing."""
import asyncio
from uuid import uuid4
from datetime import datetime
from app.db.database import AsyncSessionLocal
from sqlalchemy import select
from app.models.base import Project, Organization, User, IngestedDocument
from app.models.document_route_map import DocumentRouteMap
from app.models.auditor_output import AuditorOutput


async def create_test_data():
    """Create test project, route_map, and auditor_output."""
    async with AsyncSessionLocal() as db:
        # 0. Fetch or create organization
        result = await db.execute(select(Organization).limit(1))
        org = result.scalars().first()

        if not org:
            print("✗ No organization found. Create one first via the admin interface.")
            return

        print(f"✓ Using organization: {org.slug}")

        # 1. Create test project
        project = Project(
            id=uuid4(),
            organization_id=org.id,
            name="E-Commerce Phase B.4 Test",
            slug="ecommerce-test-b4",
            description="Test project for Phase B.4 E2E testing",
            deliverable_type="full-stack-app",
            status="active",
        )
        db.add(project)
        await db.flush()
        print(f"✓ Project created: {project.id}")

        # 1b. Fetch admin user for document upload
        result = await db.execute(select(User).where(User.is_admin == True).limit(1))
        admin = result.scalars().first()
        if not admin:
            print("✗ No admin user found.")
            return
        print(f"✓ Using admin: {admin.email}")

        # 1c. Create IngestedDocument
        doc = IngestedDocument(
            id=uuid4(),
            project_id=project.id,
            filename="ecommerce-spec-b4.pdf",
            original_filename="E-commerce Specification.pdf",
            file_type="pdf",
            file_hash="abc123def456" + str(uuid4())[:8],
            file_size_bytes=45000,
            uploaded_by=admin.id,
            arguider_status="completed",
            arguider_completed_at=datetime.now(),
        )
        db.add(doc)
        await db.flush()
        print(f"✓ IngestedDocument created: {doc.id}")

        # 3. Create realistic chunks list for DocumentRouteMap
        chunks_list = [
            {
                "id": "chunk_req_001",
                "heading_path": "/Requisitos Funcionais/Escopo",
                "chunk_type": "section",
                "text": "O sistema deve ser uma plataforma de e-commerce completa com carrinho, checkout, pagamento e administração.",
                "first_sentence": "O sistema deve ser uma plataforma de e-commerce completa",
                "position": 0,
                "tags": ["GP", "ARQ", "DEV"],
                "token_count": 25,
            },
            {
                "id": "chunk_arch_001",
                "heading_path": "/Arquitetura/Stack",
                "chunk_type": "section",
                "text": "Stack proposto: Backend Node.js/Express, Frontend React/TypeScript, Database PostgreSQL com Redis cache, Kubernetes deployment.",
                "first_sentence": "Stack proposto: Backend Node.js/Express",
                "position": 1,
                "tags": ["ARQ", "DBA", "DEV"],
                "token_count": 22,
            },
            {
                "id": "chunk_arch_002",
                "heading_path": "/Arquitetura/Integrações",
                "chunk_type": "section",
                "text": "Integrações necessárias: Stripe para pagamento, SendGrid para email, Auth0 para autenticação, DataDog para observabilidade.",
                "first_sentence": "Integrações necessárias: Stripe para pagamento",
                "position": 2,
                "tags": ["ARQ", "DEV"],
                "token_count": 20,
            },
            {
                "id": "chunk_data_001",
                "heading_path": "/Banco de Dados/Modelo",
                "chunk_type": "section",
                "text": "Modelo de dados: Users, Products, Orders, OrderItems, Payments. Tabelas normalizadas 3NF. Índices em user_id, product_id, order_id para performance.",
                "first_sentence": "Modelo de dados: Users, Products, Orders",
                "position": 3,
                "tags": ["DBA", "DEV"],
                "token_count": 23,
            },
            {
                "id": "chunk_perf_001",
                "heading_path": "/Performance/Requisitos",
                "chunk_type": "section",
                "text": "Requisitos de performance: P95 < 200ms, suportar 10K concurrent users, 99.9% uptime SLA.",
                "first_sentence": "Requisitos de performance: P95 < 200ms",
                "position": 4,
                "tags": ["ARQ", "DBA", "QA"],
                "token_count": 18,
            },
            {
                "id": "chunk_test_001",
                "heading_path": "/Testes/Cobertura",
                "chunk_type": "section",
                "text": "Cobertura de testes: unit 80%, integration 60%, e2e 40%. Testes de carga com k6. Testes de segurança com OWASP ZAP.",
                "first_sentence": "Cobertura de testes: unit 80%",
                "position": 5,
                "tags": ["QA", "DEV"],
                "token_count": 20,
            },
            {
                "id": "chunk_ux_001",
                "heading_path": "/UX/Jornadas",
                "chunk_type": "section",
                "text": "Jornadas principais: Browse Products (2 clicks), Add to Cart (1 click), Checkout (3 steps), Payment (secure Stripe integration).",
                "first_sentence": "Jornadas principais: Browse Products",
                "position": 6,
                "tags": ["UX", "UI"],
                "token_count": 21,
            },
            {
                "id": "chunk_ui_001",
                "heading_path": "/UI/Design System",
                "chunk_type": "section",
                "text": "Design system: Tailwind CSS, componentes reutilizáveis, dark mode support, acessibilidade WCAG AA.",
                "first_sentence": "Design system: Tailwind CSS",
                "position": 7,
                "tags": ["UI"],
                "token_count": 16,
            },
        ]

        # 2b. Create DocumentRouteMap with chunks
        route_map = DocumentRouteMap(
            id=uuid4(),
            document_id=doc.id,
            version=1,
            llm_provider="anthropic",
            llm_model="claude-opus-4-6",
            chunks=chunks_list,
            total_chunks=len(chunks_list),
            chunking_time_ms=1250,
            created_by=admin.id,
        )
        db.add(route_map)
        await db.flush()
        print(f"✓ RouteMap created: {route_map.id}")

        # 4. Create AuditorOutput
        auditor_output = AuditorOutput(
            id=uuid4(),
            route_map_id=route_map.id,
            summary="E-commerce platform com stack moderno (Node.js/React), integrado com Stripe, Auth0, DataDog. Requisitos de performance claros, cobertura de testes definida.",
            summary_token_count=85,
            chunk_tags={tag: [] for tag in ["GP", "ARQ", "DBA", "DEV", "QA", "UX", "UI"]},
            highlights={
                "GP": [
                    "Escopo bem-definido e completo",
                    "Timeline claro em proposição",
                ],
                "ARQ": [
                    "Stack apropriado (Node.js/React)",
                    "Integrações selecionadas adequadamente",
                ],
                "DBA": [
                    "Modelo de dados bem-estruturado",
                    "Índices de performance planejados",
                ],
                "DEV": [
                    "Dependências claras (Stripe, Auth0)",
                    "Tecnologias padrão da indústria",
                ],
                "QA": [
                    "Cobertura de testes documentada",
                    "Estratégia de testes clara",
                ],
                "UX": [
                    "Jornadas de usuário mapeadas",
                    "Fluxo de checkout bem-definido",
                ],
                "UI": [
                    "Design system proposto (Tailwind)",
                    "Acessibilidade WCAG AA",
                ],
            },
            audit_findings={},
            backlog_to_specialists=[
                {
                    "specialist": "GP",
                    "item": "Confirmar timeline de MVP (4-6 semanas?)",
                    "priority": "high",
                },
                {
                    "specialist": "ARQ",
                    "item": "Detalhar estratégia de escalabilidade horizontal",
                    "priority": "medium",
                },
                {
                    "specialist": "DBA",
                    "item": "Validar retenção de dados e LGPD compliance",
                    "priority": "high",
                },
            ],
            llm_provider="anthropic",
            llm_model="claude-opus-4-6",
            input_tokens=2500,
            output_tokens=850,
            elapsed_ms=3200,
        )
        db.add(auditor_output)
        await db.commit()

        print(f"✓ AuditorOutput created: {auditor_output.id}")
        print(f"\n📊 Test Data Summary:")
        print(f"   Project: {project.id}")
        print(f"   Project Name: {project.name}")
        print(f"   RouteMap: {route_map.id}")
        print(f"   Chunks: {len(chunks_list)}")
        print(f"\n🔗 Frontend URL:")
        print(f"   http://localhost:3000/projects/{project.id}/gatekeeper-passada/{route_map.id}")
        print(f"\n📡 API Endpoints to test:")
        print(f"   POST /api/v1/gatekeeper/passada-1")
        print(f"   GET  /api/v1/gatekeeper/personas-board/{route_map.id}?passada=1")
        print(f"   POST /api/v1/gatekeeper/human-answers")
        print(f"   POST /api/v1/gatekeeper/passada-2")

        return {
            "project_id": str(project.id),
            "route_map_id": str(route_map.id),
        }


if __name__ == "__main__":
    data = asyncio.run(create_test_data())
