# Padrão Canônico: Try/Except — Processo Binário

## Princípio

**Toda função, task e processo é BINÁRIO:**

```
✅ Sucesso → log info, prossegue
❌ Erro → log error, mensagem clara, ação esperada, parada
🛑 PROIBIDO: silêncio (parada sem log/erro = pior que crash)
```

**Regra:** Se o código está dentro de um try/except, a exceção DEVE ser tratada — logged, re-raised ou convertida em erro explícito. **NUNCA `except: pass`**.

---

## Por Que Erro Silencioso é Pior que Crash

| Cenário | Custo |
|---|---|
| **Crash imediato** | Usuário vê erro, para, avisa | 5 min debug |
| **Erro silencioso** | Código roda "de boa", resultado errado, descobrem depois | 2h retrabalho |
| **Timeout silencioso** | Doc fica `processing` para sempre, fila tranca | 4h restart + reprocessamento |
| **Exception swallowed** | Processo morre interno, usuário não sabe, tenta denovo | Retrabalho + frustração |

---

## Padrão Correto

### 1️⃣ **Função com validação canônica**

```python
async def process_document(doc_id: UUID, project_id: UUID) -> dict:
    """Processa doc. Retorna dict com resultado ou lança exceção."""
    try:
        # Validação de entrada (invariantes garantidas pelo caller)
        if not doc_id or not project_id:
            raise ValueError("doc_id e project_id são obrigatórios")
        
        # Operação que pode falhar externamente (API, DB)
        result = await some_external_service.process(doc_id)
        
        logger.info("document_processed", doc_id=str(doc_id), result_status=result.status)
        return result
    
    except ValueError as e:
        # Erro de validação — usuario fez algo errado
        logger.error("document_process_invalid_input", doc_id=str(doc_id), error=str(e))
        raise  # Propagar pra caller tratar
    
    except TimeoutError as e:
        # Erro externo previsível — log + re-raise com contexto
        logger.error(
            "document_process_timeout",
            doc_id=str(doc_id),
            timeout_seconds=30,
            error=str(e),
        )
        raise  # Caller decide retry ou erro
    
    except Exception as e:
        # Erro inesperado — sempre log ANTES de dar up
        logger.error(
            "document_process_unexpected_error",
            doc_id=str(doc_id),
            error=str(e),
            exc_info=True,  # Stack trace completo
        )
        raise  # NUNCA swallow
```

### 2️⃣ **Task assíncrona (Dramatiq/Celery)**

```python
@dramatiq.actor
def process_ingestion_task(ingestion_id: str):
    """Task: processa ingestão. Falha explícita = status em DB + log."""
    try:
        logger.info("ingestion_task_started", ingestion_id=ingestion_id)
        
        # Operação principal
        result = some_service.ingest(ingestion_id)
        
        logger.info("ingestion_task_completed", ingestion_id=ingestion_id, status=result.status)
        return result
    
    except Exception as e:
        # Task falha = marca em DB + log explícito
        logger.error(
            "ingestion_task_failed",
            ingestion_id=ingestion_id,
            error=str(e),
            exc_info=True,
        )
        # Marcar em DB que falhou
        try:
            db = AsyncSessionLocal()
            doc = db.query(IngestedDocument).filter(IngestedDocument.id == ingestion_id).first()
            if doc:
                doc.arguider_status = "error"
                doc.arguider_error_message = f"Task failed: {str(e)}"
                db.commit()
        except:
            logger.error("ingestion_task_failed_to_mark_error", ingestion_id=ingestion_id)
        
        # Re-raise para Dramatiq retry
        raise
```

### 3️⃣ **Endpoint FastAPI**

