# OCG Reativo + Billing IA — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar o OCG de estático em inteligência viva — cada documento ingerido atualiza o OCG via IA, com versionamento, delta-log, billing e propagação.

**Architecture:** 3 novos serviços (OCGUpdaterService, PropagationService, AIBillingService) + 1 tabela nova (ai_usage_log) + 2 colunas novas no OCG (context_health, change_type) + 7 endpoints novos + integração no ingestion_service._analyze_async.

**Tech Stack:** Python/FastAPI, SQLAlchemy async, DeepSeek/Anthropic via httpx, PostgreSQL

---

## Arquivos

### Criar:
- `backend/app/services/ocg_updater_service.py` — Atualiza OCG via LLM após análise do Arguidor
- `backend/app/services/propagation_service.py` — Propaga mudanças do OCG para backlog/módulos
- `backend/app/services/ai_billing_service.py` — Registra custo de cada chamada LLM por projeto
- `backend/migrations/009_ocg_reativo_billing.sql` — Migration para ai_usage_log + colunas OCG

### Modificar:
- `backend/app/models/base.py` — Adicionar modelo AIUsageLog + colunas context_health/change_type no OCG
- `backend/app/services/ingestion_service.py:227-241` — Chamar OCGUpdaterService após Arguidor
- `backend/app/services/agent_service.py:66-118` — Chamar AIBillingService em _call_llm
- `backend/app/services/audit_service.py:19-55` — Adicionar evento OCG_UPDATED
- `backend/app/routers/projects.py` — Adicionar endpoints OCG history/health/propagate + billing
- `backend/app/routers/ingestion_router.py` — Adicionar endpoint release quarentena

---

### Task 1: Migration + Modelo AIUsageLog

**Files:**
- Create: `backend/migrations/009_ocg_reativo_billing.sql`
- Modify: `backend/app/models/base.py`

- [ ] **Step 1: Criar migration SQL**

```sql
-- Migration 009: OCG reativo + billing
-- 1. Tabela ai_usage_log
CREATE TABLE IF NOT EXISTS ai_usage_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    provider VARCHAR(30) NOT NULL,
    model VARCHAR(50) NOT NULL,
    operation VARCHAR(50) NOT NULL,
    tokens_input INTEGER NOT NULL DEFAULT 0,
    tokens_output INTEGER NOT NULL DEFAULT 0,
    cost_usd DECIMAL(10,6) NOT NULL DEFAULT 0,
    actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    metadata TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_project ON ai_usage_log(project_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_operation ON ai_usage_log(project_id, operation);
CREATE INDEX IF NOT EXISTS idx_ai_usage_created ON ai_usage_log(created_at);

-- 2. Colunas novas no OCG
ALTER TABLE ocg ADD COLUMN IF NOT EXISTS context_health TEXT DEFAULT '{}';
ALTER TABLE ocg ADD COLUMN IF NOT EXISTS change_type VARCHAR(20) DEFAULT 'INITIAL';
```

Salvar em: `backend/migrations/009_ocg_reativo_billing.sql`

- [ ] **Step 2: Executar migration**

```bash
cat backend/migrations/009_ocg_reativo_billing.sql | docker exec -i gca-postgres psql -U gca -d gca
```

- [ ] **Step 3: Adicionar modelo AIUsageLog e colunas OCG em base.py**

No arquivo `backend/app/models/base.py`, antes da classe `AccessAttempt`, adicionar:

```python
class AIUsageLog(Base):
    """Log de uso de IA por projeto — billing compartimentalizado"""
    __tablename__ = "ai_usage_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(30), nullable=False)
    model = Column(String(50), nullable=False)
    operation = Column(String(50), nullable=False)  # ocg_generation, ocg_update, arguider_analysis, codegen
    tokens_input = Column(Integer, nullable=False, default=0)
    tokens_output = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    metadata = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_ai_usage_project", project_id),
        Index("idx_ai_usage_operation", project_id, operation),
        Index("idx_ai_usage_created", created_at),
    )
```

Na classe OCG, adicionar após `schema_version`:
```python
context_health = Column(Text, nullable=True, default="{}")  # JSON: {depth, confidence, quality}
change_type = Column(String(20), nullable=True, default="INITIAL")  # INITIAL, EXPAND, CONTRACT
```

- [ ] **Step 4: Restart backend e verificar**

