#!/usr/bin/env python3
"""Upload document and wait for Arguidor to process it."""
import asyncio
import time
from pathlib import Path
from app.db.database import AsyncSessionLocal
from sqlalchemy import select
from app.models.base import Project, IngestedDocument, User
from app.models.document_route_map import DocumentRouteMap
from app.models.auditor_output import AuditorOutput


async def upload_and_wait():
    """Upload document to AJA project and wait for Arguidor processing."""
    doc_path = Path("/home/luiz/Downloads/AJA_Especificacao_Requisitos_Expandida_v2_0.docx")

    if not doc_path.exists():
        print(f"❌ Arquivo não encontrado: {doc_path}")
        return

    async with AsyncSessionLocal() as db:
        # 1. Get AJA project
        result = await db.execute(select(Project).where(Project.slug == "aja"))
        project = result.scalars().first()

        if not project:
            print("❌ Projeto AJA não encontrado")
            return

        print(f"✓ Projeto encontrado: {project.name}")

        # 2. Get admin user
        result = await db.execute(select(User).where(User.is_admin == True).limit(1))
        admin = result.scalars().first()

        if not admin:
            print("❌ Admin não encontrado")
            return

        print(f"✓ Admin: {admin.email}")

        # 3. Create IngestedDocument
        import hashlib
        file_content = doc_path.read_bytes()
        file_hash = hashlib.sha256(file_content).hexdigest()

        from uuid import uuid4
        from datetime import datetime

        doc = IngestedDocument(
            id=uuid4(),
            project_id=project.id,
            filename=doc_path.name,
            original_filename=doc_path.name,
            file_type="docx",
            file_hash=file_hash,
            file_size_bytes=len(file_content),
            uploaded_by=admin.id,
            arguider_status="pending",  # Aguardando processamento
        )
        db.add(doc)
        await db.commit()
        print(f"✓ Documento criado: {doc.id}")

        # 4. Wait for Arguidor to process
        print("\n⏳ Aguardando processamento do Arguidor...")
        max_wait = 120  # 2 minutos max
        wait_interval = 5  # Verificar a cada 5 segundos
        elapsed = 0

        while elapsed < max_wait:
            await db.refresh(doc)

            if doc.arguider_status == "completed":
                print(f"✅ Arguidor completou em {elapsed}s!")
                break
            elif doc.arguider_status == "error":
                print(f"❌ Arguidor falhou: {doc.arguider_error}")
                return
            else:
                print(f"   Status: {doc.arguider_status} ({elapsed}s elapsed...)")
                await asyncio.sleep(wait_interval)
                elapsed += wait_interval

        if elapsed >= max_wait:
            print(f"⏱️  Timeout após {max_wait}s. Arguidor pode estar processando...")
            print(f"   Verifique depois: http://localhost:3000/projects/{project.id}")
            return

        # 5. Get route map and auditor output
        result = await db.execute(
            select(DocumentRouteMap).where(DocumentRouteMap.document_id == doc.id)
        )
        route_map = result.scalars().first()

        if not route_map:
            print("⚠️  RouteMap não criado ainda. Aguardando...")
            await asyncio.sleep(3)
            result = await db.execute(
                select(DocumentRouteMap).where(DocumentRouteMap.document_id == doc.id)
            )
            route_map = result.scalars().first()

        if not route_map:
            print("❌ RouteMap não encontrado")
            return

        print(f"✓ RouteMap criado: {route_map.id}")

        # 6. Check AuditorOutput
        result = await db.execute(
            select(AuditorOutput).where(AuditorOutput.route_map_id == route_map.id)
        )
        auditor = result.scalars().first()

        if not auditor:
            print("⚠️  AuditorOutput não criado ainda...")
            return

        print(f"✓ AuditorOutput criado: {auditor.id}")

        # 7. Print test URLs
        print("\n" + "="*80)
        print("🎉 DOCUMENTO PRONTO PARA TESTAR GATEKEEPER")
        print("="*80)
        print(f"\n📊 Documento: {doc.original_filename}")
        print(f"   ID: {doc.id}")
        print(f"   Chunks: {route_map.total_chunks}")
        print(f"   RouteMap ID: {route_map.id}")

        print(f"\n🔗 Frontend URL (abra no navegador):")
        print(f"   http://localhost:3000/projects/{project.id}/gatekeeper-passada/{route_map.id}")

        print(f"\n📡 API URL (teste com curl):")
        print(f"   curl -X POST http://localhost:8000/api/v1/gatekeeper/passada-1 \\")
        print(f"     -H 'Content-Type: application/json' \\")
        print(f"     -d '{{\"route_map_id\":\"{route_map.id}\", \"execute_now\":true}}'")

        print("\n" + "="*80)


if __name__ == "__main__":
    asyncio.run(upload_and_wait())
