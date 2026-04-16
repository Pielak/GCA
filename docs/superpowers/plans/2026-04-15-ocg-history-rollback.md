# OCG History + Rollback — Plano de Implementação

> **Para workers agênticos:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para executar este plano tarefa-a-tarefa. Steps usam checkbox (`- [ ]`).

**Goal:** Fechar o requisito de auditoria do OCG — registrar toda mudança com autor e trigger, permitir reverter para versão anterior.

**Architecture:** O `ocg_delta_log` já existe mas tem duas limitações: `document_id NOT NULL` (bloqueia updates não-ingesção) e não guarda autor nem snapshot para rollback. Migração amplia a tabela (changed_by, trigger_source, ocg_snapshot, document_id nullable), service universaliza o write-path, endpoint novo de rollback cria nova versão a partir de snapshot (sem destruir histórico), frontend mostra autor + trigger + botão reverter.

**Tech Stack:** PostgreSQL 16 + SQLAlchemy 2 async, FastAPI, React 18 + Vite.

---

## File Structure

**Backend — criar:**
- `backend/migrations/011_ocg_history_audit.sql` — migração (ALTER TABLE ocg_delta_log)

**Backend — modificar:**
- `backend/app/models/base.py:993-1008` — OCGDeltaLog: document_id nullable + novas colunas
- `backend/app/services/ocg_updater_service.py:396-445` — `_log_delta` sempre grava, novos parâmetros
- `backend/app/services/ocg_updater_service.py:51-170` — `update_ocg_from_arguider` aceita `trigger_source`, propaga para `_log_delta`, captura `ocg_snapshot` pós-update
- `backend/app/services/ingestion_service.py:271` — passa `actor_id` e `trigger_source='document_ingestion'`
- `backend/app/routers/projects.py:535-563` — endpoint `/ocg/history` retorna autor, trigger, id; adicionar endpoint `POST /ocg/rollback/{version_to}` e `GET /ocg/snapshot/{version_to}`

**Frontend — modificar:**
- `frontend/src/pages/projects/OCGPage.tsx:305-331` — linha do histórico mostra autor + trigger + botão "↶ Reverter"

**Testes — criar:**
- `backend/app/tests/test_ocg_history_rollback.py` — 4 testes: log universal, autor, rollback, snapshot preserva histórico

---

### Task 1: Migração do schema

**Files:**
- Create: `backend/migrations/011_ocg_history_audit.sql`

- [ ] **Step 1: Criar a migração SQL**

Conteúdo exato do arquivo `backend/migrations/011_ocg_history_audit.sql`:

```sql
-- 011 — OCG Delta Log: autor, trigger, snapshot, document_id nullable
BEGIN;

-- Torna document_id opcional (updates sem doc passam a ser logados)
ALTER TABLE ocg_delta_log ALTER COLUMN document_id DROP NOT NULL;

-- Autor da mudança (NULL = update automático/sistema)
ALTER TABLE ocg_delta_log
  ADD COLUMN IF NOT EXISTS changed_by UUID REFERENCES users(id) ON DELETE SET NULL;

-- Origem da mudança: document_ingestion | manual_edit | pillar_agent | propagation | rollback | system
ALTER TABLE ocg_delta_log
  ADD COLUMN IF NOT EXISTS trigger_source VARCHAR(50) NOT NULL DEFAULT 'document_ingestion';

-- Snapshot pós-mudança do OCG completo, usado para rollback
ALTER TABLE ocg_delta_log
  ADD COLUMN IF NOT EXISTS ocg_snapshot TEXT;

CREATE INDEX IF NOT EXISTS idx_ocg_delta_trigger ON ocg_delta_log(project_id, trigger_source);
CREATE INDEX IF NOT EXISTS idx_ocg_delta_version ON ocg_delta_log(project_id, ocg_version_to);

COMMIT;
```

- [ ] **Step 2: Aplicar migração e validar schema**