```bash
docker compose restart backend
docker exec gca-backend python -c "from app.models.base import AIUsageLog, OCG; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/009_ocg_reativo_billing.sql backend/app/models/base.py
git commit -m "Task 1: Migration + modelo AIUsageLog + colunas OCG context_health/change_type"
```

---

### Task 2: AIBillingService

**Files:**
- Create: `backend/app/services/ai_billing_service.py`

- [ ] **Step 1: Criar AIBillingService**

```python
"""
AI Billing Service — Registra custo de cada chamada LLM por projeto.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import structlog

from app.models.base import AIUsageLog

logger = structlog.get_logger(__name__)

# Preços por 1M tokens (USD) — atualizar conforme providers mudam
AI_PRICING = {
    "deepseek": {"deepseek-chat": {"input": 0.14, "output": 0.28}},
    "anthropic": {
        "claude-opus-4-6": {"input": 15.0, "output": 75.0},
        "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    },
    "openai": {"gpt-4o": {"input": 2.50, "output": 10.0}},
    "grok": {"grok-3-mini": {"input": 0.30, "output": 0.50}},
    "gemini": {"gemini-2.0-pro": {"input": 1.25, "output": 5.0}},
}


class AIBillingService:
    """Registra e consulta custos de IA por projeto."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_usage(
        self,
        project_id: Optional[UUID],
        provider: str,
        model: str,
        operation: str,
        tokens_input: int,
        tokens_output: int,
        actor_id: Optional[UUID] = None,
        metadata: Optional[dict] = None,
    ) -> AIUsageLog:
        """Registra uma chamada LLM com custo estimado."""
        cost = self._calculate_cost(provider, model, tokens_input, tokens_output)

        entry = AIUsageLog(
            project_id=project_id,
            provider=provider,
            model=model,
            operation=operation,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=cost,
            actor_id=actor_id,
            metadata=json.dumps(metadata, default=str) if metadata else None,
        )
        self.db.add(entry)
        await self.db.flush()

        logger.info("billing.usage_logged",
                    project_id=str(project_id) if project_id else "global",
                    provider=provider, model=model, operation=operation,
                    tokens=tokens_input + tokens_output, cost_usd=f"{cost:.6f}")

        return entry

    def _calculate_cost(self, provider: str, model: str, tokens_in: int, tokens_out: int) -> float:
        """Calcula custo em USD baseado na tabela de preços."""
        prices = AI_PRICING.get(provider, {}).get(model)
        if not prices:
            # Fallback: estimar baseado em preços médios
            return (tokens_in / 1_000_000 * 1.0) + (tokens_out / 1_000_000 * 3.0)
        return (tokens_in / 1_000_000 * prices["input"]) + (tokens_out / 1_000_000 * prices["output"])

    async def get_project_summary(self, project_id: UUID) -> dict:
        """Resumo de gastos de IA do projeto."""
        result = await self.db.execute(
            select(
                func.sum(AIUsageLog.cost_usd).label("total_cost"),
                func.sum(AIUsageLog.tokens_input + AIUsageLog.tokens_output).label("total_tokens"),
                func.count(AIUsageLog.id).label("total_calls"),
            ).where(AIUsageLog.project_id == project_id)
        )
        row = result.first()

        # Breakdown por operação
        op_result = await self.db.execute(
            select(
                AIUsageLog.operation,
                func.sum(AIUsageLog.cost_usd).label("cost"),
                func.sum(AIUsageLog.tokens_input + AIUsageLog.tokens_output).label("tokens"),
                func.count(AIUsageLog.id).label("calls"),
            )
            .where(AIUsageLog.project_id == project_id)
            .group_by(AIUsageLog.operation)
        )

        # Breakdown por provider
        prov_result = await self.db.execute(
            select(
                AIUsageLog.provider,
                func.sum(AIUsageLog.cost_usd).label("cost"),
                func.count(AIUsageLog.id).label("calls"),
            )
            .where(AIUsageLog.project_id == project_id)
            .group_by(AIUsageLog.provider)
        )

        return {
            "total_cost_usd": float(row.total_cost or 0),
            "total_tokens": int(row.total_tokens or 0),
            "total_calls": int(row.total_calls or 0),
            "by_operation": [
                {"operation": r.operation, "cost_usd": float(r.cost or 0), "tokens": int(r.tokens or 0), "calls": int(r.calls or 0)}
                for r in op_result
            ],
            "by_provider": [
                {"provider": r.provider, "cost_usd": float(r.cost or 0), "calls": int(r.calls or 0)}
                for r in prov_result
            ],
        }

    async def get_project_detail(self, project_id: UUID, limit: int = 50) -> list[dict]:
        """Log detalhado de cada chamada IA."""
        result = await self.db.execute(
            select(AIUsageLog)
            .where(AIUsageLog.project_id == project_id)
            .order_by(AIUsageLog.created_at.desc())
            .limit(limit)
        )
        entries = result.scalars().all()

        return [
            {
                "id": str(e.id),
                "provider": e.provider,
                "model": e.model,
                "operation": e.operation,
                "tokens_input": e.tokens_input,
                "tokens_output": e.tokens_output,
                "cost_usd": float(e.cost_usd),
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ]
```

