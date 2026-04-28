# MVP 26 — Checklist para Implementação (Dev Sênior)

**Status**: Gates 1-3 concluídos. Gate 1 ✅ Aprovado. Gate 2 ⚠️ Aprovado com ressalvas (3 MUST). Gate 3 ❌ Reprovado (6 MUST).

**Pré-requisito**: MVP 29 está fechado (Celery idempotente, Prometheus métricas). ✅

**Data da validação**: 2026-04-28

---

## GATE 2 — Arquiteto: 3 Correções Obrigatórias (MUST)

### MUST A1 — Ordem de operação: fail-closed explicit

**Problema**: Contrato diz "sem escrita de audit = sem chamada LLM", mas não especifica se `log_llm_decision()` roda antes ou depois.

**Solução obrigatória**: `log_llm_decision()` deve rodar **ANTES** da chamada LLM, com timeout 200ms explícito.

**Onde**: `backend/app/services/arguider_service.py`, antes de `_call_llm()` ou equivalente.

**Padrão**:
```python
# Em _call_llm() ou novo método:
try:
    audit_entry = await asyncio.wait_for(
        self.billing_service.log_llm_decision(
            project_id=project_id,
            model_id=model_name,
            provider=provider,
            temperature=temp,
            prompt_version=self.prompt_version,
            decision_type="ARGUIDER_ANALYSIS",
            input_hash=hash(input),
            output_hash=hash(output)  # calculado depois
        ),
        timeout=0.2  # 200ms max
    )
except asyncio.TimeoutError:
    raise HTTPException(503, "Audit write timeout — LLM call cancelled")

# Agora chama LLM
result = await self._call_llm(...)
```

**Verificação**: Teste unitário: mock DB que demora >200ms deve retornar erro 503, sem chamar LLM.

---

### MUST A2 — RBAC explícito no endpoint

**Problema**: Contrato descreve endpoints `/api/audit/llm-decisions` e `/api/metrics/ai-governance`, mas não define quem pode acessar.

**Solução obrigatória**: Adicionar RBAC:
- **Admin**: vê tudo
- **GP do projeto**: vê só seu projeto
- **Dev/Tester/QA**: `403 Forbidden`

**Onde**: `backend/app/routers/audit_llm_router.py` (novo) ou router existente.

**Padrão**:
```python
@router.get("/api/audit/llm-decisions")
async def get_llm_decisions(
    project_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # RBAC: Admin ve tudo, GP ve so seu projeto
    if current_user.role == "admin":
        pass  # pode ver qualquer projeto
    elif current_user.role == "gp":
        # verificar se current_user eh GP do project_id
        is_gp = await db.execute(
            select(exists(ProjectMember.query...))
        )
        if not is_gp:
            raise HTTPException(403, "Not authorized")
    else:
        raise HTTPException(403, "Only Admin and GP can access")
```

**Verificação**: Teste de integração: Dev tenta acessar endpoint, recebe 403.

---

### MUST A3 — Decisão explícita: colunas vs metadata_json

**Problema**: `AIUsageLog` já tem coluna `metadata_json` (TEXT/JSONB). Campos novos (`temperature`, `prompt_version`, `decision_type`) vão como:
- **Opção 1**: Colunas SQL novas (requer migration)
- **Opção 2**: Dentro de `metadata_json` (sem migration)

**Critério de aceite exige indexabilidade** — queries de observabilidade precisam filtrar/agregar por `decision_type` eficientemente.

**Solução recomendada**: **Opção 1 — Colunas SQL novas** (permite índices, mais veloz em agregações).

**Registrar em contrato**: Adicionar à seção "Regras duras de 26":
```
- **Decisão registrada (2026-04-28):** campos temperature, prompt_version, decision_type vão como colunas SQL novas em AIUsageLog (não em metadata_json) para permitir índices e queries eficientes.
```

**Verificação**: Migration 056 cria as 3 colunas, ORM mapeia.

---

## GATE 3 — DBA: 6 Correções Obrigatórias (MUST)

### MUST D1 — Auditar divergência metadata vs metadata_json

**Problema**: ORM em `base.py:439` chama `metadata_json`, mas SQL em migration 009 pode ter criado `metadata` (sem `_json`). Verificar o que existe.

**Solução obrigatória**: Rodar em `gca_test`:
```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'ai_usage_log' AND column_name LIKE 'metadata%';
```

