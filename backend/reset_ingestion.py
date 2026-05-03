"""Reset ingestion para um projeto: limpa análises, reseta status, enfileira primeiro doc."""
import asyncio
import sys
from uuid import UUID
from sqlalchemy import select, delete
from app.db.database import AsyncSessionLocal
from app.models.base import IngestedDocument, ArguiderAnalysis
from app.tasks.pipeline import pipeline_ingest_task
import structlog

logger = structlog.get_logger(__name__)

async def reset_project_ingestion(project_id_str: str):
    """Limpa análises, reseta status, enfileira primeiro doc sequencialmente."""
    project_id = UUID(project_id_str)
    
    async with AsyncSessionLocal() as db:
        # 1. Buscar todos os documentos do projeto
        docs_result = await db.execute(
            select(IngestedDocument).where(
                IngestedDocument.project_id == project_id
            ).order_by(IngestedDocument.created_at.asc())
        )
        docs = docs_result.scalars().all()
        
        if not docs:
            print(f"❌ Nenhum documento encontrado no projeto {project_id}")
            return
        
        print(f"📋 Encontrados {len(docs)} documentos")
        
        # 2. Para cada documento, deletar ArguiderAnalysis
        for doc in docs:
            await db.execute(
                delete(ArguiderAnalysis).where(
                    ArguiderAnalysis.document_id == doc.id
                )
            )
            print(f"  ✓ Deletadas análises do doc {doc.original_filename[:40]}")
        
        # 3. Resetar status de todos para pending
        for doc in docs:
            doc.arguider_status = "pending"
            doc.arguider_stage = "queued"
            doc.arguider_progress_percent = 0
            doc.arguider_error_message = None
            doc.arguider_stage_updated_at = None
        
        await db.commit()
        print(f"✓ {len(docs)} documentos resetados para 'pending'")
        
        # 4. Enfileirar apenas o primeiro
        first_doc = docs[0]
        try:
            pipeline_ingest_task.delay(
                str(first_doc.id),
                str(project_id),
                first_doc.file_type or ""
            )
            print(f"\n✅ Enfileirado primeiro documento: {first_doc.original_filename[:40]}")
            print(f"   ID: {first_doc.id}")
            print(f"   Posição: 1/{len(docs)}")
            print(f"\n📊 Fila de processamento sequencial criada com {len(docs)-1} documentos aguardando")
        except Exception as e:
            print(f"❌ Erro ao enfileirar: {e}")
            raise

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python reset_ingestion.py <project_id>")
        sys.exit(1)
    
    project_id = sys.argv[1]
    asyncio.run(reset_project_ingestion(project_id))