- [ ] **Step 2: Verificar import**

```bash
docker compose restart backend
docker exec gca-backend python -c "from app.services.ai_billing_service import AIBillingService; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/ai_billing_service.py
git commit -m "Task 2: AIBillingService — registra custo LLM por projeto"
```

---

### Task 3: Integrar billing no agent_service._call_llm

**Files:**
- Modify: `backend/app/services/agent_service.py:66-118`

- [ ] **Step 1: Modificar _call_llm para aceitar project_id e operation**

Alterar a assinatura de `_call_llm` de:
```python
async def _call_llm(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> tuple[str, int]:
```
Para:
```python
async def _call_llm(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096, project_id: UUID = None, operation: str = "ocg_generation") -> tuple[str, int]:
```

Após obter `text` e `tokens`, antes do `return`, adicionar:
```python
# Registrar billing
try:
    from app.services.ai_billing_service import AIBillingService
    billing = AIBillingService(self.db)
    # Estimar split input/output (70/30 quando não disponível individualmente)
    tokens_in = int(tokens * 0.7) if self.provider != "anthropic" else tokens
    tokens_out = int(tokens * 0.3) if self.provider != "anthropic" else 0
    await billing.log_usage(
        project_id=project_id,
        provider=self.provider,
        model=self.model,
        operation=operation,
        tokens_input=tokens_in,
        tokens_output=tokens_out,
    )
except Exception as e:
    logger.warning("billing.log_failed", error=str(e))
```

Para o branch Anthropic (que tem input/output separados), ajustar:
```python
tokens_in = response.usage.input_tokens
tokens_out = response.usage.output_tokens
tokens = tokens_in + tokens_out
```

- [ ] **Step 2: Restart e verificar**

```bash
docker compose restart backend
docker exec gca-backend python -c "from app.services.agent_service import AgentService; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/agent_service.py
git commit -m "Task 3: Billing integrado no _call_llm — registra custo de toda chamada"
```

---

### Task 4: OCGUpdaterService

**Files:**
- Create: `backend/app/services/ocg_updater_service.py`

- [ ] **Step 1: Criar OCGUpdaterService**