```python
@router.post("/documents/{doc_id}/process")
async def process_document_endpoint(doc_id: UUID, db: AsyncSession = Depends(get_db)):
    """Processa doc. Retorna 200 (sucesso) ou 4xx/5xx (erro)."""
    try:
        logger.info("process_document_request", doc_id=str(doc_id))
        
        # Buscar doc
        doc = await db.get(IngestedDocument, doc_id)
        if not doc:
            logger.warning("document_not_found", doc_id=str(doc_id))
            raise HTTPException(status_code=404, detail="Documento não encontrado")
        
        # Processar
        result = await some_service.process(doc)
        
        logger.info("document_processed", doc_id=str(doc_id), result=result)
        return {"status": "ok", "result": result}
    
    except HTTPException:
        # FastAPI HTTP exception — deixar passar
        raise
    
    except ValueError as e:
        # Erro de validação — 400
        logger.error("process_document_validation_error", doc_id=str(doc_id), error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    
    except Exception as e:
        # Erro inesperado — 500
        logger.error(
            "process_document_internal_error",
            doc_id=str(doc_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Erro interno. Contate suporte.")
```

### 4️⃣ **Context manager (with statement)**

```python
async def update_ocg_with_safety(project_id: UUID, data: dict):
    """Atualiza OCG com garantia de rollback em erro."""
    try:
        logger.info("ocg_update_started", project_id=str(project_id))
        
        async with AsyncSessionLocal() as db:
            async with db.begin():  # Transação — rollback automático em erro
                await OCGUpdaterService(db).update(project_id, data)
        
        logger.info("ocg_update_completed", project_id=str(project_id))
    
    except IntegrityError as e:
        # Violação de constraint — erro de dados
        logger.error("ocg_update_integrity_error", project_id=str(project_id), error=str(e))
        raise
    
    except Exception as e:
        # Qualquer outro erro — rollback automático + log
        logger.error(
            "ocg_update_failed",
            project_id=str(project_id),
            error=str(e),
            exc_info=True,
        )
        raise
```

---

## Padrões PROIBIDOS

### ❌ `except: pass` — NUNCA!

```python
# PROIBIDO
try:
    result = some_operation()
except:
    pass  # ← Erro silencioso!
return result
```

**Por quê:** Se `some_operation()` falha, `result` é indefinido. Próxima linha usa `result` errado. Debug leva horas.

**Correto:**
```python
try:
    result = some_operation()
except Exception as e:
    logger.error("operation_failed", error=str(e), exc_info=True)
    raise  # ou return error_response
```

### ❌ `except Exception: logger.info(...)` — NUNCA info em erro!

```python
# PROIBIDO
except Exception as e:
    logger.info(f"Algo falhou: {e}")  # ← info level = não alertável
    continue
```

**Correto:**
```python
except Exception as e:
    logger.error("operation_failed", error=str(e), exc_info=True)
    # continuar ou re-raise dependendo do contexto
```

### ❌ Comentário TODO no catch

```python
# PROIBIDO
except Exception as e:
    logger.error("unhandled_error", error=str(e))
    # TODO: fix this properly
```

**Correto:** Se sabe que é temporário, usar feature flag:
```python
if FEATURE_FLAG_STRICT_VALIDATION:
    raise
else:
    logger.warning("known_issue_being_tolerated", error=str(e))
```

### ❌ Erro em loop sem parada

```python
# PROIBIDO
for item in items:
    try:
        process(item)
    except:
        pass  # Se process falha 1000×, ninguém avisa
```

**Correto:**
```python
failed_items = []
for item in items:
    try:
        process(item)
    except Exception as e:
        logger.error("item_process_failed", item_id=item.id, error=str(e))
        failed_items.append(item.id)

if failed_items:
    logger.warning("batch_process_partial_failure", failed_count=len(failed_items), failed_ids=failed_items)
```

---

## Logging Canônico para Erros

### ✅ Erro esperado (ex: validação, timeout)

```python
logger.warning("operation_validation_failed", operation_id=str(op_id), reason="timeout")
```

### ✅ Erro inesperado (bug, crash, infra)