- Se retorna `metadata`: migration 056 deve fazer `ALTER TABLE ai_usage_log RENAME COLUMN metadata TO metadata_json;`
- Se retorna `metadata_json`: pular este passo.

**Onde**: `backend/migrations/056_mvp26_ai_usage_log_llm_trace.sql`

**Verificação**: `\d ai_usage_log` mostra coluna `metadata_json`, não `metadata`.

---

### MUST D2 — CHECK constraint de range para temperature

**Problema**: `temperature NUMERIC(4,2)` sem constraint pode aceitar -99.99 ou 999.99 (inválido).

**Solução obrigatória**: Adicionar CHECK na migration:
```sql
ADD COLUMN IF NOT EXISTS temperature NUMERIC(4,2) NULL
  CHECK (temperature IS NULL OR (temperature >= 0.00 AND temperature <= 2.00)),
```

**Onde**: `backend/migrations/056_mvp26_ai_usage_log_llm_trace.sql`

**Verificação**: Teste: `INSERT INTO ai_usage_log(..., temperature) VALUES (..., -0.01)` retorna constraint error.

---

### MUST D3 — ORM atualizado com 3 colunas novas

**Problema**: Migration cria as colunas, mas ORM em `base.py:426-449` não as mapeia → `SAWarning: Columns ... could not be reflected`.

**Solução obrigatória**: Adicionar em `backend/app/models/base.py` classe `AIUsageLog`:
```python
class AIUsageLog(Base):
    __tablename__ = "ai_usage_log"
    
    # ... campos existentes ...
    
    # Novos campos de MVP 26
    temperature = Column(Numeric(4, 2), nullable=True)
    prompt_version = Column(String(255), nullable=True)
    decision_type = Column(String(50), nullable=True)
    
    __table_args__ = (
        CheckConstraint(
            "temperature IS NULL OR (temperature >= 0.00 AND temperature <= 2.00)",
            name="ck_temperature_range"
        ),
        CheckConstraint(
            "decision_type IS NULL OR decision_type IN ("
            "'ARGUIDER_ANALYSIS', 'CODEGEN_GENERATION', 'OCG_CONSOLIDATION', 'ERS_GENERATION')",
            name="ck_decision_type_values"
        ),
    )
```

**Verificação**: `from app.models.base import AIUsageLog; print(AIUsageLog.__table__.columns.keys())` inclui `temperature`, `prompt_version`, `decision_type`.

---

### MUST D4 — Mapear decision_type para operation tokens reais

**Problema**: Migration propõe `decision_type ∈ {ARGUIDER_ANALYSIS, CODEGEN_GENERATION, OCG_CONSOLIDATION, ERS_GENERATION}`, mas `ai_billing_service.py:54` grava `operation ∈ {ocg_update, analyzer, consolidator, ...}`. Não coincidem.

**Solução obrigatória**: Escolher um:
- **Opção A**: Alterar CHECK constraint para usar tokens reais (`ocg_update`, `analyzer`, etc). Revisar todo código que define `operation`.
- **Opção B**: Criar mapper em `ai_billing_service.log_usage()`:
  ```python
  OPERATION_TO_DECISION_TYPE = {
      "analyzer": "ARGUIDER_ANALYSIS",
      "ocg_update": "OCG_CONSOLIDATION",
      "codegen": "CODEGEN_GENERATION",
  }
  decision_type = OPERATION_TO_DECISION_TYPE.get(operation)
  ```

**Recomendação**: **Opção B** (menos refactoring).

**Verificação**: `ai_usage_log` tem entries com `decision_type` preenchido após primeiro call.

---

### MUST D5 — Índice composto para observabilidade

**Problema**: Endpoint `/api/metrics/ai-governance?project_id=X` vai filtrar por `project_id + created_at`. Índices existentes não cobrem ambos.

**Solução obrigatória**: Adicionar em migration:
```sql
CREATE INDEX IF NOT EXISTS idx_ai_usage_log_project_created
  ON ai_usage_log(project_id, created_at DESC);
```

**Verificação**: `EXPLAIN ANALYZE SELECT * FROM ai_usage_log WHERE project_id = $1 AND created_at > $2` usa `Index Scan`, não `Seq Scan`.

---

### MUST D6 — Retenção documentada

**Problema**: `ai_usage_log` cresce indefinidamente. Sem política de retenção, fica problema operacional.