```python
"""
OCG Updater Service — Atualiza OCG via IA após análise do Arguidor.
Implements: expand_context, contract_context, update_context behaviors.
"""
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.models.base import OCG, IngestedDocument, ArguiderAnalysis
from app.services.ai_key_resolver import AIKeyResolver
from app.services.audit_service import AuditService, AuditEvents
from app.core.config import settings

logger = structlog.get_logger(__name__)

OCG_UPDATER_SYSTEM_PROMPT = """Você é o OCG Updater do GCA. Seu papel é atualizar o Objeto de Contexto Global (OCG) de um projeto baseado em uma nova análise de documento.

REGRAS:
1. Receba o OCG atual e a análise do Arguidor
2. Determine quais seções do OCG são afetadas
3. Atualize APENAS as seções afetadas — mantenha o restante intacto
4. Recalcule COMPOSITE_SCORE se pillar scores mudaram
5. Atualize APPROVAL_STATUS se score composto cruzou threshold (90=READY, 75=NEEDS_REVIEW, <75=AT_RISK)
6. P7 < 70 ou P2 < 70 = BLOCKED
7. Toda justificativa em Português-BR

RESPOSTA obrigatória (JSON):
{
  "updated_ocg": { ... },
  "changes": [{"field": "SEÇÃO.campo", "old": "...", "new": "...", "reason": "..."}],
  "change_type": "EXPAND" ou "CONTRACT",
  "context_health": {"depth": "initial|expanded|contracted", "confidence": 0.0-1.0, "quality": "good|partial|bad"}
}
"""


class OCGUpdaterService:
    """Atualiza OCG via IA após análise do Arguidor."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def update_from_analysis(
        self,
        project_id: UUID,
        document_id: UUID,
        analysis_result: dict,
    ) -> Optional[dict]:
        """Chama LLM para atualizar OCG baseado na análise do Arguidor."""

        # Carregar OCG atual
        result = await self.db.execute(
            select(OCG).where(OCG.project_id == project_id).order_by(OCG.created_at.desc()).limit(1)
        )
        current_ocg = result.scalar_one_or_none()
        if not current_ocg:
            logger.warning("ocg_updater.no_ocg_found", project_id=str(project_id))
            return None

        current_version = current_ocg.version or 1
        try:
            current_data = json.loads(current_ocg.ocg_data) if current_ocg.ocg_data else {}
        except json.JSONDecodeError:
            current_data = {}

        # Carregar texto do documento
        doc = await self.db.get(IngestedDocument, document_id)
        doc_info = {
            "filename": doc.original_filename if doc else "unknown",
            "file_type": doc.file_type if doc else "unknown",
        }

        # Montar prompt
        user_prompt = f"""OCG ATUAL (versão {current_version}):
{json.dumps(current_data, ensure_ascii=False, indent=2)[:8000]}

---

ANÁLISE DO ARGUIDOR para o documento "{doc_info['filename']}" ({doc_info['file_type']}):
{json.dumps(analysis_result, ensure_ascii=False, indent=2)[:4000]}

---

Atualize o OCG considerando esta nova análise. Se a análise complementa, EXPAND. Se conflita, CONTRACT."""

        # Chamar LLM
        try:
            provider = settings.DEFAULT_AI_PROVIDER or "deepseek"
            api_key = await AIKeyResolver.get_gca_key(provider)
            if not api_key:
                logger.warning("ocg_updater.no_api_key", provider=provider)
                # Fallback: marcar documento como ocg_pending
                if doc:
                    doc.arguider_status = "ocg_pending"
                    await self.db.commit()
                return None

            import httpx
            model = getattr(settings, f"{provider.upper()}_MODEL", None) or "deepseek-chat"

            provider_urls = {
                "deepseek": "https://api.deepseek.com/chat/completions",
                "openai": "https://api.openai.com/v1/chat/completions",
                "grok": "https://api.x.ai/v1/chat/completions",
            }
            url = provider_urls.get(provider, "https://api.deepseek.com/chat/completions")

            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }, json={
                    "model": model,
                    "max_tokens": 4096,
                    "temperature": 0.3,
                    "messages": [
                        {"role": "system", "content": OCG_UPDATER_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                })

            if resp.status_code not in (200, 201):
                logger.error("ocg_updater.llm_error", status=resp.status_code, body=resp.text[:200])
                if doc:
                    doc.arguider_status = "ocg_pending"
                    await self.db.commit()
                return None

            data = resp.json()
            response_text = data["choices"][0]["message"]["content"]
            tokens_used = data.get("usage", {}).get("total_tokens", 0)

            # Registrar billing
            from app.services.ai_billing_service import AIBillingService
            billing = AIBillingService(self.db)
            tokens_in = data.get("usage", {}).get("prompt_tokens", int(tokens_used * 0.7))
            tokens_out = data.get("usage", {}).get("completion_tokens", int(tokens_used * 0.3))
            await billing.log_usage(
                project_id=project_id, provider=provider, model=model,
                operation="ocg_update", tokens_input=tokens_in, tokens_output=tokens_out,
            )

            # Parsear resposta
            ocg_update = self._extract_json(response_text)
            if not ocg_update:
                logger.warning("ocg_updater.parse_failed", project_id=str(project_id))
                return None

            updated_ocg_data = ocg_update.get("updated_ocg", current_data)
            changes = ocg_update.get("changes", [])
            change_type = ocg_update.get("change_type", "UPDATE")
            context_health = ocg_update.get("context_health", {"depth": "expanded", "confidence": 0.7, "quality": "good"})

            # Persistir nova versão do OCG
            new_version = current_version + 1
            new_ocg = OCG(
                questionnaire_id=current_ocg.questionnaire_id,
                project_id=project_id,
                p1_business_score=self._get_score(updated_ocg_data, 1) or current_ocg.p1_business_score,
                p2_rules_score=self._get_score(updated_ocg_data, 2) or current_ocg.p2_rules_score,
                p3_features_score=self._get_score(updated_ocg_data, 3) or current_ocg.p3_features_score,
                p4_nfr_score=self._get_score(updated_ocg_data, 4) or current_ocg.p4_nfr_score,
                p5_architecture_score=self._get_score(updated_ocg_data, 5) or current_ocg.p5_architecture_score,
                p6_data_score=self._get_score(updated_ocg_data, 6) or current_ocg.p6_data_score,
                p7_security_score=self._get_score(updated_ocg_data, 7) or current_ocg.p7_security_score,
                overall_score=self._calc_overall(updated_ocg_data, current_ocg),
                status=self._determine_status(updated_ocg_data, current_ocg),
                is_blocking=current_ocg.is_blocking,
                version=new_version,
                schema_version="1.0.0",
                context_health=json.dumps(context_health, ensure_ascii=False),
                change_type=change_type,
                ocg_data=json.dumps(updated_ocg_data, ensure_ascii=False),
                generated_at=datetime.now(timezone.utc),
            )

            # Remover unique constraint issue — atualizar em vez de inserir novo
            current_ocg.version = new_version
            current_ocg.ocg_data = json.dumps(updated_ocg_data, ensure_ascii=False)
            current_ocg.overall_score = new_ocg.overall_score
            current_ocg.status = new_ocg.status
            current_ocg.context_health = new_ocg.context_health
            current_ocg.change_type = change_type
            current_ocg.p1_business_score = new_ocg.p1_business_score
            current_ocg.p2_rules_score = new_ocg.p2_rules_score
            current_ocg.p3_features_score = new_ocg.p3_features_score
            current_ocg.p4_nfr_score = new_ocg.p4_nfr_score
            current_ocg.p5_architecture_score = new_ocg.p5_architecture_score
            current_ocg.p6_data_score = new_ocg.p6_data_score
            current_ocg.p7_security_score = new_ocg.p7_security_score
            current_ocg.updated_at = datetime.now(timezone.utc)

            await self.db.commit()

            # Delta log
            from app.services.ocg_service import OCGService
            ocg_svc = OCGService(self.db)
            await ocg_svc.log_delta(
                project_id=project_id,
                document_id=document_id,
                version_from=current_version,
                version_to=new_version,
                fields_changed={c.get("field", "?"): {"old": c.get("old"), "new": c.get("new"), "reason": c.get("reason")} for c in changes},
            )

            # Auditoria
            audit = AuditService(self.db)
            await audit.log_event(
                event_type="OCG_UPDATED",
                resource_type="ocg",
                resource_id=current_ocg.id,
                details={
                    "version_from": current_version,
                    "version_to": new_version,
                    "change_type": change_type,
                    "changes_count": len(changes),
                    "document": doc_info["filename"],
                },
            )
            await self.db.commit()

            logger.info("ocg_updater.success",
                       project_id=str(project_id),
                       version=f"{current_version}→{new_version}",
                       change_type=change_type,
                       changes=len(changes))

            return {
                "version_from": current_version,
                "version_to": new_version,
                "change_type": change_type,
                "changes": changes,
                "context_health": context_health,
            }

        except Exception as e:
            logger.error("ocg_updater.error", project_id=str(project_id), error=str(e))
            if doc:
                doc.arguider_status = "ocg_pending"
                await self.db.commit()
            return None

    def _extract_json(self, text: str) -> Optional[dict]:
        """Extrai JSON da resposta do LLM."""
        import re
        # Tentar parse direto
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Tentar extrair bloco ```json
        match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # Tentar encontrar primeiro { até último }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        return None

    def _get_score(self, ocg_data: dict, pillar_num: int) -> Optional[float]:
        """Extrai score de um pilar do OCG data."""
        ps = ocg_data.get("PILLAR_SCORES", {})
        for key in [f"P{pillar_num}", f"P{pillar_num}_Business", f"P{pillar_num}_Compliance",
                   f"P{pillar_num}_Scope", f"P{pillar_num}_Performance", f"P{pillar_num}_Architecture",
                   f"P{pillar_num}_Data", f"P{pillar_num}_Security"]:
            val = ps.get(key)
            if isinstance(val, dict):
                return val.get("score")
            elif isinstance(val, (int, float)):
                return val
        return None

    def _calc_overall(self, ocg_data: dict, current: OCG) -> float:
        """Calcula overall score ponderado."""
        cs = ocg_data.get("COMPOSITE_SCORE", {})
        if isinstance(cs, dict):
            return cs.get("overall") or cs.get("value") or current.overall_score or 0
        if isinstance(cs, (int, float)):
            return cs
        return current.overall_score or 0

    def _determine_status(self, ocg_data: dict, current: OCG) -> str:
        """Determina status baseado nas regras de aprovação."""
        cs = ocg_data.get("COMPOSITE_SCORE", {})
        if isinstance(cs, dict):
            return cs.get("status") or current.status or "NEEDS_REVIEW"
        overall = self._calc_overall(ocg_data, current)
        if overall >= 90:
            return "READY"
        if overall >= 75:
            return "NEEDS_REVIEW"
        return "AT_RISK"
