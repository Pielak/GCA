# Ingestion Read-Only Viewer — Plano de Implementação

> **Para workers agênticos:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development ou superpowers:executing-plans. Steps usam checkbox (`- [ ]`).

**Goal:** Permitir abrir qualquer documento ingerido em read-only dentro do GCA, sem depender de origem externa.

**Architecture:** GCA hoje não persiste os bytes dos documentos ingeridos (só hash e texto extraído). Esta entrega adiciona persistência em filesystem (`backend/storage/ingested/<project_id>/<filename>`), um endpoint `GET /ingestion/{doc_id}/content` que serve o arquivo com `Content-Disposition: inline` e o frontend transforma o nome do doc em link. Docs externos existentes são reconstruídos no backfill a partir de `repo_analysis_results`.

**Tech Stack:** FastAPI (StreamingResponse/FileResponse), Python pathlib, React.

---

## File Structure

**Backend — criar:**
- `backend/app/utils/ingested_storage.py` — helper de path + write + read (isolamento)
- `backend/scripts/backfill_external_repo_content.py` — recria bytes de markdowns externos

**Backend — modificar:**
- `backend/app/services/ingestion_service.py:76-100` — gravar bytes no upload_document
- `backend/app/services/repo_analysis_service.py:1494-1526` — gravar bytes no _inject_single_document
- `backend/app/routers/ingestion_router.py` — adicionar endpoint `/content`

**Frontend — modificar:**
- `frontend/src/pages/projects/IngestionPage.tsx:213` — filename vira link clicável

**Compose — modificar:**
- `docker-compose.yml` — volume persistente `./backend/storage:/app/storage`

---

### Task 1: Storage helper + volume

**Files:**
- Create: `backend/app/utils/ingested_storage.py`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Criar helper de storage**

Conteúdo exato de `/home/luiz/GCA/backend/app/utils/ingested_storage.py`:

```python
"""Persistência de documentos ingeridos em filesystem.

Estrutura: <STORAGE_ROOT>/ingested/<project_id>/<filename>
"""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

STORAGE_ROOT = Path("/app/storage")


def ingested_path(project_id: UUID, filename: str) -> Path:
    """Caminho final do documento no filesystem."""
    return STORAGE_ROOT / "ingested" / str(project_id) / filename


def write_ingested(project_id: UUID, filename: str, content: bytes) -> Path:
    """Grava bytes em disco, cria diretório se necessário. Retorna path absoluto."""
    target = ingested_path(project_id, filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


def read_ingested(project_id: UUID, filename: str) -> bytes | None:
    """Lê bytes do disco. Retorna None se arquivo não existe."""
    target = ingested_path(project_id, filename)
    if not target.exists() or not target.is_file():
        return None
    return target.read_bytes()


def ingested_exists(project_id: UUID, filename: str) -> bool:
    return ingested_path(project_id, filename).is_file()
```

- [ ] **Step 2: Adicionar volume ao docker-compose**

Em `/home/luiz/GCA/docker-compose.yml`, no serviço `backend`, adicionar ao array `volumes:` a linha:

```yaml
      - ./backend/storage:/app/storage
```

Se o serviço backend já tiver `volumes:`, anexar; senão adicionar a chave.

- [ ] **Step 3: Criar diretório host + restart**

```bash
mkdir -p /home/luiz/GCA/backend/storage/ingested
cd /home/luiz/GCA && docker compose up -d backend
until docker compose logs backend --tail 10 2>&1 | grep -q "Application startup complete"; do sleep 2; done
docker compose exec -T backend ls -la /app/storage/ingested
```

Esperado: `ls` mostra o diretório criado.

- [ ] **Step 4: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/utils/ingested_storage.py docker-compose.yml
git commit -m "feat(ingestion): helper de storage + volume persistente para docs ingeridos

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Persistir bytes em upload_document + _inject_single_document + endpoint /content

**Files:**
- Modify: `backend/app/services/ingestion_service.py`
- Modify: `backend/app/services/repo_analysis_service.py`
- Modify: `backend/app/routers/ingestion_router.py`

- [ ] **Step 1: ingestion_service grava bytes no upload**

Em `/home/luiz/GCA/backend/app/services/ingestion_service.py`, localize o bloco após `filename = f"{uuid4()}.{ext}"` (linha ~78) e ANTES de `pii_detected, pii_fields = self._detect_pii(...)`, adicione:

```python
        # Persistir bytes em storage para abertura read-only posterior
        from app.utils.ingested_storage import write_ingested
        write_ingested(project_id, filename, file_bytes)
```

- [ ] **Step 2: repo_analysis_service grava bytes de markdowns externos**

Em `/home/luiz/GCA/backend/app/services/repo_analysis_service.py`, no método `_inject_single_document`, localize a linha `doc = IngestedDocument(` (aprox. linha 1508). Logo ANTES dela (mas depois do `file_hash` e do check de duplicata), adicione:

```python
        # Persistir markdown em storage para abertura read-only
        from app.utils.ingested_storage import write_ingested
        generated_filename = f"{uuid4()}.md"
        write_ingested(project_id, generated_filename, file_bytes)
```

E altere o valor de `filename=` dentro da construção do `IngestedDocument` de `f"{uuid4()}.md"` para `generated_filename` (referência à variável acabada de criar). Idem para `git_file_path`, que deve usar `generated_filename`.

O bloco final deve ficar assim:

```python
        doc = IngestedDocument(
            project_id=project_id,
            filename=generated_filename,
            original_filename=filename,
            file_type="markdown",
            file_hash=file_hash,
            file_size_bytes=len(file_bytes),
            uploaded_by=uploaded_by,
            quarantine_status="none",
            pii_detected=False,
            arguider_status="pending",
            git_file_path=f"docs/ingested/external/{generated_filename}",
            source_type="external_repo",
            source_url=repo_url,
            source_repo_id=repo_id,
        )
```

- [ ] **Step 3: Endpoint /content no ingestion_router**

Em `/home/luiz/GCA/backend/app/routers/ingestion_router.py`, adicione ao final do arquivo:

```python
@router.get("/projects/{project_id}/ingestion/{document_id}/content")
async def get_document_content(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Serve o conteúdo original do documento (read-only, inline)."""
    from fastapi.responses import Response
    from app.models.base import IngestedDocument
    from app.utils.ingested_storage import read_ingested

    doc = await db.get(IngestedDocument, document_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    content = read_ingested(project_id, doc.filename)
    if content is None:
        raise HTTPException(
            status_code=404,
            detail="Conteúdo não disponível. Documento foi ingerido antes da persistência — requer re-ingestão.",
        )

    mime_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "markdown": "text/markdown; charset=utf-8",
        "image": "image/png",
        "spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "code": "text/plain; charset=utf-8",
    }
    content_type = mime_map.get(doc.file_type, "application/octet-stream")

    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="{doc.original_filename}"',
            "Cache-Control": "private, max-age=60",
        },
    )
```

- [ ] **Step 4: Restart + smoke test**

```bash
cd /home/luiz/GCA && docker compose restart backend
until docker compose logs backend --tail 10 2>&1 | grep -q "Application startup complete"; do sleep 2; done
docker compose logs backend --tail 30 2>&1 | grep -iE "error|traceback" | head -5 || echo "SEM ERROS"
```

Esperado: "SEM ERROS".

- [ ] **Step 5: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/services/ingestion_service.py backend/app/services/repo_analysis_service.py backend/app/routers/ingestion_router.py
git commit -m "feat(ingestion): persistir bytes de uploads e markdowns externos; endpoint /content read-only

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Frontend — filename clicável

**Files:**
- Modify: `frontend/src/pages/projects/IngestionPage.tsx`

- [ ] **Step 1: Transformar o filename em link**

Localize o `<span className="text-slate-200 text-sm font-medium truncate">{doc.original_filename}</span>` (linha ~213). Substitua por:

```tsx
                    <a
                      href={`/api/v1/projects/${projectId}/ingestion/${doc.id}/content`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-slate-200 text-sm font-medium truncate hover:text-violet-300 hover:underline"
                      title="Abrir documento (read-only)"
                    >
                      {doc.original_filename}
                    </a>
```

- [ ] **Step 2: Rebuild frontend**

```bash
cd /home/luiz/GCA && docker compose restart frontend
until docker compose logs frontend --tail 5 2>&1 | grep -q "Local:  "; do sleep 3; done
echo "READY"
```

- [ ] **Step 3: Commit**

```bash
cd /home/luiz/GCA && git add frontend/src/pages/projects/IngestionPage.tsx
git commit -m "feat(ingestion): nome do documento vira link read-only para viewer no GCA

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Backfill de markdowns externos

**Files:**
- Create: `backend/scripts/backfill_external_repo_content.py`

- [ ] **Step 1: Criar script de backfill**

Conteúdo exato de `/home/luiz/GCA/backend/scripts/backfill_external_repo_content.py`:

```python
"""Backfill: reconstrói markdown de docs externos existentes que não têm bytes persistidos.

Estratégia: para cada IngestedDocument com source_type='external_repo' cujo arquivo
físico não existe, regenera a partir de RepoAnalysisResult + categoria inferida do
original_filename (padrão external_<repo>_<category>.md).
"""
import asyncio
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
    import json
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
                    select(RepoAnalysisResult).where(
                        RepoAnalysisResult.repo_id == doc.source_repo_id,
                        RepoAnalysisResult.category == category,
                    )
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
```

- [ ] **Step 2: Rodar o backfill**

```bash
cd /home/luiz/GCA && docker compose exec -T backend python scripts/backfill_external_repo_content.py
```

Esperado: linhas `OK ...` para cada doc externo existente que teve markdown reconstruído, seguido de sumário com contagens.

- [ ] **Step 3: Validar end-to-end**

No browser, acessar a Ingestão de um projeto que tem docs externos. Clicar no nome de um — deve abrir o markdown formatado em nova aba.

- [ ] **Step 4: Commit**

```bash
cd /home/luiz/GCA && git add backend/scripts/backfill_external_repo_content.py
git commit -m "chore(ingestion): script de backfill de markdowns externos a partir de RepoAnalysisResult

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- ✅ Abrir read-only no GCA → Task 3 (link) + Task 2 (endpoint)
- ✅ Persistência ao fazer upload → Task 2 (ingestion_service grava bytes)
- ✅ Persistência em docs externos → Task 2 (repo_analysis_service grava bytes)
- ✅ Docs externos existentes ficam acessíveis → Task 4 (backfill)

**Placeholder scan:** nenhum placeholder. Todos os códigos completos.

**Type consistency:**
- `write_ingested/read_ingested` assinatura `(project_id: UUID, filename: str, ...)` consistente em todos os sites.
- `doc.filename` é o nome gerado (UUID), `doc.original_filename` o nome humano — respeitado em todos os pontos.

---

## Execution Handoff

Plano salvo. Executando subagent-driven (com fallback inline se houver rate-limit).
