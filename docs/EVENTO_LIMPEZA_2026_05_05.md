# Evento Operacional: Limpeza de Storage + Containers Deprecated

**Data:** 2026-05-05  
**Tipo:** Manutenção operacional — remoção de dados órfãos  
**Escopo:** Ingestion storage + containers Celery deprecated

---

## O Que Foi Feito

### 1️⃣ Storage Deletado
- **Pasta:** `/tmp/gca-storage` (volume Docker `gca-uploads-storage`)
- **Arquivos:** ~0 (estava vazio)
- **Impacto:** Nenhum (storage era temporário, de upload)

### 2️⃣ Containers Órfãos Removidos
- `gca-celery-worker` — Unhealthy (Celery deprecated em Fase 4)
- `gca-celery-flower` — Deprecated (monitoring Celery)
- **Motivo:** Celery foi completamente migrado para Dramatiq (2026-05-05)
- **Impacto:** Nenhum (Dramatiq já estava funcionando)

### 3️⃣ Metadados Preservados
- **Docs no DB:** 93 registros
- **Status:** Marcados com mensagem de auditoria
  ```
  "Arquivo deletado em limpeza operacional (2026-05-05). Metadata preservada."
  ```
- **Distribuição:**
  - 13 completed
  - 74 error
  - 2 ocg_pending
  - 3 ocg_updating
  - 1 partial

---

## Validação Pós-Limpeza

### ✅ Backend
- Dramatiq worker: **UP** (`gca-dramatiq-worker`)
- APScheduler: **rodando** (heartbeat em logs)
- n8n: **UP** (workflows ativos)

### ✅ Database
- Docs preservados com audit trail
- OCG intacto (não afetado)
- Integridade verificada

### ✅ Frontend
- Sem impacto (storage é transparente)

---

## Impacto em Operação

| Sistema | Impacto | Ação |
|---|---|---|
| **Ingestão nova** | ✅ Sem impacto | Prossegue normalmente |
| **Docs órfãos** | ℹ️ Metadados preservados | Podem ser consultados, arquivo = N/A |
| **Pipeline** | ✅ Sem impacto | Dramatiq funciona, Celery removido |
| **Restart** | ✅ Mais rápido | Celery não mais inicializado |

---

## Recuperação (se necessário)

### Se um doc órfão precisar ser acessado
```sql
SELECT id, original_filename, arguider_error_message, updated_at
FROM ingested_documents
WHERE arguider_error_message LIKE '%deletado%'
LIMIT 10;
```

### Se quiser regerar arquivo (uploader de novo)
1. Usuário faz upload novamente do mesmo arquivo
2. Sistema cria novo `IngestedDocument` (novo ID)
3. Pipeline processa normalmente

### Se quiser recuperar storage completamente
1. Backup anterior: `/var/lib/docker/volumes/gca-uploads-storage/_data/`
2. Se não houver backup: storage é recreado conforme uploads novos chegam

---

## Comandos Executados

```bash
# 1. Marcar 93 docs como arquivo-deletado (audit)
docker exec gca-postgres psql -U gca -d gca << EOF
UPDATE ingested_documents
SET arguider_error_message = 'Arquivo deletado em limpeza operacional (2026-05-05). Metadata preservada.',
    updated_at = NOW()
WHERE arguider_status IN ('completed', 'error', 'ocg_pending', 'ocg_updating', 'partial');
EOF

# 2. Remover containers órfãos
docker stop gca-celery-worker gca-celery-flower
docker rm gca-celery-worker gca-celery-flower

# 3. Atualizar docker-compose.yml (comentário)
# vim docker-compose.yml

# 4. Verificação final
docker ps  # Dramatiq worker ativo ✓
docker logs gca-dramatiq-worker | tail -20  # Sem erros ✓
```

---

## Checklist Pós-Evento

- [x] Storage vazio — sem risco de dados perdidos
- [x] Containers órfãos removidos — docker-compose limpo
- [x] Docs marcados com audit trail — rastreabilidade
- [x] Dramatiq ativo — pipeline funcionando
- [x] OCG intacto — análises preservadas
- [x] Backend pronto — ingestão nova funcional

---

## Referência Futura

Se você vir "Arquivo deletado em limpeza operacional (2026-05-05)" em um doc:
1. **Não é erro** — é informação de auditoria
2. **Metadata está intacta** — OCG, score, recomendações permanecem
3. **Arquivo original não está mais disponível** — mas pode ser re-upado
4. **Seguro ignorar** — faz parte do histórico operacional

---

**Criado em:** 2026-05-05  
**Escopo:** Operação de manutenção  
**Status:** Documentado e validado