```

- [ ] **Step 2: Verificar import**

```bash
docker compose restart backend
docker exec gca-backend python -c "from app.services.ocg_updater_service import OCGUpdaterService; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/ocg_updater_service.py
git commit -m "Task 4: OCGUpdaterService — atualiza OCG via IA após Arguidor"
```

---

### Task 5: PropagationService

**Files:**
- Create: `backend/app/services/propagation_service.py`

- [ ] **Step 1: Criar PropagationService**

```python
"""
Propagation Service — Propaga mudanças do OCG para módulos dependentes.
"""
import asyncio
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.services.backlog_service import BacklogService
from app.services.audit_service import AuditService, AuditEvents

logger = structlog.get_logger(__name__)

# Mapeamento: campo OCG alterado → categorias de backlog a regenerar
PROPAGATION_MAP = {
    "STACK_RECOMMENDATION": ["modules"],
    "COMPLIANCE_CHECKLIST": ["compliance"],
    "TESTING_REQUIREMENTS": ["tests"],
    "ARCHITECTURE_OVERVIEW": ["modules", "security"],
    "RISK_ANALYSIS": [],  # Só atualiza APPROVAL_STATUS
    "PILLAR_SCORES": ["modules", "tests", "compliance", "security"],
    "CRITICAL_FINDINGS": ["modules"],
}


