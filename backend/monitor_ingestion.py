#!/usr/bin/env python3
"""Monitor ingestion and Arguidor processing in real-time."""
import asyncio
import time
from app.db.database import AsyncSessionLocal
from sqlalchemy import select, desc
from app.models.base import Project, IngestedDocument
from app.models.document_route_map import DocumentRouteMap
from app.models.auditor_output import AuditorOutput


async def monitor():
    """Monitor document ingestion and processing."""
    async with AsyncSessionLocal() as db:
        # Get AJA project
        result = await db.execute(select(Project).where(Project.slug == "aja"))
        project = result.scalars().first()

        if not project:
            print("❌ Projeto AJA não encontrado")
            return

        print(f"📦 Monitorando projeto: {project.name}")
        print("="*80)

        last_doc_id = None
        start_time = time.time()
        max_wait = 300  # 5 minutos

        while True:
            elapsed = time.time() - start_time

            # Fetch latest document
            result = await db.execute(
                select(IngestedDocument)
                .where(IngestedDocument.project_id == project.id)
                .order_by(desc(IngestedDocument.created_at))
                .limit(1)
            )
            doc = result.scalars().first()

            if not doc:
                print(f"⏳ [{elapsed:.0f}s] Aguardando documento...")
                await asyncio.sleep(2)
                continue

            # If new document, start fresh
            if last_doc_id != doc.id:
                last_doc_id = doc.id
                print(f"\n📄 Novo documento detectado: {doc.original_filename}")
                print(f"   ID: {doc.id}")

            # Check status
            print(f"⏳ [{elapsed:.0f}s] Status: {doc.arguider_status}")

            if doc.arguider_status == "completed":
                print(f"\n✅ ARGUIDOR COMPLETO!")

                # Get route map
                result = await db.execute(
                    select(DocumentRouteMap).where(
                        DocumentRouteMap.document_id == doc.id
                    )
                )
                route_map = result.scalars().first()

                if not route_map:
                    print("⚠️  RouteMap não encontrado")
                    await asyncio.sleep(2)
                    continue

                print(f"✓ RouteMap: {route_map.id}")
                print(f"✓ Chunks: {route_map.total_chunks}")

                # Check AuditorOutput
                result = await db.execute(
                    select(AuditorOutput).where(
                        AuditorOutput.route_map_id == route_map.id
                    )
                )
                auditor = result.scalars().first()

                if not auditor:
                    print("⚠️  AuditorOutput não criado ainda...")
                    await asyncio.sleep(2)
                    continue

                print(f"✓ AuditorOutput: {auditor.id}")

                # Print final URLs
                print("\n" + "="*80)
                print("🎉 PRONTO PARA TESTAR GATEKEEPER!")
                print("="*80)

                print(f"\n📊 Resumo:")
                print(f"   Documento: {doc.original_filename}")
                print(f"   Chunks: {route_map.total_chunks}")
                print(f"   Tempo total: {elapsed:.0f}s")

                print(f"\n🔗 Abra no navegador:")
                print(f"   http://localhost:3000/projects/{project.id}/gatekeeper-passada/{route_map.id}")

                print(f"\n📡 Ou teste via API:")
                print(f"   curl -X POST http://localhost:8000/api/v1/gatekeeper/passada-1 \\")
                print(f"     -H 'Content-Type: application/json' \\")
                print(f"     -d '{{\"route_map_id\":\"{route_map.id}\", \"execute_now\":true}}'")

                print("\n" + "="*80)
                return

            elif doc.arguider_status == "error":
                print(f"❌ Erro no Arguidor: {doc.arguider_error_message}")
                return

            elif elapsed > max_wait:
                print(f"⏱️  Timeout após {max_wait}s")
                return

            await asyncio.sleep(3)


if __name__ == "__main__":
    try:
        asyncio.run(monitor())
    except KeyboardInterrupt:
        print("\n\n⏸️  Monitoramento interrompido")
