"""Inventário de docs ingeridos sem bytes em disco.

Para cada IngestedDocument cujo arquivo físico não existe, decide:

- **available** (mantém): bytes existem em disco, OU é recuperável via
  backfill_external_repo_content (ou seja, source_type='external_repo' +
  filename casa com `external_<repo>_<category>.md` + RepoAnalysisResult
  existe para a categoria).
- **lost** (marca soft-deleted): bytes não estão em disco e não há fonte
  para regenerar. Tipicamente uploads antigos (anteriores à persistência).

Endpoint /api/v1/projects/<pid>/ingestion/<doc>/content passa a retornar
410 Gone para docs marcados como lost — UI para de tentar abrir órfãos.

Idempotente: rodar múltiplas vezes é seguro. Docs que voltarem a ter
bytes (ex: backfill posterior) podem ter content_status retornado a
'available' por update manual ou re-rodando este script (que não promove
de 'lost' → 'available' automaticamente, por segurança — promoção é
sempre manual).
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, update

from app.db.database import AsyncSessionLocal
from app.models.base import IngestedDocument, RepoAnalysisResult
from app.utils.ingested_storage import ingested_exists


def _infer_category(original_filename: str) -> str | None:
    """Mesma regex do backfill — extrai <category> de external_<repo>_<category>.md."""
    m = re.match(r"external_[^_]+_(.+)\.md$", original_filename)
    return m.group(1) if m else None


async def _is_recoverable_from_repo(db, doc: IngestedDocument) -> bool:
    """True se backfill_external_repo_content consegue regenerar o markdown.

    Critério: source_type='external_repo' + categoria inferível do filename
    + RepoAnalysisResult existe para (source_repo_id, category).
    """
    if doc.source_type != "external_repo" or not doc.source_repo_id:
        return False
    category = _infer_category(doc.original_filename)
    if not category:
        return False
    result = (
        await db.execute(
            select(RepoAnalysisResult).where(
                RepoAnalysisResult.repo_id == doc.source_repo_id,
                RepoAnalysisResult.category == category,
            )
        )
    ).scalar_one_or_none()
    return result is not None


async def inventory():
    async with AsyncSessionLocal() as db:
        docs = (await db.execute(select(IngestedDocument))).scalars().all()

        on_disk = 0
        recoverable = 0
        marked_lost = 0
        already_lost = 0

        lost_ids = []
        for doc in docs:
            if ingested_exists(doc.project_id, doc.filename):
                on_disk += 1
                continue

            if doc.content_status == "lost":
                already_lost += 1
                continue

            if await _is_recoverable_from_repo(db, doc):
                recoverable += 1
                print(f"REC  {doc.original_filename} (recuperável via backfill)")
                continue

            lost_ids.append(doc.id)
            marked_lost += 1
            print(
                f"LOST {doc.original_filename} (source={doc.source_type}, project={doc.project_id})"
            )

        if lost_ids:
            await db.execute(
                update(IngestedDocument)
                .where(IngestedDocument.id.in_(lost_ids))
                .values(content_status="lost")
            )
            await db.commit()

        print(
            f"\nTotal: {len(docs)} | "
            f"em disco: {on_disk} | "
            f"recuperáveis: {recoverable} | "
            f"marcados como lost agora: {marked_lost} | "
            f"já estavam lost: {already_lost}"
        )


if __name__ == "__main__":
    asyncio.run(inventory())