```python
logger.error(
    "operation_crashed",
    operation_id=str(op_id),
    error=str(e),
    exc_info=True,  # Stack trace
    context={"retry_count": 3, "timeout_seconds": 30},
)
```

### ✅ Erro recuperável com retry

```python
logger.error(
    "api_call_failed_will_retry",
    endpoint=url,
    error=str(e),
    retry_attempt=attempt,
    max_retries=3,
)
```

### ✅ Erro crítico (aborta tudo)

```python
logger.critical(
    "database_connection_lost",
    database_name=db_name,
    error=str(e),
    consequences="all_requests_will_fail",
)
```

---

## Checklist para Code Review

Antes de fazer merge, verificar:

- [ ] Toda função tem `try/except` com logging
- [ ] Nenhum `except: pass` ou `except Exception: pass`
- [ ] Exceção é re-raised (ou convertida em erro estruturado)
- [ ] Log de erro tem `exc_info=True` se for inesperado
- [ ] Erros esperados (validação, timeout) usam `logger.warning`
- [ ] Erros inesperados usam `logger.error`
- [ ] Task/job marca status em DB quando falha
- [ ] Endpoint retorna HTTP error apropriado (4xx ou 5xx)
- [ ] Mensagem de erro é útil (não "error" genérico)
- [ ] User vê mensagem clara se virar erro visível

---

## Exemplo Real: Antes vs Depois

### ❌ ANTES (com erro silencioso)

```python
async def dispatch_to_n8n(doc_id: UUID):
    """Dispara pipeline n8n."""
    try:
        payload = {
            "document_id": str(doc_id),
            "timestamp": datetime.now().isoformat(),
        }
        response = await httpx.post(WEBHOOK_URL, json=payload)
        # ← Esqueceu de checar status!
    except:
        pass  # ← Erro silencioso!
    # Se webhook falhou, doc fica em "processing" para sempre
```

**Resultado:** Doc travado, fila morta, usuário espera 30min, não acontece nada.

### ✅ DEPOIS (binário)

```python
async def dispatch_to_n8n(doc_id: UUID):
    """Dispara pipeline n8n. Retorna True (sucesso) ou lança (erro)."""
    try:
        logger.info("n8n_dispatch_started", document_id=str(doc_id))
        
        payload = {
            "document_id": str(doc_id),
            "timestamp": datetime.now().isoformat(),
        }
        response = await httpx.post(WEBHOOK_URL, json=payload, timeout=10)
        
        if response.status_code != 202:
            raise ValueError(f"n8n returned {response.status_code}: {response.text}")
        
        logger.info("n8n_dispatch_accepted", document_id=str(doc_id), request_id=response.headers.get("x-request-id"))
        return True
    
    except TimeoutError as e:
        logger.error("n8n_dispatch_timeout", document_id=str(doc_id), timeout_seconds=10)
        raise  # Caller retry
    
    except ValueError as e:
        logger.error("n8n_dispatch_rejected", document_id=str(doc_id), error=str(e))
        raise  # Caller marca doc em erro
    
    except Exception as e:
        logger.error("n8n_dispatch_unexpected", document_id=str(doc_id), error=str(e), exc_info=True)
        raise  # Caller retenta ou marca erro
```

**Resultado:** Qualquer falha é detectada e tratada. Sem silêncio.

---

## Implementação no GCA

Esta regra é **canônica** desde 2026-05-05 (MVP 35). Todo novo código deve seguir. Code review rejeita `except: pass`.

**Verificação automática:** Adicionar ao ruff/linting:
```toml
[tool.ruff.lint]
select = [..., "BLE"]  # BLE = blind-except

[tool.ruff.lint.per-file-ignores]
"backend/tests/**" = ["BLE"]  # Testes podem ser mais permissivos
```

---

**Criado em:** 2026-05-05  
**Escopo:** Honestidade técnica §0 do CLAUDE.md GCA  
**Status:** Canônico obrigatório