**Solução obrigatória**: Adicionar em migration `056`:
```sql
COMMENT ON TABLE ai_usage_log IS 'Billing e governance de chamadas LLM. '
  'Retenção: 90 dias (base legal LGPD Art. 6º IX — legítimo interesse em auditoria de custo + compliance). '
  'Revisar em 2027-Q1. Cleanup via: DELETE FROM ai_usage_log WHERE created_at < NOW() - INTERVAL 90 DAY;'
;
```

E registrar em `GCA_CANONICAL_CONTRACT.md §9 MVP 26` ou documento equivalente:
```
**Retenção de dados (26.1):**
- `AIUsageLog` retém por 90 dias (base legal: legítimo interesse LGPD Art. 6º IX).
- `GlobalAuditLog` herda retenção existente (verificar MVP 13 para política).
```

**Verificação**: Contrato ou doc de retenção lista `ai_usage_log: 90 dias`.

---

## Resumo de Arquivos a Modificar

| Arquivo | Fase | MUST | Descrição |
|---------|------|------|-----------|
| `GCA_CANONICAL_CONTRACT.md` | 26.1-26.4 | A1, A3, D6 | Registrar MUSTs + NFRs + retenção |
| `backend/migrations/056_mvp26_ai_usage_log_llm_trace.sql` | 26.1 | D1, D2, D5, D6 | Migration nova (ALTER TABLE ai_usage_log + índices + COMMENT) |
| `backend/app/models/base.py` | 26.1 | D3 | Classe `AIUsageLog`: +3 colunas + 2 CheckConstraints |
| `backend/app/services/ai_billing_service.py` | 26.1 | D4 | Mapper `OPERATION_TO_DECISION_TYPE` + parâmetros novos em `log_usage()` |
| `backend/app/services/arguider_service.py` | 26.1, 26.2 | A1 | Integração audit pré-LLM + detector de injection |
| `backend/app/services/code_generation.py` | 26.1 | A1 | Integração audit LLM call em CodeGen |
| `backend/app/routers/audit_llm_router.py` | 26.1 | A2 | Novo router: `/api/audit/llm-decisions` (GET com RBAC) |
| `backend/app/services/prompt_injection_detector.py` | 26.2 | — | Novo serviço: detector determinístico (8+ padrões) |
| `backend/app/services/rnf_validation_service.py` | 26.3 | — | Extensão: +`validate_business_rules(code, rules)` |
| `backend/app/routers/metrics.py` ou novo | 26.4 | A2 | Endpoint `/api/metrics/ai-governance` (GET com RBAC) |
| `backend/app/help_content/*.md` | 26.4 | — | Novo capítulo "Governança de IA" |
| `backend/app/tests/fixtures/injection_payloads.json` | 26.2 | — | 40+ payloads (20+ clean, 20+ injection) — permanente |
| `backend/app/tests/test_mvp26_*.py` | 26.1-26.4 | — | 40+ novos testes (≥10 por fase) |

---

## Critério de Aceite Global

1. ✅ **Migration 056 aplica** sem erro em `gca_test` (2x vezes = idempotência).
2. ✅ **ORM atualizado**: `from app.models.base import AIUsageLog; assert hasattr(AIUsageLog, 'temperature')`.
3. ✅ **Falsa positiva < 5%**: fixture de 40+ payloads retorna taxa < 5%.
4. ✅ **Latência audit write ≤ 50ms p95**: teste com DB real.
5. ✅ **Latência observabilidade ≤ 300ms p95**: para projeto com 50k entries.
6. ✅ **RBAC funciona**: Dev recebe 403, GP recebe 200.
7. ✅ **Suite**: ≥ baseline antes (181 arquivos) + 40 novos testes, zero regressão.
8. ✅ **tsc frontend = 0**.
9. ✅ **Zero DTs abertas**.

---

## Próximos Passos (Gate 3 revalidação)

1. Dev implementa com checklist acima.
2. Abre PR com migration + ORM + routers + serviços.
3. DBA revalida:
   - Migration SQL está clean (C1-C6 resolvidas).
   - ORM mapeia corretamente.
   - Índices melhoram latência.
4. **Aprovação final**: Gate 3 ✅ Aprovado.
5. Implementação continua (Fase 26.2, 26.3, 26.4).

---

**Documento criado em**: 2026-04-28  
**Status**: Pronto para Dev implementar  
**Próxima revisão**: Quando Dev submeter PR com Fase 26.1
