"""Backfill: reconstrói markdown de docs externos existentes que não têm bytes persistidos.

Estratégia: para cada IngestedDocument com source_type='external_repo' cujo arquivo
físico não existe, regenera a partir de RepoAnalysisResult + categoria inferida do
original_filename (padrão external_<repo>_<category>.md).
"""
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.database import AsyncSessionLocal
from app.models.base import IngestedDocument, RepoAnalysisResult
from app.utils.ingested_storage import ingested_exists, write_ingested


def _infer_category(original_filename: str) -> str | None:
    m = re.match(r"external_[^_]+_(.+)\.md$", original_filename)
    return m.group(1) if m else None


def _build_markdown(category: str, summary: str, metrics: dict | None) -> str:
    lines = [
        f"# {category.replace('_', ' ').title()}",
        "",
        "## Resumo",
        "",
        summary or "_Sem resumo disponível._",
        "",
    ]
    if metrics:
        lines += ["## Métricas", ""]
        for k, v in metrics.items():
            lines.append(f"- **{k}**: {v}")
        lines.append("")
    return "\n".join(lines)


async def backfill():
    async with AsyncSessionLocal() as db:
        docs = (
            await db.execute(
                select(IngestedDocument).where(
                    IngestedDocument.source_type == "external_repo"
                )
            )
        ).scalars().all()

        restored = 0
        skipped = 0
        missing = 0

        for doc in docs:
            if ingested_exists(doc.project_id, doc.filename):
                skipped += 1
                continue

            category = _infer_category(doc.original_filename)
            if not category:
                missing += 1
                print(f"SKIP categoria não inferida: {doc.original_filename}")
                continue

            result = (
                await db.execute(
                    select(RepoAnalysisResult)
                    .where(
                        RepoAnalysisResult.repo_id == doc.source_repo_id,
                        RepoAnalysisResult.category == category,
                    )
                    .order_by(RepoAnalysisResult.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            if not result:
                missing += 1
                print(f"SKIP sem result para {doc.original_filename} (category={category})")
                continue

            metrics = None
            if result.metrics:
                try:
                    metrics = json.loads(result.metrics)
                except json.JSONDecodeError:
                    metrics = None

            content = _build_markdown(category, result.summary or "", metrics)
            write_ingested(doc.project_id, doc.filename, content.encode("utf-8"))
            restored += 1
            print(f"OK  {doc.original_filename}")

        print(f"\nRestaurados: {restored} | Já existiam: {skipped} | Sem dado: {missing}")


if __name__ == "__main__":
    asyncio.run(backfill())