```bash
docker compose exec -T postgres psql -U gca -d gca -f - < /home/luiz/GCA/backend/migrations/011_ocg_history_audit.sql
docker compose exec -T postgres psql -U gca -d gca -c "\d ocg_delta_log"
```

Esperado: `document_id` com `Nullable=yes`, colunas `changed_by`, `trigger_source`, `ocg_snapshot` presentes, 2 novos indexes.

- [ ] **Step 3: Commit**

```bash
git add backend/migrations/011_ocg_history_audit.sql
git commit -m "feat(ocg): migração 011 — histórico com autor, trigger e snapshot para rollback"
```

---

### Task 2: Model OCGDeltaLog

**Files:**
- Modify: `backend/app/models/base.py:993-1008`

- [ ] **Step 1: Atualizar a classe OCGDeltaLog**

Substituir o bloco `class OCGDeltaLog(Base):` (linhas 993-1008) por:

```python
class OCGDeltaLog(Base):
    """Histórico de mudanças no OCG — auditoria + rollback"""
    __tablename__ = "ocg_delta_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("ingested_documents.id"), nullable=True)
    ocg_version_from = Column(Integer, nullable=False)
    ocg_version_to = Column(Integer, nullable=False)
    fields_changed = Column(Text, nullable=False, default="{}")  # JSON {field: {old, new, reasoning}}
    change_summary = Column(Text, nullable=True)
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    trigger_source = Column(String(50), nullable=False, default="document_ingestion")
    ocg_snapshot = Column(Text, nullable=True)  # JSON completo do OCG na versão_to — fonte do rollback
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_ocg_delta_project", project_id),
        Index("idx_ocg_delta_trigger", project_id, trigger_source),
        Index("idx_ocg_delta_version", project_id, ocg_version_to),
    )
```

- [ ] **Step 2: Restart backend e validar import**

```bash
docker compose restart backend
until docker compose logs backend --tail 10 2>&1 | grep -q "Application startup complete"; do sleep 2; done
docker compose logs backend --tail 5 2>&1 | grep -iE "error|traceback" || echo "OK sem erros"
```