class PropagationService:
    """Propaga mudanças do OCG para backlog e módulos dependentes."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def propagate(
        self,
        project_id: UUID,
        changes: list[dict],
        ocg_version: Optional[int] = None,
    ) -> dict:
        """Analisa campos alterados e dispara regeneração seletiva."""

        affected_categories = set()

        for change in changes:
            field = change.get("field", "")
            top_level = field.split(".")[0] if "." in field else field

            categories = PROPAGATION_MAP.get(top_level, [])
            affected_categories.update(categories)

        # Se qualquer coisa mudou, sempre regenerar backlog completo
        if changes:
            affected_categories.add("modules")  # Garante que módulos são reavaliados

        # Regenerar backlog
        backlog_svc = BacklogService(self.db)
        backlog_result = await backlog_svc.regenerate_from_ocg(project_id, ocg_version)

        # Registrar evento
        audit = AuditService(self.db)
        await audit.log_event(
            event_type=AuditEvents.BACKLOG_REGENERATED,
            resource_type="backlog",
            resource_id=project_id,
            details={
                "affected_categories": list(affected_categories),
                "changes_count": len(changes),
                "backlog_regenerated": backlog_result.get("regenerated", 0),
            },
        )
        await self.db.commit()

        logger.info("propagation.completed",
                   project_id=str(project_id),
                   categories=list(affected_categories),
                   backlog_items=backlog_result.get("regenerated", 0))

        return {
            "affected_categories": list(affected_categories),
            "backlog_result": backlog_result,
        }
```

- [ ] **Step 2: Verificar e commit**

```bash
docker compose restart backend
docker exec gca-backend python -c "from app.services.propagation_service import PropagationService; print('OK')"
git add backend/app/services/propagation_service.py
git commit -m "Task 5: PropagationService — propaga mudanças OCG para backlog"
```

---

### Task 6: Integrar no ingestion_service

**Files:**
- Modify: `backend/app/services/ingestion_service.py:227-241`

- [ ] **Step 1: Após bloco de audit DOCUMENT_INGESTED, adicionar chamada ao OCGUpdaterService e PropagationService**

Após a linha `await db.commit()` (que registra DOCUMENT_INGESTED), adicionar:

```python
# === OCG REATIVO: Atualizar OCG via IA ===
try:
    from app.services.ocg_updater_service import OCGUpdaterService
    from app.services.propagation_service import PropagationService

    # Carregar análise do Arguidor
    arguider_result = await db.execute(
        select(ArguiderAnalysis).where(ArguiderAnalysis.document_id == document_id)
    )
    analysis = arguider_result.scalar_one_or_none()
    analysis_data = {}
    if analysis:
        import json as _json
        try:
            analysis_data = {
                "classification": _json.loads(analysis.document_classification) if analysis.document_classification else {},
                "gaps": _json.loads(analysis.gaps) if analysis.gaps else [],
                "module_candidates": _json.loads(analysis.module_candidates) if analysis.module_candidates else [],
            }
        except _json.JSONDecodeError:
            pass

    # Atualizar OCG
    updater = OCGUpdaterService(db)
    update_result = await updater.update_from_analysis(project_id, document_id, analysis_data)

    # Propagar se houve mudanças
    if update_result and update_result.get("changes"):
        propagator = PropagationService(db)
        await propagator.propagate(
            project_id=project_id,
            changes=update_result["changes"],
            ocg_version=update_result.get("version_to"),
        )

    logger.info("ingestion.ocg_reactive_complete",
               document_id=str(document_id),
               ocg_updated=bool(update_result))

except Exception as e:
    logger.warning("ingestion.ocg_reactive_error",
                  document_id=str(document_id), error=str(e))
```

- [ ] **Step 2: Adicionar import de ArguiderAnalysis no topo do _analyze_async**

Adicionar `from app.models.base import ArguiderAnalysis` no bloco de imports dentro de `_analyze_async`.

- [ ] **Step 3: Restart e verificar**

```bash
docker compose restart backend
docker logs gca-backend --tail 3
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/ingestion_service.py
git commit -m "Task 6: Integrar OCG reativo no pipeline de ingestão"
```

---

### Task 7: Adicionar evento OCG_UPDATED ao AuditEvents

**Files:**
- Modify: `backend/app/services/audit_service.py:19-55`

- [ ] **Step 1: Adicionar OCG_UPDATED na classe AuditEvents**

Após `GATEKEEPER_EVALUATED`, adicionar:
```python
OCG_UPDATED = "OCG_UPDATED"
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/audit_service.py
git commit -m "Task 7: Evento OCG_UPDATED no catálogo de auditoria"
```

---

### Task 8: Endpoints novos

**Files:**
- Modify: `backend/app/routers/projects.py`
- Modify: `backend/app/routers/ingestion_router.py`

- [ ] **Step 1: Adicionar endpoints OCG history, delta-log, health, propagate em projects.py**

Após o endpoint `/projects/{id}/ocg`:

```python
@router.get("/{project_id}/ocg/history")
async def get_ocg_history(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Histórico de versões do OCG."""
    from sqlalchemy import select
    from app.models.base import OCGDeltaLog

    result = await db.execute(
        select(OCGDeltaLog)
        .where(OCGDeltaLog.project_id == project_id)
        .order_by(OCGDeltaLog.created_at.desc())
        .limit(50)
    )
    deltas = result.scalars().all()

    return {
        "history": [
            {
                "version_from": d.ocg_version_from,
                "version_to": d.ocg_version_to,
                "change_summary": d.change_summary,
                "fields_changed": d.fields_changed,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in deltas
        ]
    }


@router.get("/{project_id}/ocg/health")
async def get_ocg_health(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Saúde do contexto OCG."""
    from sqlalchemy import select
    from app.models.base import OCG
    import json

    result = await db.execute(
        select(OCG).where(OCG.project_id == project_id).order_by(OCG.created_at.desc()).limit(1)
    )
    ocg = result.scalar_one_or_none()
    if not ocg:
        return {"health": None, "message": "OCG não encontrado"}

    health = {}
    if ocg.context_health:
        try:
            health = json.loads(ocg.context_health)
        except json.JSONDecodeError:
            pass

    return {
        "health": health,
        "version": ocg.version,
        "change_type": ocg.change_type,
        "overall_score": ocg.overall_score,
        "status": ocg.status,
    }


@router.post("/{project_id}/ocg/propagate")
async def force_propagation(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Forçar re-propagação do OCG para módulos dependentes."""
    from app.services.propagation_service import PropagationService
    propagator = PropagationService(db)
    result = await propagator.propagate(project_id, changes=[{"field": "MANUAL_PROPAGATION"}])
    return result
```

- [ ] **Step 2: Adicionar endpoints billing em projects.py**

```python
@router.get("/{project_id}/billing")
async def get_project_billing(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Resumo de gastos de IA do projeto."""
    from app.services.ai_billing_service import AIBillingService
    billing = AIBillingService(db)
    return await billing.get_project_summary(project_id)


@router.get("/{project_id}/billing/detail")
async def get_project_billing_detail(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    """Log detalhado de chamadas IA do projeto."""
    from app.services.ai_billing_service import AIBillingService
    billing = AIBillingService(db)
    entries = await billing.get_project_detail(project_id, limit)
    return {"entries": entries, "count": len(entries)}
```

- [ ] **Step 3: Adicionar endpoint release quarentena em ingestion_router.py**

```python
@router.post("/projects/{project_id}/ingestion/{document_id}/release")
async def release_from_quarantine(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Liberar documento da quarentena e disparar análise + OCG update."""
    from app.models.base import IngestedDocument
    doc = await db.get(IngestedDocument, document_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    if doc.quarantine_status != "quarantined":
        raise HTTPException(status_code=400, detail="Documento não está em quarentena")

    doc.quarantine_status = "released"
    doc.arguider_status = "pending"
    await db.commit()

    # Disparar análise assíncrona
    from app.services.ingestion_service import IngestionService
    svc = IngestionService(db)
    import asyncio
    asyncio.create_task(svc._analyze_async(document_id, project_id, b"", doc.file_type))

    return {"message": "Documento liberado da quarentena. Análise iniciada.", "document_id": str(document_id)}
```

- [ ] **Step 4: Restart e testar endpoints**

```bash
docker compose restart backend
TOKEN=$(curl -s http://localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' -d '{"email":"pielak.ctba@gmail.com","password":"Topazio01#"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
PID="9220601b-e006-4e10-9310-ab8aa0fb9250"
curl -s "http://localhost:8000/api/v1/projects/$PID/ocg/health" -H "Authorization: Bearer $TOKEN"
curl -s "http://localhost:8000/api/v1/projects/$PID/billing" -H "Authorization: Bearer $TOKEN"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/projects.py backend/app/routers/ingestion_router.py
git commit -m "Task 8: Endpoints OCG history/health/propagate + billing + release quarentena"
```

---

### Task 9: Teste E2E — Upload documento e verificar OCG atualizado

- [ ] **Step 1: Verificar OCG atual**

```bash
curl -s "http://localhost:8000/api/v1/projects/$PID/ocg/health" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

- [ ] **Step 2: Upload um documento de teste**

```bash
echo "# Arquitetura FinanceHub Pro\n\nO sistema utiliza PostgreSQL com particionamento por data.\nRedis para cache de sessões e rate limiting.\nRabbitMQ para eventos de domínio." > /tmp/test_arch.md
curl -s -X POST "http://localhost:8000/api/v1/projects/$PID/ingestion" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/test_arch.md" \
  -F "description=Documento de arquitetura" | python3 -m json.tool
```

- [ ] **Step 3: Aguardar análise (30-60s) e verificar OCG atualizado**

```bash
sleep 60
curl -s "http://localhost:8000/api/v1/projects/$PID/ocg/health" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s "http://localhost:8000/api/v1/projects/$PID/ocg/history" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s "http://localhost:8000/api/v1/projects/$PID/billing" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

- [ ] **Step 4: Commit final**

```bash
git commit --allow-empty -m "Task 9: Teste E2E validado — OCG reativo funcional"
```

---

## Resumo de Execução

| Task | Descrição | Arquivos |
|------|-----------|----------|
| 1 | Migration + modelo AIUsageLog | migration SQL + models/base.py |
| 2 | AIBillingService | ai_billing_service.py |
| 3 | Billing no _call_llm | agent_service.py |
| 4 | OCGUpdaterService | ocg_updater_service.py |
| 5 | PropagationService | propagation_service.py |
| 6 | Integrar no ingestion | ingestion_service.py |
| 7 | Evento OCG_UPDATED | audit_service.py |
| 8 | Endpoints novos | projects.py + ingestion_router.py |
| 9 | Teste E2E | validação manual |
