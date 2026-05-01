#!/usr/bin/env python3
"""List real documents with AuditorOutput ready for Gatekeeper testing."""
import asyncio
from app.db.database import AsyncSessionLocal
from sqlalchemy import select
from app.models.base import Project, IngestedDocument
from app.models.document_route_map import DocumentRouteMap
from app.models.auditor_output import AuditorOutput


async def list_documents():
    """List all documents with route_maps and auditor outputs."""
    async with AsyncSessionLocal() as db:
        # Fetch projects
        result = await db.execute(select(Project).order_by(Project.created_at.desc()).limit(10))
        projects = result.scalars().all()

        print("\n" + "="*80)
        print("📋 PROJETOS COM DOCUMENTOS PARA TESTE GATEKEEPER")
        print("="*80)

        for project in projects:
            print(f"\n🏢 Projeto: {project.name}")
            print(f"   ID: {project.id}")
            print(f"   Slug: {project.slug}")

            # Fetch documents for this project
            result = await db.execute(
                select(IngestedDocument).where(
                    IngestedDocument.project_id == project.id
                ).order_by(IngestedDocument.created_at.desc()).limit(5)
            )
            documents = result.scalars().all()

            if not documents:
                print("   ❌ Nenhum documento encontrado")
                continue

            for doc in documents:
                print(f"\n   📄 Documento: {doc.original_filename}")
                print(f"      ID: {doc.id}")
                print(f"      Tipo: {doc.file_type}")
                print(f"      Status: {doc.arguider_status}")

                # Fetch route maps for this document
                result = await db.execute(
                    select(DocumentRouteMap).where(
                        DocumentRouteMap.document_id == doc.id
                    )
                )
                route_maps = result.scalars().all()

                if not route_maps:
                    print("      ⚠️  Sem RouteMap")
                    continue

                for route_map in route_maps:
                    print(f"\n      🗺️  RouteMap v{route_map.version}")
                    print(f"         ID: {route_map.id}")
                    print(f"         Chunks: {route_map.total_chunks}")

                    # Check if AuditorOutput exists
                    result = await db.execute(
                        select(AuditorOutput).where(
                            AuditorOutput.route_map_id == route_map.id
                        )
                    )
                    auditor = result.scalars().first()

                    if auditor:
                        print(f"         ✅ AuditorOutput pronto (LLM: {auditor.llm_provider}/{auditor.llm_model})")
                        print(f"\n            🔗 URL para testar:")
                        print(f"            http://localhost:3000/projects/{project.id}/gatekeeper-passada/{route_map.id}")
                        print(f"\n            📡 API para testar Passada 1:")
                        print(f"            curl -X POST http://localhost:8000/api/v1/gatekeeper/passada-1 \\")
                        print(f"              -H 'Content-Type: application/json' \\")
                        print(f"              -d '{{\"route_map_id\":\"{route_map.id}\", \"execute_now\":true}}'")
                    else:
                        print(f"         ❌ Sem AuditorOutput (aguardando processamento)")

        print("\n" + "="*80)


if __name__ == "__main__":
    asyncio.run(list_documents())