Esperado: `OK sem erros`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/base.py
git commit -m "feat(ocg): modelo OCGDeltaLog ganha changed_by, trigger_source, ocg_snapshot"
```

---

### Task 3: Service — log universal (sempre grava)

**Files:**
- Modify: `backend/app/services/ocg_updater_service.py:51-170, 396-445`

- [ ] **Step 1: Atualizar assinatura de `update_ocg_from_arguider` e propagar**

Em `backend/app/services/ocg_updater_service.py`, localizar a definição `async def update_ocg_from_arguider(` (linha 51) e adicionar parâmetro `trigger_source`:

```python
    async def update_ocg_from_arguider(
        self,
        project_id: UUID,
        arguider_analysis: Dict[str, Any],
        document_id: Optional[UUID] = None,
        actor_id: Optional[UUID] = None,
        trigger_source: str = "document_ingestion",
    ) -> Optional[Dict[str, Any]]:
```

Na chamada de `_log_delta` (aproximadamente linha 118), passar:

```python
        await self._log_delta(
            project_id=project_id,
            document_id=document_id,
            ocg_version_from=version_from,
            ocg_version_to=version_to,
            changes=changes,
            changed_by=actor_id,
            trigger_source=trigger_source,
            ocg_snapshot=updated_ocg,
        )
```

- [ ] **Step 2: Reescrever `_log_delta` para sempre gravar + snapshot**

Substituir o método `_log_delta` (linhas 396-445) por:

```python
    async def _log_delta(
        self,
        project_id: UUID,
        document_id: Optional[UUID],
        ocg_version_from: int,
        ocg_version_to: int,
        changes: List[Dict[str, Any]],
        changed_by: Optional[UUID] = None,
        trigger_source: str = "document_ingestion",
        ocg_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Registra delta sempre — document_id opcional (updates não-ingesção também contam)."""
        fields_changed: Dict[str, Any] = {}
        for change in changes:
            field = change.get("field", "unknown")
            fields_changed[field] = {
                "old": change.get("old_value"),
                "new": change.get("new_value"),
                "reasoning": change.get("reasoning", ""),
            }

        summary_parts = [
            f"{c.get('field', '?')}: {c.get('reasoning', '')}"
            for c in changes[:5]
        ]
        change_summary = "; ".join(summary_parts) if summary_parts else f"Mudança via {trigger_source}"

        delta_entry = OCGDeltaLog(
            project_id=project_id,
            document_id=document_id,
            ocg_version_from=ocg_version_from,
            ocg_version_to=ocg_version_to,
            fields_changed=json.dumps(fields_changed, ensure_ascii=False),
            change_summary=change_summary,
            changed_by=changed_by,
            trigger_source=trigger_source,
            ocg_snapshot=json.dumps(ocg_snapshot, ensure_ascii=False) if ocg_snapshot else None,
        )
        self.db.add(delta_entry)
        await self.db.flush()
```

- [ ] **Step 3: Atualizar caller em ingestion_service**

Em `backend/app/services/ingestion_service.py:271`, substituir:

```python
                        update_result = await updater.update_ocg_from_arguider(project_id, analysis_data)
```

por:

```python
                        update_result = await updater.update_ocg_from_arguider(
                            project_id=project_id,
                            arguider_analysis=analysis_data,
                            document_id=document_id,
                            actor_id=doc.uploaded_by if doc else None,
                            trigger_source="document_ingestion",
                        )
```

Nota: `doc` já foi carregado no mesmo escopo (linha 222 — `doc = await db.get(IngestedDocument, document_id)`).

- [ ] **Step 4: Restart backend e validar ausência de erros**

```bash
docker compose restart backend
until docker compose logs backend --tail 10 2>&1 | grep -q "Application startup complete"; do sleep 2; done
docker compose logs backend --tail 20 2>&1 | grep -iE "error|traceback" || echo "OK"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ocg_updater_service.py backend/app/services/ingestion_service.py
git commit -m "feat(ocg): log universal do delta — sempre grava, com autor, trigger e snapshot"
```

---

### Task 4: Endpoints — history enriquecido + rollback

**Files:**
- Modify: `backend/app/routers/projects.py:535-563`

- [ ] **Step 1: Substituir o endpoint de history e adicionar rollback + snapshot**

Localizar `@router.get("/{project_id}/ocg/history")` (linha 535). Substituir o bloco do endpoint (linhas 535-563) pelo seguinte, que expande o retorno e adiciona dois endpoints novos logo depois:

```python
@router.get("/{project_id}/ocg/history")
async def get_ocg_history(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Histórico de versões do OCG com autor, trigger e flag de rollback disponível."""
    from sqlalchemy import select
    from app.models.base import OCGDeltaLog, User, OCG

    result = await db.execute(
        select(OCGDeltaLog, User)
        .outerjoin(User, OCGDeltaLog.changed_by == User.id)
        .where(OCGDeltaLog.project_id == project_id)
        .order_by(OCGDeltaLog.created_at.desc())
        .limit(50)
    )
    rows = result.all()

    # Versão atual para marcar qual linha permite rollback (todas exceto a atual com snapshot)
    current_ocg = await db.execute(
        select(OCG).where(OCG.project_id == project_id).order_by(OCG.created_at.desc()).limit(1)
    )
    current = current_ocg.scalar_one_or_none()
    current_version = current.version if current else 0

    return {
        "current_version": current_version,
        "history": [
            {
                "id": str(d.id),
                "version_from": d.ocg_version_from,
                "version_to": d.ocg_version_to,
                "change_summary": d.change_summary,
                "fields_changed": d.fields_changed,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "changed_by": {
                    "id": str(u.id),
                    "full_name": u.full_name or u.email.split("@")[0],
                    "email": u.email,
                } if u else None,
                "trigger_source": d.trigger_source,
                "can_rollback": d.ocg_snapshot is not None and d.ocg_version_to != current_version,
            }
            for d, u in rows
        ],
    }


@router.get("/{project_id}/ocg/snapshot/{version_to}")
async def get_ocg_snapshot(
    project_id: UUID,
    version_to: int,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna o snapshot completo do OCG na versão indicada."""
    from sqlalchemy import select
    from app.models.base import OCGDeltaLog

    result = await db.execute(
        select(OCGDeltaLog)
        .where(OCGDeltaLog.project_id == project_id, OCGDeltaLog.ocg_version_to == version_to)
        .order_by(OCGDeltaLog.created_at.desc())
        .limit(1)
    )
    delta = result.scalar_one_or_none()
    if not delta or not delta.ocg_snapshot:
        raise HTTPException(status_code=404, detail="Snapshot não disponível para essa versão")
    import json as _json
    return {"version": version_to, "snapshot": _json.loads(delta.ocg_snapshot)}


@router.post("/{project_id}/ocg/rollback/{version_to}")
async def rollback_ocg(
    project_id: UUID,
    version_to: int,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    """Reverte OCG para snapshot de versão anterior. Cria nova versão com trigger_source='rollback'."""
    from sqlalchemy import select
    from app.models.base import OCGDeltaLog, OCG
    import json as _json
    from datetime import datetime, timezone

    current_user_id = permissions["user_id"]

    # Buscar snapshot
    snap_result = await db.execute(
        select(OCGDeltaLog)
        .where(OCGDeltaLog.project_id == project_id, OCGDeltaLog.ocg_version_to == version_to)
        .order_by(OCGDeltaLog.created_at.desc())
        .limit(1)
    )
    delta = snap_result.scalar_one_or_none()
    if not delta or not delta.ocg_snapshot:
        raise HTTPException(status_code=404, detail="Snapshot não disponível para rollback")

    snapshot = _json.loads(delta.ocg_snapshot)

    # OCG atual
    ocg_result = await db.execute(
        select(OCG).where(OCG.project_id == project_id).order_by(OCG.created_at.desc()).limit(1)
    )
    ocg = ocg_result.scalar_one_or_none()
    if not ocg:
        raise HTTPException(status_code=404, detail="OCG do projeto não encontrado")

    version_from = ocg.version
    new_version = version_from + 1

    ocg.ocg_data = _json.dumps(snapshot, ensure_ascii=False)
    ocg.version = new_version
    ocg.updated_at = datetime.now(timezone.utc)
    db.add(ocg)

    # Gravar delta de rollback (snapshot mantém histórico)
    rollback_delta = OCGDeltaLog(
        project_id=project_id,
        document_id=None,
        ocg_version_from=version_from,
        ocg_version_to=new_version,
        fields_changed=_json.dumps({"__rollback__": {"restored_from_version": version_to}}, ensure_ascii=False),
        change_summary=f"Rollback para versão {version_to}",
        changed_by=current_user_id,
        trigger_source="rollback",
        ocg_snapshot=_json.dumps(snapshot, ensure_ascii=False),
    )
    db.add(rollback_delta)
    await db.commit()

    return {
        "success": True,
        "previous_version": version_from,
        "new_version": new_version,
        "restored_from": version_to,
    }
```

- [ ] **Step 2: Validar import de `HTTPException` e `require_action`**

```bash
grep -nE "from fastapi import|require_action" /home/luiz/GCA/backend/app/routers/projects.py | head -5
```

Esperado: `HTTPException` e `require_action` já importados no topo do arquivo. Se faltar, adicionar ao import existente.

- [ ] **Step 3: Restart e smoke test dos endpoints**

```bash
docker compose restart backend
until docker compose logs backend --tail 10 2>&1 | grep -q "Application startup complete"; do sleep 2; done

# Pegar token (ajustar email se necessário)
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"pielak.ctba@gmail.com","password":"Topazio01#"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')

# Escolher um project_id válido
PROJECT_ID=$(docker compose exec -T postgres psql -U gca -d gca -tA -c "SELECT id FROM projects LIMIT 1;")

# History deve retornar 200 com current_version e array history
curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/v1/projects/$PROJECT_ID/ocg/history" | python3 -m json.tool | head -30
```

Esperado: JSON com chave `current_version` (int) e `history` (array, pode ser vazio).

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/projects.py
git commit -m "feat(ocg): endpoints /ocg/history enriquecido, /snapshot/{v} e /rollback/{v}"
```

---

### Task 5: Testes de integração

**Files:**
- Create: `backend/app/tests/test_ocg_history_rollback.py`

- [ ] **Step 1: Escrever testes de falha primeiro**

Criar arquivo `backend/app/tests/test_ocg_history_rollback.py`:

```python
"""Testes do histórico do OCG + rollback."""
import json
import pytest
from uuid import uuid4
from sqlalchemy import select

from app.models.base import OCG, OCGDeltaLog, Project, User
from app.services.ocg_updater_service import OCGUpdaterService


@pytest.mark.asyncio
async def test_log_delta_without_document_id_is_persisted(db_session, test_project, test_user):
    """Delta sem document_id ainda assim é gravado (regressão do early-return antigo)."""
    updater = OCGUpdaterService(db_session)
    await updater._log_delta(
        project_id=test_project.id,
        document_id=None,
        ocg_version_from=1,
        ocg_version_to=2,
        changes=[{"field": "STACK", "old_value": "a", "new_value": "b", "reasoning": "update"}],
        changed_by=test_user.id,
        trigger_source="manual_edit",
        ocg_snapshot={"STACK": "b"},
    )
    await db_session.flush()

    result = await db_session.execute(
        select(OCGDeltaLog).where(OCGDeltaLog.project_id == test_project.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].document_id is None
    assert rows[0].trigger_source == "manual_edit"
    assert rows[0].changed_by == test_user.id
    assert rows[0].ocg_snapshot is not None


@pytest.mark.asyncio
async def test_log_delta_preserves_snapshot_json(db_session, test_project):
    """Snapshot é persistido como JSON válido para permitir rollback."""
    updater = OCGUpdaterService(db_session)
    snap = {"PILLAR_SCORES": {"P1": 85}, "COMPOSITE_SCORE": 82}
    await updater._log_delta(
        project_id=test_project.id,
        document_id=None,
        ocg_version_from=1,
        ocg_version_to=2,
        changes=[],
        trigger_source="pillar_agent",
        ocg_snapshot=snap,
    )
    await db_session.flush()

    result = await db_session.execute(
        select(OCGDeltaLog).where(OCGDeltaLog.project_id == test_project.id)
    )
    row = result.scalar_one()
    assert json.loads(row.ocg_snapshot) == snap


@pytest.mark.asyncio
async def test_rollback_endpoint_creates_new_version(async_client, auth_headers, test_project, db_session):
    """Rollback não destrói histórico — cria nova versão com trigger_source='rollback'."""
    # Preparar: OCG em v2 com snapshot v1 disponível
    ocg = OCG(project_id=test_project.id, version=2, ocg_data=json.dumps({"STACK": "v2"}))
    db_session.add(ocg)
    await db_session.flush()
    db_session.add(OCGDeltaLog(
        project_id=test_project.id,
        ocg_version_from=0,
        ocg_version_to=1,
        fields_changed="{}",
        trigger_source="document_ingestion",
        ocg_snapshot=json.dumps({"STACK": "v1"}),
    ))
    await db_session.commit()

    resp = await async_client.post(
        f"/api/v1/projects/{test_project.id}/ocg/rollback/1",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["new_version"] == 3
    assert body["restored_from"] == 1

    # OCG atual deve ter o snapshot de v1
    await db_session.refresh(ocg)
    assert json.loads(ocg.ocg_data) == {"STACK": "v1"}
    assert ocg.version == 3

    # Delta de rollback foi registrado
    r = await db_session.execute(
        select(OCGDeltaLog).where(
            OCGDeltaLog.project_id == test_project.id,
            OCGDeltaLog.trigger_source == "rollback",
        )
    )
    rollback_entry = r.scalar_one()
    assert rollback_entry.ocg_version_to == 3


@pytest.mark.asyncio
async def test_rollback_404_when_no_snapshot(async_client, auth_headers, test_project):
    """Rollback para versão sem snapshot retorna 404."""
    resp = await async_client.post(
        f"/api/v1/projects/{test_project.id}/ocg/rollback/999",
        headers=auth_headers,
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Rodar os testes**

```bash
docker compose exec -T backend python -m pytest app/tests/test_ocg_history_rollback.py -v 2>&1 | tail -30
```

Esperado: 4 testes passando. Se fixtures `test_project`, `test_user`, `async_client`, `auth_headers`, `db_session` já existirem em `conftest.py`, os testes rodam. Se faltarem, o pytest mostrará o nome da fixture ausente — inspecionar `app/tests/conftest.py` e ajustar nomes.

- [ ] **Step 3: Commit**

```bash
git add backend/app/tests/test_ocg_history_rollback.py
git commit -m "test(ocg): cobertura de log universal + rollback + snapshot"
```

---

### Task 6: Frontend — autor, trigger e botão de rollback

**Files:**
- Modify: `frontend/src/pages/projects/OCGPage.tsx:305-331`

- [ ] **Step 1: Atualizar o carregamento de history para incluir current_version**

Localizar a função que carrega history (aproximadamente linha 206):

```typescript
      const histRes = await apiClient.get(`/projects/${id}/ocg/history`)
      setHistory(histRes.data?.history || [])
```

Substituir por:

```typescript
      const histRes = await apiClient.get(`/projects/${id}/ocg/history`)
      setHistory(histRes.data?.history || [])
      setCurrentVersion(histRes.data?.current_version || 0)
```

E adicionar o state logo após o `useState` existente para `history` (linha 167):

```typescript
  const [currentVersion, setCurrentVersion] = useState<number>(0)
```

- [ ] **Step 2: Substituir o render do case 'history'**

Localizar `case 'history':` (linha 305) e substituir o bloco inteiro (linhas 305-331) por:

```tsx
      case 'history':
        return history.length > 0 ? (
          <div className="space-y-3">
            {history.map((h: any) => (
              <div key={h.id} className="flex items-start gap-3 p-3 rounded-lg bg-slate-800/40">
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-violet-900/40 border border-violet-800/40 flex items-center justify-center">
                  <span className="text-violet-400 text-xs font-bold">v{h.version_to}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-slate-200 text-sm font-medium">
                      Versão {h.version_from} → {h.version_to}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700/50 text-slate-400 uppercase tracking-wide">
                      {h.trigger_source || 'system'}
                    </span>
                    {h.changed_by && (
                      <span className="text-slate-400 text-xs">
                        por <span className="text-slate-300">{h.changed_by.full_name}</span>
                      </span>
                    )}
                    <span className="text-slate-500 text-xs">
                      {h.created_at ? new Date(h.created_at).toLocaleString('pt-BR') : ''}
                    </span>
                  </div>
                  {h.change_summary && <p className="text-slate-400 text-xs mt-1">{h.change_summary}</p>}
                  {h.fields_changed && (
                    <details className="mt-1">
                      <summary className="text-slate-500 text-xs cursor-pointer hover:text-slate-300">
                        Ver campos alterados
                      </summary>
                      <pre className="text-slate-500 text-xs mt-1 bg-slate-900/50 rounded p-2 overflow-x-auto max-h-24">
                        {typeof h.fields_changed === 'string' ? h.fields_changed : JSON.stringify(h.fields_changed, null, 2)}
                      </pre>
                    </details>
                  )}
                  {h.can_rollback && (
                    <button
                      onClick={async () => {
                        if (!confirm(`Reverter o OCG para a versão ${h.version_to}? Isso cria uma nova versão e mantém o histórico.`)) return
                        try {
                          await apiClient.post(`/projects/${id}/ocg/rollback/${h.version_to}`)
                          await loadData()
                        } catch (e: any) {
                          alert(e?.response?.data?.detail || 'Erro ao reverter')
                        }
                      }}
                      className="mt-2 text-xs px-2 py-1 rounded bg-amber-600/20 border border-amber-600/30 text-amber-300 hover:bg-amber-600/30 transition-colors"
                    >
                      ↶ Reverter para esta versão
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-slate-500 text-sm italic">
            Nenhuma alteração registrada. O histórico se preenche automaticamente a cada mudança do OCG (ingestão, agente, edição ou propagação).
          </p>
        )
```

- [ ] **Step 3: Verificar nome da função de recarga**

Confirmar que `loadData` é a função que recarrega OCG + history no OCGPage (aproximadamente linha 185). Se o nome for diferente no arquivo, substituir `loadData()` no handler de rollback pelo nome correto.

```bash
grep -n "const loadData\|async function loadData\|const fetchOCG\|const loadOCG" /home/luiz/GCA/frontend/src/pages/projects/OCGPage.tsx
```

Esperado: função existente identificada. Ajustar `loadData()` no step 2 se necessário.

- [ ] **Step 4: Rebuild frontend e validar**

```bash
docker compose restart frontend
until docker compose logs frontend --tail 5 2>&1 | grep -q "Local:  "; do sleep 3; done
echo "READY"
```

Validação manual:
1. Abrir projeto qualquer no navegador (Ctrl+Shift+R)
2. Ir em **OCG → Histórico de Versões**
3. Rodar uma ingestão de documento — nova linha deve aparecer com autor + trigger `document_ingestion`
4. Clicar em "↶ Reverter" numa linha anterior — confirmar modal, página recarrega, nova versão com trigger `rollback` aparece no topo

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/projects/OCGPage.tsx
git commit -m "feat(ocg): histórico mostra autor + trigger e botão de rollback por versão"
```

---

## Self-Review

**Spec coverage:**
- ✅ Log de todas as alterações → Task 3 (_log_delta sempre grava)
- ✅ Quem fez a alteração → Task 1 (coluna changed_by) + Task 2 (model) + Task 4 (endpoint retorna autor) + Task 6 (frontend mostra)
- ✅ Rollback da última versão → Task 4 (endpoint POST /ocg/rollback/{v}) + Task 6 (botão)
- ✅ Histórico preserva rollbacks → Task 4 (rollback cria nova delta, não destrói)

**Placeholder scan:** nenhum "TBD", "TODO" ou "adicionar tratamento". Todo código está completo nos steps.

**Type consistency:**
- `trigger_source` é `String(50)` no model, `VARCHAR(50)` na migração, string no JSON ✓
- `changed_by` é `UUID` FK → `users.id` em ambos ✓
- `ocg_snapshot` é `Text` (JSON serializado), desserializado no rollback ✓
- Assinatura de `_log_delta` consistente entre Task 3 (definição) e chamada em `update_ocg_from_arguider` ✓

---

## Execution Handoff

Plano salvo em `docs/superpowers/plans/2026-04-15-ocg-history-rollback.md`. Opções:

**1. Subagent-Driven (recomendado)** — dispacho um subagent por task, reviso entre cada uma, iteração rápida.
**2. Inline Execution** — executo em batch nesta sessão com checkpoints de review.

Qual abordagem?
